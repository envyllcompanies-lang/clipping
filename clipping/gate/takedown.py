"""Takedowns, claims and strikes (doc 15). Blocklisting a creator removes their clips everywhere: pending posts are
cancelled and live posts get delete jobs (platforms without API delete, like Snapchat, become manual tasks)."""

from __future__ import annotations

import psycopg

from clipping.core import db, jobs

NO_API_DELETE = {"snapchat"}


def blocklist_creator(
    c: psycopg.Connection, creator_id: int, reason: str = "creator objection", actor: str = "dashboard"
) -> dict:
    c.execute("UPDATE creator SET blocklisted=true WHERE id=%s", (creator_id,))
    db.audit(c, "blocklist_creator", str(creator_id), {"reason": reason}, actor)
    return pull_clips(c, "cl.creator_id=%s", (creator_id,), reason)


def pull_clip(c: psycopg.Connection, clip_id: int, reason: str = "pulled from dashboard") -> dict:
    return pull_clips(c, "cl.id=%s", (clip_id,), reason)


def pull_clips(c: psycopg.Connection, where: str, args: tuple, reason: str) -> dict:
    posts = db.all_(
        c,
        f"""SELECT p.* FROM post p JOIN clip_version cv ON cv.id=p.clip_version_id JOIN clip cl ON cl.id=cv.clip_id
                          WHERE {where}""",
        *args,
    )
    cancelled = deleting = manual = 0
    for p in posts:
        if p["status"] in ("scheduled", "retry_wait"):
            c.execute("UPDATE post SET status='cancelled', error=%s WHERE id=%s", (reason, p["id"]))
            c.execute(
                "INSERT INTO post_transition(post_id,from_status,to_status,error) VALUES (%s,%s,'cancelled',%s)",
                (p["id"], p["status"], reason),
            )
            cancelled += 1
        elif p["status"] in ("live", "processing", "uploading"):
            if p["platform"] in NO_API_DELETE:
                c.execute(
                    "INSERT INTO fallback_task(post_id,platform,kind,details) VALUES (%s,%s,'manual_delete',%s)",
                    (
                        p["id"],
                        p["platform"],
                        db.j({"reason": reason, "platform_post_id": p["platform_post_id"]}),
                    ),
                )
                manual += 1
            else:
                jobs.enqueue(
                    c,
                    "post_delete",
                    {"post_id": p["id"], "reason": reason},
                    dedupe_key=f"del:{p['id']}",
                    priority=100,
                )
                deleting += 1
    from clipping.storage import refcount

    for cv in {p["clip_version_id"] for p in posts}:
        refcount.recount(c, cv)
    c.execute(
        f"""UPDATE clip_version SET status='pulled' WHERE clip_id IN (SELECT cl.id FROM clip cl WHERE {where})
                  AND status IN ('rendered','queued','planned','gated')""",
        args,
    )
    return {"cancelled": cancelled, "delete_jobs": deleting, "manual_deletes": manual}


def record_claim(
    c: psycopg.Connection, post_id: int, kind: str = "copyright", details: dict | None = None
) -> dict:
    """Copyright claim: record, take the post down, pause the source network-wide until resolved. Strikes also
    pause the account's posting."""
    p = db.one(
        c,
        """SELECT p.*, cl.creator_id FROM post p JOIN clip_version cv ON cv.id=p.clip_version_id
                     JOIN clip cl ON cl.id=cv.clip_id WHERE p.id=%s""",
        post_id,
    )
    c.execute(
        "INSERT INTO claim(post_id,account_id,kind,details) VALUES (%s,%s,%s,%s)",
        (post_id, p["account_id"], kind, db.j(details or {})),
    )
    if p["creator_id"]:
        c.execute("UPDATE creator SET paused=true WHERE id=%s", (p["creator_id"],))
    jobs.enqueue(
        c, "post_delete", {"post_id": post_id, "reason": kind}, dedupe_key=f"del:{post_id}", priority=100
    )
    n7 = db.scalar(
        c,
        "SELECT count(*) FROM claim WHERE account_id=%s AND created_at > now() - interval '7 days'",
        p["account_id"],
    )
    c.execute(
        "UPDATE account SET health = health || %s WHERE id=%s", (db.j({"claims_7d": n7}), p["account_id"])
    )
    if kind == "strike":
        c.execute(
            "UPDATE account SET paused_until = now() + interval '30 days' WHERE id=%s", (p["account_id"],)
        )
        db.alert(
            c,
            "strike",
            f"Strike on account {p['account_id']}: posting paused",
            str(p["account_id"]),
            "critical",
        )
    else:
        db.alert(c, "claim", f"{kind} claim on post {post_id}; source paused", str(post_id))
    return {"claims_7d": n7, "source_paused": bool(p["creator_id"])}
