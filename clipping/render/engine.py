"""Render Engine (doc 12): edit plan + crop plan + captions -> platform-ready MP4.

Frames: each planned segment is decoded from the window, cropped/zoomed/composited per frame in numpy following
the crop plan (deterministic), and piped to one FFmpeg encode that burns the ASS captions (libass) and muxes the
audio. Audio: segments cut from clean_mix.wav with 30 ms crossfades, whoosh on the cold-open jump, two-pass
loudnorm to -14 LUFS / -1 dBTP, AAC 192 kbps 48 kHz stereo. Encoder: h264_videotoolbox on macOS, libx264
elsewhere (and as the retry). Output written to a temp name and renamed when validated.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from clipping.core import hardware, media

SR = 48000


@dataclass
class RenderResult:
    path: str
    duration: float
    validation: dict
    phash: str
    thumbnail_jpg: bytes
    encoder: str
    cached: bool = False


def input_hash(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        if isinstance(p, (str, Path)) and os.path.exists(str(p)):
            st = os.stat(p)
            h.update(f"{p}:{st.st_size}:{int(st.st_mtime)}".encode())
        else:
            h.update(json.dumps(p, sort_keys=True, default=str).encode())
    return h.hexdigest()[:20]


def _interp_box(kfs: list[dict], t: float) -> np.ndarray:
    if len(kfs) == 1 or t <= kfs[0]["t"]:
        return np.array(kfs[0]["box"], float)
    if t >= kfs[-1]["t"]:
        return np.array(kfs[-1]["box"], float)
    ts = [k["t"] for k in kfs]
    i = int(np.searchsorted(ts, t))
    a, b = kfs[i - 1], kfs[i]
    w = (t - a["t"]) / max(b["t"] - a["t"], 1e-6)
    return (1 - w) * np.array(a["box"], float) + w * np.array(b["box"], float)


def zoom_factor(zooms: list[dict], t: float) -> tuple[float, tuple[float, float] | None]:
    """110-120% punch-in: ease in (150-250 ms), hold, ease out."""
    for z in zooms:
        t0 = z["t"]
        tin, hold, tout = z["in_s"], z["hold_s"], z["out_s"]
        if t0 <= t <= t0 + tin + hold + tout:
            if t < t0 + tin:
                k = (t - t0) / tin
            elif t < t0 + tin + hold:
                k = 1.0
            else:
                k = 1 - (t - t0 - tin - hold) / tout
            k = 0.5 - 0.5 * np.cos(np.pi * np.clip(k, 0, 1))
            return 1 + (z["scale"] - 1) * k, tuple(z.get("toward") or ()) or None
    return 1.0, None


def compose(frame: np.ndarray, t: float, cp: dict, src_scale: tuple[float, float]) -> np.ndarray:
    """One output frame. Crop-plan boxes are in stream pixels; src_scale maps them to this frame's pixels."""
    Wc, Hc = cp["canvas"]
    canvas = np.zeros((Hc, Wc, 3), np.uint8)
    sx, sy = src_scale
    z, toward = zoom_factor(cp.get("zooms", []), t)
    for p in cp["panels"]:
        x, y, w, h = _interp_box(p["keyframes"], t)
        if p["name"] == "game" and z > 1.0:
            cx, cy = toward if toward else (x + w / 2, y + h / 2)
            cx = np.clip(cx, x + w / (2 * z), x + w - w / (2 * z))
            cy = np.clip(cy, y + h / (2 * z), y + h - h / (2 * z))
            w, h = w / z, h / z
            x, y = cx - w / 2, cy - h / 2
        x0, y0 = int(round(x / sx)), int(round(y / sy))
        x1, y1 = int(round((x + w) / sx)), int(round((y + h) / sy))
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(frame.shape[1], max(x1, x0 + 2)), min(frame.shape[0], max(y1, y0 + 2))
        crop = frame[y0:y1, x0:x1]
        dx, dy, dw, dh = p["dst"]
        tile = cv2.resize(
            crop, (dw, dh), interpolation=cv2.INTER_CUBIC if dw > crop.shape[1] else cv2.INTER_AREA
        )
        if p.get("bubble"):
            m = np.zeros((dh, dw), np.uint8)
            cv2.rectangle(m, (0, 0), (dw - 1, dh - 1), 255, -1)
            r = min(dw, dh) // 6
            m[:r, :r] = 0
            m[:r, -r:] = 0
            m[-r:, :r] = 0
            m[-r:, -r:] = 0
            for cx, cy in ((r, r), (dw - r - 1, r), (r, dh - r - 1), (dw - r - 1, dh - r - 1)):
                cv2.circle(m, (cx, cy), r, 255, -1)
            region = canvas[dy : dy + dh, dx : dx + dw]
            region[m > 0] = tile[m > 0]
        else:
            canvas[dy : dy + dh, dx : dx + dw] = tile
    return canvas


def whoosh(sr: int = SR, dur: float = 0.35) -> np.ndarray:
    """Our own synthesized whoosh (filtered noise sweep): no third-party SFX license needed."""
    n = int(sr * dur)
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 1, n)
    from scipy.signal import butter, sosfilt

    out = np.zeros(n)
    for k in range(8):
        a, b = k * n // 8, (k + 1) * n // 8
        f = 300 + 3000 * (k / 7)
        sos = butter(2, [f * 0.7, f * 1.3], btype="band", fs=sr, output="sos")
        out[a:b] = sosfilt(sos, noise[a:b])
    env = np.sin(np.linspace(0, np.pi, n)) ** 2
    return (0.25 * out * env / (np.abs(out).max() + 1e-9)).astype(np.float32)


def build_audio(
    clean_wav: str,
    segments: list[dict],
    out_wav: Path,
    *,
    cold_open: bool,
    xfade_s: float = 0.03,
    sfx_gain_db: float = -10,
) -> float:
    import soundfile as sf

    x, sr = sf.read(clean_wav, dtype="float32", always_2d=True)
    if sr != SR:
        from scipy.signal import resample_poly

        g = np.gcd(sr, SR)
        x = resample_poly(x, SR // g, sr // g, axis=0).astype(np.float32)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    parts = []
    xf = int(xfade_s * SR)
    for seg in segments:
        a = x[int(seg["start"] * SR) : int(seg["end"] * SR)].copy()
        want = int(round((seg["end"] - seg["start"]) * SR))
        if len(a) < want:
            a = np.pad(a, ((0, want - len(a)), (0, 0)))
        ramp = np.linspace(0, 1, min(xf, len(a) // 2))[:, None]
        a[: len(ramp)] *= ramp
        a[len(a) - len(ramp) :] *= ramp[::-1]
        parts.append(a)
    y = np.concatenate(parts) if parts else np.zeros((SR, 2), np.float32)
    if cold_open and len(segments) > 1:
        wz = whoosh() * 10 ** (sfx_gain_db / 20)
        k = int(round((segments[0]["end"] - segments[0]["start"]) * SR)) - len(wz) // 2
        k = max(0, k)
        y[k : k + len(wz)] += wz[: len(y) - k, None]
    sf.write(str(out_wav), np.clip(y, -1, 1), SR)
    return len(y) / SR


def loudnorm_pass(src: Path, dst: Path, target: float = -14.0, tp: float = -1.0) -> None:
    p1 = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(src),
            "-af",
            f"loudnorm=I={target}:TP={tp}:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    txt = p1.stderr
    m = json.loads(txt[txt.rfind("{") : txt.rfind("}") + 1])
    af = (
        f"loudnorm=I={target}:TP={tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
        f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample={SR}"
    )
    media.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", af, "-ac", "2", str(dst)])


def encoder_args(name: str) -> list[str]:
    if name == "h264_videotoolbox":
        return [
            "-c:v",
            "h264_videotoolbox",
            "-profile:v",
            "high",
            "-b:v",
            "11M",
            "-maxrate",
            "14M",
            "-allow_sw",
            "1",
        ]
    return [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast" if name == "libx264-retry" else "fast",
        "-profile:v",
        "high",
        "-crf",
        "20",
        "-maxrate",
        "12M",
        "-bufsize",
        "24M",
    ]


def render(
    window_path: str,
    clean_wav: str,
    plan: dict,
    crop_plan: dict,
    ass_path: str | None,
    out_path: str,
    *,
    fps: float | None = None,
    encoder: str | None = None,
    fonts_dir: str | None = None,
    sfx: bool = True,
) -> RenderResult:
    out = Path(out_path)
    info = [s for s in media.probe(window_path)["streams"] if s["codec_type"] == "video"][0]
    sw, sh = int(info["width"]), int(info["height"])
    num, den = (int(v) for v in info.get("avg_frame_rate", "30/1").split("/"))
    src_fps = num / max(den, 1) if num else 30.0
    fps = fps or (60.0 if src_fps > 45 else 30.0)
    stream_w = crop_plan["source"]["width"]
    stream_h = crop_plan["source"]["height"]
    src_scale = (stream_w / sw, stream_h / sh)
    encoder = encoder or hardware.profile().encoder
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "a.wav"
        wav_n = Path(d) / "an.wav"
        dur = build_audio(clean_wav, plan["segments"], wav, cold_open=bool(plan.get("hook")) and sfx)
        loudnorm_pass(wav, wav_n)
        tmp = out.with_suffix(".part.mp4")
        vf = f"ass={ass_path}" + (f":fontsdir={fonts_dir}" if fonts_dir else "") if ass_path else "null"
        last_err = ""
        for enc in [encoder, "libx264-retry"] if encoder != "libx264-retry" else [encoder]:
            cmd = [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                f"{crop_plan['canvas'][0]}x{crop_plan['canvas'][1]}",
                "-r",
                str(fps),
                "-i",
                "-",
                "-i",
                str(wav_n),
                "-vf",
                f"{vf},format=yuv420p",
                *encoder_args(enc),
                "-r",
                str(fps),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                str(SR),
                "-ac",
                "2",
                "-shortest",
                "-movflags",
                "+faststart",
                str(tmp),
            ]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                for seg in plan["segments"]:
                    n = int(round((seg["end"] - seg["start"]) * fps))
                    last = np.zeros((sh, sw, 3), np.uint8)
                    it = media.iter_frames(
                        window_path, fps, seg["start"], seg["end"] - seg["start"] + 1.0 / fps
                    )
                    for i in range(n):
                        last = next(it, last)  # hold the last frame if the decoder ends a frame early
                        proc.stdin.write(
                            compose(last, seg["start"] + i / fps, crop_plan, src_scale).tobytes()
                        )
                    it.close()
                proc.stdin.close()
                err = proc.stderr.read().decode()
                if proc.wait() == 0:
                    used = enc
                    break
                last_err = err
            except (BrokenPipeError, OSError) as e:
                proc.kill()
                last_err = f"{e} {proc.stderr.read().decode()[-500:]}"
        else:
            raise RuntimeError(f"encode failed: {last_err[-800:]}")
        val = validate(tmp, dur)
        os.replace(tmp, out)
    thumb_t = output_time(plan["payoff_t"], plan["segments"]) or dur / 2
    return RenderResult(
        str(out), media.duration(out), val, perceptual_hash(out), thumbnail(out, thumb_t), used
    )


def output_time(t: float, segments: list[dict]) -> float | None:
    acc = 0.0
    for s in segments:
        if s["role"] == "body" and s["start"] <= t <= s["end"]:
            return acc + t - s["start"]
        acc += s["end"] - s["start"]
    return None


def validate(path: Path | str, planned: float) -> dict:
    """ffprobe checks: duration within 0.1 s of plan, 1080x1920, H.264/AAC, loudness -14 +-1 LU, no black >0.5 s,
    no silence >1 s."""
    pr = media.probe(path)
    v = [s for s in pr["streams"] if s["codec_type"] == "video"][0]
    a = [s for s in pr["streams"] if s["codec_type"] == "audio"]
    dur = float(pr["format"]["duration"])
    lo = media.loudness(path)
    bd = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-vf",
            "blackdetect=d=0.5:pix_th=0.05",
            "-af",
            "silencedetect=n=-50dB:d=1",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    ).stderr
    checks = {
        "duration_ok": abs(dur - planned) <= 0.1,
        "resolution_ok": (int(v["width"]), int(v["height"])) == (1080, 1920),
        "video_codec_ok": v["codec_name"] == "h264",
        "audio_codec_ok": bool(a) and a[0]["codec_name"] == "aac",
        "loudness_ok": abs(lo.get("integrated", -99) + 14) <= 1.0,
        "no_black": "black_start" not in bd,
        "no_silence": "silence_start" not in bd,
    }
    return {
        "passed": all(checks.values()),
        **checks,
        "duration": dur,
        "planned": planned,
        "lufs": lo.get("integrated"),
        "true_peak": lo.get("true_peak"),
    }


def perceptual_hash(path: Path | str, n: int = 8) -> str:
    """dHash of n frames sampled evenly, concatenated (hex). Used by the duplicate check (doc 15)."""
    import imagehash
    from PIL import Image

    fr = media.decode_frames(path, fps=n / max(media.duration(path), 1), width=160)
    idx = np.linspace(0, len(fr) - 1, min(n, len(fr))).astype(int)

    def center(
        f,
    ):  # ignore borders: light crops, frames and watermarks at the edges shouldn't change the hash
        h, w = f.shape[:2]
        return f[int(0.075 * h) : int(0.925 * h), int(0.075 * w) : int(0.925 * w)]

    return "".join(str(imagehash.dhash(Image.fromarray(center(fr[i])), 8)) for i in idx)


def thumbnail(path: Path | str, t: float) -> bytes:
    fr = media.decode_frames(path, fps=1, width=360, start=max(0.0, t), dur=1.0)
    if not len(fr):
        fr = media.decode_frames(path, fps=1, width=360)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(fr[0], cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes()


PLATFORM_SPECS = {
    "youtube": {"max_s": 180, "min_s": 1},
    "instagram": {"max_s": 180, "min_s": 3},
    "facebook": {"max_s": 90, "min_s": 3},
    "threads": {"max_s": 300, "min_s": 1},
    "tiktok": {"max_s": 600, "min_s": 3},
    "snapchat": {"max_s": 60, "min_s": 5},
}


def fits(platform: str, duration: float, validation: dict) -> bool:
    s = PLATFORM_SPECS[platform]
    return validation.get("passed", False) and s["min_s"] <= duration <= s["max_s"]
