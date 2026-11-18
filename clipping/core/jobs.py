"""Postgres job queue using SELECT ... FOR UPDATE SKIP LOCKED (doc 25). Workers are idempotent and restartable."""

from __future__ import annotations

import socket
import traceback
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import psycopg

from clipping.core import db

BACKOFF_MIN = [1, 5, 15, 60]


class PermanentError(Exception):
    """Error that must not be retried."""


def enqueue(c: psycopg.Connection, type_: str, payload: dict | None = None, *, dedupe_key: str | None = None,
            priority: int = 0, delay_s: float = 0, max_attempts: int = 4) -> int | None:
    r = db.one(
        c,
        """INSERT INTO job(type,payload,dedupe_key,priority,run_after,max_attempts)
           VALUES (%s,%s,%s,%s, now() + make_interval(secs => %s), %s)
           ON CONFLICT (type, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING RETURNING id""",
        type_, db.j(payload or {}), dedupe_key, priority, delay_s, max_attempts,
    )
    return r["id"] if r else None


def claim(c: psycopg.Connection, types: list[str], worker: str, lease_s: int = 600) -> dict | None:
    """Claim one runnable job. Expired leases (crashed workers) are re-claimable."""
    with c.transaction():
        r = db.one(
            c,
            """SELECT * FROM job WHERE type = ANY(%s) AND (
                 (status='queued' AND run_after <= now()) OR (status='running' AND locked_until < now()))
               ORDER BY priority DESC, run_after, id FOR UPDATE SKIP LOCKED LIMIT 1""",
            types,
        )
        if not r:
            return None
        c.execute(
            """UPDATE job SET status='running', locked_by=%s, locked_until=now()+make_interval(secs=>%s),
               attempts=attempts+1, updated_at=now() WHERE id=%s""",
            (worker, lease_s, r["id"]),
        )
        r["attempts"] += 1
        return r


def complete(c: psycopg.Connection, job_id: int, result: Any = None) -> None:
    c.execute("UPDATE job SET status='done', result=%s, locked_by=NULL, locked_until=NULL, updated_at=now() WHERE id=%s",
              (db.j(result), job_id))


def fail(c: psycopg.Connection, job: dict, error: str, permanent: bool = False) -> str:
    if permanent or job["attempts"] >= job["max_attempts"]:
        c.execute("UPDATE job SET status='dead', last_error=%s, locked_by=NULL, updated_at=now() WHERE id=%s", (error, job["id"]))
        return "dead"
    delay = BACKOFF_MIN[min(job["attempts"] - 1, len(BACKOFF_MIN) - 1)] * 60
    c.execute(
        """UPDATE job SET status='queued', last_error=%s, locked_by=NULL, locked_until=NULL,
           run_after=now()+make_interval(secs=>%s), updated_at=now() WHERE id=%s""",
        (error, delay, job["id"]),
    )
    return "retry"


def heartbeat(c: psycopg.Connection, worker: str, role: str, info: dict | None = None) -> None:
    c.execute(
        """INSERT INTO worker_heartbeat(worker,host,role,info) VALUES (%s,%s,%s,%s)
           ON CONFLICT (worker) DO UPDATE SET seen_at=now(), info=EXCLUDED.info, role=EXCLUDED.role""",
        (worker, socket.gethostname(), role, db.j(info or {})),
    )


def run_one(c: psycopg.Connection, handlers: dict[str, Callable[[psycopg.Connection, dict], Any]], worker: str) -> bool:
    job = claim(c, list(handlers), worker)
    if not job:
        return False
    try:
        res = handlers[job["type"]](c, job["payload"])
        complete(c, job["id"], res)
    except PermanentError as e:
        fail(c, job, str(e), permanent=True)
    except Exception as e:  # noqa: BLE001 - worker must survive any handler error
        fail(c, job, f"{e}\n{traceback.format_exc(limit=5)}")
    return True


def drain(c: psycopg.Connection, handlers: dict, worker: str = "local", limit: int = 10_000) -> int:
    n = 0
    while n < limit and run_one(c, handlers, worker):
        n += 1
    return n


def lease_left(job: dict) -> timedelta | None:
    return None
