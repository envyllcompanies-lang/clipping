"""Postgres access. Every component reads/writes through here."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from clipping.core import settings

SCHEMA = settings.ROOT / "sql" / "schema.sql"
_url_override: str | None = None


def set_url(url: str | None) -> None:
    global _url_override
    _url_override = url


def url() -> str:
    return _url_override or settings.database_url()


def connect(autocommit: bool = True) -> psycopg.Connection:
    return psycopg.connect(url(), autocommit=autocommit, row_factory=dict_row)


@contextlib.contextmanager
def conn() -> Iterator[psycopg.Connection]:
    c = connect()
    try:
        yield c
    finally:
        c.close()


@contextlib.contextmanager
def tx() -> Iterator[psycopg.Connection]:
    c = connect(autocommit=False)
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def migrate(c: psycopg.Connection | None = None) -> None:
    sql = SCHEMA.read_text()
    if c is None:
        with conn() as c2:
            c2.execute(sql)
    else:
        c.execute(sql)


def j(v: Any) -> Jsonb:
    return Jsonb(v)


def one(c: psycopg.Connection, q: str, *args: Any) -> dict | None:
    return c.execute(q, args or None).fetchone()


def all_(c: psycopg.Connection, q: str, *args: Any) -> list[dict]:
    return c.execute(q, args or None).fetchall()


def scalar(c: psycopg.Connection, q: str, *args: Any) -> Any:
    r = c.execute(q, args or None).fetchone()
    return None if r is None else next(iter(r.values()))


def get_flag(c: psycopg.Connection, key: str, default: Any = None) -> Any:
    r = one(c, "SELECT value FROM system_flag WHERE key=%s", key)
    return default if r is None else r["value"]


def set_flag(c: psycopg.Connection, key: str, value: Any) -> None:
    c.execute(
        "INSERT INTO system_flag(key,value) VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()",
        (key, j(value)),
    )


def audit(
    c: psycopg.Connection, action: str, subject: str = "", details: dict | None = None, actor: str = "system"
) -> None:
    c.execute(
        "INSERT INTO audit_log(actor,action,subject,details) VALUES (%s,%s,%s,%s)",
        (actor, action, subject, j(details or {})),
    )


def alert(
    c: psycopg.Connection, kind: str, message: str, subject: str = "", severity: str = "warning"
) -> None:
    """Raise an alert once per open (kind, subject)."""
    exists = one(
        c, "SELECT id FROM alert WHERE kind=%s AND subject=%s AND resolved_at IS NULL", kind, subject
    )
    if not exists:
        c.execute(
            "INSERT INTO alert(kind,severity,message,subject) VALUES (%s,%s,%s,%s)",
            (kind, severity, message, subject),
        )


def resolve_alert(c: psycopg.Connection, kind: str, subject: str = "") -> None:
    c.execute(
        "UPDATE alert SET resolved_at=now() WHERE kind=%s AND subject=%s AND resolved_at IS NULL",
        (kind, subject),
    )
