"""YouTube Shorts connector (doc 17), behind the standard adapter interface.

Upload: the built-in resumable videos.insert uploader below. The owner's previous uploader (@EnvyCarsLLC) is kept in
legacy/youtube-uploader/ as a reference only; it uses the same approach (OAuth refresh + resumable videos.insert),
which this adapter already implements with retries, quota mapping and per-channel tokens from the credential store.
It is never imported: the script loads its own .env and needs packages the pipeline doesn't."""

from __future__ import annotations

import datetime as dt
import os
import zoneinfo
from collections.abc import Callable

import httpx

from clipping.publish.base import Payload, PermanentError, QuotaExceeded, Result, TokenError, TransientError

API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
CHUNK = 8 * 1024 * 1024


def _midnight_pacific() -> dt.datetime:
    pt = zoneinfo.ZoneInfo("America/Los_Angeles")
    now = dt.datetime.now(pt)
    return (now + dt.timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0).astimezone(dt.UTC)


class YouTube:
    platform = "youtube"
    needs_public_url = False

    def __init__(self, token: Callable[[dict], str], transport: httpx.BaseTransport | None = None):
        self.token = token
        self.http = httpx.Client(timeout=120, transport=transport)

    def _h(self, acc: dict) -> dict:
        return {"Authorization": f"Bearer {self.token(acc)}"}

    def _raise(self, r: httpx.Response) -> None:
        if r.status_code < 400:
            return
        try:
            reason = r.json()["error"]["errors"][0]["reason"]
        except (ValueError, KeyError, IndexError, TypeError):
            reason = ""
        if reason == "quotaExceeded":
            raise QuotaExceeded("YouTube project quota used", _midnight_pacific(), scope="project")
        if reason == "uploadLimitExceeded":
            raise QuotaExceeded("channel upload limit", dt.datetime.now(dt.UTC) + dt.timedelta(hours=24))
        if r.status_code == 401 or "invalid_grant" in r.text:
            raise TokenError("YouTube token invalid")
        if r.status_code >= 500 or r.status_code == 429:
            raise TransientError(f"YouTube {r.status_code}")
        raise PermanentError(f"YouTube {r.status_code}: {reason or r.text[:200]}")

    def prepare(self, clip: dict, account: dict) -> Payload:
        f = (clip.get("packaging") or {}).get("fields", {}).get("youtube", {})
        lang = clip.get("language", "en")
        private = account.get("mode") == "fallback"  # unaudited project: uploads are locked private anyway
        body = {
            "snippet": {
                "title": f.get("title", "")[:100],
                "description": f.get("description", ""),
                "tags": f.get("tags", []) + [f"cv{clip['id']}"],
                "categoryId": "20",
                "defaultLanguage": lang,
                "defaultAudioLanguage": lang,
            },
            "status": {
                "privacyStatus": "private" if private else "public",
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": False,
            },
        }
        return Payload("youtube", account, clip["path"], body, meta={"cv": clip["id"], "private": private})

    def publish(self, payload: Payload, resume: str | None = None) -> Result:
        acc = payload.account
        size = os.path.getsize(payload.file_path)
        session = resume
        offset = 0
        if session:
            r = self.http.put(session, headers={**self._h(acc), "Content-Range": f"bytes */{size}"})
            if r.status_code in (200, 201):
                return Result(
                    "processing",
                    r.json()["id"],
                    fallback="publish_private" if payload.meta["private"] else None,
                )
            if r.status_code == 308:
                rng = r.headers.get("Range")
                offset = int(rng.split("-")[1]) + 1 if rng else 0
            else:
                session = None
        if not session:
            r = self.http.post(
                UPLOAD,
                params={"uploadType": "resumable", "part": "snippet,status"},
                json=payload.fields,
                headers={
                    **self._h(acc),
                    "X-Upload-Content-Type": "video/mp4",
                    "X-Upload-Content-Length": str(size),
                },
            )
            self._raise(r)
            session = r.headers["Location"]
        with open(payload.file_path, "rb") as fh:
            fh.seek(offset)
            while offset < size:
                chunk = fh.read(CHUNK)
                end = offset + len(chunk) - 1
                try:
                    r = self.http.put(
                        session,
                        content=chunk,
                        headers={**self._h(acc), "Content-Range": f"bytes {offset}-{end}/{size}"},
                    )
                except httpx.TransportError as e:
                    raise TransientError(f"chunk upload: {e}") from e
                if r.status_code == 308:
                    offset = end + 1
                    continue
                if r.status_code in (200, 201):
                    return Result(
                        "processing",
                        r.json()["id"],
                        upload_session=session,
                        fallback="publish_private" if payload.meta["private"] else None,
                    )
                if r.status_code >= 500:
                    e = TransientError(f"upload {r.status_code}")
                    e.session = session
                    raise e
                self._raise(r)
        raise TransientError("upload ended without a video id")

    def check(self, video_id: str, account: dict) -> Result:
        r = self.http.get(
            f"{API}/videos",
            params={"part": "status,processingDetails", "id": video_id},
            headers=self._h(account),
        )
        self._raise(r)
        items = r.json().get("items", [])
        if not items:
            return Result("failed", video_id, error="video not found")
        st = items[0]["status"]
        if st.get("uploadStatus") == "rejected":
            return Result("failed", video_id, error=f"rejected: {st.get('rejectionReason')}")
        if st.get("uploadStatus") == "failed":
            return Result("failed", video_id, error=f"failed: {st.get('failureReason')}")
        proc = items[0].get("processingDetails", {}).get("processingStatus", "succeeded")
        if proc == "succeeded" or st.get("uploadStatus") == "processed":
            return Result("live", video_id)
        if proc == "failed":
            return Result("failed", video_id, error="processing failed")
        return Result("processing", video_id)

    def remaining_quota(self, account: dict) -> int | None:
        return None  # no endpoint: tracked locally (100 uploads/day per project)

    def delete(self, video_id: str, account: dict) -> bool:
        r = self.http.delete(f"{API}/videos", params={"id": video_id}, headers=self._h(account))
        if r.status_code == 404:
            return True
        self._raise(r)
        return True

    def find_existing(self, payload: Payload) -> str | None:
        acc = payload.account
        r = self.http.get(
            f"{API}/channels", params={"part": "contentDetails", "mine": "true"}, headers=self._h(acc)
        )
        self._raise(r)
        items = r.json().get("items", [])
        if not items:
            return None
        uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        r = self.http.get(
            f"{API}/playlistItems",
            params={"part": "contentDetails", "playlistId": uploads, "maxResults": 10},
            headers=self._h(acc),
        )
        self._raise(r)
        ids = [i["contentDetails"]["videoId"] for i in r.json().get("items", [])]
        if not ids:
            return None
        r = self.http.get(
            f"{API}/videos", params={"part": "snippet", "id": ",".join(ids)}, headers=self._h(acc)
        )
        self._raise(r)
        marker = f"cv{payload.meta['cv']}"
        for v in r.json().get("items", []):
            if marker in v["snippet"].get("tags", []):
                return v["id"]
        return None

    def stats(self, video_id: str, account: dict) -> dict:
        r = self.http.get(
            f"{API}/videos", params={"part": "statistics", "id": video_id}, headers=self._h(account)
        )
        self._raise(r)
        s = (r.json().get("items") or [{}])[0].get("statistics", {})
        out = {
            "views": int(s.get("viewCount", 0)),
            "likes": int(s.get("likeCount", 0)),
            "comments": int(s.get("commentCount", 0)),
        }
        try:
            today = dt.date.today().isoformat()
            a = self.http.get(
                ANALYTICS,
                params={
                    "ids": "channel==MINE",
                    "startDate": "2026-01-01",
                    "endDate": today,
                    "metrics": "averageViewPercentage",
                    "filters": f"video=={video_id}",
                },
                headers=self._h(account),
            )
            if a.status_code == 200 and a.json().get("rows"):
                out["retention"] = float(a.json()["rows"][0][0]) / 100
        except httpx.HTTPError:
            pass
        return out
