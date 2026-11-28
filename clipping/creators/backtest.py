"""Stage backtest 32 (doc 30): reaction score alone vs viewer-clip positions, per-creator normalized vs raw (pooled
baseline), recall@20 on the test half; and heatmap recall@20 with vs without the reaction signal. Segment exclusion,
catchphrase precision and collab alignment need labelled sets (sponsor/BRB minutes, known catchphrases, known collab
sessions) and are reported as pending until those exist."""

from __future__ import annotations

from clipping.eval.harness import StageResult, stage
from clipping.heatmap import realeval

W_REACTION = 0.25


def alone(vods, normalized: bool) -> float:
    import numpy as np

    pooled = realeval.pooled_baseline(vods)
    rs = []
    for v in vods:
        half = v.T / 2
        react = realeval.reaction_series(v, normalized, pooled, fit_until=half)
        r, _, _ = realeval.recall({"reaction": react}, {"reaction": 1.0}, v, half, v.T)
        if r == r:
            rs.append(r)
    return float(np.mean(rs))


@stage("32", "Creator Profile & Reaction (real VODs)")
def run() -> StageResult:
    vods, ver = realeval.load_vods()
    norm, raw = alone(vods, True), alone(vods, False)
    base = realeval.evaluate(vods)["recall_at_20"]
    with_r = realeval.evaluate(vods, {"reaction": W_REACTION})["recall_at_20"]
    hg = realeval.halves_gain(vods, "reaction")
    return StageResult(
        {
            "reaction_gain_fit_half": hg["gain_fit_half"],
            "reaction_gain_test_half": hg["gain_test_half"],
            "reaction_weight_kept": hg["weight_kept"],
            "reaction_alone_recall_normalized": norm,
            "reaction_alone_recall_raw": raw,
            "normalized_minus_raw": norm - raw,
            "heatmap_recall_with_reaction": with_r,
            "heatmap_recall_without": base,
            "heatmap_gain_from_reaction": with_r - base,
        },
        [],
        ver,
        {
            "pending": [
                "segment exclusion (needs labelled sponsor/BRB minutes)",
                "catchphrase precision (needs transcripts of top clips)",
                "collab alignment (needs known collab sessions)",
            ]
        },
    )
