"""Chat features per 10 s bucket (doc 03). Pure functions over (t_seconds, user_hash, text, emote_count)."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache

import emoji
import numpy as np


@dataclass
class Msg:
    t: float  # seconds since stream start (server clock)
    user: str  # hashed id
    text: str
    emotes: int = 0  # number of platform emotes in the message


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _grams(s: str) -> set[str]:
    s = f"  {s} "
    return {s[i : i + 3] for i in range(len(s) - 2)}


def is_emote_heavy(m: Msg) -> bool:
    words = m.text.split()
    if not words:
        return False
    emo = m.emotes + emoji.emoji_count(m.text)
    return emo / max(len(words), 1) >= 0.5


def is_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and sum(c.isupper() for c in letters) / len(letters) >= 0.7


@lru_cache(maxsize=256)
def _token_re(tokens: tuple[str, ...]) -> re.Pattern:
    parts = []
    for tok in tokens:
        tl = re.escape(tok.lower())
        word = tok.isascii() and tok.replace(" ", "").isalnum()
        parts.append(rf"(?<![a-z0-9]){tl}(?![a-z0-9])" if word else tl)
    return re.compile("|".join(parts) or r"(?!x)x")


def token_match(text: str, tokens: list[str] | tuple[str, ...]) -> bool:
    return _token_re(tuple(tokens)).search(text.lower()) is not None


def copypasta(texts: list[str], cap: int = 150) -> float:
    """Share of messages that are near-duplicates (3-gram Jaccard >= 0.8) of another message in the bucket."""
    texts = [_norm(t) for t in texts if len(t) >= 6][:cap]
    if len(texts) < 3:
        return 0.0
    cnt = Counter(texts)
    uniq = list(cnt)[:60]
    grams = {t: _grams(t) for t in uniq}
    dup = 0
    for t in uniq:
        if cnt[t] > 1:
            dup += cnt[t]
            continue
        gt = grams[t]
        if any(u != t and len(gt & grams[u]) / max(len(gt | grams[u]), 1) >= 0.8 for u in uniq):
            dup += 1
    return dup / len(texts)


def drop_spam(msgs: list[Msg], threshold: int = 5) -> list[Msg]:
    """Exclude accounts posting the identical text >= threshold times (bots)."""
    cnt = Counter((m.user, _norm(m.text)) for m in msgs)
    bad = {k for k, v in cnt.items() if v >= threshold}
    return [m for m in msgs if (m.user, _norm(m.text)) not in bad]


def robust_z(series: np.ndarray, baseline_n: int, missing: np.ndarray | None = None) -> np.ndarray:
    """(x - median(previous N)) / MAD(previous N); missing buckets excluded from baselines and get z = nan."""
    z = np.full(len(series), np.nan)
    miss = missing if missing is not None else np.zeros(len(series), bool)
    for i in range(len(series)):
        if miss[i]:
            continue
        lo = max(0, i - baseline_n)
        hist = series[lo:i][~miss[lo:i]]
        if len(hist) < 3:
            z[i] = 0.0
            continue
        med = float(np.median(hist))
        mad = float(np.median(np.abs(hist - med))) * 1.4826
        z[i] = (series[i] - med) / max(mad, 1.0)
    return z


def bucketize(
    msgs: list[Msg],
    duration_s: float,
    tokens: dict,
    bucket_s: int = 10,
    baseline_s: int = 300,
    gaps: list[tuple[float, float]] | None = None,
    spam_threshold: int = 5,
) -> list[dict]:
    msgs = drop_spam(msgs, spam_threshold)
    n = int(np.ceil(duration_s / bucket_s))
    by = defaultdict(list)
    for m in msgs:
        k = int(m.t // bucket_s)
        if 0 <= k < n:
            by[k].append(m)
    missing = np.zeros(n, bool)
    for a, b in gaps or []:
        missing[int(a // bucket_s) : int(np.ceil(b / bucket_s))] = True
    counts = np.array([len(by[k]) for k in range(n)], float)
    z = robust_z(counts, baseline_s // bucket_s, missing)
    out = []
    for k in range(n):
        ms = by[k]
        tot = max(len(ms), 1)
        out.append(
            {
                "t": k * bucket_s,
                "msgs": len(ms),
                "unique_chatters": len({m.user for m in ms}),
                "emote_share": sum(is_emote_heavy(m) for m in ms) / tot,
                "caps_share": sum(is_caps(m.text) for m in ms) / tot,
                "laugh_share": sum(token_match(m.text, tokens.get("laugh", [])) for m in ms) / tot,
                "hype_share": sum(token_match(m.text, tokens.get("hype", [])) for m in ms) / tot,
                "copypasta_score": copypasta([m.text for m in ms]),
                "velocity_z": None if np.isnan(z[k]) else float(z[k]),
                "missing": bool(missing[k]),
            }
        )
    return out


def per_second(msgs: list[Msg], duration_s: float) -> np.ndarray:
    a = np.zeros(int(np.ceil(duration_s)) + 1)
    for m in msgs:
        if 0 <= m.t < len(a):
            a[int(m.t)] += 1
    return a


def spike_onsets(
    rate: np.ndarray, min_sep: int = 30, z_thresh: float = 4.0, baseline: int = 120
) -> list[int]:
    """Second where chat rate first jumps above baseline (3 s smoothing). Used for alignment/calibration."""
    sm = np.convolve(rate, np.ones(3) / 3, mode="same")
    out, last = [], -(10**9)
    for i in range(baseline, len(sm)):
        hist = sm[i - baseline : i - 5]
        med = np.median(hist)
        mad = max(np.median(np.abs(hist - med)) * 1.4826, 0.5)
        if (sm[i] - med) / mad > z_thresh and i - last > min_sep:
            out.append(i)
            last = i
    return out


def calibrate_lag(onsets: list[int], moment_times: list[float], max_lag: float = 15) -> float | None:
    """Reaction lag = median(onset - true moment) over pairs within max_lag (moments from viewer clips' vod_offset)."""
    diffs = []
    for t in moment_times:
        cands = [o - t for o in onsets if -2 <= o - t <= max_lag]
        if cands:
            diffs.append(min(cands, key=abs))
    return float(np.median(diffs)) if diffs else None
