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


def after_extract(c: psycopg.Connection, window_id: int) -> None:
    jobs.enqueue(c, "audio_clean", {"window_id": window_id}, dedupe_key=f"clean:{window_id}")


_ = config  # config imported for handlers added in later phases
