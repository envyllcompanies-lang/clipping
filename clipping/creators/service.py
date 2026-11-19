"""Creator profiles in the database (doc 32): build/refresh baselines from recorded features, reaction series for the
heatmap, segment labels, catchphrases from transcripts of top-clipped windows."""

from __future__ import annotations

import numpy as np
import psycopg

from clipping.core import db
from clipping.creators import profile as cp

MIN_HOURS = 3.0


def load_baseline(c: psycopg.Connection, creator_id: int) -> cp.Baseline | None:
    r = db.one(
        c,
        "SELECT baselines, reaction_style, style_weights FROM creator_profile WHERE creator_id=%s",
        creator_id,
    )
    if not r or not r["baselines"]:
        return None
    b = r["baselines"]
    return cp.Baseline(
        b["med"],
        b["mad"],
        b.get("hours", 0),
        r["reaction_style"] or "expressive",
        r["style_weights"] or dict(cp.DEFAULT_WEIGHTS),
    )


def update_profile(
    c: psycopg.Connection, creator_id: int, f: dict[str, np.ndarray], clip_anchors: list[float] | None = None
) -> cp.Baseline:
    """Blend this stream's baseline into the stored one (weighted by hours) and refit style weights from clips."""
    comps = cp.components(f)
    new = cp.baseline(comps)
    old = load_baseline(c, creator_id)
    if old and old.hours > 0:
        w_old = old.hours / (old.hours + new.hours)
        new.med = {k: w_old * old.med[k] + (1 - w_old) * new.med[k] for k in new.med}
        new.mad = {k: w_old * old.mad[k] + (1 - w_old) * new.mad[k] for k in new.mad}
        new.hours += old.hours
        new.weights = old.weights
    if clip_anchors:
        new.weights = cp.fit_style_weights(comps, new, clip_anchors)
    c.execute(
        """INSERT INTO creator_profile(creator_id,baselines,reaction_style,style_weights,hours_seen) VALUES (%s,%s,%s,%s,%s)
                 ON CONFLICT (creator_id) DO UPDATE SET baselines=EXCLUDED.baselines, reaction_style=EXCLUDED.reaction_style,
                 style_weights=EXCLUDED.style_weights, hours_seen=EXCLUDED.hours_seen, updated_at=now()""",
        (creator_id, db.j(new.to_json()), new.style, db.j(new.weights), new.hours),
    )
    return new


def reaction_for_stream(c: psycopg.Connection, creator_id: int, f: dict[str, np.ndarray]) -> np.ndarray:
    """Reaction score vs the creator's own baseline (the stream itself until 3 hours of profile exist)."""
    b = load_baseline(c, creator_id)
    comps = cp.components(f)
    if b is None or b.hours < MIN_HOURS:
        b = cp.baseline(comps)
    return cp.reaction_score(comps, b)


def label_segments(
    c: psycopg.Connection, stream_id: int, f: dict[str, np.ndarray], words: list[dict] | None = None
) -> list[dict]:
    segs = cp.segment_labels(f, words)
    c.execute("DELETE FROM creator_segment WHERE stream_id=%s", (stream_id,))
    for s in segs:
        c.execute(
            "INSERT INTO creator_segment(stream_id,start_s,end_s,label,confidence) VALUES (%s,%s,%s,%s,%s)",
            (stream_id, s["start_s"], s["end_s"], s["label"], s["confidence"]),
        )
    return segs


def never_clip(c: psycopg.Connection, stream_id: int, start_s: float, end_s: float) -> str | None:
    r = db.one(
        c,
        """SELECT label FROM creator_segment WHERE stream_id=%s AND label = ANY(%s) AND start_s < %s AND end_s > %s LIMIT 1""",
        stream_id,
        list(cp.NEVER_CLIP),
        end_s,
        start_s,
    )
    return r["label"] if r else None


def refresh_phrases(c: psycopg.Connection, creator_id: int, language: str) -> list[str]:
    top = [
        " ".join(w["word"] for w in r["words"])
        for r in db.all_(
            c,
            """
        SELECT t.words FROM transcript t JOIN "window" w ON w.id=t.window_id JOIN moment m ON m.id=w.moment_id JOIN stream s ON s.id=m.stream_id
        WHERE s.creator_id=%s AND EXISTS (SELECT 1 FROM platform_clip pc WHERE pc.stream_id=s.id AND pc.abs_utc_start BETWEEN w.start_utc AND w.end_utc)""",
            creator_id,
        )
    ]
    bg = [
        " ".join(w["word"] for w in r["words"])
        for r in db.all_(
            c,
            """
        SELECT t.words FROM transcript t JOIN "window" w ON w.id=t.window_id JOIN moment m ON m.id=w.moment_id JOIN stream s ON s.id=m.stream_id
        WHERE s.creator_id=%s""",
            creator_id,
        )
    ]
    phrases = cp.mine_phrases(top, bg)
    c.execute(
        """INSERT INTO creator_profile(creator_id,signature_phrases) VALUES (%s,%s) ON CONFLICT (creator_id)
                 DO UPDATE SET signature_phrases = creator_profile.signature_phrases || EXCLUDED.signature_phrases""",
        (creator_id, db.j({language: phrases})),
    )
    return phrases
