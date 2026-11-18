"""Source separation with Demucs htdemucs (MIT): vocals / drums / bass / other. Runs only on windows with music.
Uses Metal (MPS) on the M1 when available, CPU otherwise."""

from __future__ import annotations

from functools import lru_cache

import numpy as np

MODEL_SR = 44100


@lru_cache(maxsize=1)
def _model(name: str = "htdemucs"):
    from demucs.pretrained import get_model

    m = get_model(name)
    m.eval()
    return m


def device() -> str:
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    return "cuda" if torch.cuda.is_available() else "cpu"


def separate(audio: np.ndarray, sr: int) -> dict[str, np.ndarray]:
    """Mono float audio in -> dict of mono stems at the same sample rate."""
    import torch
    from demucs.apply import apply_model
    from scipy.signal import resample_poly

    g = np.gcd(sr, MODEL_SR)
    x = resample_poly(audio, MODEL_SR // g, sr // g).astype(np.float32)
    m = _model()
    wav = torch.from_numpy(np.stack([x, x]))[None]
    ref = wav.mean(1)
    mean, std = ref.mean(), ref.std() + 1e-8
    with torch.no_grad():
        out = apply_model(m, (wav - mean) / std, device=device(), split=True, overlap=0.25, progress=False)[0]
    out = out * std + mean
    stems = {}
    for i, name in enumerate(m.sources):
        s = out[i].mean(0).cpu().numpy()
        s = resample_poly(s, sr // g, MODEL_SR // g)[: len(audio)]
        stems[name] = np.pad(s, (0, len(audio) - len(s))).astype(np.float32)
    return stems
