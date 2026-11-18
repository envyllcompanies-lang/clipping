"""Stage backtest 08: precision/recall per event type on the event set; compute per candidate window."""

from __future__ import annotations

import time
from collections import Counter

from clipping.eval import eventfx
from clipping.eval.harness import Example, StageResult, stage
from clipping.events import detect

N = 70
TOL = 1.5
MASK = None


@stage("08", "Game Event Detection")
def run() -> StageResult:
    global MASK
    MASK = detect.learn_overlay_mask(eventfx.layout_sample(1))  # learned once per stream layout
    tp, fp, fn = Counter(), Counter(), Counter()
    ex, secs, frames_total = [], 0.0, 0
    for seed in range(800, 800 + N):
        kind = eventfx.TYPES[seed % len(eventfx.TYPES)]
        c = eventfx.clip(seed, kind)
        t0 = time.time()
        mask = MASK
        evs = detect.detect(c["frames"], c["times"], mask=mask)
        secs += time.time() - t0
        frames_total += len(c["frames"])
        truth = c["truth"]
        matched = False
        for e in evs:
            ok = truth is not None and e.type == truth["type"] and abs(e.t - truth["t"]) <= TOL
            if ok and truth["type"] == "wanted":
                ok = e.details.get("to") == truth["details"]["to"]
            if ok and not matched:
                tp[e.type] += 1
                matched = True
            else:
                fp[e.type] += 1
                ex.append(Example(f"seed{seed}:{kind}", f"fp_{e.type}", e.t, str(e.details)))
        if truth is not None and not matched:
            fn[truth["type"]] += 1
            ex.append(Example(f"seed{seed}:{kind}", f"fn_{truth['type']}", truth["t"], ""))
    m = {}
    for t in ["death", "arrest", "wanted", "mission", "crash", "loading", "menu"]:
        det = tp[t] + fp[t]
        m[f"precision_{t}"] = tp[t] / det if det else 1.0
        m[f"recall_{t}"] = tp[t] / (tp[t] + fn[t]) if (tp[t] + fn[t]) else 1.0
    m["precision_min_core"] = min(m["precision_death"], m["precision_arrest"], m["precision_wanted"])
    # compute for one 75 s candidate window at 2 fps, extrapolated from measured per-frame cost
    m["seconds_per_window"] = secs / frames_total * 150
    return StageResult(m, ex, "eventfx@v1", {"tp": dict(tp), "fp": dict(fp), "fn": dict(fn)})
