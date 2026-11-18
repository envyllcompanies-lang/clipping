"""Stage backtest 13: the analyzer recovers known style parameters from synthetic reference videos."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from clipping.eval import stylefx
from clipping.eval.harness import Example, StageResult, stage
from clipping.style import analyze

CASES = [
    dict(shot_s=2.0, cap_y=0.40, caps=True, fill="FFFFFF", stacked=0.4, zooms=0),
    dict(shot_s=1.5, cap_y=0.55, caps=True, fill="FFE11A", stacked=None, zooms=3),
    dict(shot_s=3.0, cap_y=0.70, caps=False, fill="FFFFFF", stacked=0.35, zooms=2),
    dict(shot_s=2.5, cap_y=0.45, caps=True, fill="38E07B", stacked=None, zooms=0),
    dict(shot_s=1.0, cap_y=0.38, caps=True, fill="FFE11A", stacked=0.45, zooms=4),
    dict(shot_s=4.0, cap_y=0.62, caps=False, fill="FFFFFF", stacked=None, zooms=1),
]


def _rgb(h: str) -> np.ndarray:
    return np.array([int(h[i : i + 2], 16) for i in (0, 2, 4)], float)


@stage("13", "Style Study")
def run() -> StageResult:
    cut_err, y_err, caps_ok, fill_err, lay_ok, split_err, zoom_err, ex = [], [], [], [], [], [], [], []
    with tempfile.TemporaryDirectory() as d:
        for k, case in enumerate(CASES):
            p = Path(d) / f"v{k}.mp4"
            truth = stylefx.make(p, 1300 + k, **case)
            a = analyze.analyze(str(p))
            cut_err.append(abs(a["cuts_per_10s"] - truth["cuts_per_10s"]) / truth["cuts_per_10s"])
            y = a["captions"]["position_y"]
            y_err.append(abs(y - truth["cap_y"]) if y is not None else 1.0)
            share = a["captions"]["all_caps_share"]
            caps_ok.append(share is not None and (share > 0.6) == truth["caps"])
            fill_err.append(
                np.abs(_rgb(a["captions"]["fill"][1:]) - _rgb(truth["fill"])).max() / 255
                if a["captions"]["fill"]
                else 1
            )
            lay_ok.append(a["layout"]["type"] == truth["layout"])
            if truth["split"] and a["layout"]["split"]:
                split_err.append(abs(a["layout"]["split"] - truth["split"]))
            zoom_err.append(abs(a["zooms_per_10s"] - truth["zooms"] / 12 * 10))
            ex.append(
                Example(
                    f"case{k}",
                    "cut_err",
                    cut_err[-1],
                    f"measured {a['cuts_per_10s']} vs {truth['cuts_per_10s']:.2f}; "
                    f"layout {a['layout']} vs {truth['layout']}; y {y} vs {truth['cap_y']}; fill {a['captions']['fill']}",
                )
            )
    ex.sort(key=lambda e: -e.value)
    return StageResult(
        {
            "cut_rate_rel_err": float(np.mean(cut_err)),
            "caption_y_err": float(np.mean(y_err)),
            "caps_detected": float(np.mean(caps_ok)),
            "fill_color_err": float(np.mean(fill_err)),
            "layout_detected": float(np.mean(lay_ok)),
            "split_err": float(np.mean(split_err)) if split_err else 1.0,
            "zoom_rate_abs_err": float(np.mean(zoom_err)),
        },
        ex,
        "stylefx@v1",
    )
