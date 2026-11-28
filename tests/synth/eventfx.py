"""Synthetic GTA-like frames for the event set (doc 30). The real GTA 6 HUD is learned from launch footage
(doc 08 'starts empty'); these frames exercise the profile methods with streamer overlays and distractors."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 640, 360
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
TYPES = ["death", "arrest", "mission", "wanted", "crash", "loading", "menu", "none", "none", "none"]


def _font(size: int):
    return ImageFont.truetype(FONT, size)


def _star(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill, outline=None) -> None:
    pts = []
    for k in range(10):
        ang = -np.pi / 2 + k * np.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        pts.append((cx + rr * np.cos(ang), cy + rr * np.sin(ang)))
    d.polygon(pts, fill=fill, outline=outline)


def scene(rng: np.random.Generator, t: float, objs: list, shake: float = 0) -> Image.Image:
    y = np.linspace(0, 1, H)[:, None]
    base = np.zeros((H, W, 3))
    base[..., 0] = 60 + 80 * y
    base[..., 1] = 110 + 60 * (1 - y)
    base[..., 2] = 150 + 50 * np.sin(np.linspace(0, 3, W) + t * 0.8 + objs[0][0])[None, :]
    base[..., 0] += 30 * np.sin(np.linspace(0, 6, H) + t * 1.3)[:, None]
    base += rng.normal(0, 6, base.shape)
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    for x0, y0, vx, vy, w, h, col in objs:
        x = (x0 + vx * t + shake * rng.normal()) % W
        yy = (y0 + vy * t) % (H * 0.8) + H * 0.15
        d.rectangle([x, yy, x + w, yy + h], fill=col)
    return img


def overlays(img: Image.Image, rng: np.random.Generator, t: float, chat_lines: list[str]) -> None:
    d = ImageDraw.Draw(img)
    d.rectangle([8, H - 118, 168, H - 8], fill=(30, 30, 30))  # facecam box
    fx = 88 + 12 * np.sin(t * 2)
    d.ellipse([fx - 22, H - 95, fx + 22, H - 45], fill=(200, 160, 130))
    d.rectangle([W - 150, 120, W - 6, 300], fill=(15, 15, 25))  # chat box
    f = _font(10)
    for k, line in enumerate(chat_lines[-10:]):
        d.text((W - 146, 124 + 17 * k), line, fill=(220, 220, 220), font=f)


def hud_stars(img: Image.Image, n: int, max_stars: int = 5) -> None:
    d = ImageDraw.Draw(img)
    x1, y0, y1 = 0.98 * W, 0.02 * H, 0.10 * H
    r = (y1 - y0) / 2 * 0.9
    for k in range(max_stars):
        cx = x1 - (k + 0.6) * 2.4 * r
        if k < n:
            _star(d, cx, (y0 + y1) / 2, r, fill=(255, 255, 240))
        else:
            _star(d, cx, (y0 + y1) / 2, r, fill=None, outline=(90, 90, 90))


def banner(img: Image.Image, text: str, color, desat: bool) -> Image.Image:
    if desat:
        g = np.asarray(img.convert("L"))
        img = Image.fromarray(np.stack([g] * 3, axis=2))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0.42 * H, W, 0.58 * H], fill=(0, 0, 0))
    f = _font(44)
    tw = d.textlength(text, font=f)
    d.text(((W - tw) / 2, 0.44 * H), text, fill=color, font=f)
    return img


def clip(seed: int, kind: str, seconds: float = 8, fps: float = 2) -> dict:
    """Frames for one example; returns frames, times, truth {type, t, details}."""
    rng = np.random.default_rng(seed)
    objs = [
        (
            rng.uniform(0, W),
            rng.uniform(0, H),
            rng.uniform(-60, 60),
            rng.uniform(-10, 10),
            rng.uniform(20, 60),
            rng.uniform(10, 30),
            tuple(int(v) for v in rng.integers(0, 255, 3)),
        )
        for _ in range(12)
    ]
    n = int(seconds * fps)
    t_ev = float(rng.uniform(2, seconds - (4.5 if kind in ("loading", "menu") else 3)))
    s0 = int(rng.integers(0, 4))
    s1 = int(np.clip(s0 + rng.choice([-2, -1, 1, 2, 3]), 0, 5)) if kind == "wanted" else s0
    if kind == "wanted" and s1 == s0:
        s1 = (s0 + 1) % 6
    chat = [
        f"user{int(rng.integers(100))}: {w}"
        for w in rng.choice(["lol", "W", "busted lmao", "wasted KEKW", "gg", "ez"], 30)
    ]
    subs = str(rng.choice(["where are you going", "get in the car", "we need to lose them", ""]))
    frames, times = [], []
    static_img = None
    for i in range(n):
        t = i / fps
        after = t >= t_ev
        if kind in ("loading", "menu") and after:
            if static_img is None:
                if kind == "loading":
                    static_img = Image.new("RGB", (W, H), (20, 18, 30))
                    dd = ImageDraw.Draw(static_img)
                    dd.ellipse([180, 80, 460, 300], fill=(60, 40, 90))
                else:
                    static_img = Image.new("RGB", (W, H), (25, 30, 40))
                    dd = ImageDraw.Draw(static_img)
                    for k in range(8):
                        dd.rectangle([60, 40 + 36 * k, 400, 66 + 36 * k], fill=(50, 60, 80))
                        dd.text(
                            (70, 44 + 36 * k),
                            f"OPTION {k + 1}  SETTINGS",
                            fill=(230, 230, 230),
                            font=_font(16),
                        )
            img = static_img.copy()
            if kind == "loading":
                ImageDraw.Draw(img).ellipse(
                    [W - 40 + 3 * np.sin(t), H - 40, W - 24, H - 24], fill=(200, 200, 200)
                )
            frames.append(np.asarray(img))
            times.append(t)
            continue
        img = scene(rng, t, objs, shake=25 if (kind == "crash" and abs(t - t_ev) < 0.6) else 0)
        if kind == "crash" and 0 <= t - t_ev < 1.0:
            arr = np.asarray(img).astype(float) * 0.3 + 200
            img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        hud_stars(img, s1 if (kind == "wanted" and after) else s0)
        if subs:
            d = ImageDraw.Draw(img)
            f = _font(16)
            d.text(((W - d.textlength(subs, font=f)) / 2, H * 0.86), subs, fill=(255, 255, 255), font=f)
        if after and kind in ("death", "arrest", "mission"):
            txt, col, desat = {
                "death": ("WASTED", (200, 30, 30), True),
                "arrest": ("BUSTED", (220, 220, 220), True),
                "mission": ("MISSION PASSED", (240, 200, 40), False),
            }[kind]
            img = banner(img, txt, col, desat)
        overlays(img, rng, t, chat[: 5 + i])
        frames.append(np.asarray(img))
        times.append(t)
    truth = (
        None
        if kind == "none"
        else {"type": kind, "t": t_ev, "details": {"from": s0, "to": s1} if kind == "wanted" else {}}
    )
    return {"frames": np.stack(frames), "times": np.array(times), "truth": truth}


def layout_sample(seed: int, n: int = 30) -> np.ndarray:
    """Frames spread across a 'stream' with the same overlay layout but different scenes (for overlay masks)."""
    out = []
    for k in range(n):
        rng = np.random.default_rng(seed * 1000 + k)
        objs = [
            (
                rng.uniform(0, W),
                rng.uniform(0, H),
                0,
                0,
                rng.uniform(20, 60),
                rng.uniform(10, 30),
                tuple(int(v) for v in rng.integers(0, 255, 3)),
            )
            for _ in range(12)
        ]
        img = scene(rng, float(rng.uniform(0, 100)), objs)
        hud_stars(img, int(rng.integers(0, 6)))
        overlays(
            img,
            rng,
            float(rng.uniform(0, 100)),
            [f"user{int(rng.integers(100))}: lol"] * int(rng.integers(3, 12)),
        )
        out.append(np.asarray(img))
    return np.stack(out)
