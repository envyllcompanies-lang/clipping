"""Synthetic stream frames for the reframe backtest: textured game, a moving subject with known position (the
action), optional facecam (public-domain NASA astronaut photo from scikit-image) and a chat overlay."""

from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np

W, H = 640, 360


@lru_cache(maxsize=1)
def _face() -> np.ndarray:
    from skimage import data

    a = data.astronaut()[20:240, 140:320]  # head and shoulders
    return cv2.resize(a, (120, 146))


def stream(seed: int, seconds: float = 12, fps: float = 10, cam: bool = True, cam_corner: str = "br") -> dict:
    rng = np.random.default_rng(seed)
    n = int(seconds * fps)
    tex = cv2.resize(
        rng.integers(40, 200, (H // 8, W // 4, 3)).astype(np.uint8), (W * 2, H), interpolation=cv2.INTER_CUBIC
    )
    detail = rng.normal(0, 18, (H, W * 2, 1))  # fine texture (buildings, foliage) that moves with the camera
    tex = np.clip(tex.astype(np.float32) + detail, 0, 255).astype(np.uint8)
    # subject trajectory: smooth wander with occasional jumps (scene cuts)
    cuts = sorted(
        rng.choice(
            np.arange(int(2 * fps), n - int(2 * fps)), size=int(rng.integers(0, 3)), replace=False
        ).tolist()
    )
    pos = np.array([rng.uniform(150, 490), rng.uniform(100, 260)])
    vel = rng.normal(0, 30, 2)
    frames, subj = [], []
    cam_box = None
    if cam:
        x0 = {"br": W - 150, "bl": 10, "tr": W - 150, "tl": 10}[cam_corner]
        y0 = {"br": H - 180, "bl": H - 180, "tr": 10, "tl": 10}[cam_corner]
        cam_box = (x0, y0, 140, 170)
    for i in range(n):
        if i in cuts:
            pos = np.array([rng.uniform(120, 520), rng.uniform(90, 270)])
            vel = rng.normal(0, 30, 2)
        vel = 0.9 * vel + rng.normal(0, 12, 2)
        pos = np.clip(pos + vel / fps, [60, 50], [W - 60, H - 50])
        off = int(i * 3) % W
        f = tex[:, off : off + W].copy()
        cv2.rectangle(
            f, (int(pos[0]) - 18, int(pos[1]) - 10), (int(pos[0]) + 18, int(pos[1]) + 10), (250, 240, 30), -1
        )
        cv2.rectangle(f, (W - 160, 40), (W - 10, 150), (20, 20, 30), -1)  # chat overlay
        for k in range(5):
            cv2.putText(
                f,
                f"user{(i + k) % 50}: lol",
                (W - 155, 60 + 18 * k),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (230, 230, 230),
                1,
            )
        if cam_box:
            x0, y0, cw, ch = cam_box
            cv2.rectangle(f, (x0, y0), (x0 + cw, y0 + ch), (15, 15, 15), -1)
            face = _face()
            dx = int(4 * np.sin(i / fps * 2))
            f[y0 + 12 : y0 + 12 + face.shape[0], x0 + 10 + dx : x0 + 10 + dx + face.shape[1]] = face
        frames.append(f)
        subj.append(pos.copy())
    return {
        "frames": np.stack(frames),
        "subject": np.array(subj),
        "cuts": [c / fps for c in cuts],
        "cam_box": cam_box,
        "fps": fps,
    }
