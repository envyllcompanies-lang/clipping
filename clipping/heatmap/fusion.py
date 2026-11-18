"""Fusion and candidate windows (doc 05)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def percentile_norm(x: np.ndarray) -> np.ndarray:
    """Per-stream percentile in [0, 1]; NaNs preserved; ties share the average rank."""
    out = np.full(len(x), np.nan)
    ok = ~np.isnan(x)
    n = int(ok.sum())
    if n == 0:
        return out
    if np.nanmax(x) == np.nanmin(x):
        out[ok] = 0.0
        return out
    from scipy.stats import rankdata

    out[ok] = (rankdata(x[ok]) - 1) / max(n - 1, 1)
    return out


def fuse(signals: dict[str, np.ndarray], weights: dict[str, float], smooth_s: int = 5) -> np.ndarray:
    names = [k for k in signals if weights.get(k, 0) > 0]
    if not names:
        return np.zeros(len(next(iter(signals.values()))))
    norm = np.vstack([percentile_norm(signals[k]) for k in names])
    w = np.array([weights[k] for k in names])[:, None] * ~np.isnan(norm)
    tot = w.sum(axis=0)
    score = np.where(tot > 0, (np.nan_to_num(norm) * w).sum(axis=0) / np.where(tot > 0, tot, 1), 0.0)
    if smooth_s > 1:
        score = np.convolve(score, np.ones(smooth_s) / smooth_s, mode="same")
    return score


@dataclass
class Window:
    start_s: float
    end_s: float
    peak_s: float
    score: float


def pick_windows(
    score: np.ndarray,
    *,
    separation_s: int = 45,
    pct: float = 95,
    floor: float = 0.35,
    before_s: float = 45,
    after_s: float = 30,
    max_per_hour: int = 10,
) -> list[Window]:
    from scipy.signal import find_peaks

    T = len(score)
    if T == 0:
        return []
    thresh = max(float(np.percentile(score, pct)), floor)
    peaks, _ = find_peaks(score, distance=separation_s, height=thresh)
    cands = sorted(((float(score[p]), int(p)) for p in peaks), reverse=True)
    cap = max(1, int(round(max_per_hour * T / 3600)))
    wins: list[Window] = []
    for sc, p in cands:
        w = Window(max(0.0, p - before_s), min(float(T), p + after_s), float(p), sc)
        merged = False
        for o in wins:
            if w.start_s < o.end_s and o.start_s < w.end_s:
                o.start_s, o.end_s = min(o.start_s, w.start_s), max(o.end_s, w.end_s)
                merged = True
                break
        if not merged:
            wins.append(w)
        if len(wins) >= cap:
            break
    return sorted(wins, key=lambda w: -w.score)
