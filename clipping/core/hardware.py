"""Detect RAM/platform at startup and size models (doc 06, build plan Hardware)."""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass


def total_ram_bytes() -> int:
    if platform.system() == "Darwin":
        out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True)
        return int(out.stdout.strip())
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError):
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return int(line.split()[1]) * 1024
    return 8 * 1024**3


@dataclass(frozen=True)
class Profile:
    ram_gb: float
    is_mac: bool
    whisper_model: str
    diarization: bool
    parallel_heavy: int
    encoder: str


def profile(ram_bytes: int | None = None, system: str | None = None) -> Profile:
    ram = (ram_bytes if ram_bytes is not None else total_ram_bytes()) / 1024**3
    system = system or platform.system()
    is_mac = system == "Darwin"
    if ram < 12:
        model, diar, par = "small", False, 1
    elif ram < 24:
        model, diar, par = "large-v3-turbo", True, 2
    else:
        model, diar, par = "large-v3", True, 2
    return Profile(round(ram, 1), is_mac, model, diar, par, "h264_videotoolbox" if is_mac else "libx264")
