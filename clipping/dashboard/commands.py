"""Dashboard actions -> `command` rows; `execute_pending` applies them (server worker, every few seconds, or
immediately from the dashboard). Nothing here gates posting: these are monitoring and control actions."""

from __future__ import annotations

import psycopg

from clipping.core import db, jobs


def submit(
    c: psycopg.Connection, kind: str, args: dict | None = None, user: str = "owner", run_now: bool = True
) -> int:
    cid = db.scalar(
        c,
        "INSERT INTO command(kind,args,created_by) VALUES (%s,%s,%s) RETURNING id",
        kind,
        db.j(args or {}),
        user,
    )
    db.audit(c, f"command:{kind}", str(args or {}), actor=user)
    if run_now:
        execute_pending(c)
    return cid


def _exec(c: psycopg.Connection, kind: str, a: dict) -> dict:
    from clipping.gate import takedown

    if kind == "global_pause":
        db.set_flag(c, "global_pause", True)
    elif kind == "global_resume":
        db.set_flag(c, "global_pause", False)
    elif kind == "pause_channel":
        c.execute("UPDATE channel SET paused=true WHERE id=%s", (a["channel_id"],))
    elif kind == "resume_channel":
        c.execute("UPDATE channel SET paused=false WHERE id=%s", (a["channel_id"],))
    elif kind == "set_profile":
        c.execute(
            "UPDATE channel SET style_profile=%s, config = config || %s WHERE id=%s",
            (a["profile"], db.j({"style_profile": a["profile"]}), a["channel_id"]),
        )
    elif kind == "set_slots":
        c.execute(
            "UPDATE channel SET config = config || %s WHERE id=%s",
            (db.j({"posting_slots": a["slots"]}), a["channel_id"]),
        )
    elif kind == "pull_clip":
        return takedown.pull_clip(c, a["clip_id"], a.get("reason", "pulled from dashboard"))
    elif kind == "block_creator":
        return takedown.blocklist_creator(c, a["creator_id"], a.get("reason", "blocked from dashboard"))
    elif kind in ("pin_creator", "unpin_creator"):
        c.execute("UPDATE creator SET pinned=%s WHERE id=%s", (kind == "pin_creator", a["creator_id"]))
    elif kind == "stop_recording":
        jobs.enqueue(
            c, "record_stop", {"stream_id": a["stream_id"]}, dedupe_key=f"stop:{a['stream_id']}:dash"
        )
    elif kind == "requeue_clip":
        c.execute(
            "UPDATE clip_version SET status='rendered' WHERE clip_id=%s AND status IN ('rejected','pulled')",
            (a["clip_id"],),
        )
        from clipping.gate import checks

        for r in db.all_(
            c, "SELECT id FROM clip_version WHERE clip_id=%s AND status='rendered'", a["clip_id"]
        ):
            checks.gate(c, r["id"])
    elif kind == "delete_post":
        jobs.enqueue(
            c,
            "post_delete",
            {"post_id": a["post_id"], "reason": "dashboard"},
            dedupe_key=f"del:{a['post_id']}",
            priority=100,
        )
    elif kind == "run_sweeper":
        from clipping.storage import files

        return {"deleted": files.sweep(c)}
    elif kind == "freeze_learning":
        db.set_flag(c, "learning_frozen", bool(a.get("frozen", True)))
    elif kind == "rollback_weights":
        comp = a["component"]
        cur = db.one(
            c,
            "SELECT id, version FROM weights WHERE component=%s AND active ORDER BY version DESC LIMIT 1",
            comp,
        )
        prev = db.one(
            c,
            "SELECT id FROM weights WHERE component=%s AND version < %s ORDER BY version DESC LIMIT 1",
            comp,
            cur["version"] if cur else 10**9,
        )
        if cur and prev:
            c.execute("UPDATE weights SET active=false WHERE id=%s", (cur["id"],))
            c.execute("UPDATE weights SET active=true WHERE id=%s", (prev["id"],))
    elif kind == "fallback_done":
        c.execute("UPDATE fallback_task SET done=true WHERE id=%s", (a["task_id"],))
        t = db.one(c, "SELECT * FROM fallback_task WHERE id=%s", a["task_id"])
        if t and t["post_id"] and t["kind"] in ("publish_private", "inbox_draft"):
            from clipping.publish import framework

            framework.transition(c, t["post_id"], "live", None)
    elif kind == "resolve_alert":
        c.execute("UPDATE alert SET resolved_at=now() WHERE id=%s", (a["alert_id"],))
    else:
        raise ValueError(f"unknown command {kind}")
    return {"ok": True}


def execute_pending(c: psycopg.Connection) -> int:
    n = 0
    for cmd in db.all_(c, "SELECT * FROM command WHERE status='pending' ORDER BY id"):
        try:
            res = _exec(c, cmd["kind"], cmd["args"])
            c.execute(
                "UPDATE command SET status='done', done_at=now(), result=%s WHERE id=%s",
                (db.j(res), cmd["id"]),
            )
        except Exception as e:  # noqa: BLE001
            c.execute(
                "UPDATE command SET status='failed', done_at=now(), result=%s WHERE id=%s",
                (db.j({"error": str(e)}), cmd["id"]),
            )
        n += 1
    return n
