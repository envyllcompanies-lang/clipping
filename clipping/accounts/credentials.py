"""Credential storage (doc 24): secrets encrypted at rest (TOKEN_ENCRYPTION_KEY), refresh ahead of expiry,
failures alert the dashboard to reconnect, every token use audit-logged. Values never logged."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable

import psycopg

from clipping.core import crypto, db

UTC = dt.UTC
REFRESH_AHEAD = {"kick": dt.timedelta(minutes=20), "default": dt.timedelta(hours=1)}


def store(
    c: psycopg.Connection,
    account_id: int | None,
    platform: str,
    kind: str,
    secret: dict,
    expires_at: dt.datetime | None = None,
    scopes: str = "",
) -> int:
    enc = crypto.encrypt(json.dumps(secret))
    cid = db.scalar(
        c,
        """INSERT INTO credential(platform,account_id,kind,secret_enc,expires_at,scopes,refreshed_at)
                          VALUES (%s,%s,%s,%s,%s,%s,now()) RETURNING id""",
        platform,
        account_id,
        kind,
        enc,
        expires_at,
        scopes,
    )
    c.execute(
        "DELETE FROM credential WHERE account_id IS NOT DISTINCT FROM %s AND platform=%s AND kind=%s AND id<>%s",
        (account_id, platform, kind, cid),
    )
    if account_id:
        c.execute(
            "UPDATE account SET token_ref=%s, status=CASE WHEN status='disconnected' THEN 'connected' ELSE status END WHERE id=%s",
            (cid, account_id),
        )
        db.resolve_alert(c, "token_expired", str(account_id))
    db.audit(
        c, "credential_stored", f"{platform}:{account_id}", {"kind": kind, "expires_at": str(expires_at)}
    )
    return cid


def load(c: psycopg.Connection, account_id: int, kind: str = "oauth", purpose: str = "use") -> dict | None:
    r = db.one(
        c,
        "SELECT * FROM credential WHERE account_id=%s AND kind=%s ORDER BY id DESC LIMIT 1",
        account_id,
        kind,
    )
    if not r:
        return None
    db.audit(c, "token_use", f"{r['platform']}:{account_id}", {"purpose": purpose})
    return json.loads(crypto.decrypt(r["secret_enc"])) | {
        "_expires_at": r["expires_at"].isoformat() if r["expires_at"] else None
    }


def due_for_refresh(c: psycopg.Connection, now: dt.datetime | None = None) -> list[dict]:
    now = now or dt.datetime.now(UTC)
    rows = db.all_(
        c,
        "SELECT id, platform, account_id, expires_at FROM credential WHERE expires_at IS NOT NULL AND account_id IS NOT NULL",
    )
    return [
        r for r in rows if r["expires_at"] - REFRESH_AHEAD.get(r["platform"], REFRESH_AHEAD["default"]) <= now
    ]


def refresh_all(
    c: psycopg.Connection,
    refreshers: dict[str, Callable[[dict], tuple[dict, dt.datetime]]],
    now: dt.datetime | None = None,
) -> dict:
    """refreshers[platform](secret) -> (new_secret, new_expiry). Failures mark the account and raise a reconnect alert."""
    ok = failed = 0
    for r in due_for_refresh(c, now):
        fn = refreshers.get(r["platform"])
        if fn is None:
            continue
        secret = load(c, r["account_id"], purpose="refresh") or {}
        try:
            new, exp = fn(secret)
            store(c, r["account_id"], r["platform"], "oauth", new, exp)
            ok += 1
        except Exception as e:  # noqa: BLE001 - any refresh failure needs the owner
            c.execute("UPDATE account SET status='token_expired' WHERE id=%s", (r["account_id"],))
            db.alert(
                c,
                "token_expired",
                f"{r['platform']} account {r['account_id']} needs reconnecting ({type(e).__name__})",
                str(r["account_id"]),
                "critical",
            )
            failed += 1
    return {"refreshed": ok, "failed": failed}


def token_health(c: psycopg.Connection) -> list[dict]:
    return db.all_(
        c,
        """SELECT a.id, ch.key channel, a.platform, a.handle, a.status, a.review_status, a.mode, cr.expires_at
                         FROM account a JOIN channel ch ON ch.id=a.channel_id LEFT JOIN credential cr ON cr.id=a.token_ref
                         ORDER BY ch.key, a.platform""",
    )
