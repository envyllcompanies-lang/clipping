"""Creator scoring: percentile ranks within language, weighted sum, selection (doc 01). Pure functions, no AI."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

SIGNALS = ["live_audience", "footage_volume", "clip_rate", "clip_reach", "offplatform_reach", "growth", "our_performance"]


@dataclass
class CreatorInput:
    creator_id: int
    language: str
    samples: list[tuple[float, bool, int | None]]          # (t_hours_ago, live_in_game, viewers)
    clips: list[tuple[float, int]] = field(default_factory=list)   # (t_hours_ago, views)
    has_clip_data: bool = True
    offplatform_median: float | None = None
    our_performance: float | None = None
    chat_per_viewer: float | None = None
    blocklisted: bool = False
    pinned: bool = False


@dataclass
class Scored:
    creator_id: int
    language: str
    signals: dict[str, float | None]
    percentiles: dict[str, float]
    score: float
    flags: dict = field(default_factory=dict)
    rank: int = 0
    selected: bool = False
    reason: str = ""
    below_cutoff_days: int = 0


def _week_stats(c: CreatorInput, lo: float, hi: float, interval_min: float) -> tuple[float | None, float, float | None, float | None]:
    live = [v for t, ok, v in c.samples if lo <= t < hi and ok and v is not None]
    hours = len(live) * interval_min / 60.0
    audience = statistics.fmean(live) if live else None
    clips = [views for t, views in c.clips if lo <= t < hi]
    rate = (len(clips) / hours) if (c.has_clip_data and hours > 0) else None
    reach = float(statistics.median(clips)) if (c.has_clip_data and clips) else (0.0 if c.has_clip_data and hours > 0 else None)
    return audience, hours, rate, reach


def compute_signals(c: CreatorInput, interval_min: float = 10) -> dict[str, float | None]:
    aud, hours, rate, reach = _week_stats(c, 0, 168, interval_min)
    aud_prev, _, rate_prev, _ = _week_stats(c, 168, 336, interval_min)
    growth_parts = []
    if aud is not None and aud_prev:
        growth_parts.append(aud / aud_prev - 1)
    if rate is not None and rate_prev:
        growth_parts.append(rate / rate_prev - 1)
    return {
        "live_audience": aud,
        "footage_volume": hours if hours > 0 else None,
        "clip_rate": rate,
        "clip_reach": reach,
        "offplatform_reach": c.offplatform_median,
        "growth": statistics.fmean(growth_parts) if growth_parts else None,
        "our_performance": c.our_performance,
    }


def percentile_ranks(values: dict[int, float]) -> dict[int, float]:
    """0 = lowest, 1 = highest, ties share the average rank. A single value gets 0.5."""
    n = len(values)
    if n == 0:
        return {}
    if n == 1:
        return {k: 0.5 for k in values}
    order = sorted(values.items(), key=lambda kv: kv[1])
    out: dict[int, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and order[j + 1][1] == order[i][1]:
            j += 1
        r = (i + j) / 2
        for k in range(i, j + 1):
            out[order[k][0]] = r / (n - 1)
        i = j + 1
    return out


def score_language(inputs: list[CreatorInput], weights: dict[str, float], interval_min: float = 10,
                   viewbot_ratio: float = 0.2) -> list[Scored]:
    sig = {c.creator_id: compute_signals(c, interval_min) for c in inputs}
    by_id = {c.creator_id: c for c in inputs}
    # Viewbot flag: chats per viewer far below language median -> down-weight live audience.
    cpv = [c.chat_per_viewer for c in inputs if c.chat_per_viewer is not None]
    med_cpv = statistics.median(cpv) if cpv else None
    flags = {cid: {} for cid in sig}
    for c in inputs:
        if med_cpv and c.chat_per_viewer is not None and c.chat_per_viewer < viewbot_ratio * med_cpv:
            flags[c.creator_id]["viewbot_suspect"] = True
    pct: dict[int, dict[str, float]] = defaultdict(dict)
    for s in SIGNALS:
        vals = {cid: v[s] for cid, v in sig.items() if v[s] is not None and not (isinstance(v[s], float) and math.isnan(v[s]))}
        for cid, p in percentile_ranks(vals).items():
            pct[cid][s] = p
    out = []
    for cid, v in sig.items():
        w = {s: weights.get(s, 0.0) for s in SIGNALS if s in pct[cid]}
        tot = sum(w.values())  # renormalize over available signals, before any penalty
        if flags[cid].get("viewbot_suspect") and "live_audience" in w:
            w["live_audience"] *= 0.25
        score = sum(w[s] * pct[cid][s] for s in w) / tot if tot > 0 else 0.0
        out.append(Scored(cid, by_id[cid].language, v, dict(pct[cid]), round(score, 6), flags[cid]))
    out.sort(key=lambda x: (-x.score, x.creator_id))
    for i, s in enumerate(out, 1):
        s.rank = i
    return out


def select(scored: list[Scored], slots: int, *, exploit_share: float = 0.8, previous: dict[int, dict] | None = None,
           hysteresis_days: int = 2, blocked: set[int] | frozenset = frozenset(), pinned: set[int] | frozenset = frozenset()) -> list[Scored]:
    """Pick recorder slots: pinned first, 80% top-ranked, 20% highest growth outside the top group, with hysteresis."""
    previous = previous or {}
    eligible = [s for s in scored if s.creator_id not in blocked]
    n_exploit = max(0, round(slots * exploit_share)) if slots > 1 else slots
    top_ids = {s.creator_id for s in eligible[:n_exploit]}
    chosen: list[Scored] = []

    def take(s: Scored, reason: str) -> None:
        if len(chosen) < slots and s not in chosen:
            s.selected, s.reason = True, reason
            chosen.append(s)

    for s in eligible:
        if s.creator_id in pinned:
            take(s, "pinned")
    # Hysteresis: previously selected creators below the cutoff keep their slot until N consecutive days below.
    for s in eligible:
        prev = previous.get(s.creator_id)
        if s.creator_id in top_ids:
            s.below_cutoff_days = 0
        elif prev and prev.get("selected"):
            s.below_cutoff_days = prev.get("below_cutoff_days", 0) + 1
            if s.below_cutoff_days < hysteresis_days:
                take(s, f"kept by hysteresis (day {s.below_cutoff_days} below cutoff)")
    for s in eligible[:n_exploit]:
        take(s, f"top-ranked #{s.rank} in {s.language} (score {s.score:.3f})")
    rising = sorted((s for s in eligible if s.creator_id not in top_ids and not s.selected and s.signals.get("growth") is not None),
                    key=lambda s: (-(s.signals["growth"] or 0), s.creator_id))
    for s in rising:
        take(s, f"explore: rising (growth {s.signals['growth']:+.0%})")
    for s in eligible:  # fill any remaining capacity by rank
        take(s, f"fill by rank #{s.rank}")
    return chosen


def allocate_slots(total: int, audience_by_lang: dict[str, float]) -> dict[str, int]:
    """Every active language gets >= 1 slot; the rest go proportionally to audience (largest remainder)."""
    langs = sorted(audience_by_lang)
    if not langs:
        return {}
    if total <= len(langs):
        ranked = sorted(langs, key=lambda lang: -audience_by_lang[lang])
        return {lang: (1 if lang in ranked[:total] else 0) for lang in langs}
    base = {lang: 1 for lang in langs}
    rest = total - len(langs)
    tot = sum(max(v, 0) for v in audience_by_lang.values()) or 1.0
    raw = {lang: rest * max(audience_by_lang[lang], 0) / tot for lang in langs}
    for lang in langs:
        base[lang] += int(raw[lang])
    left = total - sum(base.values())
    for lang in sorted(langs, key=lambda x: -(raw[x] - int(raw[x])))[:left]:
        base[lang] += 1
    return base
