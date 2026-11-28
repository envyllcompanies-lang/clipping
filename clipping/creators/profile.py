"""Creator Profile & Reaction Analysis (doc 32): per-creator baselines, a reaction score normalized against the
creator's own normal, reaction style, stream segment labels, catchphrases and collab alignment.

Inputs are the per-second features the pipeline already computes (loudness at 10 Hz, voice excitement, spectral
centroid/flux/high-band ratio, motion, scene change, letterbox), so the extra cost is small (doc 32 budget)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

COMPONENTS = ["loud", "jump", "voice", "pitch", "hiband", "rate"]
DEFAULT_WEIGHTS = {"loud": 0.25, "jump": 0.25, "voice": 0.15, "pitch": 0.1, "hiband": 0.15, "rate": 0.1}


def _robust(x: np.ndarray, med: float, mad: float) -> np.ndarray:
    return (x - med) / max(mad * 1.4826, 1e-6)


def components(f: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Raw per-second reaction components (before any normalization)."""
    T = len(f["voice"])
    db10 = f["audio_db10"][: T * 10].reshape(T, 10)
    loud = db10.max(axis=1)
    prev = np.array([np.median(loud[max(0, i - 5) : i]) if i else loud[0] for i in range(T)])
    return {
        "loud": loud,
        "jump": np.clip(loud - prev, 0, None),
        "voice": f["voice"].astype(float),
        "pitch": f["centroid"].astype(float),
        "hiband": f["hiband"].astype(float),
        "rate": f["flux"].astype(float),
    }


@dataclass
class Baseline:
    med: dict[str, float]
    mad: dict[str, float]
    hours: float
    style: str = "expressive"
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    def to_json(self) -> dict:
        return {
            "med": self.med,
            "mad": self.mad,
            "hours": self.hours,
            "style": self.style,
            "weights": self.weights,
        }


def baseline(comps: dict[str, np.ndarray], exclude: np.ndarray | None = None) -> Baseline:
    keep = ~exclude if exclude is not None else np.ones(len(comps["loud"]), bool)
    med = {k: float(np.nanmedian(v[keep])) for k, v in comps.items()}
    mad = {k: float(np.nanmedian(np.abs(v[keep] - med[k]))) for k, v in comps.items()}
    spread = mad["loud"]
    style = "deadpan" if spread < 2.0 else "screamer" if spread > 6.0 else "expressive"
    return Baseline(med, mad, len(comps["loud"]) / 3600, style)


def zscores(comps: dict[str, np.ndarray], b: Baseline) -> dict[str, np.ndarray]:
    return {k: _robust(v, b.med[k], b.mad[k]) for k, v in comps.items()}


def reaction_score(comps: dict[str, np.ndarray], b: Baseline, smooth: int = 3) -> np.ndarray:
    """How unusual this second is for this person: style-weighted sum of robust z-scores vs their own baseline.
    A deadpan creator's raised voice scores as high as a screamer's scream."""
    z = zscores(comps, b)
    s = sum(b.weights.get(k, 0) * np.clip(z[k], -3, 8) for k in COMPONENTS)
    if b.style == "deadpan":  # quiet-then-explode: a spike right after relative silence counts extra
        quiet = np.convolve((z["loud"] < -0.5).astype(float), np.ones(6) / 6, mode="same")
        s = s + 0.5 * np.clip(z["jump"], 0, 8) * np.roll(quiet, 3)
    return np.convolve(s, np.ones(smooth) / smooth, mode="same") if smooth > 1 else s


def raw_reaction(comps: dict[str, np.ndarray], pooled: Baseline) -> np.ndarray:
    """The un-normalized comparison (doc 32 backtest): same components against one pooled baseline for everyone."""
    z = zscores(comps, pooled)
    return np.convolve(
        sum(DEFAULT_WEIGHTS[k] * np.clip(z[k], -3, 8) for k in COMPONENTS), np.ones(3) / 3, mode="same"
    )


def fit_style_weights(
    comps: dict[str, np.ndarray], b: Baseline, clip_anchors: list[float], width: int = 8
) -> dict[str, float]:
    """Weights from what preceded this creator's own most-clipped moments: each component's mean z just before
    clip anchors vs everywhere else (positive lift only), normalized. Falls back to defaults with < 5 clips."""
    if len(clip_anchors) < 5:
        return dict(DEFAULT_WEIGHTS)
    z = zscores(comps, b)
    T = len(comps["loud"])
    m = np.zeros(T, bool)
    for a in clip_anchors:
        m[max(0, int(a) - width) : min(T, int(a) + 2)] = True
    lift = {
        k: max(0.0, float(np.nanmean(np.clip(z[k][m], -3, 8)) - np.nanmean(np.clip(z[k][~m], -3, 8))))
        for k in COMPONENTS
    }
    tot = sum(lift.values())
    if tot <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: round(0.7 * v / tot + 0.3 * DEFAULT_WEIGHTS[k], 4) for k, v in lift.items()}


# ---------------- stream segments ----------------
SEGMENTS = ["gameplay", "cutscene_watching", "chatting", "brb", "sponsor", "irl", "alert"]
NEVER_CLIP = {"brb", "sponsor", "irl"}
SPONSOR_PATTERNS = [
    r"\buse code\b",
    r"\bcode [a-z0-9]{3,}\b",
    r"\bsponsored by\b",
    r"\blink in (the )?(description|bio|chat)\b",
    r"\bpromo code\b",
    r"\bc[oó]digo\b",
    r"\bpatrocinad",
    r"\bgesponsert\b",
    r"\bsponsoris",
    r"\bспонсор",
]


def segment_labels(f: dict[str, np.ndarray], words: list[dict] | None = None, minute: int = 60) -> list[dict]:
    """One label per minute (doc 32): BRB = static screen; cutscene watching = letterboxed; sponsor = ad-read phrases;
    chatting = little game motion with continuous speech; else gameplay."""
    T = len(f["voice"])
    out = []
    text_by_min: dict[int, str] = {}
    for w in words or []:
        text_by_min.setdefault(int(w["start"] // minute), "")
        text_by_min[int(w["start"] // minute)] += " " + w["word"].lower()
    for m in range(0, T, minute):
        sl = slice(m, min(T, m + minute))
        motion, scene = float(np.median(f["motion"][sl])), float(np.max(f["scene"][sl]))
        letter = float(np.mean(f["letterbox"][sl] > 0.5))
        txt = text_by_min.get(m // minute, "")
        if motion < 0.6 and scene < 0.05:
            lab, conf = "brb", 0.9
        elif sum(bool(re.search(p, txt)) for p in SPONSOR_PATTERNS) >= 1:
            lab, conf = "sponsor", 0.8
        elif letter > 0.6:
            lab, conf = "cutscene_watching", 0.7
        elif motion < 3.0 and np.mean(f["voice"][sl] > 0) > 0.6:
            lab, conf = "chatting", 0.5
        else:
            lab, conf = "gameplay", 0.6
        out.append(
            {"start_s": float(m), "end_s": float(min(T, m + minute)), "label": lab, "confidence": conf}
        )
    return out


def never_clip_mask(segments: list[dict], T: int) -> np.ndarray:
    mask = np.zeros(T, bool)
    for s in segments:
        if s["label"] in NEVER_CLIP:
            mask[int(s["start_s"]) : int(s["end_s"])] = True
    return mask


# ---------------- signature phrases ----------------
def mine_phrases(
    top_windows: list[str], background: list[str], n_range=(2, 4), min_count: int = 3, min_lift: float = 3.0
) -> list[str]:
    """Catchphrases: n-grams seen >= min_count times across top-clipped windows and enriched vs the background."""

    def grams(texts):
        c = Counter()
        for t in texts:
            toks = re.findall(r"\w+", t.lower())
            seen = set()
            for n in range(n_range[0], n_range[1] + 1):
                for i in range(len(toks) - n + 1):
                    g = " ".join(toks[i : i + n])
                    if g not in seen:
                        c[g] += 1
                        seen.add(g)
        return c

    top, bg = grams(top_windows), grams(background)
    nt, nb = max(len(top_windows), 1), max(len(background), 1)
    out = [g for g, k in top.items() if k >= min_count and (k / nt) / ((bg.get(g, 0) + 1) / nb) >= min_lift]
    out.sort(key=lambda g: -top[g])
    keep = []
    for g in out:  # drop sub-phrases of longer kept phrases
        if not any(g in k and g != k for k in keep):
            keep.append(g)
    return keep[:20]


# ---------------- collabs ----------------
def align_offset(
    env_a: np.ndarray, env_b: np.ndarray, rate: float, max_lag_s: float = 30
) -> tuple[float, float]:
    """Offset (s) to add to b's timeline to match a, by cross-correlating audio envelopes of shared voice chat.
    Returns (offset, peak correlation)."""
    a = (env_a - env_a.mean()) / (env_a.std() + 1e-9)
    b = (env_b - env_b.mean()) / (env_b.std() + 1e-9)
    n = len(a) + len(b)
    nfft = 1 << (n - 1).bit_length()
    xc = np.fft.irfft(np.fft.rfft(a, nfft) * np.conj(np.fft.rfft(b, nfft)), nfft)
    xc = np.r_[xc[-(len(b) - 1) :], xc[: len(a)]]
    lags = np.arange(-(len(b) - 1), len(a))
    ok = np.abs(lags) <= max_lag_s * rate
    k = int(np.argmax(np.where(ok, xc, -np.inf)))
    return float(lags[k] / rate), float(xc[k] / min(len(a), len(b)))
