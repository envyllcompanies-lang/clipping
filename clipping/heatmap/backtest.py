"""Stage backtest 05 on real data: recall@20 / precision@20 of the top viewer-clipped moments per 4 h on GTA VI VODs
(eval/datasets/viewer_clips, built from Twitch Helix clips + VOD audio/video). Live signals only (audio energy,
voice excitement, visual change, plus docs 31/32 signals at their configured weights); VODs have no chat replay.
Measured on the second half of each VOD (label-fit parameters use the first half)."""

from __future__ import annotations

from clipping.core import config
from clipping.eval.harness import Example, StageResult, stage
from clipping.heatmap import realeval


def configured_extra() -> dict[str, float]:
    w = config.settings()["heatmap"]["weights"]
    return {k: w[k] for k in ("reaction", "gameplay") if w.get(k, 0) > 0}


@stage("05", "Moment Heatmap (real VODs)")
def run() -> StageResult:
    vods, ver = realeval.load_vods()
    r = realeval.evaluate(vods, configured_extra() or None)
    ex = [
        Example(f"{c}@{t:.0f}s", "missed", float(v), "top viewer-clipped moment outside the top windows")
        for c, t, v in sorted(r["misses"], key=lambda m: -m[2])
    ]
    return StageResult(
        {"recall_at_20": r["recall_at_20"], "precision_at_20": r["precision_at_20"]},
        ex,
        ver,
        {"vods": r["vods"], "extra_signals": configured_extra()},
    )
