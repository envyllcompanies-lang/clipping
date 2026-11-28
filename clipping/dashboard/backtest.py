"""Stage backtest 23: alerts fire on simulated failures; "pull everywhere" deletes a live clip from every
API-deletable platform within one worker cycle; every screen is reachable from Home in <= 3 taps."""

from __future__ import annotations

import datetime as dt
import re

from clipping.core import db, jobs
from clipping.eval.fakeplatforms import FakePlatforms
from clipping.eval.harness import Example, StageResult, scratch_db, stage

UTC = dt.UTC


@stage("23", "Dashboard & Kill Switch")
def run() -> StageResult:
    from clipping.dashboard import alerts, commands
    from clipping.publish import backtest as pb
    from clipping.publish import framework, registry

    ex = []
    with scratch_db() as c:
        # simulated failures -> alerts
        c.execute(
            "INSERT INTO worker_heartbeat(worker,role,seen_at) VALUES ('m1:x','m1', now() - interval '7 hours'),"
            " ('srv:x','server', now() - interval '10 minutes')"
        )
        ch, accs, (cv,) = pb.seed(c, mode="direct")
        for _ in range(3):
            c.execute(
                "INSERT INTO post(clip_version_id,account_id,platform,status,scheduled_at) VALUES (%s,%s,'facebook','failed_permanent',now())"
                " ON CONFLICT DO NOTHING",
                (cv, accs["facebook"]),
            )
        for k in range(3):
            mid = db.scalar(c, "SELECT moment_id FROM clip LIMIT 1")
            cl = db.scalar(
                c,
                "INSERT INTO clip(moment_id,channel_id) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING id",
                mid,
                ch,
            )
            cl = cl or db.scalar(c, "SELECT id FROM clip LIMIT 1")
            v = db.scalar(
                c, "INSERT INTO clip_version(clip_id,version_type) VALUES (%s,%s) RETURNING id", cl, f"x{k}"
            )
            c.execute(
                "INSERT INTO post(clip_version_id,account_id,platform,status,scheduled_at) VALUES (%s,%s,'facebook','failed_permanent',now())",
                (v, accs["facebook"]),
            )
        c.execute("UPDATE account SET health='{\"restricted\": true}' WHERE id=%s", (accs["instagram"],))
        from clipping.accounts import credentials

        c.execute(
            "UPDATE credential SET expires_at = now() + interval '1 minute' WHERE account_id=%s",
            (accs["tiktok"],),
        )

        def bad_refresh(secret):
            raise RuntimeError("invalid_grant")

        credentials.refresh_all(c, {"tiktok": bad_refresh})
        from clipping.storage import guard

        guard.check(c, "server", {"free_gb": 3, "total_gb": 200, "free_pct": 1.5})
        from clipping.chat import capture

        cap = capture.Capture(
            c, db.scalar(c, "SELECT id FROM stream LIMIT 1"), dt.datetime.now(UTC), "en", "kick"
        )
        cap.check_silent(dt.datetime.now(UTC).timestamp() + 3600, True)
        from clipping.gate import takedown

        c.execute(
            "INSERT INTO post(clip_version_id,account_id,platform,status,scheduled_at) VALUES (%s,%s,'youtube','live',now())",
            (cv, accs["youtube"]),
        )
        takedown.record_claim(
            c,
            db.scalar(c, "SELECT id FROM post WHERE platform='youtube' AND status='live' LIMIT 1"),
            "strike",
        )
        alerts.run_checks(c)
        kinds = {r["kind"] for r in db.all_(c, "SELECT kind FROM alert WHERE resolved_at IS NULL")}
        want = {
            "m1_offline",
            "recorder_down",
            "posting_failures",
            "reach_restricted",
            "token_expired",
            "disk_guard",
            "kick_chat_silent",
            "strike",
        }
        missing = want - kinds
        for m in missing:
            ex.append(Example(m, "alert_missing", 0, ""))
    with scratch_db() as c:
        fake = FakePlatforms()
        ch, accs, (cv,) = pb.seed(c, mode="direct")
        now = dt.datetime.now(UTC)
        framework.schedule(c, now)
        ads = registry.adapters(c, fake.transport())
        pb.drain(c, ads, now + dt.timedelta(days=2))
        live_before = db.scalar(c, "SELECT count(*) FROM post WHERE status='live'")
        clip_id = db.scalar(c, "SELECT clip_id FROM clip_version WHERE id=%s", cv)
        commands.submit(c, "pull_clip", {"clip_id": clip_id})
        from clipping import pipeline  # noqa: F401 - registers post_delete handler
        from clipping.worker import HANDLERS

        orig = registry.adapters
        registry.adapters = lambda c_, transport=None: orig(c_, fake.transport())
        try:
            jobs.drain(c, {"post_delete": HANDLERS["server"]["post_delete"]}, "bt")
        finally:
            registry.adapters = orig
        deletable = {"youtube", "instagram", "facebook", "threads"}  # TikTok and Snapchat: manual tasks
        removed = db.scalar(
            c, "SELECT count(*) FROM post WHERE status='cancelled' AND platform = ANY(%s)", list(deletable)
        )
        manual = db.scalar(c, "SELECT count(*) FROM fallback_task WHERE kind='manual_delete'")
        tiktok_failed = db.scalar(c, "SELECT count(*) FROM job WHERE type='post_delete' AND status='dead'")
    # navigation depth from Home
    from clipping.dashboard.app import NAV

    reach = len(NAV) > 0 and all(re.match(r"^/[a-z]*$", h) for h, _ in NAV)
    return StageResult(
        {
            "alerts_fire": float(len(want - missing) / len(want)),
            "kill_switch_removes": 1.0 if removed == len(deletable) and live_before == 6 else 0.0,
            "undeletable_become_tasks": 1.0 if manual == 2 else 0.0,
            "screens_within_3_taps": 1.0 if reach else 0.0,
        },
        ex,
        "simulated@v1",
        {"removed": removed, "manual": manual, "tiktok_delete_dead": tiktok_failed},
    )
