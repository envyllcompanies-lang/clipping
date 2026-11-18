"""Music detection per second (doc 07).

`heuristic` (default on the server, cheap): sustained spectral peaks, tonality, beat periodicity and the absence of
4 Hz syllabic modulation. `panns` (M1, accurate on real audio): AudioSet CNN14 'Music' probability.
"""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np

# Logistic coefficients fit on the synthetic audio training seeds (clipping.audio.backtest fit_detector).
COEF = {"sustain": 0.0, "flat": 0.0, "rhythm": 0.0, "mod4": 0.0, "bias": 0.0}
_COEF_FILE = os.path.join(os.path.dirname(__file__), "music_coef.json")
if os.path.exists(_COEF_FILE):
    import json

    COEF.update(json.load(open(_COEF_FILE)))


def _stft(x: np.ndarray, n: int, hop: int) -> np.ndarray:
    if len(x) < n:
        x = np.pad(x, (0, n - len(x)))
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
    return np.abs(np.fft.rfft(frames, axis=1))


def features(audio: np.ndarray, sr: int) -> np.ndarray:
    """Per-second feature matrix [sustain, flat, rhythm, mod4]."""
    if sr != 8000:
        from scipy.signal import resample_poly

        g = np.gcd(sr, 8000)
        audio = resample_poly(audio, 8000 // g, sr // g)
        sr = 8000
    T = max(1, len(audio) // sr)
    n, hop = 512, 128  # 64 ms / 16 ms at 8 kHz
    S = _stft(audio.astype(np.float64), n, hop)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    band = S[:, (freqs >= 100) & (freqs <= 3500)]
    logS = 20 * np.log10(band + 1e-9)
    fps = sr / hop
    # sustain: spectral peaks that persist into the next frame
    med = np.median(logS, axis=1, keepdims=True)
    pk = (logS > med + 15) & (logS >= np.roll(logS, 1, 1)) & (logS >= np.roll(logS, -1, 1))
    pk_d = pk | np.roll(pk, 1, 1) | np.roll(pk, -1, 1)
    persist = np.r_[0, (pk[1:] & pk_d[:-1]).sum(1) / np.maximum(pk[1:].sum(1), 1)]
    flat = np.exp(np.mean(np.log(band + 1e-9), 1)) / (band.mean(1) + 1e-9)
    energy = band.sum(1)
    flux = np.r_[0, np.clip(np.diff(logS, axis=0), 0, None).mean(1)]
    out = np.zeros((T, 4))
    fpsec = int(round(fps))
    for s in range(T):
        a, b = s * fpsec, min(len(persist), (s + 1) * fpsec)
        if b <= a:
            continue
        out[s, 0] = persist[a:b].mean()
        out[s, 1] = flat[a:b].mean()
        lo, hi = max(0, a - 2 * fpsec), min(len(flux), b + 2 * fpsec)  # 5 s context for rhythm
        f = flux[lo:hi] - flux[lo:hi].mean()
        if len(f) > fpsec:
            ac = np.correlate(f, f, "full")[len(f) - 1:]
            ac = ac / (ac[0] + 1e-9)
            l0, l1 = int(0.3 * fps), min(len(ac) - 1, int(1.0 * fps))
            out[s, 2] = ac[l0:l1].max() if l1 > l0 else 0
        e = energy[lo:hi]
        if len(e) > fpsec:
            e = (e - e.mean()) / (e.std() + 1e-9)
            spec = np.abs(np.fft.rfft(e))
            fr = np.fft.rfftfreq(len(e), 1 / fps)
            out[s, 3] = spec[(fr >= 3) & (fr <= 6)].sum() / (spec[fr > 0.5].sum() + 1e-9)
    return out


def heuristic_prob(audio: np.ndarray, sr: int) -> np.ndarray:
    F = features(audio, sr)
    z = COEF["bias"] + F @ np.array([COEF["sustain"], COEF["flat"], COEF["rhythm"], COEF["mod4"]])
    p = 1 / (1 + np.exp(-z))
    return np.convolve(p, np.ones(3) / 3, mode="same") if len(p) >= 3 else p


@lru_cache(maxsize=1)
def _panns():
    from panns_inference import AudioTagging  # optional heavy dependency

    at = AudioTagging(checkpoint_path=None, device="mps" if _has_mps() else "cpu")
    from panns_inference import labels

    return at, [i for i, lab in enumerate(labels) if lab in ("Music", "Musical instrument", "Song", "Pop music", "Rock music",
                                                               "Hip hop music", "Electronic music")]


def _has_mps() -> bool:
    try:
        import torch

        return bool(torch.backends.mps.is_available())
    except Exception:  # noqa: BLE001
        return False


def panns_prob(audio: np.ndarray, sr: int) -> np.ndarray:
    from scipy.signal import resample_poly

    at, idx = _panns()
    x = resample_poly(audio, 32000 // np.gcd(sr, 32000), sr // np.gcd(sr, 32000)).astype(np.float32)
    T = max(1, len(x) // 32000)
    chunks = np.stack([np.pad(x[max(0, (s - 0) * 32000 - 16000): s * 32000 + 48000], (0, 0))[:64000].copy()
                       if len(x[max(0, s * 32000 - 16000): s * 32000 + 48000]) >= 64000
                       else np.pad(x[max(0, s * 32000 - 16000): s * 32000 + 48000], (0, 64000 - len(x[max(0, s * 32000 - 16000): s * 32000 + 48000])))
                       for s in range(T)])
    clip, _ = at.inference(chunks)
    return clip[:, idx].max(axis=1)


def backend() -> str:
    b = os.environ.get("CLIPPING_MUSIC_MODEL", "auto")
    if b != "auto":
        return b
    try:
        import panns_inference  # noqa: F401

        return "panns" if os.path.exists(os.path.expanduser("~/panns_data/Cnn14_mAP=0.431.pth")) else "heuristic"
    except ImportError:
        return "heuristic"


def music_prob(audio: np.ndarray, sr: int, which: str | None = None) -> np.ndarray:
    which = which or "heuristic"
    if which == "panns":
        return panns_prob(audio, sr)
    return heuristic_prob(audio, sr)
