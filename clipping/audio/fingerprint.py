"""Landmark audio fingerprint (spectral peak pairs, Shazam-style) to check that a song no longer matches after
music removal. Stand-in for platform Content ID, which is the real test (private uploads, doc 07)."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import maximum_filter

SR = 8000


def _resample(x: np.ndarray, sr: int, to: int = SR) -> np.ndarray:
    if sr == to:
        return x
    from scipy.signal import resample_poly

    g = np.gcd(sr, to)
    return resample_poly(x, to // g, sr // g)


def landmarks(x: np.ndarray, sr: int, fan: int = 5) -> set[tuple[int, int, int, int]]:
    """Returns {(f1, f2, dt, t1)} hashes from constellation peaks."""
    x = _resample(np.asarray(x, np.float64), sr)
    n, hop = 512, 128
    if len(x) < n:
        return set()
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
    S = 20 * np.log10(np.abs(np.fft.rfft(frames, axis=1)) + 1e-9)[:, 4:200]
    peaks = (S == maximum_filter(S, size=(15, 15))) & (S > np.percentile(S, 97))
    ts, fs = np.nonzero(peaks)
    order = np.argsort(ts)
    ts, fs = ts[order], fs[order]
    out = set()
    for i in range(len(ts)):
        for j in range(i + 1, min(i + 1 + fan, len(ts))):
            dt = ts[j] - ts[i]
            if 1 <= dt <= 64:
                out.add((int(fs[i]), int(fs[j]), int(dt), int(ts[i])))
    return out


def match_score(reference: np.ndarray, query: np.ndarray, sr: int) -> float:
    """Share of query hashes that agree with the reference at one consistent time offset (0 = no match)."""
    ref = landmarks(reference, sr)
    q = landmarks(query, sr)
    if not ref or not q:
        return 0.0
    idx: dict[tuple, list[int]] = {}
    for f1, f2, dt, t in ref:
        idx.setdefault((f1, f2, dt), []).append(t)
    offsets: dict[int, int] = {}
    for f1, f2, dt, t in q:
        for tr in idx.get((f1, f2, dt), ()):
            offsets[tr - t] = offsets.get(tr - t, 0) + 1
    best = max(offsets.values()) if offsets else 0
    return best / len(q)


def matches(reference: np.ndarray, query: np.ndarray, sr: int, threshold: float = 0.05) -> bool:
    return match_score(reference, query, sr) >= threshold
