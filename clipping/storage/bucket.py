"""Short-lived object storage for window transfer and public URLs (docs 21, 25).

S3-compatible when BUCKET_* is set; otherwise a local folder served by the dashboard at /public/<token>.
Public copies use unguessable names and are deleted once platforms finish processing.
"""

from __future__ import annotations

import datetime as dt
import secrets
import shutil
from pathlib import Path

import psycopg

from clipping.core import db, settings
from clipping.storage import files


def _s3():
    import boto3  # optional dependency, only when a real bucket is configured

    return boto3.client("s3", endpoint_url=settings.env("BUCKET_ENDPOINT"),
                        aws_access_key_id=settings.env("BUCKET_ACCESS_KEY"), aws_secret_access_key=settings.env("BUCKET_SECRET_KEY"))


def use_s3() -> bool:
    return settings.has("BUCKET_ENDPOINT", "BUCKET_NAME", "BUCKET_ACCESS_KEY", "BUCKET_SECRET_KEY")


def public_base() -> str:
    return settings.env("PUBLIC_BASE_URL", "http://localhost:8000/public")


def put_public(c: psycopg.Connection, src: str | Path, clip_version_id: int, ttl_h: float = 24) -> str:
    name = f"{secrets.token_urlsafe(24)}{Path(src).suffix}"
    exp = dt.datetime.now(dt.UTC) + dt.timedelta(hours=ttl_h)
    if use_s3():
        _s3().upload_file(str(src), settings.env("BUCKET_NAME"), name, ExtraArgs={"ContentType": "video/mp4"})
        url = _s3().generate_presigned_url("get_object", Params={"Bucket": settings.env("BUCKET_NAME"), "Key": name},
                                           ExpiresIn=int(ttl_h * 3600))
        c.execute("""INSERT INTO file(path,kind,size,owner_type,owner_id,expires_at) VALUES (%s,'public',%s,'clip_version',%s,%s)""",
                  (f"s3://{name}", Path(src).stat().st_size, clip_version_id, exp))
        return url
    dst = files.managed("public") / name
    shutil.copyfile(src, dst)
    files.register(c, dst, "public", "clip_version", clip_version_id, expires_at=exp)
    return f"{public_base()}/{name}"


def delete_for(c: psycopg.Connection, clip_version_id: int) -> int:
    rows = db.all_(c, "SELECT path FROM file WHERE kind='public' AND owner_type='clip_version' AND owner_id=%s AND deleted_at IS NULL",
                   clip_version_id)
    for r in rows:
        delete_public(c, r["path"])
    return len(rows)


def delete_public(c: psycopg.Connection, path: str) -> None:
    if path.startswith("s3://"):
        _s3().delete_object(Bucket=settings.env("BUCKET_NAME"), Key=path[5:])
        c.execute("UPDATE file SET deleted_at=now() WHERE path=%s", (path,))
    else:
        files.delete_path(c, path)


def delete_by_url(c: psycopg.Connection, url: str) -> None:
    name = url.split("?")[0].rsplit("/", 1)[-1]
    for r in db.all_(c, "SELECT path FROM file WHERE kind='public' AND deleted_at IS NULL AND path LIKE %s", f"%{name}"):
        delete_public(c, r["path"])
