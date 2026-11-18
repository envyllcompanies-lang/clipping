"""In-memory fakes of the six platform APIs (httpx.MockTransport) for connector tests and the publishing backtest.
Behaviour follows each platform's documented flow; failure injection covers 5xx, rate limits, quota, crashes."""

from __future__ import annotations

import itertools
import json
import re
import urllib.parse

import httpx


class FakePlatforms:
    def __init__(self):
        self.ids = itertools.count(1000)
        self.yt_sessions: dict[str, dict] = {}
        self.yt_videos: dict[str, dict] = {}
        self.ig_containers: dict[str, dict] = {}
        self.posts: dict[str, list] = {
            p: [] for p in ("youtube", "instagram", "facebook", "threads", "tiktok", "snapchat")
        }
        self.tt: dict[str, dict] = {}
        self.snap_media: dict[str, dict] = {}
        self.fail_next: dict[str, list[int]] = {}  # route key -> status codes to return next
        self.audited_tiktok = False
        self.container_polls_before_finish = 1
        self.deleted: list[str] = []
        self.calls: list[str] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def _inject(self, key: str):
        q = self.fail_next.get(key)
        if q:
            code = q.pop(0)
            body = {
                "error": {
                    "code": 613 if code == 400 else code,
                    "message": "injected",
                    "errors": [{"reason": "backendError"}],
                }
            }
            if code == 403:
                body = {"error": {"errors": [{"reason": "quotaExceeded"}], "message": "quota"}}
            return httpx.Response(code, json=body)
        return None

    def handle(self, req: httpx.Request) -> httpx.Response:
        u = req.url
        host, path = u.host, u.path
        self.calls.append(f"{req.method} {host}{path}")
        q = dict(urllib.parse.parse_qsl(u.query.decode()))
        body = {}
        if req.content and req.headers.get("content-type", "").startswith(("application/json",)):
            body = json.loads(req.content)
        elif req.content and "x-www-form-urlencoded" in req.headers.get("content-type", ""):
            body = dict(urllib.parse.parse_qsl(req.content.decode()))
        # ---- YouTube
        if host == "www.googleapis.com" and path == "/upload/youtube/v3/videos" and req.method == "POST":
            if r := self._inject("yt_init"):
                return r
            sid = f"https://upload.example/session/{next(self.ids)}"
            self.yt_sessions[sid] = {
                "meta": body,
                "size": int(req.headers["X-Upload-Content-Length"]),
                "got": 0,
            }
            return httpx.Response(200, headers={"Location": sid})
        if host == "upload.example":
            s = self.yt_sessions[str(u)]
            cr = req.headers.get("Content-Range", "")
            if cr.startswith("bytes */"):
                if s["got"] >= s["size"]:
                    return httpx.Response(200, json={"id": s["vid"]})
                return httpx.Response(308, headers={"Range": f"bytes=0-{s['got'] - 1}"} if s["got"] else {})
            if r := self._inject("yt_chunk"):
                return r
            m = re.match(r"bytes (\d+)-(\d+)/(\d+)", cr)
            s["got"] = int(m.group(2)) + 1
            if s["got"] >= s["size"]:
                vid = f"yt{next(self.ids)}"
                s["vid"] = vid
                self.yt_videos[vid] = {"meta": s["meta"], "polls": 0}
                self.posts["youtube"].append(vid)
                return httpx.Response(200, json={"id": vid})
            return httpx.Response(308, headers={"Range": f"bytes=0-{s['got'] - 1}"})
        if host == "www.googleapis.com" and path == "/youtube/v3/videos" and req.method == "GET":
            ids = q.get("id", "").split(",")
            items = []
            for vid in ids:
                v = self.yt_videos.get(vid)
                if not v:
                    continue
                v["polls"] += 1
                items.append(
                    {
                        "id": vid,
                        "status": {
                            "uploadStatus": "processed" if v["polls"] > 1 else "uploaded",
                            "privacyStatus": v["meta"]["status"]["privacyStatus"],
                        },
                        "processingDetails": {
                            "processingStatus": "succeeded" if v["polls"] > 1 else "processing"
                        },
                        "snippet": v["meta"]["snippet"],
                        "statistics": {"viewCount": "1234", "likeCount": "56", "commentCount": "7"},
                    }
                )
            return httpx.Response(200, json={"items": items})
        if host == "www.googleapis.com" and path == "/youtube/v3/videos" and req.method == "DELETE":
            self.deleted.append(q["id"])
            self.yt_videos.pop(q["id"], None)
            return httpx.Response(204)
        if host == "www.googleapis.com" and path == "/youtube/v3/channels":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "UC1",
                            "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}},
                            "snippet": {"title": "Brand", "customUrl": "@gta6clips.en"},
                        }
                    ]
                },
            )
        if host == "www.googleapis.com" and path == "/youtube/v3/playlistItems":
            return httpx.Response(
                200, json={"items": [{"contentDetails": {"videoId": v}} for v in list(self.yt_videos)[-10:]]}
            )
        if host == "youtubeanalytics.googleapis.com":
            return httpx.Response(200, json={"rows": [[48.5]]})
        # ---- Meta (Instagram / Facebook) and Threads
        if host in ("graph.facebook.com", "graph.threads.net"):
            if r := self._inject(f"meta:{path}"):
                return r
            parts = path.strip("/").split("/")[1:]
            if len(parts) == 2 and parts[1] in ("media", "threads") and req.method == "POST":
                cid = f"c{next(self.ids)}"
                self.ig_containers[cid] = {"polls": 0, "kind": parts[1], "body": body}
                return httpx.Response(200, json={"id": cid})
            if len(parts) == 1 and parts[0] in self.ig_containers and req.method == "GET":
                ct = self.ig_containers[parts[0]]
                ct["polls"] += 1
                done = ct["polls"] > self.container_polls_before_finish
                return httpx.Response(
                    200,
                    json={
                        "status_code": "FINISHED" if done else "IN_PROGRESS",
                        "status": "FINISHED" if done else "IN_PROGRESS",
                    },
                )
            if len(parts) == 2 and parts[1] in ("media_publish", "threads_publish"):
                pid = f"m{next(self.ids)}"
                self.posts["instagram" if parts[1] == "media_publish" else "threads"].append(pid)
                return httpx.Response(200, json={"id": pid})
            if len(parts) == 2 and parts[1] == "video_reels":
                if body.get("upload_phase") == "start":
                    vid = f"fb{next(self.ids)}"
                    return httpx.Response(
                        200, json={"video_id": vid, "upload_url": f"https://rupload.facebook.com/x/{vid}"}
                    )
                self.posts["facebook"].append(body["video_id"])
                return httpx.Response(200, json={"success": True})
            if len(parts) == 2 and parts[1] in ("content_publishing_limit", "threads_publishing_limit"):
                return httpx.Response(200, json={"data": [{"config": {"quota_total": 50}, "quota_usage": 3}]})
            if len(parts) == 2 and parts[1] in ("insights", "video_insights"):
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {"name": "views", "values": [{"value": 900}]},
                            {"name": "likes", "values": [{"value": 40}]},
                        ]
                    },
                )
            if len(parts) == 1 and parts[0].startswith("fb") and req.method == "GET":
                return httpx.Response(200, json={"status": {"video_status": "ready"}})
            if req.method == "DELETE":
                self.deleted.append(parts[0])
                return httpx.Response(200, json={"success": True})
            return httpx.Response(200, json={"id": parts[0] if parts else "x", "username": "brand"})
        if host == "rupload.facebook.com":
            return httpx.Response(200, json={"success": True})
        # ---- TikTok
        if host == "open.tiktokapis.com":
            if r := self._inject(f"tt:{path}"):
                return r
            if path.endswith("/creator_info/query/"):
                opts = (
                    ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"]
                    if self.audited_tiktok
                    else ["SELF_ONLY"]
                )
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "creator_nickname": "Brand",
                            "nickname": "Brand",
                            "privacy_level_options": opts,
                            "comment_disabled": False,
                            "duet_disabled": False,
                            "stitch_disabled": False,
                            "max_video_post_duration_sec": 600,
                        },
                        "error": {"code": "ok"},
                    },
                )
            if path.endswith("/video/init/"):
                if (
                    "inbox" not in path
                    and not self.audited_tiktok
                    and body.get("post_info", {}).get("privacy_level") != "SELF_ONLY"
                ):
                    return httpx.Response(
                        403, json={"error": {"code": "unaudited_client_can_only_post_to_private_accounts"}}
                    )
                pid = f"p{next(self.ids)}"
                self.tt[pid] = {"inbox": "inbox" in path, "polls": 0}
                return httpx.Response(
                    200,
                    json={
                        "data": {"publish_id": pid, "upload_url": f"https://upload.tiktok.example/{pid}"},
                        "error": {"code": "ok"},
                    },
                )
            if path.endswith("/status/fetch/"):
                t = self.tt[body["publish_id"]]
                t["polls"] += 1
                if t["polls"] < 2:
                    st = "PROCESSING_UPLOAD"
                else:
                    st = "SEND_TO_USER_INBOX" if t["inbox"] else "PUBLISH_COMPLETE"
                    if body["publish_id"] not in self.posts["tiktok"]:
                        self.posts["tiktok"].append(body["publish_id"])
                return httpx.Response(
                    200,
                    json={
                        "data": {"status": st, "publicaly_available_post_id": [int(body["publish_id"][1:])]},
                        "error": {"code": "ok"},
                    },
                )
            if path.startswith("/v2/video/query/"):
                return httpx.Response(
                    200,
                    json={
                        "data": {"videos": [{"view_count": 5000, "like_count": 300}]},
                        "error": {"code": "ok"},
                    },
                )
        if host == "upload.tiktok.example":
            return httpx.Response(201)
        # ---- Snapchat
        if host == "businessapi.snapchat.com":
            if path.endswith("/media") and req.method == "POST":
                mid = f"sm{next(self.ids)}"
                self.snap_media[mid] = {"parts": 0, "key": body["key"]}
                return httpx.Response(200, json={"media_id": mid})
            if "multipart-upload" in path:
                if q.get("action") == "UPLOAD_PART":
                    self.snap_media[path.split("/")[-2]]["parts"] += 1
                return httpx.Response(200, json={})
            if path.endswith("/spotlights") and req.method == "POST":
                sid = f"sp{next(self.ids)}"
                self.posts["snapchat"].append(sid)
                return httpx.Response(200, json={"id": sid})
            if "/spotlights/" in path:
                return httpx.Response(200, json={"status": "PUBLISHED", "views": 777})
        return httpx.Response(404, json={"error": {"message": f"fake: no route {req.method} {host}{path}"}})
