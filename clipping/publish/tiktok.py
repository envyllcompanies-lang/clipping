"""TikTok connector (doc 19): Content Posting API. Direct Post with FILE_UPLOAD (no verified domain needed), or the
creator's inbox as a draft while the app is unaudited (fallback: the owner taps Post in the TikTok app).
The creator info query runs before every post; the posting UI respects its values (audit requirement)."""

from __future__ import annotations

import datetime as dt
import math
import os
from collections.abc import Callable

import httpx

from clipping.publish.base import (
    Payload,
    PermanentError,
    QuotaExceeded,
    RateLimited,
    Result,
    TokenError,
    TransientError,
)

API = "https://open.tiktokapis.com/v2"
CHUNK = 10 * 1024 * 1024


class TikTok:
    platform = "tiktok"
    needs_public_url = False

    def __init__(self, token: Callable[[dict], str], transport: httpx.BaseTransport | None = None):
        self.token = token
        self.http = httpx.Client(timeout=120, transport=transport)

    def _post(self, path: str, acc: dict, body: dict) -> dict:
        try:
            r = self.http.post(
                f"{API}/{path}",
                json=body,
                headers={
                    "Authorization": f"Bearer {self.token(acc)}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
            )
        except httpx.TransportError as e:
            raise TransientError(str(e)) from e
        d = r.json() if r.content else {}
        err = str((d.get("error") or {}).get("code", "ok"))
        if err == "ok" and r.status_code < 400:
            return d.get("data", {})
        if err in ("access_token_invalid", "scope_not_authorized") or r.status_code == 401:
            raise TokenError(f"TikTok {err}")
        if err == "rate_limit_exceeded" or r.status_code == 429:
            raise RateLimited("TikTok rate limit", dt.datetime.now(dt.UTC) + dt.timedelta(minutes=2))
        if err == "spam_risk_too_many_posts":
            raise QuotaExceeded("TikTok daily cap", dt.datetime.now(dt.UTC) + dt.timedelta(hours=24))
        if err == "spam_risk_user_banned_from_posting" or err.startswith("spam_risk"):
            raise QuotaExceeded(
                f"TikTok spam/risk flag ({err}): pausing account",
                dt.datetime.now(dt.UTC) + dt.timedelta(hours=36),
            )
        if err == "unaudited_client_can_only_post_to_private_accounts":
            raise _Unaudited(err)
        if r.status_code >= 500:
            raise TransientError(f"TikTok {r.status_code} {err}")
        raise PermanentError(f"TikTok {err}: {(d.get('error') or {}).get('message', '')}")

    def creator_info(self, acc: dict) -> dict:
        return self._post("post/publish/creator_info/query/", acc, {})

    def prepare(self, clip: dict, account: dict) -> Payload:
        f = (clip.get("packaging") or {}).get("fields", {}).get("tiktok", {})
        return Payload(
            "tiktok",
            account,
            clip["path"],
            {"title": f.get("caption", "")[:2200]},
            meta={
                "cv": clip["id"],
                "duration": clip.get("duration_s") or 0,
                "manual": clip.get("manual_post_info"),
            },
        )

    def _source(self, path: str) -> dict:
        size = os.path.getsize(path)
        chunk = min(CHUNK, size)
        return {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk,
            "total_chunk_count": max(1, size // chunk),
        }

    def _upload(self, url: str, path: str) -> None:
        size = os.path.getsize(path)
        chunk = min(CHUNK, size)
        n = max(1, size // chunk)
        with open(path, "rb") as fh:
            for i in range(n):
                start = i * chunk
                end = size - 1 if i == n - 1 else start + chunk - 1
                fh.seek(start)
                data = fh.read(end - start + 1)
                try:
                    r = self.http.put(
                        url,
                        content=data,
                        headers={"Content-Type": "video/mp4", "Content-Range": f"bytes {start}-{end}/{size}"},
                    )
                except httpx.TransportError as e:
                    raise TransientError(str(e)) from e
                if r.status_code >= 500:
                    raise TransientError(f"TikTok chunk {r.status_code}")
                if r.status_code >= 400:
                    raise PermanentError(f"TikTok chunk {r.status_code}")

    def publish(self, payload: Payload, resume: str | None = None) -> Result:
        acc = payload.account
        if resume:
            return self.check(resume, acc)
        info = self.creator_info(acc)
        max_s = info.get("max_video_post_duration_sec", 600)
        if payload.meta["duration"] and payload.meta["duration"] > max_s:
            raise PermanentError(f"video {payload.meta['duration']:.0f}s over this creator's max {max_s}s")
        manual = payload.meta.get("manual") or {}
        opts = info.get("privacy_level_options", ["SELF_ONLY"])
        if acc.get("mode") == "fallback" or (opts == ["SELF_ONLY"] and not manual):
            # unaudited app: a direct post could only be private, so send a draft the owner publishes with one tap
            d = self._post(
                "post/publish/inbox/video/init/", acc, {"source_info": self._source(payload.file_path)}
            )
            self._upload(d["upload_url"], payload.file_path)
            return Result(
                "processing", d["publish_id"], upload_session=d["publish_id"], fallback="inbox_draft"
            )
        privacy = manual.get("privacy_level") or (
            "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in opts else opts[0]
        )
        if privacy not in opts:
            raise PermanentError(f"privacy {privacy} not allowed for this creator ({opts})")
        post_info = {
            "title": manual.get("title", payload.fields["title"]),
            "privacy_level": privacy,
            "disable_comment": bool(manual.get("disable_comment", info.get("comment_disabled", False))),
            "disable_duet": bool(manual.get("disable_duet", info.get("duet_disabled", False))),
            "disable_stitch": bool(manual.get("disable_stitch", info.get("stitch_disabled", False))),
            "video_cover_timestamp_ms": 1000,
            "brand_content_toggle": bool(manual.get("brand_content_toggle", False)),
        }
        try:
            d = self._post(
                "post/publish/video/init/",
                acc,
                {"post_info": post_info, "source_info": self._source(payload.file_path)},
            )
        except _Unaudited:
            d = self._post(
                "post/publish/inbox/video/init/", acc, {"source_info": self._source(payload.file_path)}
            )
            self._upload(d["upload_url"], payload.file_path)
            return Result(
                "processing", d["publish_id"], upload_session=d["publish_id"], fallback="inbox_draft"
            )
        self._upload(d["upload_url"], payload.file_path)
        return Result("processing", d["publish_id"], upload_session=d["publish_id"])

    def check(self, publish_id: str, account: dict) -> Result:
        d = self._post("post/publish/status/fetch/", account, {"publish_id": publish_id})
        st = d.get("status")
        if st == "PUBLISH_COMPLETE":
            ids = d.get("publicaly_available_post_id") or d.get("publicly_available_post_id") or []
            return Result("live", str(ids[0]) if ids else publish_id)
        if st == "SEND_TO_USER_INBOX":
            return Result("live", publish_id, fallback="inbox_draft")
        if st == "FAILED":
            return Result("failed", publish_id, error=d.get("fail_reason"))
        return Result("processing", publish_id)

    def remaining_quota(self, account: dict) -> int | None:
        return None

    def delete(self, post_id: str, account: dict) -> bool:
        raise PermanentError("TikTok has no delete endpoint in the Content Posting API: delete in the app")

    def find_existing(self, payload: Payload) -> str | None:
        return None

    def stats(self, video_id: str, account: dict) -> dict:
        d = self._post(
            "video/query/?fields=id,view_count,like_count,comment_count,share_count",
            account,
            {"filters": {"video_ids": [video_id]}},
        )
        v = (d.get("videos") or [{}])[0]
        return {
            "views": v.get("view_count", 0),
            "likes": v.get("like_count", 0),
            "comments": v.get("comment_count", 0),
            "shares": v.get("share_count", 0),
        }


class _Unaudited(PermanentError):
    pass


def creator_info_for(c, account_id: int) -> dict:
    """Creator info for the posting screen; a clearly-labelled placeholder when no token is connected yet."""
    from clipping.core import db
    from clipping.publish import registry

    acc = db.one(c, "SELECT * FROM account WHERE id=%s", account_id)
    try:
        return registry.adapters(c)["tiktok"].creator_info(acc) | {"username": acc.get("handle") or ""}
    except Exception:  # noqa: BLE001 - not connected yet
        return {
            "nickname": "(not connected)",
            "username": acc.get("handle") or "",
            "privacy_level_options": ["SELF_ONLY"],
            "comment_disabled": False,
            "duet_disabled": False,
            "stitch_disabled": False,
            "max_video_post_duration_sec": 600,
        }


def queue_manual_post(c, clip_version_id: int, account_id: int, post_info: dict) -> int:
    """A user-initiated post from the posting screen (audit flow): scheduled now with the user's choices."""
    from clipping.core import db

    pid = db.scalar(
        c,
        """INSERT INTO post(clip_version_id,account_id,platform,scheduled_at,fields) VALUES (%s,%s,'tiktok',now(),%s)
                          ON CONFLICT (clip_version_id,account_id) DO UPDATE SET fields=EXCLUDED.fields RETURNING id""",
        clip_version_id,
        account_id,
        db.j({"manual_post_info": post_info}),
    )
    return pid


_ = math
