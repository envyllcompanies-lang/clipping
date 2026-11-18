"""Stage backtest 02 on a real live stream: the recorder's own streamlink -> ffmpeg pipeline records a live GTA VI
channel for a few minutes; recording must start within 60 s, windows extract exactly (stream copy, UTC span matches
content) in under 10 s. The rolling-buffer disk bound is checked with segment rows over a 6 h timeline."""

from __future__ import annotations

import datetime as dt
import time

import numpy as np

from clipping.core import config, db, media
from clipping.eval.harness import Example, StageResult, scratch_db, stage
from clipping.radar.sources import TwitchHelix
from clipping.recorder import recorder

UTC = dt.UTC


@stage("02", "Stream Recorder (real live stream)")
def run(seconds: int = 210) -> StageResult:
    h = TwitchHelix.from_env()
    gid = h.resolve_game(["Grand Theft Auto VI"])
    live = sorted(h.live_streams(gid), key=lambda s: -s.viewer_count)
    target = live[min(5, len(live) - 1)]  # a big but not the biggest channel
    ex = []
    with scratch_db() as c:
        cr = db.one(
            c,
            "INSERT INTO creator(platform,platform_id,handle,language) VALUES ('twitch',%s,%s,%s) RETURNING *",
            target.user_id,
            target.login,
            target.language,
        )
        sid = recorder.start_stream(c, cr["id"], target.stream_id, None, target.language)
        w = recorder.Worker(c, dict(cr), sid)
        w.command = recorder.record_command(
            recorder.stream_url("twitch", target.login), w.dir, 30, "480p,480p30,360p,worst"
        )
        t0 = time.time()
        first = {}

        import threading

        def watch():
            while time.time() - t0 < seconds:
                if list(w.dir.glob("*.ts")) and "t" not in first:
                    first["t"] = time.time() - t0
                time.sleep(0.5)

        th = threading.Thread(target=watch, daemon=True)
        th.start()
        w.run(is_live=lambda: True, poll_s=3, max_seconds=seconds)
        th.join(1)
        segs = db.all_(c, "SELECT * FROM segment WHERE stream_id=%s ORDER BY start_utc", sid)
        times, exact = [], []
        if len(segs) >= 3:
            s0, s1 = segs[0]["start_utc"], segs[-1]["end_utc"]
            st = db.one(c, "SELECT started_at FROM stream WHERE id=%s", sid)["started_at"]
            rng = np.random.default_rng(2)
            for _ in range(6):
                a = s0 + dt.timedelta(seconds=float(rng.uniform(5, max(6, (s1 - s0).total_seconds() - 40))))
                mid = db.scalar(
                    c,
                    "INSERT INTO moment(stream_id,start_s,end_s,peak_s,score) VALUES (%s,%s,%s,%s,1) RETURNING id",
                    sid,
                    (a - st).total_seconds(),
                    (a - st).total_seconds() + 20,
                    (a - st).total_seconds() + 10,
                )
                wid = db.scalar(
                    c,
                    'INSERT INTO "window"(moment_id,start_utc,end_utc) VALUES (%s,%s,%s) RETURNING id',
                    mid,
                    a,
                    a + dt.timedelta(seconds=20),
                )
                t = time.time()
                recorder.extract_window(c, wid)
                times.append(time.time() - t)
                win = db.one(c, 'SELECT * FROM "window" WHERE id=%s', wid)
                span = (win["end_utc"] - win["start_utc"]).total_seconds()
                dur = media.duration(win["path"])
                ok = (
                    abs(dur - span) < 0.5
                    and win["start_utc"] <= a
                    and win["end_utc"] >= a + dt.timedelta(seconds=20)
                )
                exact.append(bool(ok))
                if not ok:
                    ex.append(Example(f"window{wid}", "exact", 0, f"dur={dur:.2f} span={span:.2f}"))
        # disk bound over a 6 h timeline (segment rows; bytes irrelevant)
        sid2 = recorder.start_stream(c, cr["id"], "sim", dt.datetime(2026, 1, 1, tzinfo=UTC))
        buf_h = config.settings()["recorder"]["buffer_hours"]
        t_start = dt.datetime(2026, 1, 1, tzinfo=UTC)
        max_live = 0
        for minute in range(360):
            t = t_start + dt.timedelta(minutes=minute)
            c.execute(
                "INSERT INTO segment(stream_id,path,start_utc,end_utc,size) VALUES (%s,%s,%s,%s,1)",
                (sid2, f"/nonexistent/{minute}.ts", t, t + dt.timedelta(minutes=1)),
            )
            recorder.prune(c, now=t + dt.timedelta(minutes=1))
            max_live = max(
                max_live,
                db.scalar(c, "SELECT count(*) FROM segment WHERE stream_id=%s AND NOT deleted", sid2),
            )
    times.sort()
    return StageResult(
        {
            "recording_started_s": first.get("t", 999.0),
            "segments_recorded": float(len(segs)),
            "extract_exact": float(np.mean(exact)) if exact else 0.0,
            "extract_p95_s": times[int(0.95 * (len(times) - 1))] if times else 999.0,
            "disk_ratio": max_live / (buf_h * 60),
        },
        ex,
        f"live:{target.login}",
        {"channel": target.login, "viewers": target.viewer_count},
    )
