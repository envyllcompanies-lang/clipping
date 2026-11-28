"""Stage backtest 31 (doc 30): heatmap recall@20 with vs without the gameplay score on real GTA VI VODs (it must
improve recall, or its weight goes to zero), and calibration builds a GTA 6 profile from raw VODs without labels.
Type precision and per-type boundary IoU need a labelled type set and are pending until one exists."""

from __future__ import annotations

from clipping.eval.harness import StageResult, stage
from clipping.heatmap import realeval
from clipping.moments import analysis as ma

W_GAMEPLAY = 0.2


@stage("31", "Gameplay Moment Analysis (real VODs)")
def run() -> StageResult:
    vods, ver = realeval.load_vods()
    prof = ma.calibrate([v.f for v in vods], save=False)
    base = realeval.evaluate(vods)["recall_at_20"]
    with_g = realeval.evaluate(vods, {"gameplay": W_GAMEPLAY})["recall_at_20"]
    hg = realeval.halves_gain(vods, "gameplay")
    return StageResult(
        {
            "gameplay_gain_fit_half": hg["gain_fit_half"],
            "gameplay_gain_test_half": hg["gain_test_half"],
            "gameplay_weight_kept": hg["weight_kept"],
            "heatmap_recall_with_gameplay": with_g,
            "heatmap_recall_without": base,
            "heatmap_gain_from_gameplay": with_g - base,
            "calibration_built": 1.0
            if prof["letterbox_threshold"] and prof["calibrated_on_seconds"] > 0
            else 0.0,
        },
        [],
        ver,
        {"profile": prof, "pending": ["type precision (needs labelled types)", "boundary IoU per type"]},
    )
