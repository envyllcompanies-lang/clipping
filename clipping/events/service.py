"""Event detection on candidate windows; per-stream overlay masks (doc 08)."""

from __future__ import annotations

import numpy as np
import psycopg

from clipping.core import db, media
from clipping.events import detect


def stream_mask(c: psycopg.Connection, stream_id: int) -> np.ndarray | None:
    """Overlay mask learned once per stream from ~30 frames spread across its segments (cached in stream.layout)."""
    st = db.one(c, "SELECT layout FROM stream WHERE id=%s", stream_id)
    lay = st["layout"] or {}
    if "overlay_mask" in lay:
        return np.array(lay["overlay_mask"], bool)
    segs = db.all_(
        c, "SELECT path FROM segment WHERE stream_id=%s AND NOT deleted ORDER BY start_utc", stream_id
    )
    if len(segs) < 3:
        return None
    picks = [segs[int(k)] for k in np.linspace(0, len(segs) - 1, min(30, len(segs)))]
    frames = [media.decode_frames(s["path"], fps=1, width=320, dur=1.0)[:1] for s in picks]
    frames = np.concatenate([f for f in frames if len(f)])
    if len(frames) < 3:
        return None
    mask = detect.learn_overlay_mask(frames)
    lay["overlay_mask"] = mask.tolist()
    c.execute("UPDATE stream SET layout=%s WHERE id=%s", (db.j(lay), stream_id))
    return mask


def process_window(c: psycopg.Connection, window_id: int, fps: float = 2.0) -> dict:
    w = db.one(
        c,
        """SELECT w.*, m.stream_id, s.started_at, cr.language FROM "window" w JOIN moment m ON m.id=w.moment_id
                     JOIN stream s ON s.id=m.stream_id JOIN creator cr ON cr.id=s.creator_id WHERE w.id=%s""",
        window_id,
    )
    frames = media.decode_frames(w["path"], fps=fps, width=320)
    times = np.arange(len(frames)) / fps
    mask = stream_mask(c, w["stream_id"])
    if mask is not None and mask.shape != frames.shape[1:3]:
        mask = None
    evs = detect.detect(frames, times, language=w["language"] or "en", mask=mask)
    offset = (w["start_utc"] - w["started_at"]).total_seconds()
    c.execute("DELETE FROM game_event WHERE window_id=%s", (window_id,))
    for e in evs:
        c.execute(
            "INSERT INTO game_event(stream_id,window_id,t_s,type,confidence,details) VALUES (%s,%s,%s,%s,%s,%s)",
            (w["stream_id"], window_id, offset + e.t, e.type, float(e.confidence), db.j(e.details)),
        )
    neg = detect.negative_spans(evs)
    covered = sum(b - a for a, b in neg) / max(times[-1] if len(times) else 1, 1)
    return {"events": len(evs), "negative_share": round(covered, 3)}
