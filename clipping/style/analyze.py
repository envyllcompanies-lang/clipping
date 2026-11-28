"""Style study analyzer (doc 13): measures one video's editing habits; profiles aggregate many videos.

Works on any local file; how reference samples are obtained is an owner decision (YouTube's terms)."""

from __future__ import annotations

import re
import statistics
from collections import Counter

import cv2
import numpy as np

from clipping.core import media


def cuts(frames: np.ndarray, fps: float, thresh: float = 0.35, bands: int = 3) -> list[float]:
    """Histogram-distance cuts, per horizontal band: in stacked layouts a cut often changes only the gameplay panel."""
    H = frames.shape[1]
    edges = np.linspace(0, H, bands + 1).astype(int)

    def hist(img):
        h = cv2.calcHist([cv2.cvtColor(img, cv2.COLOR_RGB2HSV)], [0, 1], None, [16, 8], [0, 180, 0, 256])
        return cv2.normalize(h, None).flatten()

    hs = [[hist(f[edges[b] : edges[b + 1]]) for b in range(bands)] for f in frames]
    out = []
    for i in range(1, len(hs)):
        d = max(cv2.compareHist(hs[i - 1][b], hs[i][b], cv2.HISTCMP_BHATTACHARYYA) for b in range(bands))
        if d > thresh and (not out or i / fps - out[-1] > 0.25):
            out.append(i / fps)
    return out


def step_scales(frames: np.ndarray, cut_times: list[float], fps: float) -> np.ndarray:
    """Per-step scale between consecutive frames from ORB matches (RANSAC similarity). Static points are dropped
    (captions/logos drawn over the video say nothing about zoom). NaN where unknown or across cuts."""
    orb = cv2.ORB_create(500)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    cut_idx = {int(round(t * fps)) for t in cut_times}
    out = np.full(len(frames), np.nan)
    prev = None
    for i, f in enumerate(frames):
        kp, des = orb.detectAndCompute(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY), None)
        if prev is not None and i not in cut_idx and des is not None and prev[1] is not None and len(kp) > 10:
            ms = bf.match(prev[1], des)
            if len(ms) >= 10:
                a = np.float32([prev[0][m.queryIdx].pt for m in ms])
                b = np.float32([kp[m.trainIdx].pt for m in ms])
                mv = np.linalg.norm(b - a, axis=1) > 0.5
                if mv.sum() >= 10:
                    M, _ = cv2.estimateAffinePartial2D(a[mv], b[mv], method=cv2.RANSAC)
                    if M is not None:
                        out[i] = float(np.sqrt(M[0, 0] ** 2 + M[0, 1] ** 2))
        prev = (kp, des)
    return out


def zoom_events(
    frames: np.ndarray,
    fps: float,
    cut_times: list[float],
    min_scale: float = 1.07,
    ramp_s: float = 0.4,
    panel: tuple[int, int] | None = None,
) -> tuple[list[float], list[float]]:
    """Punch-ins: a consistent scale ramp of >= min_scale within ramp_s seconds, on the gameplay panel."""
    if panel:
        frames = frames[:, panel[0] : panel[1]]
    sc = step_scales(frames, cut_times, fps)
    ls = np.log(np.nan_to_num(sc, nan=1.0))
    n = max(2, int(round(ramp_s * fps)))
    events, amounts, i = [], [], 1
    while i < len(ls):
        win = ls[i : i + n]
        pos = win > np.log(1.008)
        k = int(np.argmax(np.cumsum(np.where(pos, win, -1)) >= np.log(min_scale))) if pos.any() else -1
        tot = float(np.sum(win[: k + 1])) if k >= 0 else 0.0
        if pos[0] and k >= 0 and pos[: k + 1].all() and tot >= np.log(min_scale) and tot <= np.log(1.45):
            events.append(i / fps)
            amounts.append(float(np.exp(tot)))
            i += int(round(0.6 * fps))
        else:
            i += 1
    return events, amounts


def captions(frames: np.ndarray, fps: float, ocr=None) -> dict:
    """OCR at ~1 fps: coverage, vertical position (fraction of height), words per line, caps share, fill color."""
    import pytesseract

    step = max(1, int(round(fps)))
    seen, ys, wpl, caps, fills = 0, [], [], [], []
    texts, boxed = [], []
    n = 0
    for i in range(0, len(frames), step):
        n += 1
        f = frames[i]
        H, W = f.shape[:2]
        g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY)
        d = (
            ocr(f)
            if ocr
            else pytesseract.image_to_data(g, output_type=pytesseract.Output.DICT, config="--psm 11")
        )
        lines: dict[int, list[str]] = {}
        boxes = []
        for k, txt in enumerate(d["text"]):
            txt = txt.strip()
            if len(txt) < 2 or float(d["conf"][k]) < 50 or not any(ch.isalpha() for ch in txt):
                continue
            yc = d["top"][k] + d["height"][k] / 2
            lines.setdefault(int(yc // (0.04 * H)), []).append(txt)
            boxes.append((d["left"][k], d["top"][k], d["width"][k], d["height"][k], txt))
        big = [b for b in boxes if b[3] > 0.025 * H]
        if not big:
            continue
        seen += 1
        texts.append(" ".join(sorted(re.sub(r"\W", "", b[4].lower()) for b in big)))
        # white rounded box with black text vs white text with outline: the box is bright around the letters
        ring = []
        for x, y, w, h, _ in big[:6]:
            y0, y1, x0, x1 = (
                max(0, y - h // 3),
                min(H, y + h + h // 3),
                max(0, x - h // 3),
                min(W, x + w + h // 3),
            )
            ring.append(float(np.median(f[y0:y1, x0:x1].mean(axis=2))))
        boxed.append(statistics.median(ring) > 170)
        ys.append(float(np.median([(b[1] + b[3] / 2) / H for b in big])))
        for words in lines.values():
            wpl.append(len(words))
        letters = "".join(b[4] for b in big)
        caps.append(
            sum(ch.isupper() for ch in letters if ch.isalpha()) / max(1, sum(ch.isalpha() for ch in letters))
        )
        for x, y, w, h, _ in big[:6]:
            pad = max(2, h // 6)
            y0, y1, x0, x1 = max(0, y - pad), min(H, y + h + pad), max(0, x - pad), min(W, x + w + pad)
            patch = f[y0:y1, x0:x1]
            lum = patch.mean(axis=2)
            bright = (lum > 100).astype(np.uint8)
            n, lab, stt, _ = cv2.connectedComponentsWithStats(bright)
            ph, pw = bright.shape
            keep = np.zeros_like(bright, bool)
            for c in range(
                1, n
            ):  # caption strokes are enclosed by the black outline: they don't touch the box border
                bx, by, bw, bh = stt[c, 0], stt[c, 1], stt[c, 2], stt[c, 3]
                if bx > 0 and by > 0 and bx + bw < pw and by + bh < ph:
                    keep |= lab == c
            if keep.sum() > 10:
                fills.append(np.median(patch[keep], axis=0))
    fill = "#{:02X}{:02X}{:02X}".format(*[int(v) for v in np.median(fills, axis=0)]) if fills else None
    if texts:  # doc 13 text mode: the same text for > 80% of the clip = hook-only headline
        top_share = Counter(texts).most_common(1)[0][1] / len(texts)
        distinct = len(set(texts))
        text_mode = "hook_only" if top_share > 0.8 else ("hook_key_lines" if distinct <= 4 else "full")
    else:
        text_mode = None
    return {
        "text_mode": text_mode,
        "text_style": ("box" if sum(boxed) > len(boxed) / 2 else "outline") if boxed else None,
        "coverage": seen / max(n, 1),
        "position_y": statistics.median(ys) if ys else None,
        "words_per_line": statistics.median(wpl) if wpl else None,
        "all_caps_share": statistics.fmean(caps) if caps else None,
        "fill": fill,
    }


def _text_boxes(img: np.ndarray) -> list[tuple[int, int, int, int]]:
    import pytesseract

    d = pytesseract.image_to_data(
        cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), output_type=pytesseract.Output.DICT, config="--psm 11"
    )
    return [
        (d["left"][k], d["top"][k], d["width"][k], d["height"][k])
        for k, t in enumerate(d["text"])
        if t.strip() and float(d["conf"][k]) > 30
    ]


def layout_by_cuts(frames: np.ndarray, cut_times: list[float], fps: float) -> dict | None:
    """At a cut only one panel of a stacked layout changes: the per-row change profile steps at the seam.
    In a full layout the whole frame changes. Returns None when there are too few cuts to decide."""
    H = frames.shape[1]
    lo, hi = int(0.15 * H), int(0.85 * H)
    splits = []
    full_votes = 0
    for t in cut_times:
        i = int(round(t * fps))
        if i < 1 or i >= len(frames):
            continue
        r = np.abs(frames[i].astype(np.float32) - frames[i - 1].astype(np.float32)).mean(axis=(1, 2))
        r = np.convolve(r, np.ones(5) / 5, mode="same")
        best, best_y = 0.0, None
        cs = np.cumsum(r)
        for y in range(lo, hi):
            above, below = cs[y] / y, (cs[-1] - cs[y]) / (H - y)
            small, big = min(above, below), max(above, below)
            if big > 15 and small < 0.25 * big and big - small > best:
                best, best_y = big - small, y
        if best_y is None:
            full_votes += 1
        else:
            splits.append(best_y)
    n = len(splits) + full_votes
    if n < 2:
        return None
    if splits and len(splits) >= 0.6 * n:
        med = float(np.median(splits))
        agree = [y for y in splits if abs(y - med) <= 0.03 * H]
        if len(agree) >= 0.6 * n:
            return {"type": "stacked", "split": round((float(np.median(agree)) + 1) / H, 3)}
    if full_votes >= 0.6 * n:
        return {"type": "full", "split": None}
    return None


def layout(frames: np.ndarray, boxes_fn=_text_boxes) -> dict:
    """Stacked vs full: a full-width horizontal seam at the same row in most frames, across different shots.
    Columns covered by caption text are ignored, so a wide caption's edge isn't mistaken for a seam."""
    H, W = frames.shape[1:3]
    sample = frames[:: max(1, len(frames) // 40)]
    votes = np.zeros(H)
    for f in sample:
        g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32)
        d = np.abs(np.diff(g, axis=0))
        valid = np.ones_like(d, bool)
        for x, y, w, h in boxes_fn(f) if boxes_fn else []:
            pad = max(8, h)  # OCR boxes exclude the thick caption outline
            valid[max(0, y - pad) : y + h + pad, max(0, x - pad) : x + w + pad] = False
        jump = (d > 18) & valid
        nvalid = np.maximum(valid.sum(axis=1), 1)
        share = jump.sum(axis=1) / nvalid  # share of (non-caption) columns with a jump at this row
        edge = int(0.15 * W)
        vl, vr = valid[:, :edge].sum(axis=1), valid[:, -edge:].sum(axis=1)
        left = (vl < 3) | (jump[:, :edge].sum(axis=1) > 0.2 * vl)
        right = (vr < 3) | (jump[:, -edge:].sum(axis=1) > 0.2 * vr)
        reaches = (
            left & right & ((vl >= 3) | (vr >= 3))
        )  # full width, unlike captions; a side hidden by a caption is unknown
        rowmean = (d * valid).sum(axis=1) / nvalid
        cand = (
            reaches
            & (share > 0.35)
            & (nvalid >= 0.3 * W)
            & (rowmean > max(20.0, 4 * float(np.median(rowmean))))
        )
        cand[: int(0.15 * H)] = False
        cand[int(0.85 * H) :] = False
        votes[np.nonzero(cand)[0]] += 1
    # merge adjacent rows (seams can straddle two rows)
    win = max(2, H // 100)
    sm = np.convolve(votes, np.ones(win), mode="same")
    row = int(np.argmax(sm))
    if sm[row] >= 0.6 * len(sample):
        return {"type": "stacked", "split": round((row + 1) / H, 3)}
    return {"type": "full", "split": None}


def ending(frames: np.ndarray) -> dict:
    a, b = frames[0].astype(np.float32), frames[-1].astype(np.float32)
    sim = 1 - np.abs(a - b).mean() / 255
    return {"loop": bool(sim > 0.9), "last_first_similarity": round(float(sim), 3)}


def analyze(path: str, fps: float = 10, ocr=None) -> dict:
    dur = media.duration(path)
    frames = media.decode_frames(path, fps=fps, width=360)
    ct = cuts(frames, fps)
    shots = np.diff([0.0, *ct, dur])
    lay = layout_by_cuts(frames, ct, fps) or layout(frames)
    panel = (int(lay["split"] * frames.shape[1]) + 2, frames.shape[1]) if lay["type"] == "stacked" else None
    z, amt = zoom_events(frames, fps, ct, panel=panel)
    cap = captions(frames, fps, ocr)
    first = frames[: int(3 * fps)]
    cap3 = captions(first, fps, ocr) if len(first) else {"coverage": 0}
    lo = media.loudness(path)
    return {
        "duration": round(dur, 2),
        "vertical": frames.shape[1] > frames.shape[2],
        "cuts_per_10s": round(len(ct) / dur * 10, 3),
        "median_shot_s": round(float(np.median(shots)), 3),
        "zooms_per_10s": round(len(z) / dur * 10, 3),
        "zoom_amount": round(float(np.median(amt)), 3) if amt else None,
        "captions": cap,
        "hook": {"text_first_3s": cap3["coverage"] > 0, "cuts_first_3s": sum(t < 3 for t in ct)},
        "layout": lay,
        "audio": {"lufs": lo.get("integrated"), "lra": lo.get("lra")},
        "ending": ending(frames),
    }


def _arm_shares(analyses: list[dict]) -> dict:
    """Starting text-arm mix measured from the reference videos (doc 11/13)."""
    out = {}
    for key, field in (("text_mode_arms", "text_mode"), ("text_style_arms", "text_style")):
        vals = [a["captions"].get(field) for a in analyses if a["captions"].get(field)]
        if vals:
            out[key] = {k: round(v / len(vals), 3) for k, v in Counter(vals).items()}
    caps = [
        a["captions"]["all_caps_share"] for a in analyses if a["captions"].get("all_caps_share") is not None
    ]
    if caps:
        up = sum(c > 0.6 for c in caps) / len(caps)
        out["headline_case_arms"] = {"sentence": round(1 - up, 3), "upper": round(up, 3)}
    return out


def profile_from(analyses: list[dict], name: str, source: str) -> dict:
    """Aggregate per-video measurements: median targets, min-max ranges, shares for booleans (doc 13)."""

    def stat(vals):
        vals = [v for v in vals if v is not None]
        return {"median": statistics.median(vals), "min": min(vals), "max": max(vals)} if vals else None

    shorts = [a for a in analyses if a["vertical"] and a["duration"] <= 180] or analyses
    lay = Counter(a["layout"]["type"] for a in analyses)
    splits = [a["layout"]["split"] for a in analyses if a["layout"]["split"]]
    cap_y = stat([a["captions"]["position_y"] for a in analyses])
    d = stat([a["duration"] for a in shorts])
    return {
        "name": name,
        "source": source,
        "n_videos": len(analyses),
        "length": {
            "short": {"target": round(d["median"]), "min": round(d["min"]), "max": round(d["max"])},
            "long": {"target": 75, "min": 61, "max": 90},
        },
        "pacing": {
            "cuts_per_10s": stat([a["cuts_per_10s"] for a in shorts])["median"],
            "median_shot_s": stat([a["median_shot_s"] for a in shorts])["median"],
            "zooms_per_10s": stat([a["zooms_per_10s"] for a in shorts])["median"],
            "zoom_amount": (stat([a["zoom_amount"] for a in shorts]) or {"median": 1.15})["median"],
            "dead_air_s": 0.4,
        },
        "hook": {
            "cold_open_share": round(
                sum(a["hook"]["cuts_first_3s"] > 0 for a in analyses) / len(analyses), 3
            ),
            "hook_text_share": round(sum(a["hook"]["text_first_3s"] for a in analyses) / len(analyses), 3),
            "hook_s": 2.0,
            "hook_text_s": 2.5,
            "transition": "whoosh",
        },
        "layout": {
            "arms": {k: round(v / len(analyses), 3) for k, v in lay.items()},
            "stacked": {"cam_ratio": round(statistics.median(splits), 3) if splits else 0.4},
        },
        "captions": {
            "coverage": stat([a["captions"]["coverage"] for a in analyses])["median"],
            "position_y": cap_y["median"] if cap_y else None,
            "words_per_line": [
                2,
                max(
                    2,
                    round(
                        (stat([a["captions"]["words_per_line"] for a in analyses]) or {"median": 3})["median"]
                    ),
                ),
            ],
            "all_caps": (stat([a["captions"]["all_caps_share"] for a in analyses]) or {"median": 1})["median"]
            > 0.6,
            **_arm_shares(analyses),
            "fill": Counter(a["captions"]["fill"] for a in analyses if a["captions"]["fill"]).most_common(1)[
                0
            ][0]
            if any(a["captions"]["fill"] for a in analyses)
            else "#FFFFFF",
        },
        "audio": {
            "lufs": (stat([a["audio"]["lufs"] for a in analyses]) or {"median": -14})["median"],
            "true_peak": -1,
        },
        "ending": {"loop_share": round(sum(a["ending"]["loop"] for a in analyses) / len(analyses), 3)},
    }
