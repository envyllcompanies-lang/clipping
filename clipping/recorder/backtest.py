"""Stage backtest 02: window extraction exactness/speed and rolling-buffer disk bound."""

from __future__ import annotations

import datetime as dt
import time

import numpy as np

from clipping.core import config, db, media
from clipping.eval.fixtures import make_segments
from clipping.eval.harness import Example, StageResult, scratch_db, stage
from clipping.recorder import recorder

UTC = dt.UTC


@stage("02", "Stream Recorder")
def run() -> StageResult:
    rng = np.random.default_rng(2)
    ex: list[Example] = []
    with scratch_db() as c:
        cr = db.one(c, "INSERT INTO creator(platform,platform_id,handle,language) VALUES ('twitch','1','bt','en') RETURNING *")
        base = int(time.time()) - 1800
        sid = recorder.start_stream(c, cr["id"], "bt", dt.datetime.fromtimestamp(base, UTC))
        d = recorder.segment_dir("bt", sid)
        make_segments(d, 30, base)
        recorder.register_segments(c, sid, d, include_last=True)
        times, exact = [], []
        for i in range(20):
            s = float(rng.uniform(60, 1600))
            mid = db.scalar(c, "INSERT INTO moment(stream_id,start_s,end_s,peak_s,score) VALUES (%s,%s,%s,%s,1) RETURNING id",
                            sid, s, s + 75, s + 45)
            wid = db.scalar(c, 'INSERT INTO "window"(moment_id) VALUES (%s) RETURNING id', mid)
            t0 = time.time()
            recorder.extract_window(c, wid)
            times.append(time.time() - t0)
            w = db.one(c, 'SELECT * FROM "window" WHERE id=%s', wid)
            span = (w["end_utc"] - w["start_utc"]).total_seconds()
            dur = media.duration(w["path"])
            want0 = dt.datetime.fromtimestamp(base + s - 30, UTC)
            want1 = dt.datetime.fromtimestamp(base + s + 75 + 30, UTC)
            ok = abs(dur - span) < 0.2 and w["start_utc"] <= want0 and w["end_utc"] >= min(want1, w["end_utc"])
            codec_copy = media.probe(w["path"])["streams"][0]["codec_name"] == "h264"
            exact.append(ok and codec_copy)
            if not ok:
                ex.append(Example(f"window{wid}", "exact", 0, f"dur={dur:.2f} span={span:.2f}"))
        # Disk bound over a simulated 6 h stream (rows only; bytes from the measured bitrate).
        sid2 = recorder.start_stream(c, cr["id"], "sim", dt.datetime(2026, 1, 1, tzinfo=UTC))
        buf_h = config.settings()["recorder"]["buffer_hours"]
        t_start = dt.datetime(2026, 1, 1, tzinfo=UTC)
        max_live = 0
        for minute in range(0, 360):
            t = t_start + dt.timedelta(minutes=minute)
            c.execute("INSERT INTO segment(stream_id,path,start_utc,end_utc,size) VALUES (%s,%s,%s,%s,%s)",
                      (sid2, f"/nonexistent/sim/{minute}.ts", t, t + dt.timedelta(minutes=1), 45_000_000))
            if minute % 37 == 0:
                mid = db.scalar(c, "INSERT INTO moment(stream_id,start_s,end_s,peak_s,score) VALUES (%s,%s,%s,%s,1) RETURNING id",
                                sid2, minute * 60 - 100, minute * 60 - 25, minute * 60 - 50)
                c.execute('INSERT INTO "window"(moment_id,status) VALUES (%s,%s)', (mid, "requested" if minute % 74 else "extracted"))
            recorder.prune(c, now=t + dt.timedelta(minutes=1))
            live = db.scalar(c, "SELECT count(*) FROM segment WHERE stream_id=%s AND NOT deleted", sid2)
            max_live = max(max_live, live)
    times.sort()
    p95 = times[int(0.95 * (len(times) - 1))]
    return StageResult({"extract_exact": float(np.mean(exact)), "extract_p95_s": p95,
                        "disk_ratio": max_live / (buf_h * 60)}, ex, "synthetic@v1",
                       {"max_live_segments": max_live})
