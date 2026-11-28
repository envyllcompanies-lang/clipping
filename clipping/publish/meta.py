"""Meta connectors (doc 18): Instagram Reels, Facebook Reels (Pages), Threads — one Meta app.

Instagram and Threads pull the video from a public URL (temporary bucket copy, deleted once the container is
FINISHED); Facebook Reels use a hosted resumable upload. Only clips the gate marked as transformed reach here."""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Callable

import httpx

from clipping.core import settings
from clipping.publish.base import Payload, PermanentError, RateLimited, Result, TokenError, TransientError

GRAPH = "https://graph.facebook.com"
THREADS = "https://graph.threads.net"


def version() -> str:
    return settings.env("META_GRAPH_VERSION", "v21.0")


class _Graph:
    platform = ""
    needs_public_url = True

    def __init__(
        self, token: Callable[[dict], str], transport: httpx.BaseTransport | None = None, base: str = GRAPH
    ):
        self.token = token
        self.base = base
        self.http = httpx.Client(timeout=120, transport=transport)

    def url(self, path: str) -> str:
        return f"{self.base}/{version()}/{path.lstrip('/')}"

    def call(self, method: str, path: str, account: dict, **kw) -> dict:
        params = dict(kw.pop("params", {}) or {}, access_token=self.token(account))
        try:
            r = self.http.request(method, self.url(path), params=params, **kw)
        except httpx.TransportError as e:
            raise TransientError(str(e)) from e
        if r.status_code < 400:
            return r.json() if r.content else {}
        try:
            err = r.json().get("error", {})
        except ValueError:
            err = {}
        code = err.get("code")
        if code in (4, 17, 32, 613) or err.get("error_subcode") == 2207042:
            raise RateLimited(f"Meta rate limit ({code})", dt.datetime.now(dt.UTC) + dt.timedelta(hours=1))
        if code == 190 or r.status_code == 401:
            raise TokenError(f"Meta token: {err.get('message')}")
        if r.status_code >= 500 or err.get("is_transient"):
            raise TransientError(f"Meta {r.status_code}: {err.get('message')}")
        raise PermanentError(f"Meta {r.status_code} ({code}): {err.get('message')}")

    def delete(self, post_id: str, account: dict) -> bool:
        self.call("DELETE", post_id, account)
        return True

    def find_existing(self, payload: Payload) -> str | None:
        return None


class Instagram(_Graph):
    platform = "instagram"

    def prepare(self, clip: dict, account: dict) -> Payload:
        f = (clip.get("packaging") or {}).get("fields", {}).get("instagram", {})
        return Payload(
            "instagram",
            account,
            clip["path"],
            {"caption": f.get("caption", "")[:2200]},
            meta={"cv": clip["id"]},
        )

    def publish(self, payload: Payload, resume: str | None = None) -> Result:
        acc = payload.account
        uid = acc["platform_account_id"]
        if resume:  # container already created before a crash: poll it instead of creating another
            return self.check_container(resume, acc)
        d = self.call(
            "POST",
            f"{uid}/media",
            acc,
            data={
                "media_type": "REELS",
                "video_url": payload.public_url,
                "caption": payload.fields["caption"],
                "share_to_feed": "true",
            },
        )
        return Result("uploading", None, upload_session=d["id"])

    def check_container(self, container: str, acc: dict) -> Result:
        d = self.call("GET", container, acc, params={"fields": "status_code,status"})
        sc = d.get("status_code")
        if sc == "FINISHED":
            pub = self.call(
                "POST", f"{acc['platform_account_id']}/media_publish", acc, data={"creation_id": container}
            )
            return Result("live", pub["id"], upload_session=container)
        if sc in ("ERROR", "EXPIRED"):
            return Result("failed", None, error=f"container {sc}: {d.get('status')}")
        return Result("uploading", None, upload_session=container)

    def check(self, media_id: str, account: dict) -> Result:
        return Result("live", media_id)

    def remaining_quota(self, account: dict) -> int | None:
        d = self.call(
            "GET",
            f"{account['platform_account_id']}/content_publishing_limit",
            account,
            params={"fields": "config,quota_usage"},
        )
        data = (d.get("data") or [{}])[0]
        total = (data.get("config") or {}).get("quota_total", 50)
        return int(total) - int(data.get("quota_usage", 0))

    def stats(self, media_id: str, account: dict) -> dict:
        d = self.call(
            "GET",
            f"{media_id}/insights",
            account,
            params={"metric": "views,reach,likes,comments,saved,shares"},
        )
        vals = {m["name"]: (m.get("values") or [{}])[0].get("value", 0) for m in d.get("data", [])}
        return {
            "views": vals.get("views", 0),
            "likes": vals.get("likes", 0),
            "comments": vals.get("comments", 0),
            "saves": vals.get("saved", 0),
            "shares": vals.get("shares", 0),
        }

    def account_status(self, account: dict) -> dict:
        """Recommendation eligibility (originality rules): read from the account's status where the API exposes it."""
        try:
            d = self.call("GET", account["platform_account_id"], account, params={"fields": "id,username"})
            return {"restricted": False, "username": d.get("username")}
        except PermanentError:
            return {"restricted": None}


class Threads(_Graph):
    platform = "threads"

    def __init__(self, token, transport=None):
        super().__init__(token, transport, THREADS)

    def url(self, path: str) -> str:
        return f"{self.base}/v1.0/{path.lstrip('/')}"

    def prepare(self, clip: dict, account: dict) -> Payload:
        f = (clip.get("packaging") or {}).get("fields", {}).get("threads", {})
        text = f.get("text", "")
        if f.get("topic_tag"):
            text = f"{text} {f['topic_tag']}"  # one topic tag per post through the API
        return Payload("threads", account, clip["path"], {"text": text[:500]}, meta={"cv": clip["id"]})

    def publish(self, payload: Payload, resume: str | None = None) -> Result:
        acc = payload.account
        if resume:
            return self.check_container(resume, acc)
        d = self.call(
            "POST",
            f"{acc['platform_account_id']}/threads",
            acc,
            data={"media_type": "VIDEO", "video_url": payload.public_url, "text": payload.fields["text"]},
        )
        return Result("uploading", None, upload_session=d["id"])

    def check_container(self, container: str, acc: dict) -> Result:
        d = self.call("GET", container, acc, params={"fields": "status,error_message"})
        if d.get("status") == "FINISHED":
            pub = self.call(
                "POST", f"{acc['platform_account_id']}/threads_publish", acc, data={"creation_id": container}
            )
            return Result("live", pub["id"], upload_session=container)
        if d.get("status") in ("ERROR", "EXPIRED"):
            return Result("failed", None, error=d.get("error_message") or d.get("status"))
        return Result("uploading", None, upload_session=container)

    def check(self, post_id: str, account: dict) -> Result:
        return Result("live", post_id)

    def remaining_quota(self, account: dict) -> int | None:
        d = self.call(
            "GET",
            f"{account['platform_account_id']}/threads_publishing_limit",
            account,
            params={"fields": "quota_usage,config"},
        )
        data = (d.get("data") or [{}])[0]
        return int((data.get("config") or {}).get("quota_total", 250)) - int(data.get("quota_usage", 0))

    def stats(self, post_id: str, account: dict) -> dict:
        d = self.call("GET", f"{post_id}/insights", account, params={"metric": "views,likes,replies,reposts"})
        vals = {m["name"]: (m.get("values") or [{}])[0].get("value", 0) for m in d.get("data", [])}
        return {
            "views": vals.get("views", 0),
            "likes": vals.get("likes", 0),
            "comments": vals.get("replies", 0),
            "shares": vals.get("reposts", 0),
        }


class Facebook(_Graph):
    platform = "facebook"
    needs_public_url = False

    def prepare(self, clip: dict, account: dict) -> Payload:
        f = (clip.get("packaging") or {}).get("fields", {}).get("facebook", {})
        return Payload(
            "facebook",
            account,
            clip["path"],
            {"description": f.get("description", "")},
            meta={"cv": clip["id"]},
        )

    def publish(self, payload: Payload, resume: str | None = None) -> Result:
        acc = payload.account
        page = acc["platform_account_id"]
        vid = resume
        if not vid:
            d = self.call("POST", f"{page}/video_reels", acc, data={"upload_phase": "start"})
            vid = d["video_id"]
            upload_url = d.get("upload_url") or f"https://rupload.facebook.com/video-upload/{version()}/{vid}"
            size = os.path.getsize(payload.file_path)
            with open(payload.file_path, "rb") as fh:
                try:
                    r = self.http.post(
                        upload_url,
                        content=fh.read(),
                        headers={
                            "Authorization": f"OAuth {self.token(acc)}",
                            "offset": "0",
                            "file_size": str(size),
                        },
                    )
                except httpx.TransportError as e:
                    raise TransientError(str(e)) from e
            if r.status_code >= 400:
                raise (
                    TransientError(f"FB upload {r.status_code}")
                    if r.status_code >= 500
                    else PermanentError(f"FB upload {r.status_code}: {r.text[:200]}")
                )
        self.call(
            "POST",
            f"{page}/video_reels",
            acc,
            data={
                "upload_phase": "finish",
                "video_id": vid,
                "video_state": "PUBLISHED",
                "description": payload.fields["description"],
            },
        )
        return Result("processing", vid, upload_session=vid)

    def check(self, video_id: str, account: dict) -> Result:
        d = self.call("GET", video_id, account, params={"fields": "status"})
        st = d.get("status", {})
        if (
            st.get("video_status") == "ready"
            or (st.get("publishing_phase") or {}).get("status") == "complete"
        ):
            return Result("live", video_id)
        if st.get("video_status") == "error":
            return Result("failed", video_id, error=str(st))
        return Result("processing", video_id)

    def remaining_quota(self, account: dict) -> int | None:
        return None  # 30 per Page per 24 h, tracked locally

    def stats(self, video_id: str, account: dict) -> dict:
        d = self.call("GET", f"{video_id}/video_insights", account)
        vals = {m["name"]: (m.get("values") or [{}])[0].get("value", 0) for m in d.get("data", [])}
        return {
            "views": vals.get("blue_reels_play_count", vals.get("total_video_views", 0)),
            "likes": vals.get("post_video_likes_by_reaction_type", {}).get("REACTION_LIKE", 0)
            if isinstance(vals.get("post_video_likes_by_reaction_type"), dict)
            else 0,
        }
