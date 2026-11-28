"""Game Event Detection (doc 08), driven entirely by the game profile (config/games/<slug>.yaml).

Methods: banner (OCR on a region + keyword match per language, desaturation check), stars (count star-shaped bright
blobs in the HUD region), flash (brightness + motion spikes), static (long low-motion spans -> loading/menu
negatives). Regions are fractions of the detected game rectangle; streamer overlays are masked out.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

import cv2
import numpy as np

from clipping.core import config


@dataclass
class Event:
    t: float
    type: str
    confidence: float
    details: dict = field(default_factory=dict)


def frame_stats(frames: np.ndarray, mask: np.ndarray | None = None) -> dict[str, np.ndarray]:
    hsv = np.stack([cv2.cvtColor(f, cv2.COLOR_RGB2HSV) for f in frames])
    gray = frames.mean(axis=3)
    keep = ~mask if mask is not None else np.ones(gray.shape[1:], bool)
    motion = np.r_[0, np.abs(np.diff(gray, axis=0))[:, keep].mean(axis=1)]
    return {
        "bright": hsv[..., 2][:, keep].mean(axis=1),
        "sat": hsv[..., 1][:, keep].mean(axis=1),
        "motion": motion,
    }


def learn_overlay_mask(frames: np.ndarray, var_thresh: float = 4.0, min_area: float = 0.002) -> np.ndarray:
    """Regions static across the stream (alerts, chat boxes, logos) that aren't the game. Uses temporal std; small
    specks are dropped. Run on ~30 frames sampled across the stream."""
    gray = frames.mean(axis=3).astype(np.float32)
    static = gray.std(axis=0) < var_thresh
    n, lab, stats, _ = cv2.connectedComponentsWithStats(static.astype(np.uint8))
    area = gray.shape[1] * gray.shape[2]
    out = np.zeros_like(static)
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a < min_area * area:
            continue
        x, y, w, h = (
            stats[i, k] for k in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT)
        )
        if a >= 0.5 * w * h and w * h < 0.4 * area:
            out[y : y + h, x : x + w] = (
                True  # box-shaped overlay (chat box, alert panel): mask the whole box, text included
            )
        else:
            out[lab == i] = True
    return out


def crop(
    frame: np.ndarray,
    region: list[float],
    rect: tuple[int, int, int, int] | None = None,
    mask: np.ndarray | None = None,
) -> np.ndarray:
    H, W = frame.shape[:2]
    if mask is not None:
        frame = frame.copy()
        frame[mask] = 0
    x0, y0, x1, y1 = rect or (0, 0, W, H)
    gw, gh = x1 - x0, y1 - y0
    return frame[
        y0 + int(region[1] * gh) : y0 + int(region[3] * gh),
        x0 + int(region[0] * gw) : x0 + int(region[2] * gw),
    ]


def ocr(img: np.ndarray) -> str:
    import pytesseract

    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    g = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    if (b > 0).mean() < 0.5:
        b = 255 - b  # tesseract wants dark text on light background
    return pytesseract.image_to_string(b, config="--psm 6").lower()


def keyword_hit(text: str, keywords: list[str], ratio: float = 0.75) -> str | None:
    words = [
        w for w in "".join(c if c.isalnum() or c.isspace() else " " for c in text).split() if len(w) >= 3
    ]
    for kw in keywords:
        parts = kw.lower().split()
        for i in range(len(words) - len(parts) + 1):
            cand = " ".join(words[i : i + len(parts)])
            if difflib.SequenceMatcher(None, cand, kw.lower()).ratio() >= ratio:
                return kw
    return None


def count_stars(region: np.ndarray) -> int:
    """Count filled star icons: bright blobs with star-like solidity (~0.45-0.75) and similar size."""
    hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
    v = hsv[..., 2]
    k = max(5, (region.shape[0] // 2) * 2 + 1)
    tophat = cv2.morphologyEx(v, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    # bright relative to the surroundings (works over bright skies), and low-saturation (white/pale HUD icons)
    m = ((tophat > 50) & (v > 150) & (hsv[..., 1] < 140)).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
    bg = float(np.median(v[cv2.dilate(m, np.ones((3, 3), np.uint8)) == 0])) if (m == 0).any() else 0.0
    areas = []
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if float(v[lab == i].mean()) - bg < 40:
            continue  # background showing through an empty outline star, not a filled icon
        w, h = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if a < 12 or not (0.6 < w / max(h, 1) < 1.6):
            continue
        cnts, _ = cv2.findContours((lab == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        hull = cv2.convexHull(cnts[0])
        sol = a / max(cv2.contourArea(hull), 1)
        if 0.4 < sol < 0.8:
            areas.append(a)
    if not areas:
        return 0
    med = np.median(areas)
    return int(sum(0.5 * med <= a <= 2 * med for a in areas))


def detect(
    frames: np.ndarray,
    times: np.ndarray,
    *,
    game: str = "gta6",
    language: str = "en",
    rect=None,
    mask: np.ndarray | None = None,
    ocr_fn=ocr,
) -> list[Event]:
    prof = config.game(game)["events"]
    st = frame_stats(frames, mask)
    fps = 1 / max(float(np.median(np.diff(times))), 1e-3) if len(times) > 1 else 2.0
    events: list[Event] = []
    k1 = max(1, int(round(fps)))
    med_b = np.array(
        [
            np.median(st["bright"][max(0, i - k1 * 2) : i]) if i else st["bright"][0]
            for i in range(len(frames))
        ]
    )
    med_s = np.array(
        [np.median(st["sat"][max(0, i - k1 * 3) : i]) if i else st["sat"][0] for i in range(len(frames))]
    )
    med_m = np.array(
        [
            np.median(st["motion"][max(0, i - k1 * 3) : i]) if i > 1 else st["motion"][i]
            for i in range(len(frames))
        ]
    )
    # banner events: OCR only on candidate frames - desaturation drop, or the banner region changing much more than
    # the rest of the frame (a banner appearing). One OCR pass over the union of banner regions per candidate.
    banner_types = {k: v for k, v in prof.items() if v.get("method") == "banner"}
    if banner_types:
        regs = [v["region"] for v in banner_types.values()]
        union = [
            min(r[0] for r in regs),
            min(r[1] for r in regs),
            max(r[2] for r in regs),
            max(r[3] for r in regs),
        ]
        gray = frames.mean(axis=3)
        H, W = gray.shape[1:]
        inside = np.zeros((H, W), bool)
        inside[int(union[1] * H) : int(union[3] * H), int(union[0] * W) : int(union[2] * W)] = True
        if mask is not None:
            inside &= ~mask
        outside = ~inside & (~mask if mask is not None else True)
        last_banner = -1e9
        for i in range(1, len(frames)):
            d = np.abs(gray[i] - gray[i - 1])
            d_in, d_out = d[inside].mean(), d[outside].mean() if outside.any() else 0.0
            appear = d_in > 12 and d_in > 2.5 * (d_out + 1)
            desat = st["sat"][i] < 0.6 * med_s[i] and med_s[i] > 20
            if not (appear or desat) or times[i] - last_banner < 3:
                continue
            # read the frame after the change too (banners animate in)
            for k in (i, min(i + 1, len(frames) - 1)):
                txt = ocr_fn(crop(frames[k], union, rect, mask))
                hit_type = None
                for etype, spec in banner_types.items():
                    kws = spec.get("keywords", {}).get(language, []) + spec.get("keywords", {}).get("en", [])
                    hit = keyword_hit(txt, kws)
                    if hit:
                        hit_type = (etype, hit, spec)
                        break
                if hit_type:
                    etype, hit, spec = hit_type
                    det = (
                        {"result": "failed" if "fail" in hit else "passed", "text": hit}
                        if etype == "mission"
                        else {"text": hit}
                    )
                    conf = 0.7 + 0.2 * desat + 0.1 * (not spec.get("desaturate") or desat)
                    events.append(Event(float(times[i]), etype, round(float(min(conf, 1.0)), 2), det))
                    last_banner = times[i]
                    break
    # wanted level changes: stable star count change
    if "wanted" in prof:
        mx = prof["wanted"].get("max_stars", 5)
        raw = [min(count_stars(crop(f, prof["wanted"]["region"], rect, mask)), mx) for f in frames]
        # HUD is unreadable during flashes and desaturated banner screens: carry the last reading through them
        unreadable = [
            (i > 0 and st["bright"][i] - med_b[i] > 30) or (st["sat"][i] < 0.6 * med_s[i] and med_s[i] > 20)
            for i in range(len(frames))
        ]
        counts, last = [], None
        for i, c in enumerate(raw):
            last = last if unreadable[i] and last is not None else c
            counts.append(last)
        hold = max(2, int(round(1.5 * fps)))  # wanted levels persist; ignore shorter blips
        runs = [i for i in range(hold - 1, len(counts)) if len(set(counts[i - hold + 1 : i + 1])) == 1]
        if runs:
            stable = counts[runs[0]]
            for i in runs[1:]:
                if counts[i] != stable:
                    first = i - hold + 1  # the change happened where this stable run began
                    events.append(
                        Event(
                            float(times[first]),
                            "wanted",
                            0.9 if abs(counts[i] - stable) <= 2 else 0.75,
                            {"from": stable, "to": counts[i]},
                        )
                    )
                    stable = counts[i]
    # crashes / explosions
    if "crash" in prof:
        spec = prof["crash"]
        last = -1e9
        for i in range(1, len(frames)):
            if (
                st["bright"][i] - med_b[i] > spec.get("brightness_jump", 60) * 0.5
                and st["motion"][i] > spec.get("motion_jump", 3.0) * max(med_m[i], 2.0)
                and times[i] - last > 2
            ):
                events.append(
                    Event(
                        float(times[i]),
                        "crash",
                        0.8,
                        {"bright_jump": round(float(st["bright"][i] - med_b[i]), 1)},
                    )
                )
                last = times[i]
    # negatives: static spans >= 3 s
    max_motion = prof.get("loading", {}).get("max_motion", 0.5)
    low = st["motion"] < max_motion
    i = 0
    while i < len(low):
        if low[i]:
            j = i
            while j < len(low) and low[j]:
                j += 1
            if times[min(j, len(times) - 1)] - times[i] >= 3:
                reg = frames[i]
                edge = cv2.Canny(cv2.cvtColor(reg, cv2.COLOR_RGB2GRAY), 80, 200).mean() / 255
                kind = "menu" if edge > 0.01 else "loading"  # menus are text-dense; loading art is smooth
                events.append(
                    Event(
                        float(times[i]),
                        kind,
                        0.9,
                        {"end": float(times[min(j, len(times) - 1)]), "negative": True},
                    )
                )
            i = j
        else:
            i += 1
    neg = [(e.t - 1.5, e.details["end"] + 1.5) for e in events if e.details.get("negative")]
    events = [e for e in events if not (e.type == "wanted" and any(a <= e.t <= b for a, b in neg))]
    return sorted(events, key=lambda e: e.t)


def negative_spans(events: list[Event]) -> list[tuple[float, float]]:
    return [(e.t, e.details["end"]) for e in events if e.details.get("negative")]
