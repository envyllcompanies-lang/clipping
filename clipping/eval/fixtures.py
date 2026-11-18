"""Synthetic media fixtures (fast, deterministic) shared by tests and backtests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from clipping.core import media


def make_source(
    out: Path,
    seconds: float,
    size: str = "640x360",
    fps: int = 30,
    gop: int = 30,
    audio: str = "sine=frequency=440",
) -> Path:
    media.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={size}:rate={fps}",
            "-f",
            "lavfi",
            "-i",
            audio,
            "-t",
            str(seconds),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-g",
            str(gop),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-f",
            "mpegts",
            str(out),
        ]
    )
    return out


def make_segments(
    seg_dir: Path, minutes: int, base_epoch: int, seg_s: int = 60, size: str = "320x180"
) -> list[Path]:
    """A recorded stream as epoch-named segments, built in non-real time."""
    seg_dir.mkdir(parents=True, exist_ok=True)
    src = seg_dir / "_src.ts"
    make_source(src, minutes * seg_s, size=size, fps=15, gop=15)
    media.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(src),
            "-map",
            "0",
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_time",
            str(seg_s),
            "-reset_timestamps",
            "1",
            "-segment_format",
            "mpegts",
            str(seg_dir / "n%05d.ts"),
        ]
    )
    src.unlink()
    out, t = [], base_epoch
    for p in sorted(seg_dir.glob("n*.ts")):
        d = media.duration(p)
        dst = seg_dir / f"{t}.ts"
        p.rename(dst)
        out.append(dst)
        t += round(d)
    return out


def realtime_command(seconds: int, seg_dir: Path, seg_s: int = 2) -> str:
    return (
        f"ffmpeg -v error -re -f lavfi -i testsrc2=size=160x90:rate=15 -f lavfi -i sine -t {seconds} -c:v libx264 "
        f"-preset ultrafast -g 15 -c:a aac -f mpegts - | ffmpeg -v error -probesize 32k -analyzeduration 200000 -i - -map 0 -c copy -f segment -segment_time {seg_s} "
        f"-segment_format mpegts -reset_timestamps 1 -strftime 1 {seg_dir}/%s.ts"
    )


def has_ffmpeg() -> bool:
    return subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0
