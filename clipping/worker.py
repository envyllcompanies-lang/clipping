"""Worker daemons (doc 25). `clip worker server` on the VPS, `clip worker m1` on the MacBook.

Periodic tasks run on fixed intervals; queued work moves through the job table. Every handler is idempotent.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import socket
import threading
import time
from collections.abc import Callable

import psycopg

from clipping.core import config, db, jobs

log = logging.getLogger("clipping.worker")
UTC = dt.UTC

HANDLERS: dict[str, dict[str, Callable]] = {"server": {}, "m1": {}}
PERIODIC: dict[str, list[tuple[str, float, Callable]]] = {"server": [], "m1": []}


def handler(role: str, job_type: str):
    def deco(fn):
        HANDLERS[role][job_type] = fn
        return fn

    return deco


def periodic(role: str, name: str, every_s: float):
    def deco(fn):
        PERIODIC[role].append((name, every_s, fn))
        return fn

    return deco


# ---------------- Phase 1: sources (server) ----------------
_recorders: dict[int, threading.Thread] = {}


@periodic("server", "radar_poll", 600)
def radar_poll(c: psycopg.Connection) -> None:
    from clipping.radar import service, sources

    srcs = sources.live_sources()
    if not srcs:
        return
    ids = service.resolve_game_ids(srcs)
    service.poll_live(c, srcs, ids)


@periodic("server", "radar_rank", 86400)
def radar_rank(c: psycopg.Connection) -> None:
    from clipping.radar import service

    service.daily_rank(c)


@periodic("server", "clips_hourly", 3600)
def clips_hourly(c: psycopg.Connection) -> None:
    from clipping.ingest import clips
    from clipping.radar.sources import TwitchHelix

    api = TwitchHelix.from_env()
    gid = config.game().get("twitch_id")
    if not api or not gid:
        return
    clips.discover(c, api, gid)
    clips.per_creator(c, api)
    clips.map_to_utc(c, api)


@periodic("server", "sweeper", 300)
def sweeper(c: psycopg.Connection) -> None:
    from clipping.recorder import recorder
    from clipping.storage import files

    recorder.prune(c)
    files.sweep(c)


@periodic("server", "disk_guard", 60)
def disk_guard_server(c: psycopg.Connection) -> None:
    from clipping.storage import guard

    guard.check(c, "server")


@periodic("server", "chat_purge", 86400)
def chat_purge(c: psycopg.Connection) -> None:
    from clipping.chat import capture

    capture.purge_raw(c)


@handler("server", "record_start")
def record_start(c: psycopg.Connection, p: dict) -> dict:
    from clipping.recorder import recorder

    if db.get_flag(c, "pause_heavy_server"):
        raise RuntimeError("disk guard: recording paused")
    if recorder.free_slots(c) <= 0:
        raise RuntimeError("no free recorder slots")
    cr = db.one(c, "SELECT * FROM creator WHERE id=%s", p["creator_id"])
    if cr["blocklisted"] or cr["paused"]:
        return {"skipped": "blocklisted/paused"}
    started = (
        dt.datetime.fromisoformat(p["started_at"].replace("Z", "+00:00")) if p.get("started_at") else None
    )
    sid = recorder.start_stream(c, cr["id"], p["stream_id"], started, p.get("language"))
    if cr["id"] in _recorders and _recorders[cr["id"]].is_alive():
        return {"stream_id": sid, "already": True}

    def run():
        with db.conn() as c2:
            w = recorder.Worker(c2, cr, sid)

            def live():
                return (
                    db.scalar(
                        c2,
                        "SELECT count(*) FROM job WHERE type='record_stop' AND payload->>'stream_id'=%s AND status='queued'",  # noqa: E731
                        str(sid),
                    )
                    == 0
                )

            w.run(is_live=live)

    t = threading.Thread(target=run, daemon=True, name=f"rec-{cr['handle']}")
    t.start()
    _recorders[cr["id"]] = t
    _start_chat(cr, sid)
    return {"stream_id": sid}


def _start_chat(cr: dict, stream_id: int) -> None:
    import asyncio

    from clipping.chat import capture, clients

    def run():
        with db.conn() as c2:
            st = db.one(c2, "SELECT * FROM stream WHERE id=%s", stream_id)
            cap = capture.Capture(c2, stream_id, st["started_at"], cr["language"] or "en", cr["platform"])

            async def main():
                if cr["platform"] == "twitch":
                    gen = clients.twitch_stream(cr["handle"], cap.gap)
                elif cr["platform"] == "kick" and str(cr["platform_id"]).isdigit():
                    gen = clients.kick_stream(int(cr["platform_id"]), cap.gap)
                else:
                    return
                last = time.time()
                async for ev in gen:
                    cap.add(ev)
                    if time.time() - last >= 1:
                        cap.flush()
                        last = time.time()
                    if db.scalar(c2, "SELECT status FROM stream WHERE id=%s", stream_id) == "ended":
                        break
                cap.flush()
                capture.compute_buckets(c2, stream_id)

            asyncio.run(main())

    threading.Thread(target=run, daemon=True, name=f"chat-{cr['handle']}").start()


@handler("server", "record_stop")
def record_stop(c: psycopg.Connection, p: dict) -> dict:
    from clipping.recorder import recorder

    recorder.end_stream(c, p["stream_id"])
    return {"ended": p["stream_id"]}


@handler("server", "extract_window")
def extract_window(c: psycopg.Connection, p: dict) -> dict:
    from clipping.recorder import recorder

    if db.get_flag(c, "pause_extract_server"):
        raise RuntimeError("disk guard: extraction paused")
    return recorder.extract_window(c, p["window_id"])


def load_all() -> None:
    """Import modules that register later-phase handlers."""
    import importlib

    for m in ("clipping.pipeline",):
        try:
            importlib.import_module(m)
        except ModuleNotFoundError as e:
            if e.name != m:
                raise


def loop(role: str, once: bool = False, idle_sleep: float = 2.0) -> None:
    load_all()
    name = f"{role}:{socket.gethostname()}:{os.getpid()}"
    last_run: dict[str, float] = {}
    with db.conn() as c:
        if role == "server":
            from clipping.recorder import recorder
            from clipping.storage import files

            files.reconcile(c)
            recorder.recover_on_restart(c)
        while True:
            now = time.time()
            jobs.heartbeat(
                c, name, role, {"recorders": len([t for t in _recorders.values() if t.is_alive()])}
            )
            for pname, every, fn in PERIODIC[role]:
                if now - last_run.get(pname, 0) >= every:
                    last_run[pname] = now
                    try:
                        fn(c)
                    except Exception as e:  # noqa: BLE001 - periodic tasks must not kill the daemon
                        log.exception("periodic %s failed: %s", pname, e)
            if db.get_flag(c, "global_pause") and role == "m1":
                did = False
            else:
                did = jobs.run_one(c, HANDLERS[role], name)
            if once:
                return
            if not did:
                time.sleep(idle_sleep)
