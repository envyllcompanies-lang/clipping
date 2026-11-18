"""Synthetic reference videos with known style parameters (for the style-study backtest)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

FONT = str(
    __import__("pathlib").Path(__file__).resolve().parents[2] / "assets/fonts/Montserrat-ExtraBold.ttf"
)
SOURCES = [
    "testsrc2",
    "testsrc",
    "mandelbrot=start_scale=2:end_scale=2:start_x=-0.75",
    "yuvtestsrc",
    "zoneplate",
    "mandelbrot=start_scale=0.5:end_scale=0.5:start_x=-1.2:start_y=0.2",
    "mandelbrot=start_scale=1:end_scale=1:start_x=-0.4:start_y=0.6",
]  # textured; no full-width bands
WORDS = [
    "HE",
    "DID",
    "NOT",
    "SEE",
    "THAT",
    "COMING",
    "FIVE",
    "STARS",
    "ONE",
    "TIRE",
    "NO",
    "WAY",
    "BRO",
    "LOOK",
]


def make(
    out: Path,
    seed: int,
    *,
    seconds: float = 12,
    shot_s: float = 2.0,
    cap_y: float = 0.5,
    caps: bool = True,
    fill: str = "FFFFFF",
    stacked: float | None = 0.4,
    zooms: int = 0,
    W: int = 360,
    H: int = 640,
) -> dict:
    rng = np.random.default_rng(seed)
    n_shots = int(np.ceil(seconds / shot_s))
    parts, filters = [], []
    for k in range(n_shots):
        src = SOURCES[(seed + k) % len(SOURCES)]
        name, _, opts = src.partition("=")
        parts += [
            "-t",
            str(shot_s),
            "-f",
            "lavfi",
            "-i",
            f"{name}=size={W}x{H}:rate=30" + (f":{opts}" if opts else ""),
        ]
        filters.append(f"[{k}:v]format=yuv420p,setsar=1[s{k}]")
    chain = (
        ";".join(filters)
        + ";"
        + "".join(f"[s{k}]" for k in range(n_shots))
        + f"concat=n={n_shots}:v=1:a=0[g]"
    )
    last = "g"
    if zooms:
        zt = sorted(rng.uniform(1, seconds - 1.5, zooms))
        expr = "+".join(f"0.15*between(t,{t:.2f},{t + 0.8:.2f})*min(1,(t-{t:.2f})/0.2)" for t in zt)
        zexpr = expr.replace("t,", "(in/30),").replace("(t-", "((in/30)-")
        chain += f";[g]zoompan=z='1+{zexpr}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30,setsar=1[z]"
        last = "z"
    if stacked:
        top = int(H * stacked)
        # facecam panel: a different source (the streamer's camera), gameplay panel: crop of the game feed
        parts += ["-t", str(seconds), "-f", "lavfi", "-i", f"color=c=0x2B2F3A:size={W}x{top}:rate=30"]
        cam_idx = n_shots
        chain += (
            f";[{last}]crop={W}:{H - top}:0:{(H - top) // 4}[game];[{cam_idx}:v]format=yuv420p,setsar=1,"
            f"drawbox=x='{W // 3}+20*sin(t*2)':y={top // 4}:w={W // 3}:h={top // 2}:color=0xC8A082:t=fill[cam];"
            f"[cam][game]vstack[st]"
        )
        last = "st"
    txts = []
    for k in range(int(seconds / 1.0)):
        words = " ".join(rng.choice(WORDS, 3))
        words = words if caps else words.capitalize().lower().capitalize()
        txts.append(
            f"drawtext=fontfile={FONT}:text='{words}':fontsize={int(H * 0.055)}:fontcolor=0x{fill}:borderw=4:bordercolor=black:"
            f"x=(w-text_w)/2:y={cap_y}*h-text_h/2:enable='between(t,{k},{k + 0.95})'"
        )
    chain += f";[{last}]" + ",".join(txts) + "[out]"
    audio_idx = n_shots + (1 if stacked else 0)
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        *parts,
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=300:duration={seconds}",
        "-filter_complex",
        chain,
        "-map",
        "[out]",
        "-map",
        f"{audio_idx}:a",
        "-t",
        str(seconds),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-c:a",
        "aac",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return {
        "cuts_per_10s": (n_shots - 1) / seconds * 10,
        "cap_y": cap_y,
        "caps": caps,
        "fill": fill,
        "layout": "stacked" if stacked else "full",
        "split": stacked,
        "zooms": zooms,
    }
