"""Disk guard (doc 21): pause extraction/recording/rendering as free space drops; purge at the floor."""

from __future__ import annotations

import shutil
from pathlib import Path

import psycopg

from clipping.core import config, db
from clipping.storage import files


def disk_status(path: Path) -> dict:
    u = shutil.disk_usage(path)
    return {"free_gb": u.free / 1024**3, "total_gb": u.total / 1024**3, "free_pct": 100 * u.free / u.total}


def level(st: dict, role: str = "m1") -> str:
    cfg = config.settings()["storage"]
    if role == "m1":
        t, v = cfg["guard_m1_gb"], st["free_gb"]
    else:
        t, v = cfg["guard_server_pct"], st["free_pct"]
    if v < t["purge"]:
        return "purge"
    if v < t["pause"]:
        return "pause"
    if v < t["normal"]:
        return "low"
    return "normal"


def check(c: psycopg.Connection, role: str, st: dict | None = None, path: Path | None = None) -> str:
    from clipping.core import settings

    st = st or disk_status(path or settings.data_dir())
    lv = level(st, role)
    db.set_flag(c, f"disk_level_{role}", {"level": lv, **{k: round(v, 2) for k, v in st.items()}})
    db.set_flag(c, f"pause_extract_{role}", lv != "normal")
    db.set_flag(c, f"pause_heavy_{role}", lv in ("pause", "purge"))
    if lv == "normal":
        db.resolve_alert(c, "disk_guard", role)
    else:
        files.sweep(c)
        if lv in ("pause", "purge"):
            db.alert(
                c, "disk_guard", f"{role} disk low: {st['free_gb']:.1f} GB free ({lv})", role, "critical"
            )
        if lv == "purge":
            purge(c)
    return lv


def purge(c: psycopg.Connection, n: int = 20) -> int:
    """Delete oldest unbuilt windows and lowest-score queued renders first."""
    rows = db.all_(
        c,
        """SELECT w.id, w.path FROM "window" w WHERE w.status IN ('extracted','requested') AND w.path IS NOT NULL
                         ORDER BY w.created_at LIMIT %s""",
        n,
    )
    for r in rows:
        files.delete_path(c, r["path"])
        c.execute("""UPDATE "window" SET status='expired' WHERE id=%s""", (r["id"],))
    rend = db.all_(
        c,
        """SELECT cv.id, cv.path FROM clip_version cv JOIN clip cl ON cl.id=cv.clip_id JOIN moment m ON m.id=cl.moment_id
                         WHERE cv.status IN ('rendered','gated') AND cv.path IS NOT NULL ORDER BY m.score LIMIT %s""",
        n,
    )
    for r in rend:
        files.delete_path(c, r["path"])
        c.execute("UPDATE clip_version SET status='media_deleted' WHERE id=%s", (r["id"],))
    return len(rows) + len(rend)
