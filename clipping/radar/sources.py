"""Platform clients for the radar and ingest: Twitch Helix, Kick public API, YouTube Data API.

All return normalized dicts so fakes (tests, missing keys) can stand in. Official APIs only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from clipping.core import settings
from clipping.core.http import request


@dataclass
class LiveStream:
    platform: str
    user_id: str
    login: str
    viewer_count: int
    language: str
    started_at: str
    title: str
    game_id: str
    stream_id: str


class LiveSource(Protocol):
    platform: str

    def resolve_game(self, names: list[str]) -> str | None: ...
    def live_streams(self, game_id: str) -> list[LiveStream]: ...


class _OAuthApp:
    token_url = ""

    def __init__(self, client_id: str, client_secret: str, client: httpx.Client | None = None):
        self.client_id, self.client_secret = client_id, client_secret
        self.http = client or httpx.Client(timeout=30)
        self._token: str | None = None
        self._exp = 0.0

    def token(self) -> str:
        if not self._token or time.time() > self._exp - 300:
            r = request(
                self.http,
                "POST",
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
            )
            d = r.json()
            self._token, self._exp = d["access_token"], time.time() + int(d.get("expires_in", 3600))
        return self._token


class TwitchHelix(_OAuthApp):
    platform = "twitch"
    token_url = "https://id.twitch.tv/oauth2/token"
    base = "https://api.twitch.tv/helix"

    @classmethod
    def from_env(cls) -> TwitchHelix | None:
        if not settings.has("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET"):
            return None
        return cls(settings.env("TWITCH_CLIENT_ID"), settings.env("TWITCH_CLIENT_SECRET"))

    def get(self, path: str, params: Any) -> dict:
        r = request(
            self.http,
            "GET",
            f"{self.base}/{path}",
            params=params,
            headers={"Client-ID": self.client_id, "Authorization": f"Bearer {self.token()}"},
        )
        return r.json()

    def paginate(self, path: str, params: dict, max_items: int = 10_000) -> list[dict]:
        out, cursor = [], None
        while len(out) < max_items:
            p = dict(params, first=100)
            if cursor:
                p["after"] = cursor
            d = self.get(path, p)
            out += d.get("data", [])
            cursor = (d.get("pagination") or {}).get("cursor")
            if not cursor or not d.get("data"):
                break
        return out[:max_items]

    def resolve_game(self, names: list[str]) -> str | None:
        for n in names:
            d = self.get("games", {"name": n}).get("data", [])
            if d:
                return d[0]["id"]
        for n in names:
            for g in self.get("search/categories", {"query": n}).get("data", []):
                if g["name"].lower() in [x.lower() for x in names]:
                    return g["id"]
        return None

    def live_streams(self, game_id: str) -> list[LiveStream]:
        return [
            LiveStream(
                "twitch",
                s["user_id"],
                s["user_login"],
                int(s["viewer_count"]),
                s.get("language") or "",
                s["started_at"],
                s.get("title", ""),
                s["game_id"],
                s["id"],
            )
            for s in self.paginate("streams", {"game_id": game_id})
        ]

    def clips(
        self,
        *,
        game_id: str | None = None,
        broadcaster_id: str | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
        max_items: int = 1000,
    ) -> list[dict]:
        p: dict = {}
        if game_id:
            p["game_id"] = game_id
        if broadcaster_id:
            p["broadcaster_id"] = broadcaster_id
        if started_at:
            p["started_at"] = started_at
        if ended_at:
            p["ended_at"] = ended_at
        return self.paginate("clips", p, max_items)

    def videos(self, ids: list[str]) -> list[dict]:
        out = []
        for i in range(0, len(ids), 100):
            out += self.get("videos", [("id", x) for x in ids[i : i + 100]]).get("data", [])
        return out

    def followers(self, broadcaster_id: str) -> int:
        return int(self.get("channels/followers", {"broadcaster_id": broadcaster_id}).get("total", 0))


class KickAPI(_OAuthApp):
    platform = "kick"
    token_url = "https://id.kick.com/oauth/token"
    base = "https://api.kick.com/public/v1"

    @classmethod
    def from_env(cls) -> KickAPI | None:
        if not settings.has("KICK_CLIENT_ID", "KICK_CLIENT_SECRET"):
            return None
        return cls(settings.env("KICK_CLIENT_ID"), settings.env("KICK_CLIENT_SECRET"))

    def get(self, path: str, params: Any) -> dict:
        return request(
            self.http,
            "GET",
            f"{self.base}/{path}",
            params=params,
            headers={"Authorization": f"Bearer {self.token()}"},
        ).json()

    def resolve_game(self, names: list[str]) -> str | None:
        for n in names:
            for cat in self.get("categories", {"q": n}).get("data", []):
                if cat["name"].lower() in [x.lower() for x in names]:
                    return str(cat["id"])
        return None

    def live_streams(self, game_id: str) -> list[LiveStream]:
        out, page = [], 1
        while True:
            d = self.get("livestreams", {"category_id": game_id, "limit": 100, "page": page}).get("data", [])
            for s in d:
                out.append(
                    LiveStream(
                        "kick",
                        str(s["broadcaster_user_id"]),
                        s.get("slug") or str(s["broadcaster_user_id"]),
                        int(s.get("viewer_count", 0)),
                        (s.get("language") or "")[:2],
                        s.get("started_at", ""),
                        s.get("stream_title", ""),
                        str(game_id),
                        str(s.get("channel_id", s["broadcaster_user_id"])),
                    )
                )
            if len(d) < 100 or page >= 50:
                return out
            page += 1


class YouTubeData:
    platform = "youtube"
    base = "https://www.googleapis.com/youtube/v3"

    def __init__(self, key: str, client: httpx.Client | None = None):
        self.key, self.http = key, client or httpx.Client(timeout=30)
        self.units_used = 0

    @classmethod
    def from_env(cls) -> YouTubeData | None:
        k = settings.env("YOUTUBE_API_KEY")
        return cls(k) if k else None

    def get(self, path: str, params: dict, cost: int) -> dict:
        self.units_used += cost
        return request(self.http, "GET", f"{self.base}/{path}", params=dict(params, key=self.key)).json()

    def search_uploads(
        self,
        query: str,
        published_after: str,
        language: str | None = None,
        max_pages: int = 1,
        event_type: str | None = None,
        duration: str | None = None,
    ) -> list[dict]:
        out, token = [], None
        for _ in range(max_pages):
            p = {
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": 50,
                "publishedAfter": published_after,
            }
            if language:
                p["relevanceLanguage"] = language
            if event_type:
                p["eventType"] = event_type
            if duration:
                p["videoDuration"] = duration
            if token:
                p["pageToken"] = token
            d = self.get("search", p, 100)
            out += d.get("items", [])
            token = d.get("nextPageToken")
            if not token:
                break
        return out

    def video_stats(self, ids: list[str]) -> list[dict]:
        out = []
        for i in range(0, len(ids), 50):
            out += self.get(
                "videos",
                {"part": "statistics,snippet,liveStreamingDetails", "id": ",".join(ids[i : i + 50])},
                1,
            ).get("items", [])
        return out


class FakeLiveSource:
    """In-memory stand-in for tests and keyless development."""

    def __init__(self, platform: str, game_id: str = "g1", streams: list[LiveStream] | None = None):
        self.platform, self.game_id, self.streams = platform, game_id, streams or []
        self.clip_list: list[dict] = []
        self.video_list: list[dict] = []

    def resolve_game(self, names: list[str]) -> str | None:
        return self.game_id

    def live_streams(self, game_id: str) -> list[LiveStream]:
        return [s for s in self.streams if s.game_id == game_id]

    def clips(self, **kw) -> list[dict]:
        b = kw.get("broadcaster_id")
        return [c for c in self.clip_list if not b or c.get("broadcaster_id") == b]

    def videos(self, ids: list[str]) -> list[dict]:
        return [v for v in self.video_list if v["id"] in ids]


def live_sources() -> list:
    return [s for s in (TwitchHelix.from_env(), KickAPI.from_env()) if s]
