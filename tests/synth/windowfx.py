"""A synthetic candidate window file: reframe-style gameplay with a facecam, TTS speech + game SFX, a crash flash."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from tests.synth import audiofx, reframefx


def make(
    out: Path, seed: int = 1, seconds: float = 60, fps: float = 10, cam: bool = True, music: bool = False
) -> dict:
    s = reframefx.stream(seed, seconds=seconds, fps=fps, cam=cam)
    frames = s["frames"].copy()
    crash = seconds * 0.6
    k = int(crash * fps)
    frames[k : k + int(fps)] = np.clip(frames[k : k + int(fps)].astype(np.int16) + 120, 0, 255).astype(
        np.uint8
    )
    mix = audiofx.mixture(seed, seconds, music=music, music_db=-6)
    audio = mix["mix"].copy()
    a = int(crash * audiofx.SR)
    audio[a : a + audiofx.SR] += (
        0.6
        * np.random.default_rng(seed).normal(0, 1, audiofx.SR).astype(np.float32)
        * np.exp(-np.arange(audiofx.SR) / 4000)
    )
    wav = out.with_suffix(".wav")
    audiofx.write_wav(wav, np.clip(audio, -1, 1), audiofx.SR)
    h, w = frames.shape[1:3]
    p = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{w}x{h}",
            "-r",
            str(fps),
            "-i",
            "-",
            "-i",
            str(wav),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-g",
            str(int(fps)),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            "-f",
            "mpegts",
            str(out),
        ],
        stdin=subprocess.PIPE,
    )
    p.stdin.write(frames.tobytes())
    p.stdin.close()
    p.wait()
    wav.unlink()
    return {
        "path": str(out),
        "crash_t": crash,
        "subject": s["subject"],
        "cam_box": s["cam_box"],
        "cuts": s["cuts"],
        "song_seed": mix["song_seed"] if music else None,
    }
