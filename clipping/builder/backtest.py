"""Stage backtest 09: boundary IoU with the matching viewer clip (>= 0.6), payoff included (>= 95%), every plan
valid, both versions produced, and no clip opens on a back-reference."""

from __future__ import annotations

import numpy as np

from clipping.builder import plan as bp
from clipping.eval.harness import Example, StageResult, stage

WORDS = [
    "bro",
    "get",
    "in",
    "the",
    "car",
    "go",
    "left",
    "right",
    "now",
    "cops",
    "behind",
    "us",
    "wait",
    "look",
    "at",
    "this",
    "guy",
    "we",
    "have",
    "five",
    "stars",
    "no",
    "way",
    "chat",
    "watch",
    "drive",
    "faster",
    "jump",
    "off",
    "bridge",
]


def synth_window(seed: int) -> tuple[bp.Inputs, dict]:
    rng = np.random.default_rng(seed)
    dur = 135.0
    pay = float(rng.uniform(70, 80))
    words, t, idx = [], 0.5, 0
    backref_at = float(rng.uniform(pay - 30, pay - 12)) if rng.random() < 0.3 else None
    while t < dur - 1:
        n = int(rng.integers(4, 12))
        sent = list(rng.choice(WORDS, n))
        if backref_at is not None and abs(t - backref_at) < 3:
            sent = ["like", "i", "said"] + sent
            backref_at = None
        for k, w in enumerate(sent):
            d = float(rng.uniform(0.18, 0.4))
            word = str(w) + ("." if k == len(sent) - 1 else "")
            words.append(
                {
                    "index": idx,
                    "word": word,
                    "start": round(t, 3),
                    "end": round(t + d, 3),
                    "conf": float(rng.uniform(0.6, 1)),
                }
            )
            idx += 1
            t += d + float(rng.uniform(0.02, 0.12))
        t += float(rng.choice([0.2, 0.5, 0.9, 1.6]))
    kind = str(rng.choice(["death", "crash", "wanted", "none"]))
    events = [] if kind == "none" else [{"t": pay, "type": kind, "confidence": float(rng.uniform(0.7, 1))}]
    peak = pay + float(rng.normal(0, 1.5))
    activity = np.clip(rng.normal(0.2, 0.15, int(dur) + 2), 0, 1)
    activity[int(pay) - 3 : int(pay) + 3] = 0.9
    truth = {
        "start": pay - float(rng.uniform(15, 28)),
        "end": pay + float(rng.uniform(1.5, 4)),
        "payoff": pay,
    }
    return bp.Inputs(dur, words, events, peak, [], activity, [], "en", "streamer"), truth


@stage("09", "Clip Builder")
def run() -> StageResult:
    ious, pay_in, valid, both, clean_open, ex = [], [], [], [], [], []
    for seed in range(900, 960):
        inp, truth = synth_window(seed)
        res = bp.build(inp)
        both.append("short" in res["versions"] and "long" in res["versions"])
        for v, p in res["versions"].items():
            errs = bp.validate(p, inp)
            valid.append(not errs)
            clean_open.append(p["standalone"])
            if errs:
                ex.append(Example(f"seed{seed}:{v}", "invalid", 1, "; ".join(errs)))
        p = res["versions"].get("short")
        if not p:
            ious.append(0.0)
            pay_in.append(False)
            ex.append(Example(f"seed{seed}", "no_short", 0, res["discarded"] or ""))
            continue
        inter = max(0.0, min(p["end_t"], truth["end"]) - max(p["start_t"], truth["start"]))
        union = max(p["end_t"], truth["end"]) - min(p["start_t"], truth["start"])
        ious.append(inter / union)
        pay_in.append(p["start_t"] < truth["payoff"] < p["end_t"])
        if ious[-1] < 0.6:
            ex.append(
                Example(
                    f"seed{seed}",
                    "iou",
                    ious[-1],
                    f"plan {p['start_t']:.1f}-{p['end_t']:.1f} truth "
                    f"{truth['start']:.1f}-{truth['end']:.1f} payoff {truth['payoff']:.1f}",
                )
            )
    ex.sort(key=lambda e: e.value)
    return StageResult(
        {
            "boundary_iou": float(np.mean(ious)),
            "payoff_included": float(np.mean(pay_in)),
            "plans_valid": float(np.mean(valid)),
            "both_versions": float(np.mean(both)),
            "standalone_openings": float(np.mean(clean_open)),
        },
        ex,
        "synthetic@v1",
    )
