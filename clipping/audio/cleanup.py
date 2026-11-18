"""Audio Cleanup & Music Removal per window (doc 07).

1. Detect music per second (cheap). No music -> skip separation.
2. Separate (Demucs) only where music was found.
3. Remix music spans: voice full, game effects ducked, music stems dropped; crossfade into untouched spans.
4. Residual check on the cleaned mix -> music_risk.
5. Loudness: two-pass loudnorm to -14 LUFS, -1 dBTP, light compression (in the render step for the final mix;
   here for clean_mix.wav).
Outputs: voice.wav (transcription), clean_mix.wav (render), per-second music probability.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from clipping.audio import music as music_mod

THRESH = 0.5
MIN_MUSIC_S = 3  # radio is sustained; shorter blips are speech/SFX artifacts
RISK_THRESH = 0.85  # separated audio carries artifacts the cheap detector over-reads
RISK_SHARE = 0.15


@dataclass
class CleanResult:
    voice: np.ndarray
    clean: np.ndarray
    music_before: np.ndarray
    music_after: np.ndarray
    separated: bool
    music_spans: list[tuple[int, int]] = field(default_factory=list)
    music_risk: bool = False
    risk_spans: list[tuple[int, int]] = field(default_factory=list)


def spans(mask: np.ndarray, min_len: int = 1, pad: int = 1) -> list[tuple[int, int]]:
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            if j - i >= min_len:
                out.append((max(0, i - pad), min(n, j + pad)))
            i = j
        else:
            i += 1
    merged: list[tuple[int, int]] = []
    for a, b in out:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


def _envelope(n: int, sr: int, sp: list[tuple[int, int]], fade_s: float = 0.25) -> np.ndarray:
    env = np.zeros(n, np.float32)
    f = int(fade_s * sr)
    for a, b in sp:
        lo, hi = a * sr, min(n, b * sr)
        env[lo:hi] = 1
        if f:
            ramp = np.linspace(0, 1, f, dtype=np.float32)
            s0 = max(0, lo - f)
            env[s0:lo] = np.maximum(env[s0:lo], ramp[f - (lo - s0) :])
            e1 = min(n, hi + f)
            env[hi:e1] = np.maximum(env[hi:e1], ramp[::-1][: e1 - hi])
    return env


def clean(
    audio: np.ndarray, sr: int, detector: str = "heuristic", separator=None, sfx_gain_db: float = -18.0
) -> CleanResult:
    before = music_mod.music_prob(audio, sr, detector)
    sp = spans(before > THRESH, min_len=MIN_MUSIC_S)
    if not sp:
        return CleanResult(audio.copy(), audio.copy(), before, before, False)
    if separator is None:
        from clipping.audio.separate import separate as separator
    stems = separator(audio, sr)
    vocals = stems["vocals"]
    sfx = stems.get("other", 0) * 10 ** (sfx_gain_db / 20) + stems.get("drums", 0) * 10 ** (
        (sfx_gain_db - 12) / 20
    )
    remix = (vocals + sfx).astype(np.float32)
    env = _envelope(len(audio), sr, sp)
    cleaned = (env * remix + (1 - env) * audio).astype(np.float32)
    voice = (env * vocals + (1 - env) * audio).astype(np.float32)
    after = music_mod.music_prob(cleaned, sr, detector)
    risk_mask = after > RISK_THRESH
    risk = spans(risk_mask, pad=0)
    return CleanResult(
        voice,
        cleaned,
        before,
        after,
        True,
        sp,
        bool(risk_mask.mean() > RISK_SHARE or sum(b - a for a, b in risk) > 2),
        risk,
    )


def loudnorm(src: Path, dst: Path, target: float = -14.0, tp: float = -1.0, lra: float = 11.0) -> dict:
    """Two-pass FFmpeg loudnorm with light compression."""
    from clipping.core import media

    p1 = media.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(src),
            "-af",
            f"acompressor=threshold=-18dB:ratio=3:attack=10:release=200,loudnorm=I={target}:TP={tp}:LRA={lra}:print_format=json",
            "-f",
            "null",
            "-",
        ]
    )
    txt = p1.stderr
    m = json.loads(txt[txt.rfind("{") : txt.rfind("}") + 1])
    af = (
        f"acompressor=threshold=-18dB:ratio=3:attack=10:release=200,loudnorm=I={target}:TP={tp}:LRA={lra}:"
        f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
        f"offset={m['target_offset']}:linear=true"
    )
    media.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", af, "-ar", "48000", str(dst)])
    return m


def process_window(c, window_id: int, detector: str | None = None) -> dict:
    """Job handler: window file -> voice.wav + clean_mix.wav in work/<window>/, flags music_risk."""
    from clipping.audio.fingerprint import _resample  # noqa: F401
    from clipping.core import db, media
    from clipping.eval.audiofx import write_wav
    from clipping.storage import files

    w = db.one(c, 'SELECT * FROM "window" WHERE id=%s', window_id)
    sr = 16000
    audio = media.decode_audio(w["path"], sr)
    res = clean(audio, sr, detector or music_mod.backend())
    wd = files.work_dir(c, f"w{window_id}")
    write_wav(wd / "voice.wav", res.voice, sr)
    raw = write_wav(wd / "clean_raw.wav", res.clean, sr)
    loudnorm(raw, wd / "clean_mix.wav")
    raw.unlink()
    info = {
        "separated": res.separated,
        "music_spans": res.music_spans,
        "risk_spans": res.risk_spans,
        "music_after": np.round(res.music_after, 3).tolist(),
        "voice": str(wd / "voice.wav"),
        "clean_mix": str(wd / "clean_mix.wav"),
    }
    c.execute(
        'UPDATE "window" SET music_risk=%s, audio=%s, status=%s WHERE id=%s',
        (res.music_risk, db.j(info), "cleaned", window_id),
    )
    return info
