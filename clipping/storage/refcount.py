"""Refcount for rendered clips (doc 21): delete media when every target post is live or failed_permanent."""

from __future__ import annotations

import psycopg

from clipping.core import db
from clipping.storage import bucket, files

FINAL = ("live", "failed_permanent", "cancelled")


def set_pending(c: psycopg.Connection, clip_version_id: int, n: int) -> None:
    c.execute("UPDATE clip_version SET pending_posts=%s WHERE id=%s", (n, clip_version_id))


def post_finished(c: psycopg.Connection, clip_version_id: int) -> int:
    """Atomically decrement; at zero delete the file + bucket copies and mark media_deleted. Returns remaining."""
    left = db.scalar(c, """UPDATE clip_version SET pending_posts=GREATEST(pending_posts-1,0) WHERE id=%s
                           RETURNING pending_posts""", clip_version_id)
    if left == 0:
        release_media(c, clip_version_id)
    return left


def recount(c: psycopg.Connection, clip_version_id: int) -> int:
    left = db.scalar(c, "SELECT count(*) FROM post WHERE clip_version_id=%s AND status <> ALL(%s)", clip_version_id, list(FINAL))
    c.execute("UPDATE clip_version SET pending_posts=%s WHERE id=%s", (left, clip_version_id))
    if left == 0 and db.scalar(c, "SELECT count(*) FROM post WHERE clip_version_id=%s", clip_version_id):
        release_media(c, clip_version_id)
    return left


def release_media(c: psycopg.Connection, clip_version_id: int) -> None:
    cv = db.one(c, "SELECT path FROM clip_version WHERE id=%s", clip_version_id)
    if cv and cv["path"]:
        files.delete_path(c, cv["path"])
    bucket.delete_for(c, clip_version_id)
    c.execute("UPDATE clip_version SET status='media_deleted' WHERE id=%s", (clip_version_id,))
