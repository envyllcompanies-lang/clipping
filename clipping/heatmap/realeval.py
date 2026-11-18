"""Real-data heatmap evaluation shared by the 05, 31 and 32 backtests (eval/datasets/viewer_clips).

Labels: viewer clips, grouped into moments (anchors within 30 s are one moment; views summed). Recall@20 per 4 h of
the top-10 moments by views; label-fit parameters (style weights, refits) are fit on the first half of each VOD
and graded on the second half. VODs carry no chat replay, so chat signals are absent here."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from clipping.core import config
from clipping.creators import profile as cp
from clipping.heatmap import fusion, signals
from clipping.moments import analysis as ma

ANCHOR = 0.65
TOP_K = 10


@dataclass
class Vod:
    meta: dict
    f: dict[str, np.ndarray]

    @property
    def T(self) -> int:
        return len(self.f["voice"])

    def anchors(self) -> list[tuple[float, int]]:
        return [
            (c["t_start"] + ANCHOR * c["duration"], c["views"])
            for c in self.meta["clips"]
            if 0 <= c["t_start"] < self.T
        ]


def load_vods(version: str | None = None, partial_dir=None) -> tuple[list[Vod], str]:
    if partial_dir is not None:  # in-progress build: npz files present, labels from Helix
        raise NotImplementedError
    from clipping.eval import helix_builder

    meta, arrays, ver = helix_builder.load(version)
    return [Vod(m, arrays[m["video_id"]]) for m in meta], ver


def moments(anchors: list[tuple[float, int]], gap: float = 30) -> list[tuple[float, int]]:
    out: list[list] = []
    for t, v in sorted(anchors):
        if out and t - out[-1][2] <= gap:
            out[-1][1] += v
            out[-1][2] = t
            out[-1][3].append((t, v))
        else:
            out.append([t, v, t, [(t, v)]])
    res = []
    for _, views, _, members in out:
        t = max(members, key=lambda m: m[1])[0]  # most-viewed clip's anchor stands for the moment
        res.append((t, views))
    return res


def base_signals(v: Vod) -> dict[str, np.ndarray]:
    f, T = v.f, v.T
    return {
        "audio_energy": signals.audio_spikes(f["audio_db10"], 0.1, T, music=f["music"]),
        "voice_excitement": f["voice"].astype(float),
        "visual_change": f["scene"].astype(float),
    }


def reaction_series(
    v: Vod, normalized: bool, pooled: cp.Baseline | None = None, fit_until: float | None = None
) -> np.ndarray:
    comps = cp.components(v.f)
    if not normalized:
        return cp.raw_reaction(comps, pooled)
    b = cp.baseline(comps)
    if fit_until is not None:
        b.weights = cp.fit_style_weights(comps, b, [t for t, _ in v.anchors() if t < fit_until])
    return cp.reaction_score(comps, b)


def pooled_baseline(vods: list[Vod]) -> cp.Baseline:
    allc = [cp.components(v.f) for v in vods]
    joined = {k: np.concatenate([c[k] for c in allc]) for k in allc[0]}
    return cp.baseline(joined)


def recall(
    sig: dict[str, np.ndarray], weights: dict[str, float], v: Vod, lo: float = 0, hi: float | None = None
) -> tuple[float, float, list]:
    cfg = config.settings()["heatmap"]
    hi = hi or v.T
    score = fusion.fuse(sig, weights, cfg["smooth_s"])
    wins = fusion.pick_windows(
        score,
        separation_s=cfg["peak_separation_s"],
        pct=cfg["peak_percentile"],
        floor=0.0,
        before_s=cfg["window_before_s"],
        after_s=cfg["window_after_s"],
        max_per_hour=cfg["max_per_hour"],
    )
    wins = [w for w in wins if lo <= w.peak_s < hi][: max(1, int(round(20 * (hi - lo) / 14400)))]
    truth = sorted([m for m in moments(v.anchors()) if lo <= m[0] < hi], key=lambda m: -m[1])[:TOP_K]
    if not truth:
        return float("nan"), float("nan"), []
    hit = [any(w.start_s <= t <= w.end_s for w in wins) for t, _ in truth]
    all_m = [m[0] for m in moments(v.anchors())]
    prec = [any(w.start_s <= t <= w.end_s for t in all_m) for w in wins]
    misses = [(t, views) for (t, views), h in zip(truth, hit, strict=True) if not h]
    return float(np.mean(hit)), float(np.mean(prec)) if prec else 0.0, misses


def evaluate(
    vods: list[Vod],
    extra: dict[str, float] | None = None,
    normalized_reaction: bool = True,
    test_half: bool = True,
) -> dict:
    """Heatmap recall@20 on the test half of every VOD with the base live signals plus optional extra signals
    (gameplay, reaction) at the given weights."""
    cfg = config.settings()["heatmap"]["weights"]
    w = {k: cfg.get(k, 0.1) for k in ("audio_energy", "voice_excitement", "visual_change")}
    pooled = pooled_baseline(vods)
    recs, precs, misses = [], [], []
    for v in vods:
        half = v.T / 2
        sig = base_signals(v)
        if extra:
            react = reaction_series(v, normalized_reaction, pooled, fit_until=half if test_half else None)
            if "reaction" in extra:
                sig["reaction"] = react
            if "gameplay" in extra:
                sig["gameplay"], _ = ma.gameplay_score(v.f, react)
            w = {**w, **extra}
        r, p, m = recall(sig, w, v, half if test_half else 0, v.T)
        if r == r:
            recs.append(r)
            precs.append(p)
            misses += [(v.meta["creator"], t, views) for t, views in m]
    return {
        "recall_at_20": float(np.mean(recs)),
        "precision_at_20": float(np.mean(precs)),
        "vods": len(recs),
        "misses": misses,
    }
