"""Reframe & Layout (doc 10): 16:9 stream -> 9:16 crop plan.

1. Detect the stream layout once per stream: facecam box (stable face), game rect (minus letterbox), overlay mask.
2. Choose a vertical layout per clip: an A/B arm (stacked is the starting favorite), with per-clip rules
   (no facecam -> full gameplay; low-res source -> full gameplay).
3. Gameplay crop path: weighted motion center, critically damped spring, capped pan speed, jumps at scene cuts.
4. Punch-in zooms at emphasis times toward the action point; none during fast pans.
5. Safe zones and the caption band; the face is kept above the band.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np

from clipping.core.settings import ROOT

CANVAS = (1080, 1920)
YUNET = ROOT / "var" / "models" / "face_detection_yunet_2023mar.onnx"
YUNET_URL = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"


def ensure_yunet() -> str:
    if not YUNET.exists():
        import httpx

        YUNET.parent.mkdir(parents=True, exist_ok=True)
        r = httpx.get(YUNET_URL, follow_redirects=True, timeout=120)
        r.raise_for_status()
        YUNET.write_bytes(r.content)
    return str(YUNET)


@lru_cache(maxsize=4)
def _yunet(w: int, h: int):
    return cv2.FaceDetectorYN.create(ensure_yunet(), "", (w, h), 0.7)


def faces(frame: np.ndarray) -> list[tuple[int, int, int, int, float]]:
    """(x, y, w, h, score) boxes from YuNet; Haar cascade if the model can't load."""
    h, w = frame.shape[:2]
    try:
        det = _yunet(w, h)
        _, f = det.detect(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        return [] if f is None else [(int(r[0]), int(r[1]), int(r[2]), int(r[3]), float(r[14])) for r in f]
    except Exception:  # noqa: BLE001
        cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        return [
            (x, y, ww, hh, 0.8)
            for x, y, ww, hh in cas.detectMultiScale(cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY), 1.1, 5)
        ]


def _iou(a, b) -> float:
    ax, ay, aw, ah = a[:4]
    bx, by, bw, bh = b[:4]
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / max(aw * ah + bw * bh - inter, 1)


@dataclass
class StreamLayout:
    width: int
    height: int
    facecam: tuple[int, int, int, int] | None  # camera panel box in source pixels
    face: tuple[int, int, int, int] | None  # typical face box inside it
    game: tuple[int, int, int, int]
    overlay_mask: np.ndarray | None = None

    def to_json(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "facecam": self.facecam,
            "face": self.face,
            "game": self.game,
        }


def letterbox(frames: np.ndarray) -> tuple[int, int, int, int]:
    """Game rect = frame minus black bars (rows/cols near-black in every sampled frame)."""
    m = frames.max(axis=0).mean(axis=2)
    rows = np.nonzero(m.max(axis=1) > 20)[0]
    cols = np.nonzero(m.max(axis=0) > 20)[0]
    if len(rows) == 0 or len(cols) == 0:
        return (0, 0, frames.shape[2], frames.shape[1])
    return (int(cols[0]), int(rows[0]), int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1))


def detect_layout(frames: np.ndarray, min_share: float = 0.6, stable_frames: int = 10) -> StreamLayout:
    """frames: ~30 RGB frames sampled across the stream. A face in the same small rectangle in most frames
    (and at least `stable_frames`) is the facecam; its static border refines the panel box."""
    H, W = frames.shape[1:3]
    dets = [max(faces(f), key=lambda b: b[4], default=None) for f in frames]
    boxes = [d for d in dets if d is not None and d[2] * d[3] < 0.25 * W * H]
    facecam = face = None
    if boxes:
        clusters: list[list] = []
        for b in boxes:
            for cl in clusters:
                if _iou(cl[0], b) > 0.3:
                    cl.append(b)
                    break
            else:
                clusters.append([b])
        best = max(clusters, key=len)
        if len(best) >= max(min_share * len(frames), min(stable_frames, len(frames))):
            fx, fy = int(np.median([b[0] for b in best])), int(np.median([b[1] for b in best]))
            fw, fh = int(np.median([b[2] for b in best])), int(np.median([b[3] for b in best]))
            face = (fx, fy, fw, fh)
            facecam = _cam_panel(frames, face)
    from clipping.events.detect import learn_overlay_mask

    mask = learn_overlay_mask(frames) if len(frames) >= 5 else None
    return StreamLayout(W, H, facecam, face, letterbox(frames), mask)


def _cam_panel(frames: np.ndarray, face: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Grow from the face until hitting the camera box edge: a straight edge whose color differs across it in
    every frame (cams sit in a box over the game). Fallback: 3x face width, 2.5x face height."""
    H, W = frames.shape[1:3]
    fx, fy, fw, fh = face
    med = np.median(frames.astype(np.float32), axis=0).mean(axis=2)
    gx = np.abs(np.diff(med, axis=1))
    gy = np.abs(np.diff(med, axis=0))
    cy0, cy1 = max(0, fy - fh), min(H - 1, fy + 2 * fh)
    cx0, cx1 = max(0, fx - fw), min(W - 1, fx + 2 * fw)

    def edge(profile, start, stop, step):
        best, pos = 0.0, None
        for k in range(start, stop, step):
            if profile[k] > best and profile[k] > 25:
                best, pos = profile[k], k
        return pos

    colp = gx[cy0:cy1].mean(axis=0)
    rowp = gy[:, cx0:cx1].mean(axis=1)
    left = edge(colp, max(0, fx - 1), max(0, fx - 3 * fw), -1)
    right = edge(colp, min(W - 2, fx + fw + 1), min(W - 1, fx + fw + 3 * fw), 1)
    top = edge(rowp, max(0, fy - 1), max(0, fy - 2 * fh), -1)
    bottom = edge(rowp, min(H - 2, fy + fh + 1), min(H - 1, fy + fh + 3 * fh), 1)
    x0 = (left + 1) if left is not None else max(0, fx - fw)
    x1 = right if right is not None else min(W, fx + 2 * fw)
    y0 = (top + 1) if top is not None else max(0, fy - int(0.75 * fh))
    y1 = bottom if bottom is not None else min(H, fy + int(1.75 * fh))
    return (int(x0), int(y0), int(x1 - x0), int(y1 - y0))


def choose_layout(
    lay: StreamLayout,
    arms: dict[str, float],
    rng: random.Random | None = None,
    source_height: int | None = None,
) -> str:
    """Per-clip rules first (no facecam or low-res -> full), then sample an A/B arm by its share."""
    if lay.facecam is None or (source_height or lay.height) < 720:
        return "full"
    rng = rng or random.Random()
    names = [a for a in arms if arms[a] > 0]
    r, acc = rng.random() * sum(arms[a] for a in names), 0.0
    for a in names:
        acc += arms[a]
        if r <= acc:
            return a
    return names[-1]


def motion_targets(
    frames: np.ndarray, fps: float, rect: tuple[int, int, int, int], exclude: np.ndarray | None = None
) -> np.ndarray:
    """Per-frame action point (x, y) in source pixels: weighted center of frame-difference magnitude in the rect."""
    x0, y0, w, h = rect
    g = frames[:, y0 : y0 + h, x0 : x0 + w].mean(axis=3).astype(np.float32)
    out = np.zeros((len(frames), 2))
    prev_pt = np.array([x0 + w / 2, y0 + h / 2])
    orb = cv2.ORB_create(600)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    kmask = None
    if exclude is not None:
        # static overlays (chat, cam box, alerts) would pin the motion estimate at zero: no keypoints there
        kmask = cv2.erode(
            (~exclude[y0 : y0 + h, x0 : x0 + w]).astype(np.uint8) * 255, np.ones((9, 9), np.uint8)
        )
    g8 = np.clip(g, 0, 255).astype(np.uint8)
    # static overlays show residual edges once the pan is undone (they didn't move): exclude them generously
    excl_d = (
        cv2.dilate(exclude[y0 : y0 + h, x0 : x0 + w].astype(np.uint8), np.ones((21, 21), np.uint8)).astype(
            bool
        )
        if exclude is not None
        else None
    )
    feats = [orb.detectAndCompute(img, kmask) for img in g8]
    for i in range(len(frames)):
        d = np.zeros_like(g[0])
        if i:
            (kp0, d0), (kp1, d1) = feats[i - 1], feats[i]
            dx = dy = 0.0
            if d0 is not None and d1 is not None and len(kp0) > 8 and len(kp1) > 8:
                ms = bf.match(d0, d1)
                if len(ms) >= 8:
                    a_ = np.float32([kp0[m.queryIdx].pt for m in ms])
                    b_ = np.float32([kp1[m.trainIdx].pt for m in ms])
                    M, _ = cv2.estimateAffinePartial2D(a_, b_, method=cv2.RANSAC, ransacReprojThreshold=2.0)
                    if M is not None:
                        dx, dy = float(M[0, 2]), float(M[1, 2])
            # undo the camera pan; what still differs is moving objects
            prev = cv2.warpAffine(
                g[i - 1], np.float32([[1, 0, dx], [0, 1, dy]]), (w, h), borderMode=cv2.BORDER_REPLICATE
            )
            d = np.abs(g[i] - prev)
            m = int(np.ceil(max(abs(dx), abs(dy)))) + 2
            d[:m], d[-m:], d[:, :m], d[:, -m:] = 0, 0, 0, 0
        if exclude is not None:
            d[excl_d] = 0
        d = cv2.GaussianBlur(d, (0, 0), 3)
        d[d < max(20.0, float(np.percentile(d, 99.5)))] = (
            0  # residual warp noise is low and everywhere; objects are strong
        )
        tot = d.sum()
        if tot > 1e-3 * d.size:
            ys, xs = np.mgrid[0:h, 0:w]
            prev_pt = np.array([x0 + (xs * d).sum() / tot, y0 + (ys * d).sum() / tot])
        out[i] = prev_pt
    return out


def smooth_path(
    targets: np.ndarray, fps: float, cuts: list[int], max_speed: float, omega: float = 4.0
) -> np.ndarray:
    """Critically damped spring following targets; speed capped (px/s); instant jump at scene cuts."""
    pos = targets[0].astype(float).copy()
    vel = np.zeros(2)
    dt = 1.0 / fps
    out = np.zeros_like(targets, dtype=float)
    cutset = set(cuts)
    for i, tgt in enumerate(targets):
        if i in cutset:
            pos, vel = tgt.astype(float).copy(), np.zeros(2)
        else:
            acc = omega * omega * (tgt - pos) - 2 * omega * vel
            vel = vel + acc * dt
            sp = np.linalg.norm(vel)
            if sp > max_speed:
                vel *= max_speed / sp
            pos = pos + vel * dt
        out[i] = pos
    return out


def crop_box(
    center: np.ndarray, cw: int, ch: int, bounds: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    bx, by, bw, bh = bounds
    x = int(np.clip(center[0] - cw / 2, bx, bx + bw - cw))
    y = int(np.clip(center[1] - ch / 2, by, by + bh - ch))
    return (x, y, cw, ch)


def plan(
    frames: np.ndarray,
    fps: float,
    lay: StreamLayout,
    layout: str,
    *,
    scene_cuts: list[float] | None = None,
    emphasis_t: list[float] | None = None,
    zoom_amount: float = 1.15,
    cam_ratio: float = 0.40,
    caption_lines: int = 2,
    caption_size_pct: float = 0.062,
    time_offset: float = 0.0,
) -> dict:
    """frames: the clip's source frames (any resolution, scaled to lay.width x lay.height coordinates by ratio)."""
    Wc, Hc = CANVAS
    sx = lay.width / frames.shape[2]
    sy = lay.height / frames.shape[1]
    cuts_idx = [int(round(t * fps)) for t in (scene_cuts or [])]
    gx, gy, gw, gh = lay.game
    small_rect = (int(gx / sx), int(gy / sy), max(1, int(gw / sx)), max(1, int(gh / sy)))
    excl = None
    if lay.facecam:
        fxc, fyc, fwc, fhc = lay.facecam
        excl = np.zeros(frames.shape[1:3], bool)
        excl[int(fyc / sy) : int((fyc + fhc) / sy), int(fxc / sx) : int((fxc + fwc) / sx)] = True
    if lay.overlay_mask is not None and lay.overlay_mask.shape == frames.shape[1:3]:
        excl = lay.overlay_mask if excl is None else (excl | lay.overlay_mask)
    tg = motion_targets(frames, fps, small_rect, excl) * np.array([sx, sy])
    band_h = int(Hc * caption_size_pct * 1.25 * caption_lines)
    avoid_boxes = [lay.facecam] if lay.facecam else []
    if lay.overlay_mask is not None:
        n, _, st, _ = cv2.connectedComponentsWithStats(lay.overlay_mask.astype(np.uint8))
        msx, msy = lay.width / lay.overlay_mask.shape[1], lay.height / lay.overlay_mask.shape[0]
        avoid_boxes += [
            (int(st[i, 0] * msx), int(st[i, 1] * msy), int(st[i, 2] * msx), int(st[i, 3] * msy))
            for i in range(1, n)
            if st[i, 4] > 0.003 * lay.overlay_mask.size
        ]
    panels = []
    if layout == "stacked" and lay.facecam:
        cam_h = int(Hc * cam_ratio)
        game_h = Hc - cam_h
        # facecam: crop the cam box with ~10% padding, fill the 1080-wide panel (crop sides, never letterbox),
        # face in the upper-middle so it stays clear of the caption band on the seam
        fx, fy, fw, fh = lay.facecam
        pad_x, pad_y = int(0.1 * fw), int(0.1 * fh)
        bx, by = max(0, fx - pad_x), max(0, fy - pad_y)
        bw, bh = min(lay.width - bx, fw + 2 * pad_x), min(lay.height - by, fh + 2 * pad_y)
        aspect = Wc / cam_h
        cw, ch = (bw, int(bw / aspect)) if bw / bh <= aspect else (int(bh * aspect), bh)
        cw, ch = min(cw, bw), min(ch, bh)
        face = lay.face or (fx + fw // 3, fy + fh // 4, fw // 3, fh // 2)
        face_cx, face_cy = face[0] + face[2] / 2, face[1] + face[3] / 2
        # face center at 42% of panel height -> its bottom stays above the band
        cy = face_cy - ch * (0.42 - 0.5)
        cam_box = crop_box(np.array([face_cx, cy]), cw, ch, (bx, by, bw, bh))
        panels.append(
            {"name": "cam", "dst": [0, 0, Wc, cam_h], "keyframes": [{"t": 0.0, "box": list(cam_box)}]}
        )
        gch = gh
        gcw = int(gch * Wc / game_h)
        if gcw > gw:
            gcw, gch = gw, int(gw * game_h / Wc)
        if game_h / gch > 1.5:  # never upscale beyond 1.5x: widen the crop instead
            gch = min(gh, int(game_h / 1.5))
            gcw = min(gw, int(gch * Wc / game_h))
        path = smooth_path(tg, fps, cuts_idx, max_speed=0.25 * lay.width)
        kfs = [
            {"t": round(i / fps + time_offset, 3), "box": list(crop_box(p, gcw, gch, lay.game))}
            for i, p in enumerate(path)
        ]
        panels.append({"name": "game", "dst": [0, cam_h, Wc, game_h], "keyframes": kfs})
        seam = cam_h
        band = [seam - band_h // 2, seam + band_h // 2]
        s = cam_h / cam_box[3]
        face_dst = [
            int((face[0] - cam_box[0]) * s),
            int((face[1] - cam_box[1]) * s),
            int(face[2] * s),
            int(face[3] * s),
        ]
    else:
        gch = gh
        gcw = int(gch * Wc / Hc)
        path = smooth_path(tg, fps, cuts_idx, max_speed=0.25 * lay.width)
        kfs = [
            {"t": round(i / fps + time_offset, 3), "box": list(crop_box(p, gcw, gch, lay.game))}
            for i, p in enumerate(path)
        ]
        panels.append({"name": "game", "dst": [0, 0, Wc, Hc], "keyframes": kfs})
        face_dst = None
        if layout == "small_cam" and lay.facecam:
            bw_ = int(Wc * 0.34)
            fx, fy, fw, fh = lay.facecam
            bh_ = int(bw_ * fh / max(fw, 1))
            panels.append(
                {
                    "name": "cam",
                    "dst": [int(0.04 * Wc), int(0.06 * Hc), bw_, bh_],
                    "keyframes": [{"t": 0.0, "box": list(lay.facecam)}],
                    "bubble": True,
                }
            )
            face_dst = [int(0.04 * Wc), int(0.06 * Hc), bw_, bh_]
        mid = int(Hc * 0.55)
        band = [mid - band_h // 2, mid + band_h // 2]
    zooms = []
    speeds = np.r_[0, np.linalg.norm(np.diff(path, axis=0), axis=1) * fps]
    for t in emphasis_t or []:
        i = int(np.clip(round((t - time_offset) * fps), 0, len(path) - 1))
        if speeds[i] > 0.15 * lay.width:  # no zooms during fast pans
            continue
        if zooms and t - zooms[-1]["t"] < 1.5:
            continue
        zooms.append(
            {
                "t": round(t, 3),
                "scale": zoom_amount,
                "in_s": 0.2,
                "hold_s": 0.6,
                "out_s": 0.3,
                "toward": [round(float(tg[i][0]), 1), round(float(tg[i][1]), 1)],
            }
        )
    safe = {
        "bottom_clear": [0, int(0.8 * Hc), Wc, int(0.2 * Hc)],
        "right_clear": [int(0.85 * Wc), 0, int(0.15 * Wc), Hc],
    }
    return {
        "layout": layout,
        "canvas": [Wc, Hc],
        "panels": panels,
        "zooms": zooms,
        "caption_band": band,
        "face_dst": face_dst,
        "safe_zones": safe,
        "fps": fps,
        "source": lay.to_json(),
    }


def caption_clear(cp: dict) -> bool:
    """Captions never over the face and never in platform UI zones."""
    y0, y1 = cp["caption_band"]
    if y1 > cp["safe_zones"]["bottom_clear"][1]:
        return False
    f = cp.get("face_dst")
    if f:
        fy0, fy1 = f[1], f[1] + f[3]
        if not (fy1 <= y0 or fy0 >= y1):
            return False
    return True


def subject_in_crop(cp: dict, subject_xy: np.ndarray, fps: float) -> float:
    """Share of frames whose tracked subject point lies inside the gameplay crop."""
    game = next(p for p in cp["panels"] if p["name"] == "game")
    kf = game["keyframes"]
    inside = 0
    for i, (x, y) in enumerate(subject_xy):
        bx, by, bw, bh = kf[min(i, len(kf) - 1)]["box"]
        inside += bx <= x <= bx + bw and by <= y <= by + bh
    return inside / max(len(subject_xy), 1)


_ = os
