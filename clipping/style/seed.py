"""Seed examples for the style study (doc 13): owner-captured GTA 6 clips with views
(docs/research/gta6-clip-examples.md) loaded as the first labelled examples before the automated study has data.

Small sample (7 clips, one account, < 1 day of views): starting priors only; the A/B system decides. The parsed
examples and the priors derived from them are written to config/styles/examples/gta6-clip-examples.yaml."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from clipping.captions.headline import EMOJI_RE
from clipping.core import config
from clipping.core.settings import ROOT

SOURCE = ROOT / "docs" / "research" / "gta6-clip-examples.md"
OUT = "styles/examples/gta6-clip-examples.yaml"

MOMENT_MAP = [  # first match wins; values are doc 31 taxonomy types
    ("music", "music_celebrity"),
    ("comedy", "comedy"),
    ("crash", "crash"),
    ("arrest", "death"),  # busted banner: the fail/death payoff type
    ("fail", "death"),
    ("discovery", "discovery"),
]


def _views(s: str) -> int:
    m = re.search(r"([\d.]+)\s*([KkMm]?)", s.replace("*", ""))
    if not m:
        return 0
    return int(float(m.group(1)) * {"": 1, "k": 1_000, "m": 1_000_000}[m.group(2).lower()])


def _moment(s: str) -> str:
    low = s.lower()
    return next((t for k, t in MOMENT_MAP if k in low), "comedy")


def _layout(s: str) -> str:
    low = s.lower()
    return "letterbox" if "raw 16:9" in low or "black bars" in low else "stacked"


def _text_style(s: str) -> str:
    low = s.lower()
    return "box" if "box" in low else "outline"  # white outlined text / plain white text in a black bar


def parse(path: Path | str = SOURCE) -> list[dict]:
    """Rows of the "Snapchat examples" table."""
    rows, in_table = [], False
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_table = "snapchat examples" in line.lower()
            continue
        if not in_table or not line.startswith("|") or set(line) <= set("|- "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 7 or not cells[0].isdigit():
            continue
        n, shot, creator, mtype, layout, text, views = cells[:7]
        headline = text.split(":", 1)[1].strip() if ":" in text else ""
        rows.append(
            {
                "id": int(n),
                "platform": "snapchat",
                "screenshot": (re.search(r"\(([^)]+)\)", shot) or [None, None])[1],
                "creator": creator,
                "moment_type": _moment(mtype),
                "moment_note": mtype,
                "layout": _layout(layout),
                "text_style": _text_style(text),
                "headline_case": "upper" if "ALL CAPS" in text else "sentence",
                "quote_hook": "quote" in text.lower(),
                "emojis": len(EMOJI_RE.findall(text)) or int("emoji row" in (layout + text).lower()),
                "headline": headline,
                "views": _views(views),
            }
        )
    return rows


def priors(examples: list[dict]) -> dict:
    """Starting shares derived from the examples (counts for text arms, views for layout and moment types)."""
    n = len(examples)
    cnt = lambda k: {v: round(c / n, 3) for v, c in Counter(e[k] for e in examples).items()}  # noqa: E731

    def mean_views(k: str) -> dict:
        out: dict[str, list[int]] = {}
        for e in examples:
            out.setdefault(e[k], []).append(e["views"])
        return {v: int(sum(x) / len(x)) for v, x in out.items()}

    return {
        "n": n,
        "text_style": cnt("text_style"),
        "headline_case": cnt("headline_case"),
        "layout": cnt("layout"),
        "mean_views_by_layout": mean_views("layout"),
        "mean_views_by_moment_type": mean_views("moment_type"),
        "emoji_ending_share": round(sum(e["emojis"] > 0 for e in examples) / n, 3),
        "quote_hook_share": round(sum(e["quote_hook"] for e in examples) / n, 3),
        "creator_named_share": round(
            sum(e["creator"].split()[0].lower() in e["headline"].lower() or e["quote_hook"] for e in examples)
            / n,
            3,
        ),
    }


def load(save: bool = True) -> dict:
    ex = parse()
    doc = {
        "source": str(SOURCE.relative_to(ROOT)),
        "note": "owner-captured seed examples; small sample, starting priors only (doc 13)",
        "examples": ex,
        "priors": priors(ex),
    }
    if save:
        config.save(OUT, doc)
    return doc


def examples() -> list[dict]:
    """Seed examples as labelled data for the style study (falls back to parsing the research doc)."""
    try:
        return config.load(OUT)["examples"]
    except FileNotFoundError:
        return parse()
