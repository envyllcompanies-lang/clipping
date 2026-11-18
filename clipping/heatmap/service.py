"""Heatmap service: features per recorded segment (cached), stream scoring, moments and window requests (doc 05)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import psycopg

from clipping.core import config, db, jobs, media
from clipping.heatmap import fusion, signals

UTC = dt.UTC
SR = 8000


def segment_features(c: psycopg.Connection, seg: dict) -> dict:
    r = db.one(c, "SELECT * FROM segment_feature WHERE segment_id=%s", seg["id"])
    if r:
        return r
    audio = media.decode_audio(seg["path"], SR)
    T = int(round((seg["end_utc"] - seg["start_utc"]).total_seconds()))
    dbs = signals.rms_db(audio, SR, 0.1)
    voice = signals.voice_excitement(audio, SR, T)
    try:
        # Keyframes only (Twitch GOP ~2 s): full 2 fps decode of 1080p60 costs ~5x more and breaks the 2 min/h budget.
        frames = media.decode_frames(seg["path"], width=240, gray=True, keyframes_only=True)
        d = (
            np.r_[
                0,
                0.5
                * np.abs(np.diff([np.histogram(f, 32, (0, 255))[0] / f.size for f in frames], axis=0)).sum(
                    axis=1
                ),
            ]
            if len(frames) > 1
            else np.zeros(1)
        )
        scene = d[np.minimum((np.arange(T * 2) * len(d) / max(T * 2, 1)).astype(int), len(d) - 1)]
    except Exception:  # noqa: BLE001 - audio-only stream
        scene = np.zeros(T * 2)
    from clipping.audio import music as music_mod

    mus = music_mod.music_prob(audio, SR)
    c.execute(
        "INSERT INTO segment_feature VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        (seg["id"], dbs.tolist(), voice.tolist(), scene.tolist(), mus.tolist()),
    )
    return {"audio_db": dbs.tolist(), "voice": voice.tolist(), "scene": scene.tolist(), "music": mus.tolist()}


def stream_arrays(c: psycopg.Connection, stream_id: int) -> tuple[int, dict[str, np.ndarray]]:
    st = db.one(c, "SELECT * FROM stream WHERE id=%s", stream_id)
    t0 = st["started_at"]
    segs = db.all_(
        c, "SELECT * FROM segment WHERE stream_id=%s AND NOT deleted ORDER BY start_utc", stream_id
    )
    end = max([s["end_utc"] for s in segs] + [st["ended_at"] or t0])
    T = max(1, int((end - t0).total_seconds()))
    audio_db = np.full(T * 10, -60.0)
    voice = np.full(T, np.nan)
    scene = np.zeros(T * 2)
    music = np.zeros(T)
    have = np.zeros(T, bool)
    for s in segs:
        f = segment_features(c, s)
        off = int((s["start_utc"] - t0).total_seconds())
        for arr, rate, src in (
            (audio_db, 10, f["audio_db"]),
            (scene, 2, f["scene"]),
            (voice, 1, f["voice"]),
            (music, 1, f["music"] or []),
        ):
            src = np.asarray(src, float)
            a, b = off * rate, min(len(arr), off * rate + len(src))
            if b > a > -1:
                arr[a:b] = src[: b - a]
        have[off : off + int((s["end_utc"] - s["start_utc"]).total_seconds())] = True
    cfg = config.settings()["heatmap"]
    buckets = [
        {"t": (b["t_start"] - t0).total_seconds(), **b}
        for b in db.all_(c, "SELECT * FROM chat_bucket WHERE stream_id=%s ORDER BY t_start", stream_id)
    ]
    clips = [
        {
            "t_start": (r["abs_utc_start"] - t0).total_seconds(),
            "duration": r["duration"] or 30,
            "views": r["view_count"] or 0,
        }
        for r in db.all_(
            c, "SELECT * FROM platform_clip WHERE stream_id=%s AND abs_utc_start IS NOT NULL", stream_id
        )
    ]
    evs = [
        {"t": r["t_s"], "type": r["type"], "confidence": r["confidence"]}
        for r in db.all_(c, "SELECT * FROM game_event WHERE stream_id=%s", stream_id)
    ]
    samples = [
        (int((r["sampled_at"] - t0).total_seconds()), r["viewer_count"] or 0)
        for r in db.all_(
            c,
            """SELECT sampled_at, viewer_count FROM creator_stat WHERE creator_id=%s AND sampled_at BETWEEN %s AND %s ORDER BY sampled_at""",
            st["creator_id"],
            t0,
            end,
        )
    ]
    vel, mix = signals.from_buckets(buckets, T, lag_s=cfg["reaction_lag_s"])
    aud = signals.audio_spikes(audio_db, 0.1, T, music=music)
    aud[~have] = np.nan
    ev_w = {
        k: v.get("weight", 0.5) * (0 if v.get("negative") else 1) for k, v in config.game()["events"].items()
    }
    sig = {
        "chat_velocity": vel,
        "chat_reaction": mix,
        "viewer_clips": signals.clip_density(clips, T, cfg["clip_kernel_s"]),
        "audio_energy": aud,
        "voice_excitement": voice,
        "visual_change": signals.per_second_max(scene, 2, T),
        "game_events": signals.events_curve(evs, T, ev_w) if evs else np.full(T, np.nan),
        "viewer_jump": signals.viewer_jumps(samples, T),
    }
    if not clips:
        sig["viewer_clips"] = np.full(T, np.nan)  # Kick / unclipped: drop, renormalize
    return T, sig


def active_weights(c: psycopg.Connection, language: str | None) -> dict:
    cfg = config.settings()["heatmap"]["weights"]
    for comp in (f"heatmap:{language}", "heatmap"):
        r = db.one(
            c,
            'SELECT "values" FROM weights WHERE component=%s AND active ORDER BY version DESC LIMIT 1',
            comp,
        )
        if r:
            return r["values"]
    return cfg


def score_stream(c: psycopg.Connection, stream_id: int, request_windows: bool = True) -> list[int]:
    cfg = config.settings()["heatmap"]
    st = db.one(c, "SELECT * FROM stream WHERE id=%s", stream_id)
    T, sig = stream_arrays(c, stream_id)
    score = fusion.fuse(sig, active_weights(c, st["language"]), cfg["smooth_s"])
    upsert = (
        'INSERT INTO heatmap_signal(stream_id,name,"values") VALUES (%s,%s,%s) '
        'ON CONFLICT (stream_id,name) DO UPDATE SET "values"=EXCLUDED."values"'
    )
    for name, arr in sig.items():  # kept for weekly weight refits (labels arrive later as viewer clips)
        c.execute(upsert, (stream_id, name, [None if np.isnan(v) else round(float(v), 3) for v in arr]))
    c.execute(
        """INSERT INTO heatmap_curve(stream_id,step_s,"values") VALUES (%s,1,%s) ON CONFLICT (stream_id)
                 DO UPDATE SET "values"=EXCLUDED."values", computed_at=now()""",
        (stream_id, np.round(score, 4).tolist()),
    )
    wins = fusion.pick_windows(
        score,
        separation_s=cfg["peak_separation_s"],
        pct=cfg["peak_percentile"],
        floor=cfg["abs_floor"],
        before_s=cfg["window_before_s"],
        after_s=cfg["window_after_s"],
        max_per_hour=cfg["max_per_hour"],
    )
    ids = []
    for rank, w in enumerate(wins, 1):
        at = int(w.peak_s)
        sv = {k: (None if np.isnan(v[at]) else round(float(v[at]), 4)) for k, v in sig.items()}
        ex = db.one(
            c,
            "SELECT id FROM moment WHERE stream_id=%s AND start_s < %s AND end_s > %s",
            stream_id,
            w.end_s,
            w.start_s,
        )
        if ex:
            c.execute(
                "UPDATE moment SET score=GREATEST(score,%s), rank=%s, signals=%s WHERE id=%s",
                (w.score, rank, db.j(sv), ex["id"]),
            )
            ids.append(ex["id"])
            continue
        mid = db.scalar(
            c,
            """INSERT INTO moment(stream_id,start_s,end_s,peak_s,signals,score,rank) VALUES (%s,%s,%s,%s,%s,%s,%s)
                              RETURNING id""",
            stream_id,
            w.start_s,
            w.end_s,
            w.peak_s,
            db.j(sv),
            w.score,
            rank,
        )
        ids.append(mid)
        if request_windows:
            wid = db.scalar(
                c,
                """INSERT INTO "window"(moment_id,start_utc,end_utc) VALUES (%s,%s,%s) RETURNING id""",
                mid,
                st["started_at"] + dt.timedelta(seconds=w.start_s),
                st["started_at"] + dt.timedelta(seconds=w.end_s),
            )
            jobs.enqueue(
                c,
                "extract_window",
                {"window_id": wid},
                dedupe_key=f"extract:{wid}",
                priority=int(w.score * 100),
            )
    return ids


def refit(c: psycopg.Connection, holdout_frac: float = 0.3, min_streams: int = 6) -> dict | None:
    """Weekly: logistic fit, label = a viewer clip lands within 15 s; ships only if held-out recall@20 improves."""
    from clipping.analytics.loop import ship
    from clipping.heatmap import learn

    sids = [
        r["stream_id"]
        for r in db.all_(
            c,
            """SELECT DISTINCT hs.stream_id FROM heatmap_signal hs JOIN platform_clip pc ON pc.stream_id=hs.stream_id
                                                  WHERE pc.abs_utc_start IS NOT NULL ORDER BY 1""",
        )
    ]
    if len(sids) < min_streams:
        return None
    data = {}
    for sid in sids:
        st = db.one(c, "SELECT started_at FROM stream WHERE id=%s", sid)
        sig = {
            r["name"]: np.array([np.nan if v is None else v for v in r["values"]], float)
            for r in db.all_(c, 'SELECT name, "values" FROM heatmap_signal WHERE stream_id=%s', sid)
        }
        T = len(next(iter(sig.values())))
        clips = [
            {
                "t_start": (r["abs_utc_start"] - st["started_at"]).total_seconds(),
                "duration": r["duration"] or 30,
                "views": r["view_count"] or 0,
            }
            for r in db.all_(
                c, "SELECT * FROM platform_clip WHERE stream_id=%s AND abs_utc_start IS NOT NULL", sid
            )
        ]
        data[sid] = (sig, clips, T)
    k = max(1, int(len(sids) * holdout_frac))
    train, hold = sids[:-k], sids[-k:]
    names = [n for n in config.settings()["heatmap"]["weights"] if n != "viewer_clips"]
    X = np.vstack([learn.design(data[s][0], names) for s in train if all(n in data[s][0] for n in names)])
    y = np.concatenate(
        [
            learn.labels_from_clips(data[s][1], data[s][2])
            for s in train
            if all(n in data[s][0] for n in names)
        ]
    )
    new = learn.to_weights(learn.fit_logistic(X, y), names)
    if not new:
        return None
    new["viewer_clips"] = config.settings()["heatmap"]["weights"]["viewer_clips"]
    cur = active_weights(c, None)

    def recall(w):
        hits = []
        for s in hold:
            sig, clips, T = data[s]
            score = fusion.fuse({n: sig[n] for n in sig if n != "viewer_clips"}, w, 5)
            wins = fusion.pick_windows(score, floor=0.0)[: max(1, int(20 * T / 14400))]
            pos = [
                cl["t_start"] + 0.65 * cl["duration"] for cl in sorted(clips, key=lambda x: -x["views"])[:10]
            ]
            hits += [any(wn.start_s <= p <= wn.end_s for wn in wins) for p in pos]
        return float(np.mean(hits)) if hits else 0.0

    r_new, r_cur = recall(new), recall(cur)
    top = max((n for n in new if n != "viewer_clips"), key=new.get)
    shipped = ship(
        c,
        "heatmap",
        new,
        r_new,
        r_cur,
        f"Heatmap refit: '{top.replace('_', ' ')}' predicts viewer clips best",
    )
    return {"weights": new, "holdout_new": r_new, "holdout_current": r_cur, "shipped": shipped}
