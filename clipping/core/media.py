"""ffmpeg/ffprobe helpers shared by components."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np


def run(cmd: list[str], timeout: float = 600) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed ({p.returncode}): {p.stderr[-1500:]}")
    return p


def probe(path: str | Path) -> dict:
    p = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    return json.loads(p.stdout)


def duration(path: str | Path) -> float:
    return float(probe(path)["format"]["duration"])


def decode_audio(
    path: str | Path, sr: int = 8000, start: float | None = None, dur: float | None = None
) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path)]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    p = subprocess.run(cmd, capture_output=True, timeout=1200)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode()[-800:])
    return np.frombuffer(p.stdout, dtype=np.float32).copy()


def decode_frames(
    path: str | Path,
    fps: float = 2,
    width: int = 240,
    start: float | None = None,
    dur: float | None = None,
    gray: bool = False,
    keyframes_only: bool = False,
) -> np.ndarray:
    info = [s for s in probe(path)["streams"] if s["codec_type"] == "video"][0]
    w0, h0 = int(info["width"]), int(info["height"])
    height = int(round(h0 * width / w0 / 2) * 2)
    cmd = ["ffmpeg", "-v", "error"]
    if keyframes_only:
        cmd += ["-skip_frame", "nokey"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path)]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    pix = "gray" if gray else "rgb24"
    vf = f"scale={width}:{height}" if keyframes_only else f"fps={fps},scale={width}:{height}"
    cmd += (
        ["-vsync", "0", "-vf", vf, "-f", "rawvideo", "-pix_fmt", pix, "-"]
        if keyframes_only
        else ["-vf", vf, "-f", "rawvideo", "-pix_fmt", pix, "-"]
    )
    p = subprocess.run(cmd, capture_output=True, timeout=1200)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode()[-800:])
    ch = 1 if gray else 3
    arr = np.frombuffer(p.stdout, dtype=np.uint8)
    n = arr.size // (width * height * ch)
    shape = (n, height, width) if gray else (n, height, width, 3)
    return arr[: n * width * height * ch].reshape(shape)


def loudness(path: str | Path) -> dict:
    p = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    txt = p.stderr
    out: dict = {}
    summary = txt[txt.rfind("Summary:") :]
    for line in summary.splitlines():
        line = line.strip()
        if line.startswith("I:"):
            out["integrated"] = float(line.split()[1])
        elif line.startswith("LRA:"):
            out["lra"] = float(line.split()[1])
        elif line.startswith("Peak:"):
            out["true_peak"] = float(line.split()[1])
    return out


def iter_frames(
    path: str | Path,
    fps: float,
    start: float = 0.0,
    dur: float | None = None,
    size: tuple[int, int] | None = None,
):
    """Stream RGB frames one at a time (constant memory) at a fixed fps, starting at `start` (accurate seek)."""
    info = [s for s in probe(path)["streams"] if s["codec_type"] == "video"][0]
    w, h = size or (int(info["width"]), int(info["height"]))
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(path)]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = w * h * 3
    try:
        while True:
            buf = proc.stdout.read(n)
            if len(buf) < n:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()
