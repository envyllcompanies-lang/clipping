"""Stage backtest 10: facecam found, subject kept in crop (>= 95%), face inside the top panel and captions never
over the face (100%), smooth crop motion."""

from __future__ import annotations

import random

import numpy as np

from clipping.eval import reframefx
from clipping.eval.harness import Example, StageResult, stage
from clipping.reframe import layout as rl

SCALE = 3  # synthetic 640x360 frames stand in for 1920x1080 streams


@stage("10", "Reframe & Layout")
def run() -> StageResult:
    found, false_cam, inside, clear, face_in, jitter, ex = [], [], [], [], [], [], []
    for k in range(12):
        has_cam = k % 4 != 3
        s = reframefx.stream(1000 + k, cam=has_cam, cam_corner=["br", "bl", "tl", "br"][k % 4])
        fr = s["frames"]
        lay = rl.detect_layout(fr[:: max(1, len(fr) // 30)])
        lay = rl.StreamLayout(
            lay.width * SCALE,
            lay.height * SCALE,
            tuple(v * SCALE for v in lay.facecam) if lay.facecam else None,
            tuple(v * SCALE for v in lay.face) if lay.face else None,
            tuple(v * SCALE for v in lay.game),
            lay.overlay_mask,
        )
        if has_cam:
            ok = (
                lay.facecam is not None and rl._iou(tuple(v / SCALE for v in lay.facecam), s["cam_box"]) > 0.5
            )
            found.append(ok)
            if not ok:
                ex.append(
                    Example(f"stream{k}", "facecam_missed", 0, f"got {lay.facecam} want {s['cam_box']}")
                )
        else:
            false_cam.append(lay.facecam is not None)
        for layout in ("stacked", "full"):
            if layout == "stacked" and not lay.facecam:
                continue
            cp = rl.plan(fr, s["fps"], lay, layout, scene_cuts=s["cuts"], emphasis_t=[2.0, 6.0, 9.5])
            share = rl.subject_in_crop(cp, s["subject"] * SCALE, s["fps"])
            inside.append(share)
            clear.append(rl.caption_clear(cp))
            if layout == "stacked":
                f = cp["face_dst"]
                face_in.append(
                    f[1] >= 0
                    and f[1] + f[3] <= cp["panels"][0]["dst"][3]
                    and f[0] >= -5
                    and f[0] + f[2] <= 1085
                )
            kf = next(p for p in cp["panels"] if p["name"] == "game")["keyframes"]
            xs = np.array([b["box"][0] for b in kf], float)
            steps = np.abs(np.diff(xs)) * s["fps"]
            cut_idx = {int(round(c * s["fps"])) for c in s["cuts"]}
            steps = [v for i, v in enumerate(steps, 1) if i not in cut_idx]
            jitter.append(max(steps, default=0) / (0.25 * lay.width))
            if share < 0.95:
                ex.append(Example(f"stream{k}:{layout}", "subject_in_crop", share, ""))
    _ = random
    return StageResult(
        {
            "facecam_found": float(np.mean(found)),
            "facecam_false": float(np.mean(false_cam)),
            "subject_in_crop": float(np.mean(inside)),
            "caption_clear": float(np.mean(clear)),
            "face_in_top_panel": float(np.mean(face_in)),
            "max_pan_speed_ratio": float(np.max(jitter)),
        },
        ex,
        "reframefx@v1",
    )
