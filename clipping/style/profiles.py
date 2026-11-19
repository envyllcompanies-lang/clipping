"""Style profiles (doc 13): load, validate, blend, and pick A/B arms. Switching styles is pure config."""

from __future__ import annotations

import copy
from typing import Any

from clipping.core import config

REQUIRED = ["length", "pacing", "hook", "layout", "captions", "audio", "ending"]


def load(name: str) -> dict:
    p = config.style(name)
    missing = [k for k in REQUIRED if k not in p]
    if missing:
        base = config.style("house")
        for k in missing:
            p[k] = copy.deepcopy(base[k])
    return p


def _blend(values: list[Any], weights: list[float]) -> Any:
    if all(isinstance(v, bool) for v in values):
        tot = {}
        for v, w in zip(values, weights, strict=True):
            tot[v] = tot.get(v, 0) + w
        return max(tot, key=tot.get)
    if all(isinstance(v, (int, float)) for v in values):
        return round(sum(v * w for v, w in zip(values, weights, strict=True)) / sum(weights), 4)
    if all(isinstance(v, dict) for v in values):
        keys = set().union(*values)
        return {
            k: _blend(
                [v[k] for v in values if k in v], [w for v, w in zip(values, weights, strict=True) if k in v]
            )
            for k in keys
        }
    if all(isinstance(v, list) for v in values) and len({len(v) for v in values}) == 1:
        return [_blend(list(col), weights) for col in zip(*values, strict=True)]
    return max(zip(values, weights, strict=True), key=lambda vw: vw[1])[0]  # categorical: majority by weight


def blend(names: list[str], weights: list[float] | None = None, name: str = "blend") -> dict:
    """Weighted average of numbers, majority vote of booleans/categories (doc 13)."""
    weights = weights or [1.0] * len(names)
    profs = [load(n) for n in names]
    out = {
        k: _blend([p[k] for p in profs if k in p], [w for p, w in zip(profs, weights, strict=True) if k in p])
        for k in REQUIRED
    }
    out["name"] = name
    out["source"] = "blend of " + ", ".join(f"{n}×{w}" for n, w in zip(names, weights, strict=True))
    return out


def layout_arms(profile: dict) -> dict[str, float]:
    arms = profile["layout"].get("arms") or {"stacked": 1.0}
    tot = sum(arms.values())
    return {k: v / tot for k, v in arms.items()}


TEXT_ARMS = {
    "text_mode": ("text_mode_arms", {"full": 1.0}),
    "text_style": ("text_style_arms", {"outline": 1.0}),
    "headline_case": ("headline_case_arms", {"upper": 1.0}),
}


def text_arms(profile: dict, kind: str) -> dict[str, float]:
    """Starting shares for a caption text arm (doc 11): text_mode, text_style or headline_case."""
    key, default = TEXT_ARMS[kind]
    arms = profile["captions"].get(key) or default
    tot = sum(arms.values())
    return {k: v / tot for k, v in arms.items()}


def sample(arms: dict[str, float], rng) -> str:
    names = [a for a in arms if arms[a] > 0]
    r, acc = rng.random() * sum(arms[a] for a in names), 0.0
    for a in names:
        acc += arms[a]
        if r <= acc:
            return a
    return names[-1]
