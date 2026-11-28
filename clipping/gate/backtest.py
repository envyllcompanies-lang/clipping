"""Stage backtest 15 (mechanics): a repeat of the same moment/video to the same account is rejected, the first post
is allowed, every decision has a reason, and blocklisting pulls clips everywhere. Duplicate detection accuracy is
graded on real footage once the real clip-window set exists (synthetic duplicate sets were removed)."""

from __future__ import annotations

from clipping.core import db
from clipping.eval.harness import StageResult, scratch_db, stage
from clipping.gate import checks, takedown

PHASH = "0f0f0f0f0f0f0f0f" * 8


@stage("15", "Auto-Gate")
def run() -> StageResult:
    with scratch_db() as c:
        ch = db.scalar(
            c,
            "INSERT INTO channel(key,language,time_zone,score_floor) VALUES ('gta6-en','en','UTC',0.3) RETURNING id",
        )
        db.scalar(
            c,
            "INSERT INTO account(channel_id,platform,status) VALUES (%s,'youtube','connected') RETURNING id",
            ch,
        )
        db.scalar(
            c,
            "INSERT INTO account(channel_id,platform,status) VALUES (%s,'snapchat','connected') RETURNING id",
            ch,
        )
        cr = db.scalar(
            c, "INSERT INTO creator(platform,platform_id,handle) VALUES ('twitch','1','x') RETURNING id"
        )
        st = db.scalar(
            c,
            "INSERT INTO stream(creator_id,platform_stream_id,started_at) VALUES (%s,'s',now()) RETURNING id",
            cr,
        )
        plan = {
            "transformations": ["hook_text", "captions", "credit", "zooms"],
            "segments": [{"start": 0, "end": 30, "role": "body"}],
        }

        def make_cv(start_s):
            mid = db.scalar(
                c,
                "INSERT INTO moment(stream_id,start_s,end_s,peak_s,score) VALUES (%s,%s,%s,%s,0.8) RETURNING id",
                st,
                start_s,
                start_s + 75,
                start_s + 45,
            )
            clip = db.scalar(
                c,
                "INSERT INTO clip(moment_id,channel_id,creator_id,edit_plan,packaging) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                mid,
                ch,
                cr,
                db.j({"versions": {"short": plan}}),
                db.j({"safe": True, "hook_text": "x"}),
            )
            return db.scalar(
                c,
                """INSERT INTO clip_version(clip_id,version_type,phash,duration_s,validation,status)
                                   VALUES (%s,'short',%s,30,%s,'rendered') RETURNING id""",
                clip,
                PHASH,
                db.j({"passed": True}),
            )

        cv1 = make_cv(100)
        d1 = checks.gate(c, cv1)
        for t in d1.targets:
            c.execute(
                "INSERT INTO post(clip_version_id,account_id,platform,status,scheduled_at) VALUES (%s,%s,%s,'live',now())",
                (cv1, t["account_id"], t["platform"]),
            )
        d2 = checks.gate(c, make_cv(102))
        reasons_ok = db.scalar(c, "SELECT bool_and(reason IS NOT NULL AND reason <> '') FROM gate_result")
        res = takedown.blocklist_creator(c, cr)
        pulled = db.scalar(c, "SELECT count(*) FROM post WHERE status IN ('scheduled','retry_wait')") == 0
        jobs_ok = (
            db.scalar(c, "SELECT count(*) FROM job WHERE type='post_delete'") == res["delete_jobs"]
            and res["manual_deletes"] == 1
        )
    return StageResult(
        {
            "repeat_to_same_account_blocked": 1.0 if d2.status == "rejected" else 0.0,
            "first_post_allowed": 1.0 if d1.status == "queued" and len(d1.targets) == 2 else 0.0,
            "decisions_have_reasons": 1.0 if reasons_ok else 0.0,
            "blocklist_pulls_everywhere": 1.0 if pulled and jobs_ok else 0.0,
        },
        [],
        "mechanics@v1",
    )
