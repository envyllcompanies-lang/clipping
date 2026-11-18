"""Publisher framework & scheduler (doc 16): post jobs per account, platform limits with a reserve, retries with
backoff, idempotency (unique clip_version+account and a platform lookup before any retry), fallback modes, and the
storage refcount signal when a post is final."""

from __future__ import annotations

import datetime as dt
import hashlib
import zoneinfo

import psycopg

from clipping.core import config, db
from clipping.publish.base import (
    PermanentError,
    QuotaExceeded,
    RateLimited,
    Result,
    TokenError,
    TransientError,
)
from clipping.storage import refcount

UTC = dt.UTC
BACKOFF_MIN = [1, 5, 15, 60]
MAX_ATTEMPTS = 4
FRESHNESS_H = 72
SPACING_MIN = 15
RESERVE = 0.10
FINAL = ("live", "failed_permanent", "cancelled")


def limit_24h(platform: str) -> int:
    return int(config.platforms()[platform]["limit_24h"])


def transition(c: psycopg.Connection, post_id: int, to: str, error: str | None = None, **fields) -> None:
    old = db.scalar(c, "SELECT status FROM post WHERE id=%s", post_id)
    sets = ", ".join(f"{k}=%s" for k in fields)
    c.execute(
        f"UPDATE post SET status=%s, error=%s{', ' + sets if sets else ''} WHERE id=%s",
        (to, error, *fields.values(), post_id),
    )
    c.execute(
        "INSERT INTO post_transition(post_id,from_status,to_status,error) VALUES (%s,%s,%s,%s)",
        (post_id, old, to, error),
    )
    if to in FINAL and old not in FINAL:
        cv = db.scalar(c, "SELECT clip_version_id FROM post WHERE id=%s", post_id)
        refcount.post_finished(c, cv)


def used_24h(c: psycopg.Connection, account_id: int, scope: str = "publish") -> int:
    return db.scalar(
        c,
        "SELECT count(*) FROM quota_use WHERE account_id=%s AND scope=%s AND at > now() - interval '24 hours'",
        account_id,
        scope,
    )


def has_capacity(c: psycopg.Connection, account: dict) -> bool:
    """Stay under the platform limit with a reserve kept for retries (failed attempts can count, doc 16)."""
    cap = int(limit_24h(account["platform"]) * (1 - RESERVE))
    if account["platform"] == "youtube":  # 100/day per Google Cloud project, shared by all channels
        proj = db.scalar(
            c,
            "SELECT count(*) FROM quota_use q JOIN account a ON a.id=q.account_id WHERE a.platform='youtube' "
            "AND q.scope='publish' AND q.at > now() - interval '24 hours'",
        )
        if proj >= cap:
            return False
    return used_24h(c, account["id"]) < cap


def warmup_cap(account: dict, ch_cfg: dict, now: dt.datetime) -> int:
    """New accounts post lightly at first and ramp up over the warm-up period (doc 24)."""
    days = max(1, ch_cfg.get("warmup_days", 21))
    age = (now - account["created_at"]).days if account.get("created_at") else days
    full = int(limit_24h(account["platform"]) * (1 - RESERVE))
    if age >= days:
        return full
    return max(1, int(full * (0.15 + 0.85 * age / days)))


def slot_times(ch_cfg: dict, day: dt.date, account_id: int) -> list[dt.datetime]:
    """Posting slots in the channel's time zone, staggered per account so a network never posts in sync."""
    tz = zoneinfo.ZoneInfo(ch_cfg.get("time_zone", "UTC"))
    jitter = int(hashlib.sha256(str(account_id).encode()).hexdigest(), 16) % 23 - 11  # -11..+11 minutes
    out = []
    for s in ch_cfg.get("posting_slots", ["10:00", "13:00", "16:00", "19:00", "21:30"]):
        h, m = (int(x) for x in s.split(":"))
        local = dt.datetime.combine(day, dt.time(h, m), tz) + dt.timedelta(minutes=jitter)
        out.append(local.astimezone(UTC))
    return out


def next_slot(c: psycopg.Connection, account: dict, ch_cfg: dict, now: dt.datetime) -> dt.datetime | None:
    """First free slot at least SPACING_MIN after this account's other scheduled posts, within the warm-up cap."""
    taken = [
        r["scheduled_at"]
        for r in db.all_(
            c,
            """SELECT scheduled_at FROM post WHERE account_id=%s AND status NOT IN ('cancelled','failed_permanent')
                                                      AND scheduled_at > %s - interval '1 day'""",
            account["id"],
            now,
        )
    ]
    for d in range(0, 4):
        day = (now + dt.timedelta(days=d)).date()
        day_count = sum(1 for t in taken if t.date() == day)
        if day_count >= warmup_cap(account, ch_cfg, now):
            continue
        for t in slot_times(ch_cfg, day, account["id"]):
            if t < now:
                continue
            if all(abs((t - x).total_seconds()) >= SPACING_MIN * 60 for x in taken):
                return t
    return None


def schedule(c: psycopg.Connection, now: dt.datetime | None = None) -> int:
    """Queued clip versions -> post rows per target account. Fresh/trending clips first; >72 h old clips expire."""
    if db.get_flag(c, "global_pause"):
        return 0
    now = now or dt.datetime.now(UTC)
    n = 0
    rows = db.all_(
        c,
        """SELECT cv.*, m.score, m.created_at moment_at, cl.channel_id FROM clip_version cv JOIN clip cl ON cl.id=cv.clip_id
                         JOIN moment m ON m.id=cl.moment_id WHERE cv.status='queued' ORDER BY m.score DESC, m.created_at DESC""",
    )
    for cv in rows:
        if now - cv["moment_at"] > dt.timedelta(hours=FRESHNESS_H):
            c.execute("UPDATE clip_version SET status='expired' WHERE id=%s", (cv["id"],))
            continue
        made = 0
        for t in cv["targets"]:
            acc = db.one(
                c,
                """SELECT a.*, ch.config ch_cfg, ch.paused ch_paused, ch.time_zone FROM account a JOIN channel ch ON ch.id=a.channel_id
                               WHERE a.id=%s""",
                t["account_id"],
            )
            if not acc or acc["ch_paused"]:
                continue
            ch_cfg = dict(acc["ch_cfg"] or {}, time_zone=acc["time_zone"])
            slot = next_slot(c, acc, ch_cfg, now)
            if slot is None:
                continue
            freshness = max(0.0, 1 - (now - cv["moment_at"]).total_seconds() / (FRESHNESS_H * 3600))
            pid = db.scalar(
                c,
                """INSERT INTO post(clip_version_id,account_id,platform,scheduled_at,priority)
                                  VALUES (%s,%s,%s,%s,%s) ON CONFLICT (clip_version_id,account_id) DO NOTHING RETURNING id""",
                cv["id"],
                acc["id"],
                acc["platform"],
                slot,
                round(cv["score"] + freshness, 4),
            )
            if pid:
                c.execute("INSERT INTO post_transition(post_id,to_status) VALUES (%s,'scheduled')", (pid,))
                made += 1
        if made or db.scalar(c, "SELECT count(*) FROM post WHERE clip_version_id=%s", cv["id"]):
            c.execute("UPDATE clip_version SET status='scheduled' WHERE id=%s", (cv["id"],))
            refcount.recount(c, cv["id"])
        n += made
    return n


def clip_for(c: psycopg.Connection, post: dict) -> dict:
    return db.one(
        c,
        """SELECT cv.*, cl.packaging, cl.channel_id, ch.language, ch.config ch_cfg FROM clip_version cv
                        JOIN clip cl ON cl.id=cv.clip_id JOIN channel ch ON ch.id=cl.channel_id WHERE cv.id=%s""",
        post["clip_version_id"],
    )


def run_post(c: psycopg.Connection, post_id: int, adapters: dict, now: dt.datetime | None = None) -> str:
    """Advance one post through its states. Safe to call again after a crash at any point."""
    now = now or dt.datetime.now(UTC)
    post = db.one(c, "SELECT * FROM post WHERE id=%s", post_id)
    if post["status"] in FINAL:
        return post["status"]
    acc = db.one(c, "SELECT * FROM account WHERE id=%s", post["account_id"])
    ad = adapters[post["platform"]]
    if db.get_flag(c, "global_pause") or db.scalar(
        c, "SELECT paused FROM channel WHERE id=%s", acc["channel_id"]
    ):
        return post["status"]
    if acc["paused_until"] and acc["paused_until"] > now:
        return post["status"]
    try:
        if post["status"] == "processing" and post["platform_post_id"]:
            r = ad.check(post["platform_post_id"], acc)
            return _apply(c, post, r, ad)
        if post["status"] == "uploading" and post["upload_session"]:
            # container/session already exists (IG/Threads container, YouTube resumable session): resume it,
            # never re-create, never count quota again
            payload = ad.prepare(clip_for(c, post), acc)
            r = ad.publish(payload, resume=post["upload_session"])
            return _apply(c, post, r, ad, payload)
        if post["status"] in ("scheduled", "retry_wait", "uploading"):
            if post["status"] == "retry_wait" and post["next_attempt_at"] and post["next_attempt_at"] > now:
                return post["status"]
            if post["scheduled_at"] > now and post["status"] == "scheduled":
                return post["status"]
            if not has_capacity(c, acc):
                return post["status"]
            clip = clip_for(c, post)
            clip["manual_post_info"] = (post["fields"] or {}).get("manual_post_info")
            payload = ad.prepare(clip, acc)
            if post["attempts"] > 0 or post["status"] == "uploading":
                existing = ad.find_existing(payload)  # crashed mid-upload: never post twice
                if existing:
                    transition(c, post_id, "processing", None, platform_post_id=existing)
                    return "processing"
            if ad.needs_public_url and not payload.public_url and not post["upload_session"]:
                from clipping.storage import bucket

                payload.public_url = bucket.put_public(c, clip["path"], clip["id"])
            transition(c, post_id, "uploading", None, attempts=post["attempts"] + 1)
            c.execute(
                "INSERT INTO quota_use(account_id,platform,scope) VALUES (%s,%s,'publish')",
                (acc["id"], acc["platform"]),
            )
            r = ad.publish(payload, resume=post["upload_session"])
            c.execute(
                "UPDATE post SET fields = COALESCE(fields, '{}'::jsonb) || %s WHERE id=%s",
                (db.j(payload.fields), post_id),
            )
            return _apply(c, post, r, ad, payload)
    except TokenError as e:
        c.execute("UPDATE account SET status='token_expired' WHERE id=%s", (acc["id"],))
        db.alert(
            c,
            "token_expired",
            f"{acc['platform']} account {acc['id']} needs reconnecting: {e}",
            str(acc["id"]),
            "critical",
        )
        transition(c, post_id, "failed_permanent", f"token: {e}")
        return "failed_permanent"
    except QuotaExceeded as e:
        if e.scope == "project":
            c.execute("UPDATE account SET paused_until=%s WHERE platform=%s", (e.until, acc["platform"]))
        else:
            c.execute("UPDATE account SET paused_until=%s WHERE id=%s", (e.until, acc["id"]))
        transition(c, post_id, "retry_wait", str(e), next_attempt_at=e.until)
        return "retry_wait"
    except (RateLimited, TransientError) as e:
        if getattr(e, "session", None):
            c.execute("UPDATE post SET upload_session=%s WHERE id=%s", (e.session, post_id))
        attempts = db.scalar(c, "SELECT attempts FROM post WHERE id=%s", post_id)
        if attempts >= MAX_ATTEMPTS:
            transition(c, post_id, "failed_permanent", f"gave up after {attempts} attempts: {e}")
            return "failed_permanent"
        wait = getattr(e, "until", None) or now + dt.timedelta(
            minutes=BACKOFF_MIN[min(attempts, len(BACKOFF_MIN)) - 1 if attempts else 0]
        )
        transition(c, post_id, "retry_wait", str(e), next_attempt_at=wait)
        return "retry_wait"
    except PermanentError as e:
        transition(c, post_id, "failed_permanent", str(e))
        return "failed_permanent"
    return post["status"]


def _apply(c: psycopg.Connection, post: dict, r: Result, ad, payload=None) -> str:
    if r.upload_session:
        c.execute("UPDATE post SET upload_session=%s WHERE id=%s", (r.upload_session, post["id"]))
    if r.fallback:
        c.execute("UPDATE post SET fallback=true WHERE id=%s", (post["id"],))
        if not db.one(c, "SELECT 1 FROM fallback_task WHERE post_id=%s AND kind=%s", post["id"], r.fallback):
            c.execute(
                "INSERT INTO fallback_task(post_id,platform,kind,details) VALUES (%s,%s,%s,%s)",
                (post["id"], post["platform"], r.fallback, db.j({"platform_post_id": r.platform_post_id})),
            )
    if r.status == "processing":
        transition(c, post["id"], "processing", None, platform_post_id=r.platform_post_id)
    elif r.status == "live":
        transition(
            c,
            post["id"],
            "live",
            None,
            platform_post_id=r.platform_post_id or post["platform_post_id"],
            posted_at=dt.datetime.now(UTC),
        )
        _release_public(c, post)
    elif r.status == "failed":
        transition(c, post["id"], "failed_permanent", r.error)
        _release_public(c, post)
    elif r.status == "uploading":
        pass
    return r.status if r.status != "failed" else "failed_permanent"


def _release_public(c: psycopg.Connection, post: dict) -> None:
    """Delete the bucket copy once no other post of this clip still needs it to be pulled."""
    pending = db.scalar(
        c,
        """SELECT count(*) FROM post WHERE clip_version_id=%s AND platform IN ('instagram','threads','tiktok')
                              AND status IN ('scheduled','uploading','retry_wait') AND id<>%s""",
        post["clip_version_id"],
        post["id"],
    )
    if not pending:
        from clipping.storage import bucket

        bucket.delete_for(c, post["clip_version_id"])


def run_due(c: psycopg.Connection, adapters: dict, now: dt.datetime | None = None, limit: int = 50) -> dict:
    now = now or dt.datetime.now(UTC)
    rows = db.all_(
        c,
        """SELECT id FROM post WHERE (status='scheduled' AND scheduled_at <= %s)
                         OR (status='retry_wait' AND next_attempt_at <= %s) OR status IN ('processing','uploading')
                         ORDER BY priority DESC, scheduled_at LIMIT %s""",
        now,
        now,
        limit,
    )
    out: dict[str, int] = {}
    for r in rows:
        if db.scalar(c, "SELECT platform FROM post WHERE id=%s", r["id"]) not in adapters:
            continue
        s = run_post(c, r["id"], adapters, now)
        out[s] = out.get(s, 0) + 1
    return out


def delete_post(c: psycopg.Connection, post_id: int, adapters: dict) -> bool:
    p = db.one(c, "SELECT * FROM post WHERE id=%s", post_id)
    acc = db.one(c, "SELECT * FROM account WHERE id=%s", p["account_id"])
    ok = bool(p["platform_post_id"]) and adapters[p["platform"]].delete(p["platform_post_id"], acc)
    if ok or not p["platform_post_id"]:
        transition(c, post_id, "cancelled", "deleted (takedown)")
        db.audit(c, "post_deleted", str(post_id), {"platform": p["platform"]})
    return ok
