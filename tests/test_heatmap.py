import datetime as dt
import time

import numpy as np

from clipping.core import db
from clipping.eval.fixtures import make_segments
from clipping.heatmap import fusion, learn, service, signals
from clipping.recorder import recorder

UTC = dt.UTC


def test_missing_signal_dropped_and_renormalized():
    T = 100
    a = np.zeros(T)
    a[50] = 10
    b = np.full(T, np.nan)
    s1 = fusion.fuse({"a": a, "b": b}, {"a": 0.5, "b": 0.5}, smooth_s=1)
    s2 = fusion.fuse({"a": a}, {"a": 1.0}, smooth_s=1)
    assert np.allclose(s1, s2) and s1.argmax() == 50


def test_pick_windows_separation_merge_and_cap():
    T = 3600
    s = np.zeros(T)
    for p, h in ((500, 2.0), (520, 1.0), (1500, 1.0), (2500, 1.0), (3000, 1.0)):
        s[p] = h
    s = np.convolve(s, np.ones(5) / 5, mode="same")
    w = fusion.pick_windows(s, separation_s=45, pct=95, floor=0.1, max_per_hour=3)
    assert len(w) == 3
    assert all(x.end_s - x.start_s >= 75 for x in w)
    peak = next(x for x in w if 400 < x.peak_s < 600)
    assert peak.start_s == peak.peak_s - 45


def test_dull_stream_produces_nothing():
    rng = np.random.default_rng(0)
    s = rng.uniform(0, 0.2, 3600)
    assert fusion.pick_windows(s, floor=0.35) == []


def test_clip_density_anchor_and_reaction_lag():
    d = signals.clip_density([{"t_start": 100, "duration": 30, "views": 100}], 300)
    assert abs(d.argmax() - 119.5) <= 1
    b = [
        {
            "t": t,
            "velocity_z": 10.0 if t == 110 else 0.0,
            "laugh_share": 0,
            "hype_share": 0,
            "caps_share": 0,
            "copypasta_score": 0,
        }
        for t in range(0, 300, 10)
    ]
    vel, _ = signals.from_buckets(b, 300, lag_s=5)
    assert abs(np.nanargmax(vel) - 110) <= 1  # bucket center 115, shifted back by 5 s


def test_audio_spikes_and_music_downweight():
    db10 = np.full(600, -30.0)
    db10[300:305] = -12
    sp = signals.audio_spikes(db10, 0.1, 60)
    assert sp.argmax() == 30 and sp[30] >= 10
    m = np.zeros(60)
    m[30] = 1.0
    assert signals.audio_spikes(db10, 0.1, 60, music=m)[30] < sp[30] * 0.3


def test_logistic_refit_recovers_informative_signal():
    rng = np.random.default_rng(1)
    T = 5000
    good = rng.random(T)
    y = (good > 0.8).astype(float)
    sig = {"good": good, "noise": rng.random(T)}
    X = learn.design(sig, ["good", "noise"])
    w = learn.to_weights(learn.fit_logistic(X, y), ["good", "noise"])
    assert w["good"] > 0.8


def test_score_stream_from_recorded_segments(conn, tmp_data):
    cr = db.scalar(
        conn,
        "INSERT INTO creator(platform,platform_id,handle,language) VALUES ('twitch','1','h','en') RETURNING id",
    )
    base = int(time.time()) - 600
    sid = recorder.start_stream(conn, cr, "x", dt.datetime.fromtimestamp(base, UTC), "en")
    d = recorder.segment_dir("h", sid)
    make_segments(d, 4, base)
    recorder.register_segments(conn, sid, d, include_last=True)
    t0 = dt.datetime.fromtimestamp(base, UTC)
    rows = [
        (
            sid,
            t0 + dt.timedelta(seconds=t),
            50 if 120 <= t < 140 else 2,
            2,
            0,
            0,
            0.5 if 120 <= t < 140 else 0,
            0,
            0,
            None,
            False,
        )
        for t in range(0, 240, 10)
    ]
    conn.cursor().executemany("INSERT INTO chat_bucket VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)

    conn.execute("UPDATE stream SET ended_at=%s WHERE id=%s", (t0 + dt.timedelta(seconds=240), sid))
    conn.execute("UPDATE chat_bucket SET velocity_z = CASE WHEN msgs > 10 THEN 8 ELSE 0 END")
    ids = service.score_stream(conn, sid)
    assert ids, "expected a candidate moment"
    m = db.one(conn, "SELECT * FROM moment WHERE id=%s", ids[0])
    assert 100 <= m["peak_s"] <= 150
    assert db.scalar(conn, "SELECT count(*) FROM job WHERE type='extract_window'") == len(ids)
    assert db.scalar(conn, "SELECT count(*) FROM segment_feature") == 4
    service.score_stream(conn, sid)  # re-score: no duplicate moments
    assert db.scalar(conn, "SELECT count(*) FROM moment") == len(ids)
