"""Real chat dataset (doc 03): live IRC capture on the top GTA VI channels + viewer clips made during the capture.
Stores per-second message counts, gaps and 10 s bucket features (no usernames, no message text) plus clip positions."""

from __future__ import annotations

import asyncio
import datetime as dt
import time

import numpy as np

from clipping.chat import clients, features
from clipping.core import config
from clipping.eval import datasets
from clipping.radar.sources import TwitchHelix

UTC = dt.UTC


async def _capture(logins: list[str], seconds: int) -> dict:
    res = {l_: {"msgs": [], "gaps": []} for l_ in logins}

    async def one(login):
        def gap(a, b):
            res[login]["gaps"].append((a, b))

        gen = clients.twitch_stream(login, gap)
        end = time.time() + seconds
        try:
            while time.time() < end:
                ev = await asyncio.wait_for(gen.__anext__(), timeout=max(1.0, end - time.time()))
                res[login]["msgs"].append(
                    features.Msg(ev.received_at, ev.user_hash, ev.text, len(ev.emote_ids))
                )
        except (TimeoutError, StopAsyncIteration):
            pass
        finally:
            await gen.aclose()

    await asyncio.gather(*(one(l_) for l_ in logins))
    return res


def build(minutes: int = 12, channels: int = 3, version: str | None = None, log=print):
    h = TwitchHelix.from_env()
    gid = h.resolve_game(["Grand Theft Auto VI"])
    live = sorted(h.live_streams(gid), key=lambda s: -s.viewer_count)
    picks, langs = [], set()
    for s in live:
        if s.language not in langs:
            picks.append(s)
            langs.add(s.language)
        if len(picks) >= channels:
            break
    t0 = time.time()
    log(f"capturing {[p.login for p in picks]} for {minutes} min")
    cap = asyncio.run(_capture([p.login for p in picks], minutes * 60))
    t1 = time.time()
    time.sleep(120)  # clips made at the end of the capture take a moment to appear
    out = []
    for p in picks:
        msgs = cap[p.login]["msgs"]
        T = int(t1 - t0) + 1
        rel = [features.Msg(m.t - t0, m.user, m.text, m.emotes) for m in msgs]
        gaps = [(a - t0, b - t0) for a, b in cap[p.login]["gaps"]]
        buckets = features.bucketize(rel, T, config.chat_tokens(p.language or "en"), gaps=gaps)
        vids = h.get("videos", {"user_id": p.user_id, "type": "archive", "first": 1}).get("data", [])
        vod_start = dt.datetime.fromisoformat(vids[0]["created_at"].replace("Z", "+00:00")) if vids else None
        cl = h.clips(
            broadcaster_id=p.user_id,
            started_at=dt.datetime.fromtimestamp(t0, UTC).isoformat().replace("+00:00", "Z"),
            ended_at=dt.datetime.fromtimestamp(t1 + 120, UTC).isoformat().replace("+00:00", "Z"),
            max_items=500,
        )
        clips = []
        for c in cl:
            if (
                c.get("vod_offset") is not None
                and vod_start
                and c.get("video_id") == (vids[0]["id"] if vids else None)
            ):
                abs_start = vod_start + dt.timedelta(seconds=c["vod_offset"])
                clips.append(
                    {
                        "t_start": abs_start.timestamp() - t0,
                        "duration": c["duration"],
                        "views": c["view_count"],
                    }
                )
        out.append(
            {
                "login": p.login,
                "language": p.language,
                "viewers": p.viewer_count,
                "duration_s": T,
                "per_second": features.per_second(rel, T).astype(int).tolist(),
                "gaps": gaps,
                "buckets": buckets,
                "clips": clips,
            }
        )
        log(f"{p.login}: {len(msgs)} msgs, {len(gaps)} gaps, {len(clips)} clips with positions")
    version = version or dt.datetime.now(UTC).strftime("%Y-%m-%dT%H%M")
    return datasets.write(
        "live_chat",
        version,
        {"channels.json": out},
        {
            "source": "Twitch IRC (anonymous read) + Helix clips",
            "minutes": minutes,
            "note": "no usernames or message text stored",
        },
    )


_ = np
