"""Per-second signals for the heatmap (doc 05). Pure numpy; each returns an array of length T (NaN = missing)."""

from __future__ import annotations

import math

import numpy as np

SIGNALS = ["chat_velocity", "viewer_clips", "audio_energy", "voice_excitement", "chat_reaction", "game_events", "visual_change",
           "viewer_jump"]


def _shift(a: np.ndarray, lag_s: float) -> np.ndarray:
    """Shift a reaction signal earlier by lag seconds (chat reacts after the on-screen cause)."""
    k = int(round(lag_s))
    if k <= 0:
        return a
    out = np.full_like(a, np.nan)
    out[:-k] = a[k:]
    return out


def from_buckets(buckets: list[dict], T: int, bucket_s: int = 10, lag_s: float = 4.5) -> tuple[np.ndarray, np.ndarray]:
    """Chat velocity (robust z) and reaction mix interpolated to 1 s, shifted back by the reaction lag."""
    vel = np.full(T, np.nan)
    mix = np.full(T, np.nan)
    if not buckets:
        return vel, mix
    centers, vz, rm, miss = [], [], [], []
    for b in buckets:
        centers.append(b["t"] + bucket_s / 2)
        m = bool(b.get("missing"))
        miss.append(m)
        vz.append(np.nan if m or b.get("velocity_z") is None else b["velocity_z"])
        rm.append(np.nan if m else 0.4 * b["laugh_share"] + 0.4 * b["hype_share"] + 0.1 * b["caps_share"] + 0.1 * b["copypasta_score"])
    centers = np.array(centers)
    t = np.arange(T)
    for src, dst in ((np.array(vz), vel), (np.array(rm), mix)):
        ok = ~np.isnan(src)
        if ok.sum() >= 2:
            dst[:] = np.interp(t, centers[ok], src[ok])
        idx = np.clip((t // bucket_s).astype(int), 0, len(buckets) - 1)
        dst[np.array(miss)[idx]] = np.nan
    return _shift(vel, lag_s), _shift(mix, lag_s)


def clip_density(clips: list[dict], T: int, kernel_s: float = 10, anchor: float = 0.65) -> np.ndarray:
    """Gaussian KDE of viewer-clip positions weighted by log(views+1).

    Each clip is placed at start + anchor x duration: viewers clip the lead-up and end shortly after the moment,
    so the moment sits in the back half of the clip, not at its start.
    """
    out = np.zeros(T)
    if not clips:
        return out
    t = np.arange(T)
    for c in clips:
        pos = c["t_start"] + anchor * c.get("duration", 30)
        if -60 < pos < T + 60:
            lo, hi = int(max(0, pos - 4 * kernel_s)), int(min(T, pos + 4 * kernel_s))
            out[lo:hi] += math.log(c["views"] + 1) * np.exp(-0.5 * ((t[lo:hi] - pos) / kernel_s) ** 2)
    return out


def rms_db(audio: np.ndarray, sr: int, hop_s: float = 0.05) -> np.ndarray:
    hop = int(sr * hop_s)
    n = len(audio) // hop
    if n == 0:
        return np.zeros(0)
    frames = audio[: n * hop].reshape(n, hop)
    return 20 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-6)


def audio_spikes(db: np.ndarray, hop_s: float, T: int, jump_db: float = 10.0, music: np.ndarray | None = None) -> np.ndarray:
    """dB jump over the previous 1 s median, per second max; jumps under `jump_db` count partially. Music-heavy
    seconds are down-weighted (radio makes energy noisy)."""
    per = int(round(1 / hop_s))
    if len(db) < per + 1:
        return np.zeros(T)
    from numpy.lib.stride_tricks import sliding_window_view

    med = np.median(sliding_window_view(db, per), axis=1)            # med[i] = median(db[i:i+per])
    jump = np.zeros_like(db)
    jump[per:] = db[per:] - med[: len(db) - per]
    jump = np.clip(jump, 0, None)
    score = np.where(jump >= jump_db, jump, jump * 0.3)
    n = min(T, len(score) // per)
    out = np.zeros(T)
    out[:n] = score[: n * per].reshape(n, per).max(axis=1)
    if music is not None:
        m = np.zeros(T)
        m[: min(T, len(music))] = music[:T]
        out *= 1 - 0.8 * np.clip(m, 0, 1)
    return out


def voice_excitement(audio: np.ndarray, sr: int, T: int) -> np.ndarray:
    """Voice-band (300-3000 Hz) energy variability and spectral flux per second, z-scored against the stream."""
    out = np.zeros(T)
    if len(audio) < sr:
        return out
    n = min(T, len(audio) // sr)
    frames = audio[: n * sr].reshape(n, sr)
    spec = np.abs(np.fft.rfft(frames.reshape(n * 10, sr // 10), axis=1))
    freqs = np.fft.rfftfreq(sr // 10, 1 / sr)
    band = spec[:, (freqs >= 300) & (freqs <= 3000)]
    e = np.log(band.sum(axis=1) + 1e-6).reshape(n, 10)
    flux = np.r_[0, np.abs(np.diff(band, axis=0)).sum(axis=1)].reshape(n, 10).mean(axis=1)
    feat = e.std(axis=1) + 0.5 * np.log(flux + 1e-6)
    z = (feat - np.median(feat)) / (np.median(np.abs(feat - np.median(feat))) * 1.4826 + 1e-6)
    out[:n] = z
    return out


def visual_change(frames: np.ndarray, fps: float, T: int) -> np.ndarray:
    """Histogram distance between consecutive frames (2 fps, 240 px), per-second max."""
    out = np.zeros(T)
    if len(frames) < 2:
        return out
    hists = []
    for f in frames:
        g = f if f.ndim == 2 else f.mean(axis=2)
        h, _ = np.histogram(g, bins=32, range=(0, 255))
        hists.append(h / max(h.sum(), 1))
    hists = np.array(hists)
    d = np.r_[0, 0.5 * np.abs(np.diff(hists, axis=0)).sum(axis=1)]
    return per_second_max(d, fps, T)


def per_second_max(x: np.ndarray, rate: float, T: int) -> np.ndarray:
    per = max(1, int(round(rate)))
    n = min(T, len(x) // per)
    out = np.zeros(T)
    if n:
        out[:n] = x[: n * per].reshape(n, per).max(axis=1)
    return out


def events_curve(events: list[dict], T: int, weights: dict[str, float], width_s: float = 3) -> np.ndarray:
    out = np.zeros(T)
    t = np.arange(T)
    for e in events:
        w = weights.get(e["type"], 0.5)
        if w <= 0:
            continue
        lo, hi = int(max(0, e["t"] - 4 * width_s)), int(min(T, e["t"] + 4 * width_s))
        out[lo:hi] = np.maximum(out[lo:hi], w * e.get("confidence", 1.0) * np.exp(-0.5 * ((t[lo:hi] - e["t"]) / width_s) ** 2))
    return out


def viewer_jumps(samples: list[tuple[int, int]], T: int) -> np.ndarray:
    """Positive change in viewers between 10-minute samples, spread across the interval (relative change)."""
    out = np.full(T, np.nan) if len(samples) < 2 else np.zeros(T)
    for (t0, v0), (t1, v1) in zip(samples, samples[1:], strict=False):
        if v0 > 0 and t1 > t0:
            out[max(0, t0):min(T, t1)] = max(0.0, (v1 - v0) / v0)
    return out
