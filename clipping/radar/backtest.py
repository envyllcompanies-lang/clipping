"""Stage backtest 01: Spearman between radar score and next-week hours watched (bar >= 0.6)."""

from __future__ import annotations

from collections import defaultdict

from scipy.stats import spearmanr

from clipping.core import config
from clipping.eval import datasets
from clipping.eval.harness import Example, StageResult, dataset_dir, dsver, stage
from clipping.radar import scoring


@stage("01", "Creator Radar")
def run() -> StageResult:
    d = dataset_dir("radar_creators")
    creators = datasets.read(d, "creators.json")
    w = config.settings()["radar"]["weights"]
    by_lang = defaultdict(list)
    for c in creators:
        by_lang[c["language"]].append(scoring.CreatorInput(
            c["id"], c["language"], [tuple(s) for s in c["samples"] if s[0] < 168] + [tuple(s) for s in c["samples"] if s[0] >= 168],
            [tuple(x) for x in c["clips"]], c["platform"] == "twitch", c["offplatform"]))
    target = {c["id"]: c["next_week_hours_watched"] for c in creators}
    rhos, examples = [], []
    for lang, items in sorted(by_lang.items()):
        scored = scoring.score_language(items, w)
        xs = [s.score for s in scored]
        ys = [target[s.creator_id] for s in scored]
        rhos.append(spearmanr(xs, ys).statistic)
        # worst: biggest rank disagreement
        lang_ids = [s.creator_id for s in scored]
        rank_t = {cid: r for r, cid in enumerate(sorted(lang_ids, key=lambda k: -target[k]), 1)}
        for s in scored:
            examples.append(Example(f"{lang}:creator{s.creator_id}", "rank_gap", abs(s.rank - rank_t[s.creator_id]),
                                    f"score={s.score:.3f} target={target[s.creator_id]:.0f}"))
    examples.sort(key=lambda e: -e.value)
    return StageResult({"spearman": float(sum(rhos) / len(rhos))}, examples, dsver(d))
