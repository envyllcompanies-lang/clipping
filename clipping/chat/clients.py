"""Live chat clients (doc 03). Read-only, always.

- Twitch: IRC over WebSocket, anonymous (justinfan) login; needs no per-channel permission for public chat.
- Kick: the Pusher WebSocket Kick's own site uses (unofficial; can change). Silence while live raises an alert.
- YouTube: chat-replay-downloader style polling is optional; quota-costing API avoided.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from clipping.core.crypto import hash_user

TWITCH_WS = "wss://irc-ws.chat.twitch.tv:443"
KICK_WS = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false"


@dataclass
class ChatEvent:
    received_at: float
    platform_ts: float | None
    user_hash: str
    text: str
    emote_ids: list[str]
    is_sub: bool
    is_mod: bool


def parse_twitch(line: str, now: float | None = None) -> ChatEvent | None:
    """Parse one IRCv3 PRIVMSG line with tags."""
    if "PRIVMSG" not in line:
        return None
    tags = {}
    rest = line
    if line.startswith("@"):
        raw, rest = line[1:].split(" ", 1)
        for kv in raw.split(";"):
            k, _, v = kv.partition("=")
            tags[k] = v
    try:
        prefix, _, msg = rest.partition(" PRIVMSG ")
        text = msg.split(" :", 1)[1]
    except IndexError:
        return None
    user = tags.get("user-id") or prefix.lstrip(":").split("!")[0]
    emotes = [e.split(":")[0] for e in tags.get("emotes", "").split("/") if e]
    ts = float(tags["tmi-sent-ts"]) / 1000 if tags.get("tmi-sent-ts", "").isdigit() else None
    badges = tags.get("badges", "")
    return ChatEvent(
        now or time.time(),
        ts,
        hash_user(user),
        text.rstrip("\r\n"),
        emotes,
        tags.get("subscriber") == "1",
        tags.get("mod") == "1" or "moderator" in badges,
    )


def parse_kick(frame: str, now: float | None = None) -> ChatEvent | None:
    try:
        d = json.loads(frame)
    except json.JSONDecodeError:
        return None
    if not str(d.get("event", "")).endswith("ChatMessageEvent"):
        return None
    data = json.loads(d["data"]) if isinstance(d.get("data"), str) else d.get("data", {})
    sender = data.get("sender", {})
    badges = [b.get("type") for b in sender.get("identity", {}).get("badges", [])]
    content = data.get("content", "")
    emotes = re.findall(r"\[emote:(\d+):[^\]]*\]", content)
    return ChatEvent(
        now or time.time(),
        None,
        hash_user(str(sender.get("id", ""))),
        content,
        emotes,
        "subscriber" in badges,
        "moderator" in badges,
    )


async def _backoff(attempt: int) -> None:
    await asyncio.sleep(min(60, 2**attempt) * (0.5 + random.random() / 2))


async def twitch_stream(channel: str, on_gap: Callable[[float, float], None]) -> AsyncIterator[ChatEvent]:
    import websockets

    attempt, down_since = 0, None
    while True:
        try:
            async with websockets.connect(TWITCH_WS, ping_interval=60) as ws:
                await ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
                await ws.send("PASS SCHMOOPIIE")
                await ws.send(f"NICK justinfan{random.randint(10000, 99999)}")
                await ws.send(f"JOIN #{channel.lower()}")
                if down_since:
                    on_gap(down_since, time.time())
                    down_since = None
                attempt = 0
                async for raw in ws:
                    for line in str(raw).split("\r\n"):
                        if line.startswith("PING"):
                            await ws.send("PONG :tmi.twitch.tv")
                        ev = parse_twitch(line)
                        if ev:
                            yield ev
        except Exception:  # noqa: BLE001 - reconnect on any socket error
            down_since = down_since or time.time()
            attempt += 1
            await _backoff(attempt)


async def kick_stream(chatroom_id: int, on_gap: Callable[[float, float], None]) -> AsyncIterator[ChatEvent]:
    import websockets

    attempt, down_since = 0, None
    while True:
        try:
            async with websockets.connect(KICK_WS) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "event": "pusher:subscribe",
                            "data": {"auth": "", "channel": f"chatrooms.{chatroom_id}.v2"},
                        }
                    )
                )
                if down_since:
                    on_gap(down_since, time.time())
                    down_since = None
                attempt = 0
                async for raw in ws:
                    if '"pusher:ping"' in str(raw):
                        await ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                        continue
                    ev = parse_kick(str(raw))
                    if ev:
                        yield ev
        except Exception:  # noqa: BLE001
            down_since = down_since or time.time()
            attempt += 1
            await _backoff(attempt)
