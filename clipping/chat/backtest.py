"""Stage backtest 03: missing-time share and chat-spike alignment after reaction-lag calibration (<= 2 s)."""

from __future__ import annotations

import numpy as np

from clipping.chat import features
from clipping.core import config
from clipping.eval.harness import Example, StageResult, stage
from clipping.eval.simstream import simulate


@stage("03", "Chat Capture")
def run() -> StageResult:
    errs, missing_extra, ex = [], [], []
    for seed in range(300, 306):
        s = simulate(seed, hours=2)
        b = features.bucketize(s.msgs, s.duration_s, config.chat_tokens("en"), gaps=s.gaps)
        flagged = sum(x["missing"] for x in b) * 10
        true_gap = sum(bb - a for a, bb in s.gaps)
        missing_extra.append(
            max(0.0, flagged - true_gap - 20 * len(s.gaps)) / s.duration_s
        )  # only real gaps flagged
        rate = features.per_second(s.msgs, s.duration_s)
        onsets = features.spike_onsets(rate)
        truth = [m["t"] for m in s.moments]
        half = len(truth) // 2
        lag = features.calibrate_lag(onsets, truth[:half]) or config.settings()["chat"]["reaction_lag_s"]
        for t in truth[half:]:
            near = [o for o in onsets if -5 <= o - lag - t <= 10]
            if not near:
                continue  # weak-chat moments: no spike to align (scored by other signals)
            e = min(abs(o - lag - t) for o in near)
            errs.append(e)
            if e > 2:
                ex.append(Example(f"seed{seed}@{t:.0f}", "align_err", e, f"lag={lag:.1f}"))
    ex.sort(key=lambda e: -e.value)
    errs = np.array(errs)
    return StageResult(
        {
            "align_within_2s": float(np.mean(errs <= 2)),
            "align_median_s": float(np.median(errs)),
            "excess_missing_share": float(np.mean(missing_extra)),
        },
        ex,
        "simstream@v1",
        {"n": int(len(errs))},
    )
