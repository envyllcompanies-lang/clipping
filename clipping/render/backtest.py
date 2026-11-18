"""Stage backtest 12: every rendered version passes validation (duration, 1080x1920, H.264/AAC, -14 LUFS +-1,
no black/silence) and fits its platforms' specs; render time per 40 s of output measured."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from clipping import run
from clipping.eval import windowfx
from clipping.eval.harness import Example, StageResult, stage
from clipping.render import engine

TARGETS = {"short": ["youtube", "instagram", "facebook", "threads", "snapchat"], "long": ["tiktok"]}


@stage("12", "Render Engine")
def run_stage() -> StageResult:
    passed, fit, per40, ex, n_versions = [], [], [], [], 0
    with tempfile.TemporaryDirectory() as d:
        for seed, layout in ((21, "stacked"), (22, "full"), (23, "small_cam")):
            w = windowfx.make(Path(d) / f"w{seed}.ts", seed=seed, seconds=135)
            r = run.run_window(
                w["path"], str(Path(d) / f"o{seed}"), peak_t=w["crash_t"], layout=layout, seed=seed
            )
            for vname, v in r["versions"].items():
                n_versions += 1
                passed.append(v["validation"]["passed"])
                for plat in TARGETS[vname]:
                    fit.append(engine.fits(plat, v["duration"], v["validation"]))
                per40.append(v["render_s"] / v["duration"] * 40)
                if not v["validation"]["passed"]:
                    ex.append(
                        Example(
                            f"seed{seed}:{vname}:{layout}",
                            "validation",
                            0,
                            str({k: x for k, x in v["validation"].items() if x is False}),
                        )
                    )
    return StageResult(
        {
            "validation_pass": float(np.mean(passed)),
            "platform_fit": float(np.mean(fit)),
            "versions_rendered": float(n_versions / 6),
            "render_s_per_40s_linux": float(np.mean(per40)),
        },
        ex,
        "windowfx@v1",
        {"encoder": "libx264 (Linux fallback); M1 uses h264_videotoolbox"},
    )
