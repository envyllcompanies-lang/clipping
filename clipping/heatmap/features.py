"""Per-second features shared by the live heatmap (per recorded segment) and the real-dataset builder, so backtests
grade exactly what production computes: 10 Hz loudness, voice excitement, music probability, spectral centroid,
flux, high-band ratio, onset density, and from 160p/240p frames at 2 fps: motion, brightness, scene change,
letterbox ratio and edge density (inputs to docs 05, 31, 32)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from clipping.core import media

SR = 8000
KEYS = [
    "audio_db10",
    "voice",
    "music",
    "centroid",
    "flux",
    "hiband",
    "onsets",
    "motion",
    "bright",
    "scene",
    "letterbox",
    "edges",
]


def compute(
    audio_src: Path | str, video_src: Path | str | None, T: int, keyframes_only: bool = False
) -> dict[str, np.ndarray]:
    from clipping.audio import music as music_mod
    from clipping.heatmap import signals

    a = media.decode_audio(audio_src, SR)
    a = a[: T * SR] if len(a) >= T * SR else np.pad(a, (0, T * SR - len(a)))
    db10 = signals.rms_db(a, SR, 0.1)[: T * 10]
    voice = signals.voice_excitement(a, SR, T)
    mus = music_mod.music_prob(a, SR)[:T]
    mus = np.pad(mus, (0, T - len(mus)))
    frames = a.reshape(T * 10, SR // 10)
    spec = np.abs(np.fft.rfft(frames * np.hanning(SR // 10), axis=1))
    freqs = np.fft.rfftfreq(SR // 10, 1 / SR)
    cent = (spec * freqs).sum(1) / (spec.sum(1) + 1e-9)
    flux = np.r_[0, np.clip(np.diff(np.log(spec + 1e-6), axis=0), 0, None).mean(1)]
    hi = spec[:, freqs > 2000].sum(1) / (spec.sum(1) + 1e-9)

    def per(x, fn=np.mean):
        return fn(x.reshape(T, 10), axis=1)

    onset = per((flux > np.percentile(flux, 95)).astype(float), np.sum)
    out_v = {k: np.zeros(T) for k in ("motion", "bright", "scene", "letterbox", "edges")}
    fr = np.zeros((0, 90, 160), np.uint8)
    if video_src is not None:
        try:
            fr = media.decode_frames(video_src, fps=2, width=160, gray=True, keyframes_only=keyframes_only)
            if (
                keyframes_only and len(fr) > 1
            ):  # 1080p60 live segments: keyframes (~0.5 fps) resampled onto the 2 fps grid
                idx = np.minimum((np.arange(T * 2) * len(fr) / (T * 2)).astype(int), len(fr) - 1)
                fr = fr[idx]
        except Exception:  # noqa: BLE001 - audio-only source
            pass
    n = min(len(fr), T * 2)
    if n >= 2:
        f = fr[:n].astype(np.float32)
        motion = np.r_[0, np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))]
        bright = f.mean(axis=(1, 2))
        hist = np.array([np.histogram(x, 32, (0, 255))[0] / x.size for x in f])
        scene = np.r_[0, 0.5 * np.abs(np.diff(hist, axis=0)).sum(1)]
        rows = f.mean(axis=2)
        h = f.shape[1]
        letter = ((rows[:, : h // 8] < 18).mean(1) + (rows[:, -h // 8 :] < 18).mean(1)) / 2
        edges = np.abs(np.diff(f, axis=2)).mean(axis=(1, 2))
        m = n // 2
        for k, v, fn in (
            ("motion", motion, np.mean),
            ("bright", bright, np.mean),
            ("scene", scene, np.max),
            ("letterbox", letter, np.mean),
            ("edges", edges, np.mean),
        ):
            out_v[k][:m] = fn(v[: m * 2].reshape(m, 2), axis=1)
    return {
        "audio_db10": db10.astype(np.float32),
        "voice": voice.astype(np.float32),
        "music": mus.astype(np.float32),
        "centroid": per(cent).astype(np.float32),
        "flux": per(flux).astype(np.float32),
        "hiband": per(hi).astype(np.float32),
        "onsets": onset.astype(np.float32),
        **{k: v.astype(np.float32) for k, v in out_v.items()},
    }
