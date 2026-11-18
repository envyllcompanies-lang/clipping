"""Pipeline job chain (doc 25). Server: score -> extract. M1: audio clean -> transcribe -> events -> build/render.
Each handler is idempotent and enqueues the next step with a dedupe key."""

from __future__ import annotations

import psycopg

from clipping.core import config, db, jobs
from clipping.worker import handler, periodic


@periodic("server", "heatmap_live", 120)
def heatmap_live(c: psycopg.Connection) -> None:
    from clipping.heatmap import service

    for r in db.all_(
        c, "SELECT id FROM stream WHERE status='recording' OR ended_at > now() - interval '2 hours'"
    ):
        if db.get_flag(c, "pause_extract_server"):
            service.score_stream(c, r["id"], request_windows=False)
        else:
            service.score_stream(c, r["id"])


@handler("server", "heatmap_rescore")
def heatmap_rescore(c: psycopg.Connection, p: dict) -> dict:
    from clipping.heatmap import service

    return {"moments": service.score_stream(c, p["stream_id"])}


@handler("server", "vod_fetch_check")
def vod_fetch_check(c: psycopg.Connection, p: dict) -> dict:
    from clipping.ingest import clips

    req = clips.needs_vod(c, p["clip_row"])
    if req:
        jobs.enqueue(c, "vod_fetch", req, dedupe_key=f"vod:{req['video_id']}:{int(req['start_s'])}")
    return {"requested": bool(req)}


@handler("m1", "audio_clean")
def audio_clean(c: psycopg.Connection, p: dict) -> dict:
    from clipping.audio import cleanup

    if db.get_flag(c, "pause_heavy_m1"):
        raise RuntimeError("disk guard: heavy work paused")
    res = cleanup.process_window(c, p["window_id"])
    jobs.enqueue(c, "transcribe", p, dedupe_key=f"asr:{p['window_id']}")
    return {"separated": res["separated"]}


@handler("m1", "transcribe")
def transcribe(c: psycopg.Connection, p: dict) -> dict:
    from clipping.transcribe import engine

    res = engine.process_window(c, p["window_id"])
    jobs.enqueue(c, "events", p, dedupe_key=f"events:{p['window_id']}")
    return res


@handler("m1", "events")
def events(c: psycopg.Connection, p: dict) -> dict:
    from clipping.events import service

    res = service.process_window(c, p["window_id"])
    jobs.enqueue(c, "build", p, dedupe_key=f"build:{p['window_id']}")
    return res


@handler("m1", "build")
def build(c: psycopg.Connection, p: dict) -> dict:
    from clipping.produce import produce

    if db.get_flag(c, "global_pause"):
        raise RuntimeError("global pause: rendering held")
    return produce(c, p["window_id"])


def after_extract(c: psycopg.Connection, window_id: int) -> None:
    jobs.enqueue(c, "audio_clean", {"window_id": window_id}, dedupe_key=f"clean:{window_id}")


_ = config  # config imported for handlers added in later phases


# ---------------- Phase 4-5: control and publishing (server) ----------------
@periodic("server", "commands", 5)
def run_commands(c: psycopg.Connection) -> None:
    from clipping.dashboard import commands

    commands.execute_pending(c)


@periodic("server", "alerts", 60)
def alerts(c: psycopg.Connection) -> None:
    from clipping.dashboard import alerts as al

    al.run_checks(c)
    al.deliver(c)


@periodic("server", "token_refresh", 300)
def token_refresh(c: psycopg.Connection) -> None:
    from clipping.accounts import credentials
    from clipping.publish import oauth

    credentials.refresh_all(c, oauth.refreshers())


@periodic("server", "scheduler", 60)
def scheduler(c: psycopg.Connection) -> None:
    from clipping.publish import framework

    framework.schedule(c)


@periodic("server", "publisher", 30)
def publisher(c: psycopg.Connection) -> None:
    from clipping.publish import framework, registry

    framework.run_due(c, registry.adapters(c))


@handler("server", "post_delete")
def post_delete(c: psycopg.Connection, p: dict) -> dict:
    from clipping.publish import framework, registry

    return {"deleted": framework.delete_post(c, p["post_id"], registry.adapters(c))}


# ---------------- Phase 6: accounts and languages ----------------
@periodic("server", "language_weekly", 7 * 86400)
def language_weekly(c: psycopg.Connection) -> None:
    from clipping.languages import market

    market.weekly(c)


@periodic("server", "signup_codes", 30)
def signup_codes(c: psycopg.Connection) -> None:
    """Poll the owner inbox for verification codes only while some slot is mid-signup (doc 27)."""
    import time

    from clipping.accounts import provision

    provision.purge_codes(c)
    if not db.scalar(c, "SELECT count(*) FROM account_slot WHERE status='signed_up'"):
        return
    gm = provision.gmail_client(c)
    if gm:
        for raw in gm.recent_raw(int(time.time()) - 900):
            provision.route_code(c, raw)
