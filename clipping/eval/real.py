"""Real ground truth from our own recordings (doc 30, "fresh data"): every recorded stream with viewer clips mapped
to it becomes a viewer-clip replay (heatmap signals + clips). Rolling 14-day window. Needs the Twitch keys so the
recorder and clip ingest have run; the heatmap backtest grades on it automatically when present."""

from __future__ import annotations

import datetime as dt

import psycopg

from clipping.core import db
from clipping.eval import datasets

UTC = dt.UTC


def build_recent(c: psycopg.Connection, days: int = 14, min_clips: int = 5) -> str | None:
    since = dt.datetime.now(UTC) - dt.timedelta(days=days)
    streams = db.all_(
        c,
        """SELECT s.id, s.started_at, cr.language FROM stream s JOIN creator cr ON cr.id=s.creator_id
                            WHERE s.started_at > %s AND EXISTS (SELECT 1 FROM heatmap_signal h WHERE h.stream_id=s.id)""",
        since,
    )
    items = []
    for s in streams:
        clips = [
            {
                "t_start": (r["abs_utc_start"] - s["started_at"]).total_seconds(),
                "duration": r["duration"] or 30,
                "views": r["view_count"] or 0,
            }
            for r in db.all_(
                c, "SELECT * FROM platform_clip WHERE stream_id=%s AND abs_utc_start IS NOT NULL", s["id"]
            )
        ]
        if len(clips) < min_clips:
            continue
        sig = {
            r["name"]: r["values"]
            for r in db.all_(c, 'SELECT name, "values" FROM heatmap_signal WHERE stream_id=%s', s["id"])
        }
        items.append({"stream_id": s["id"], "language": s["language"], "signals": sig, "clips": clips})
    if not items:
        return None
    ver = dt.date.today().isoformat()
    datasets.write(
        "viewer_clips_recent",
        ver,
        {"streams.json": items},
        {"source": "our recordings + Twitch viewer clips", "streams": len(items)},
    )
    return ver
