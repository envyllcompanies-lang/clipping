"""File Manager (doc 21): every file registered, deleted directly (os.unlink, never Trash), sweeper + reconcile."""

from __future__ import annotations

import datetime as dt
import os
import shutil
from pathlib import Path

import psycopg

from clipping.core import config, db, settings

UTC = dt.UTC
MANAGED = ("recordings", "windows", "work", "renders", "public")


def managed(kind: str) -> Path:
    if kind not in MANAGED:
        raise ValueError(f"{kind} is not a managed folder")
    p = settings.data_dir() / kind
    p.mkdir(parents=True, exist_ok=True)
    return p


def is_managed(path: Path) -> bool:
    root = settings.data_dir().resolve()
    try:
        rel = Path(path).resolve().relative_to(root)
    except ValueError:
        return False
    return bool(rel.parts) and rel.parts[0] in MANAGED


def register(
    c: psycopg.Connection,
    path: str | Path,
    kind: str,
    owner_type: str | None = None,
    owner_id: int | None = None,
    expires_at: dt.datetime | None = None,
    max_age_h: float | None = None,
) -> None:
    path = Path(path)
    if not is_managed(path):
        raise ValueError(f"refusing to register file outside managed folders: {path}")
    if expires_at is None:
        age = max_age_h if max_age_h is not None else config.settings()["storage"]["max_age_h"].get(kind, 24)
        expires_at = dt.datetime.now(UTC) + dt.timedelta(hours=age)
    size = path.stat().st_size if path.exists() else 0
    c.execute(
        """INSERT INTO file(path,kind,size,owner_type,owner_id,expires_at) VALUES (%s,%s,%s,%s,%s,%s)
                 ON CONFLICT (path) DO UPDATE SET size=EXCLUDED.size, expires_at=EXCLUDED.expires_at, deleted_at=NULL,
                   missing=false, owner_type=EXCLUDED.owner_type, owner_id=EXCLUDED.owner_id""",
        (str(path), kind, size, owner_type, owner_id, expires_at),
    )


def _unlink(path: Path) -> None:
    """Permanent delete. os.unlink / rmtree bypass the macOS Trash entirely."""
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            os.unlink(path)
    except FileNotFoundError:
        pass


def delete_path(c: psycopg.Connection, path: str | Path) -> None:
    _unlink(Path(path))
    c.execute("UPDATE file SET deleted_at=now() WHERE path=%s AND deleted_at IS NULL", (str(path),))


def work_dir(c: psycopg.Connection, job_id: str | int) -> Path:
    p = managed("work") / str(job_id)
    p.mkdir(parents=True, exist_ok=True)
    register(c, p, "work", "job", None)
    return p


def _owner_alive(c: psycopg.Connection, owner_type: str | None, owner_id: int | None) -> bool:
    if owner_type is None or owner_id is None:
        return True
    q = {
        "stream": "SELECT 1 FROM stream WHERE id=%s",
        "window": """SELECT 1 FROM "window" WHERE id=%s AND status NOT IN ('rendered','discarded','expired')""",
        "clip_version": "SELECT 1 FROM clip_version WHERE id=%s AND status<>'media_deleted'",
    }.get(owner_type)
    return True if q is None else db.one(c, q, owner_id) is not None


def sweep(c: psycopg.Connection, now: dt.datetime | None = None) -> int:
    """Delete everything past expires_at or orphaned (no live owner)."""
    now = now or dt.datetime.now(UTC)
    n = 0
    for r in db.all_(c, "SELECT * FROM file WHERE deleted_at IS NULL"):
        if (r["expires_at"] and r["expires_at"] <= now) or not _owner_alive(
            c, r["owner_type"], r["owner_id"]
        ):
            delete_path(c, r["path"])
            if r["kind"] == "segment":
                c.execute("UPDATE segment SET deleted=true WHERE path=%s", (r["path"],))
            n += 1
    return n


def reconcile(c: psycopg.Connection) -> dict:
    """Startup: unknown files in managed folders are deleted; registered-but-missing files get marked."""
    known = {r["path"] for r in db.all_(c, "SELECT path FROM file WHERE deleted_at IS NULL")}
    removed = 0
    for kind in MANAGED:
        root = managed(kind)
        for p in sorted(root.rglob("*"), key=lambda x: -len(x.parts)):
            if str(p) in known:
                continue
            if p.is_file():
                if any(str(p).startswith(k + os.sep) for k in known):
                    continue  # inside a registered work dir
                _unlink(p)
                removed += 1
            elif p.is_dir() and not any(p.iterdir()) and str(p) not in known:
                p.rmdir()
    missing = 0
    for path in known:
        if not Path(path).exists():
            c.execute("UPDATE file SET missing=true, deleted_at=now() WHERE path=%s", (path,))
            missing += 1
    return {"removed_unknown": removed, "marked_missing": missing}


def usage_by_kind(c: psycopg.Connection) -> list[dict]:
    return db.all_(
        c,
        "SELECT kind, count(*) n, coalesce(sum(size),0) bytes FROM file WHERE deleted_at IS NULL GROUP BY kind ORDER BY kind",
    )
