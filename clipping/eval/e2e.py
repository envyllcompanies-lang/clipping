"""Stage backtest 25: one recorded stream end to end through the job queue (server + M1 roles) and the bucket."""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import time
from pathlib import Path

from clipping.core import db, jobs, media
from clipping.eval import windowfx
from clipping.eval.fakeplatforms import FakePlatforms
from clipping.eval.harness import Example, StageResult, scratch_db, stage

UTC = dt.UTC


@stage("25", "Infrastructure: end-to-end through the queue")
def run() -> StageResult:
    from clipping import pipeline, worker  # noqa: F401 - registers handlers
    from clipping.accounts import credentials
    from clipping.analytics import loop
    from clipping.heatmap import service
    from clipping.produce import sync_channels
    from clipping.publish import framework, registry
    from clipping.recorder import recorder
    from clipping.storage import files

    os.environ.setdefault("CLIPPING_ASR_MODEL", "small")
    ex, stages = [], {}
    with scratch_db() as c:
        chans = sync_channels(c)
        for a in db.all_(c, "SELECT id, platform FROM account WHERE channel_id=%s", chans["en"]):
            c.execute(
                "UPDATE account SET status='connected', mode='fallback', platform_account_id=%s, created_at=now()-interval '60 days' WHERE id=%s",
                (f"{a['platform']}-id", a["id"]),
            )
            credentials.store(
                c,
                a["id"],
                a["platform"],
                "oauth",
                {"access_token": "t"},
                dt.datetime.now(UTC) + dt.timedelta(days=30),
            )
        cr = db.scalar(
            c,
            "INSERT INTO creator(platform,platform_id,handle,language) VALUES ('twitch','42','streamer','en') RETURNING id",
        )
        base = int(time.time()) - 600
        sid = recorder.start_stream(c, cr, "live1", dt.datetime.fromtimestamp(base, UTC), "en")
        d = recorder.segment_dir("streamer", sid)
        d.mkdir(parents=True, exist_ok=True)
        w = windowfx.make(d / "_full.ts", seed=11, seconds=240)
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(d / "_full.ts"),
                "-map",
                "0",
                "-c",
                "copy",
                "-f",
                "segment",
                "-segment_time",
                "60",
                "-reset_timestamps",
                "1",
                "-segment_format",
                "mpegts",
                str(d / "n%03d.ts"),
            ],
            check=True,
        )
        (d / "_full.ts").unlink()
        t = base
        for p in sorted(d.glob("n*.ts")):
            dur = media.duration(p)
            p.rename(d / f"{t}.ts")
            t += round(dur)
        recorder.register_segments(c, sid, d, include_last=True)
        crash = w["crash_t"]
        t0 = dt.datetime.fromtimestamp(base, UTC)
        rows = [
            (
                sid,
                t0 + dt.timedelta(seconds=s),
                80 if crash + 2 <= s < crash + 22 else 3,
                40 if crash + 2 <= s < crash + 22 else 3,
                0,
                0,
                0.5 if crash + 2 <= s < crash + 22 else 0.0,
                0.3,
                0,
                9.0 if crash + 2 <= s < crash + 22 else 0.0,
                False,
            )
            for s in range(0, 240, 10)
        ]
        c.cursor().executemany("INSERT INTO chat_bucket VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
        c.execute(
            "UPDATE stream SET status='ended', ended_at=%s WHERE id=%s", (t0 + dt.timedelta(seconds=240), sid)
        )
        moments = service.score_stream(c, sid)
        stages["moments"] = len(moments)
        near = [m for m in db.all_(c, "SELECT * FROM moment") if m["start_s"] <= crash <= m["end_s"]]
        if not near:
            ex.append(
                Example(
                    "heatmap",
                    "crash_not_in_window",
                    crash,
                    str([(m["start_s"], m["end_s"]) for m in db.all_(c, "SELECT * FROM moment")]),
                )
            )
        # keep only the window covering the crash for speed
        keep = near[0]["id"] if near else moments[0]
        c.execute(
            """UPDATE job SET status='done' WHERE type='extract_window' AND (payload->>'window_id')::int NOT IN
                     (SELECT id FROM "window" WHERE moment_id=%s)""",
            (keep,),
        )
        srv = worker.HANDLERS["server"]
        m1 = worker.HANDLERS["m1"]
        stages["server_jobs"] = jobs.drain(c, {"extract_window": srv["extract_window"]}, "srv")
        stages["m1_jobs"] = jobs.drain(
            c, {k: m1[k] for k in ("audio_clean", "transcribe", "events", "build")}, "m1"
        )
        dead = db.all_(
            c, "SELECT type, last_error FROM job WHERE status IN ('dead') OR (status='queued' AND attempts>0)"
        )
        for j in dead:
            ex.append(Example(j["type"], "job_failed", 0, (j["last_error"] or "")[:300]))
        queued = db.scalar(c, "SELECT count(*) FROM clip_version WHERE status='queued'")
        stages["queued_versions"] = queued
        now = dt.datetime.now(UTC)
        framework.schedule(c, now)
        fake = FakePlatforms()
        ads = registry.adapters(c, fake.transport())
        for i in range(16):
            framework.run_due(c, ads, now + dt.timedelta(days=2, minutes=20 * i))
        live = db.scalar(c, "SELECT count(DISTINCT platform) FROM post WHERE status='live'")
        stages["platforms_live"] = live
        later = now + dt.timedelta(days=3)
        c.execute("UPDATE post SET posted_at=%s WHERE status='live'", (now,))
        loop.pull_stats(c, ads, later)
        stats_ok = db.scalar(c, "SELECT count(*) FROM post_stat") >= live
        segs_left = db.scalar(c, "SELECT count(*) FROM file WHERE kind='render' AND deleted_at IS NULL")
        window_gone = not any(
            Path(r["path"]).exists() for r in db.all_(c, 'SELECT path FROM "window" WHERE path IS NOT NULL')
        )
        files.sweep(c)
    ok = bool(near) and not dead and queued >= 1 and live == 6 and stats_ok and window_gone
    return StageResult(
        {
            "end_to_end_ok": 1.0 if ok else 0.0,
            "platforms_live": float(live),
            "renders_left_after_upload": float(segs_left),
        },
        ex,
        "windowfx-stream@v1",
        stages,
    )
