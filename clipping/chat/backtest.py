"""Stage backtest 03 on real live chat (eval/datasets/live_chat, built by `clip eval build-real live_chat`):
missing time from socket gaps (< 1%), and chat-spike alignment with viewer-clipped moments after reaction-lag
calibration (calibrate on half the clips, measure on the other half). Clip positions are the clip's anchor point.

Viewer clips land within roughly +-15 s of the moment, so the doc's 2-second alignment can't be verified against them;
it is reported (no bar) and gets graded against doc 08 on-screen events once live recordings exist."""

from __future__ import annotations

import numpy as np

from clipping.chat import features
from clipping.eval import datasets
from clipping.eval.harness import Example, StageResult, dataset_dir, dsver, stage

ANCHOR = 0.65


@stage("03", "Chat Capture (real)")
def run() -> StageResult:
    d = dataset_dir("live_chat")
    chans = datasets.read(d, "channels.json")
    missing, errs, ex, n_clips, near10 = [], [], [], 0, []
    for ch in chans:
        T = ch["duration_s"]
        missing.append(sum(b - a for a, b in ch["gaps"]) / T)
        rate = np.array(ch["per_second"], float)
        onsets = features.spike_onsets(rate, min_sep=20, z_thresh=2.5, baseline=60)
        moments = sorted(
            {round(c["t_start"] + ANCHOR * c["duration"]) for c in ch["clips"] if 60 <= c["t_start"] < T - 30}
        )
        n_clips += len(moments)
        if len(moments) < 4 or not onsets:
            continue
        cal, test = moments[::2], moments[1::2]
        lag = features.calibrate_lag(onsets, cal, max_lag=20)
        if lag is None:
            continue
        for t in test:
            near = [o for o in onsets if -10 <= o - lag - t <= 20]
            near10.append(any(abs(o - lag - t) <= 10 for o in onsets))
            if near:
                e = min(abs(o - lag - t) for o in near)
                errs.append(e)
                if e > 2:
                    ex.append(Example(f"{ch['login']}@{t}", "align_err", e, f"lag={lag:.1f}"))
    errs = np.array(errs) if errs else np.array([99.0])
    ex.sort(key=lambda e: -e.value)
    return StageResult(
        {
            "missing_share": float(np.mean(missing)),
            "clip_moments_with_spike_10s": float(np.mean(near10)) if near10 else 0.0,
            "align_within_2s_vs_clip_labels": float(np.mean(errs <= 2)),
            "align_median_s_vs_clip_labels": float(np.median(errs)),
        },
        ex,
        dsver(d),
        {"aligned": int(len(errs)), "clip_moments": n_clips},
    )
