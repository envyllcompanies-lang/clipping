"""Synthetic audio for the audio set (doc 30): TTS speech (ffmpeg flite), game SFX, and distinct synthetic songs.

Songs are procedurally generated (chords, bassline, drums) so each has a unique fingerprint, standing in for
in-game radio tracks. Deterministic per seed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

SR = 16000
VOICES = ["kal", "slt", "rms", "awb"]
LINES = [
    "bro what are you doing get in the car right now",
    "no no no the cops are right behind us go left",
    "chat did you see that he just flew off the bridge",
    "okay okay we have five stars this is so bad",
    "wait wait wait look at this guy over here",
    "i cannot believe that just happened that was insane",
]


def tts(text: str, voice: str = "kal", sr: int = SR) -> np.ndarray:
    p = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"flite=text='{text}':voice={voice}",
            "-ac",
            "1",
            "-ar",
            str(sr),
            "-f",
            "f32le",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    return np.frombuffer(p.stdout, np.float32).copy()


def song(seed: int, seconds: float, sr: int = SR) -> np.ndarray:
    rng = np.random.default_rng(seed)
    bpm = rng.uniform(80, 150)
    beat = 60 / bpm
    root = 110 * 2 ** (rng.integers(0, 12) / 12)
    prog = rng.choice([[0, 5, 7, 3], [0, 7, 9, 5], [0, 3, 5, 7], [0, 9, 5, 7]])
    t = np.arange(int(seconds * sr)) / sr
    out = np.zeros_like(t)
    bar = 4 * beat
    for i, start in enumerate(np.arange(0, seconds, bar)):
        sl = (t >= start) & (t < start + bar)
        f0 = root * 2 ** (prog[i % 4] / 12)
        tt = t[sl] - start
        env = np.exp(-tt / (bar * 0.8))
        for semi in (0, 4 if rng.random() < 0.6 else 3, 7):
            f = f0 * 2 * 2 ** (semi / 12)
            out[sl] += (
                0.12
                * env
                * (
                    np.sin(2 * np.pi * f * tt)
                    + 0.4 * np.sin(4 * np.pi * f * tt)
                    + 0.2 * np.sin(6 * np.pi * f * tt)
                )
            )
        out[sl] += 0.2 * np.sign(np.sin(2 * np.pi * f0 / 2 * tt)) * 0.5 * env
        mel = f0 * 4 * 2 ** (rng.choice([0, 2, 4, 7, 9, 12], size=8) / 12)
        for k, mf in enumerate(mel):
            ms = (tt >= k * bar / 8) & (tt < (k + 1) * bar / 8)
            mt = tt[ms] - k * bar / 8
            out[np.where(sl)[0][ms]] += 0.1 * np.exp(-mt * 6) * np.sin(2 * np.pi * mf * mt)
    for bstart in np.arange(0, seconds, beat):  # drums
        k0 = int(bstart * sr)
        n = int(0.15 * sr)
        tk = np.arange(min(n, len(out) - k0)) / sr
        out[k0 : k0 + len(tk)] += 0.5 * np.sin(2 * np.pi * 60 * tk * np.exp(-tk * 20)) * np.exp(-tk * 25)
        h0 = int((bstart + beat / 2) * sr)
        hn = min(int(0.04 * sr), max(0, len(out) - h0))
        out[h0 : h0 + hn] += 0.08 * rng.normal(size=hn) * np.exp(-np.arange(hn) / sr * 120)
    return (out / (np.abs(out).max() + 1e-9) * 0.5).astype(np.float32)


def sfx(seed: int, seconds: float, sr: int = SR) -> np.ndarray:
    """Engine hum plus explosions/crashes and gunshots: broadband, non-tonal, non-rhythmic."""
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    rpm = 30 + 10 * np.cumsum(rng.normal(0, 0.002, n))
    engine = (
        0.05 * np.sin(2 * np.pi * np.cumsum(rpm) / sr) * (1 + 0.3 * rng.normal(size=n).cumsum() / np.sqrt(n))
    )
    out = engine + 0.01 * rng.normal(size=n)
    for _ in range(rng.poisson(seconds / 6)):
        k0 = int(rng.uniform(0, max(1, n - sr)))
        ln = int(rng.uniform(0.3, 1.5) * sr)
        noise = np.cumsum(rng.normal(size=ln))
        noise = noise / (np.abs(noise).max() + 1e-9)
        out[k0 : k0 + ln] += (
            0.6 * noise[: len(out[k0 : k0 + ln])] * np.exp(-np.arange(len(out[k0 : k0 + ln])) / sr * 3)
        )
    return out.astype(np.float32) * (t >= 0)


def speech_track(seed: int, seconds: float, sr: int = SR) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.zeros(int(seconds * sr), np.float32)
    pos = 0
    while pos < len(out):
        seg = tts(str(rng.choice(LINES)), str(rng.choice(VOICES)), sr) * float(rng.uniform(0.6, 1.0))
        k = min(len(seg), len(out) - pos)
        out[pos : pos + k] += seg[:k]
        pos += k + int(rng.uniform(0.2, 1.5) * sr)
    return out


def mixture(seed: int, seconds: float = 20, music: bool = True, sr: int = SR, music_db: float = -6) -> dict:
    v = speech_track(seed, seconds, sr)
    g = sfx(seed + 1000, seconds, sr)
    m = song(seed + 2000, seconds, sr) * (10 ** (music_db / 20)) if music else np.zeros_like(v)
    return {
        "voice": v,
        "sfx": g,
        "music": m,
        "mix": (v + 0.5 * g + m).astype(np.float32),
        "sr": sr,
        "song_seed": seed + 2000,
    }


def write_wav(path: Path, x: np.ndarray, sr: int) -> Path:
    import soundfile as sf

    sf.write(str(path), x, sr)
    return path
