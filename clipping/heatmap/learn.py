"""Weight refits (doc 05/22): L2 logistic regression, label = a viewer clip lands within 15 s. Kept only if it
beats current weights on a held-out set."""

from __future__ import annotations

import numpy as np

from clipping.heatmap.fusion import percentile_norm


def design(signals: dict[str, np.ndarray], names: list[str]) -> np.ndarray:
    return np.vstack([np.nan_to_num(percentile_norm(signals[k]), nan=0.5) for k in names]).T


def labels_from_clips(clips: list[dict], T: int, within_s: float = 15, anchor: float = 0.65) -> np.ndarray:
    y = np.zeros(T)
    for c in clips:
        p = int(c["t_start"] + anchor * c.get("duration", 30))
        y[max(0, p - int(within_s)): min(T, p + int(within_s))] = 1
    return y


def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 400, lr: float = 0.5) -> np.ndarray:
    n, d = X.shape
    Xb = np.hstack([X, np.ones((n, 1))])
    w = np.zeros(d + 1)
    pos = max(y.mean(), 1e-3)
    sw = np.where(y > 0, 0.5 / pos, 0.5 / (1 - pos))  # class balance
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xb @ w))
        g = Xb.T @ ((p - y) * sw) / n + l2 * np.r_[w[:-1], 0] / n
        w -= lr * g
    return w[:-1]


def to_weights(coef: np.ndarray, names: list[str], floor: float = 0.0) -> dict[str, float]:
    c = np.clip(coef, floor, None)
    if c.sum() <= 0:
        return {}
    c = c / c.sum()
    return {k: round(float(v), 4) for k, v in zip(names, c, strict=True)}
