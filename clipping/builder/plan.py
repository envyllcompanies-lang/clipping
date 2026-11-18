"""Clip Builder (doc 09): window -> edit plans (short, long, optional loop) using rules first and an LLM tie-break
that only ever sees and returns word indices. Times are derived from indices in code."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np

from clipping.core import config
from clipping.llm import client as llm

SENT_END = (".", "!", "?", "…", "。", "！", "？")
EVENT_PRIORITY = {"death": 1.0, "arrest": 0.95, "crash": 0.9, "wanted": 0.7, "mission": 0.6}
LONG_HOLD = {"crash", "death"}  # hold longer after explosions/crashes so they land
MAX_GAP_SILENCE = 0.3


@dataclass
class Inputs:
    duration: float  # window length (s)
    words: list[dict]  # numbered, window-relative times
    events: list[dict] = field(default_factory=list)  # {t, type, confidence} window-relative
    peak_t: float | None = None  # heatmap peak (window-relative; chat already lag-shifted)
    scene_cuts: list[float] = field(default_factory=list)
    activity: np.ndarray | None = None  # per-second action level 0..1 (motion + game audio)
    negative_spans: list[tuple[float, float]] = field(default_factory=list)  # loading/menu
    language: str = "en"
    creator: str = ""
    moment: dict | None = None  # doc 31 typed moment: type, type_confidence, anchor_s, start_s, end_s, hook_style
    catchphrases: list[str] = field(default_factory=list)  # doc 32 signature lines (kept in the clip when present)


@dataclass
class Candidate:
    t: float
    word: int | None
    kind: str


def payoff(inp: Inputs) -> tuple[float, str, int | None]:
    """Game event > heatmap peak (audio spike aligned with chat peak) > LLM punchline (set later)."""
    best = None
    for e in inp.events:
        if e["type"] not in EVENT_PRIORITY or e.get("confidence", 1) < 0.6:
            continue
        near = 1.0 if inp.peak_t is None else max(0.0, 1 - abs(e["t"] - inp.peak_t) / 30)
        s = EVENT_PRIORITY[e["type"]] * e.get("confidence", 1) * (0.5 + 0.5 * near)
        if best is None or s > best[0]:
            best = (s, e["t"], e["type"])
    m = inp.moment or {}
    if best:
        t, kind = best[1], best[2]
    elif m.get("type_confidence", 0) >= 0.5 and m.get("anchor_s") is not None:  # doc 31: typed payoff (impact, beat, laugh)
        t, kind = float(m["anchor_s"]), m["type"]
    elif inp.peak_t is not None:
        t, kind = inp.peak_t, "peak"
    else:
        t, kind = inp.duration / 2, "middle"
    w = next((x["index"] for x in inp.words if x["start"] <= t <= x["end"] + 0.3), None)
    return float(t), kind, w


def start_candidates(inp: Inputs, pay: float, lo_s: float, hi_s: float) -> list[Candidate]:
    out = []
    ws = inp.words
    for i, w in enumerate(ws):
        if not (pay - hi_s <= w["start"] <= pay - lo_s):
            continue
        prev = ws[i - 1] if i else None
        if prev is None or prev["word"].endswith(SENT_END):
            out.append(Candidate(w["start"] - 0.05, i, "sentence"))
        elif w["start"] - prev["end"] > MAX_GAP_SILENCE:
            out.append(Candidate(w["start"] - 0.05, i, "silence"))
    for t in inp.scene_cuts:
        if pay - hi_s <= t <= pay - lo_s and not inside_word(ws, t):
            out.append(Candidate(t, None, "scene"))
    if not ws:  # visual-only: time grid
        out += [Candidate(t, None, "grid") for t in np.arange(max(0, pay - hi_s), pay - lo_s + 0.01, 1.0)]
    return [c for c in out if c.t >= 0 and not in_spans(c.t, inp.negative_spans)]


def end_candidates(inp: Inputs, pay: float, kind: str) -> list[Candidate]:
    hold_lo = 1.0 if kind in LONG_HOLD else 0.5
    hold_hi = 3.0 if kind in LONG_HOLD else 2.0
    if kind in ("peak", "middle"):  # payoff estimated from the heatmap curve (+-2-3 s): leave room after it
        hold_lo, hold_hi = 3.0, 5.0
    ws = inp.words
    out = []
    after = [w for w in ws if w["start"] >= pay - 0.2]
    for i, w in enumerate(after[:12]):  # end within one sentence after the payoff
        nxt = after[i + 1] if i + 1 < len(after) else None
        if pay + hold_lo <= w["end"] + 0.1 <= pay + hold_hi + 2.5 and (
            w["word"].endswith(SENT_END) or nxt is None or nxt["start"] - w["end"] > MAX_GAP_SILENCE
        ):
            out.append(Candidate(min(inp.duration, w["end"] + 0.15), w["index"], "sentence_end"))
        if w["word"].endswith(SENT_END) and w["end"] > pay + hold_lo:
            break
    for t in np.arange(pay + hold_lo, pay + hold_hi + 0.01, 0.25):  # silence: never cut mid-word
        if not inside_word(ws, t) and t <= inp.duration:
            out.append(Candidate(float(t), None, "silence"))
    for a, b in zip(ws, ws[1:], strict=False):  # word boundaries inside continuous speech
        mid = (a["end"] + b["start"]) / 2
        if pay + hold_lo <= mid <= pay + hold_hi and mid <= inp.duration:
            out.append(Candidate(round(mid, 3), a["index"], "word_boundary"))
    return out


def inside_word(ws: list[dict], t: float) -> bool:
    return any(w["start"] < t < w["end"] for w in ws)


def in_spans(t: float, spans) -> bool:
    return any(a <= t <= b for a, b in spans)


def backref(inp: Inputs, start_word: int | None) -> bool:
    if start_word is None:
        return False
    refs = config.load("backrefs.yaml").get(inp.language, [])
    text = " ".join(w["word"] for w in inp.words[start_word : start_word + 6]).lower()
    text = "".join(ch for ch in text if ch.isalnum() or ch.isspace() or ord(ch) > 127)
    return any(text.startswith(r) for r in refs)


def choose_rule(
    starts: list[Candidate], ends: list[Candidate], pay: float, target: float, lo: float, hi: float,
    hint: tuple[float, float] | None = None,
) -> tuple[Candidate, Candidate] | None:
    """hint: doc 31 type-specific (start, end) recommendation; candidates near it score higher."""
    best, best_s = None, -1e9
    for s in starts:
        for e in ends:
            length = e.t - s.t
            if not (lo <= length <= hi) or not (s.t < pay < e.t):
                continue
            score = -abs(length - target) / target
            score += {"sentence": 0.3, "silence": 0.15, "scene": 0.1}.get(s.kind, 0)
            score += 0.2 if e.kind == "sentence_end" else 0
            score -= 0.05 * max(0.0, e.t - pay - 1.5)
            if hint is not None:
                score -= 0.02 * (abs(s.t - hint[0]) + abs(e.t - hint[1]))
            if score > best_s:
                best, best_s = (s, e), score
    return best


def llm_choose(inp: Inputs, starts, ends, pay_word, style: dict, c=None) -> dict | None:
    """Word-index prompt. The model never sees or returns times; output validated against candidate sets."""
    if not llm.available() or not inp.words:
        return None
    sw = sorted({s.word for s in starts if s.word is not None})
    ew = sorted({e.word for e in ends if e.word is not None})
    if not sw or not ew:
        return None
    marks = {}
    for e in inp.events:
        w = next((x["index"] for x in inp.words if x["start"] >= e["t"] - 0.3), None)
        if w is not None:
            marks.setdefault(w, []).append(f"<{e['type']}>")
    numbered = " ".join(f"[{w['index']}]{w['word']}{''.join(marks.get(w['index'], []))}" for w in inp.words)
    prompt = (
        f"Transcript of a {inp.language} GTA 6 stream moment by {inp.creator}. Words are numbered.\n{numbered}\n\n"
        f"Valid start words: {sw}\nValid end words: {ew}\nPayoff word (rules): {pay_word}\n"
        f"Style: cold open {style['hook']['cold_open_share'] >= 0.5}, target {style['length']['short']['target']} s.\n"
        'Pick the clip that makes sense to a cold viewer. Return JSON: {"start_word": int, "end_word": int, '
        '"hook": {"start_word": int, "end_word": int}, "payoff_word": int, "emphasis_words": [int], '
        '"standalone": bool, "reason_code": str}'
    )
    for _ in range(2):  # invalid output is retried once, then rules decide
        out = llm.call_json(
            prompt, "You edit short-form gaming clips. Answer only with word indices from the lists.", c=c
        )
        if (
            out
            and out.get("start_word") in sw
            and out.get("end_word") in ew
            and out["start_word"] < out["end_word"]
        ):
            h = out.get("hook") or {}
            if not (
                isinstance(h.get("start_word"), int)
                and isinstance(h.get("end_word"), int)
                and 0 <= h["start_word"] <= h["end_word"] < len(inp.words)
            ):
                out["hook"] = None
            out["emphasis_words"] = [
                i for i in out.get("emphasis_words", []) if isinstance(i, int) and 0 <= i < len(inp.words)
            ]
            return out
    return None


def dead_air_cuts(inp: Inputs, s: float, e: float, min_gap: float) -> list[tuple[float, float]]:
    """Pauses over min_gap removed only when nothing happens on screen (low activity) and never in negative spans."""
    cuts = []
    ws = [w for w in inp.words if s <= w["start"] and w["end"] <= e]
    for a, b in zip(ws, ws[1:], strict=False):
        gap0, gap1 = a["end"] + 0.08, b["start"] - 0.08
        if gap1 - gap0 >= min_gap:
            act = inp.activity
            quiet = act is None or float(np.max(act[int(gap0) : int(np.ceil(gap1)) + 1], initial=0)) < 0.3
            if quiet:
                cuts.append((round(gap0, 3), round(gap1, 3)))
    return cuts


def emphasis(
    inp: Inputs, s: float, e: float, pay: float, every_s: float, chosen: list[int] | None = None
) -> list[float]:
    """Punch-in times: payoff + emphasized words, at the profile's zoom rate (one per ~every_s seconds)."""
    pts = [pay]
    cand = []
    for w in inp.words:
        if s <= w["start"] <= e:
            score = (
                w.get("conf", 1)
                + (1.0 if w["word"].isupper() and len(w["word"]) > 1 else 0)
                + (0.5 if w["word"].endswith("!") else 0)
            )
            if chosen and w["index"] in chosen:
                score += 2
            cand.append((score, w["start"]))
    for _, t in sorted(cand, reverse=True):
        if all(abs(t - p) >= every_s for p in pts):
            pts.append(t)
    return sorted(round(p, 3) for p in pts if s <= p <= e)


def build_version(inp: Inputs, style: dict, version: str, c=None) -> dict | None:
    pay, kind, pay_word = payoff(inp)
    L = style["length"]["long" if version == "long" else "short"]
    lo_back, hi_back = (8, 50) if version != "long" else (40, 88)
    starts = start_candidates(inp, pay, lo_back, hi_back)
    starts = [s for s in starts if not backref(inp, s.word)]
    ends = end_candidates(inp, pay, kind)
    pick = None
    chosen_llm = llm_choose(inp, starts, ends, pay_word, style, c) if version == "short" else None
    if chosen_llm:
        s = next(x for x in starts if x.word == chosen_llm["start_word"])
        e = next(x for x in ends if x.word == chosen_llm["end_word"])
        if L["min"] <= e.t - s.t <= L["max"] and s.t < pay < e.t:
            pick = (s, e)
    m = inp.moment or {}
    hint = (m["start_s"], m["end_s"]) if version == "short" and m.get("type_confidence", 0) >= 0.5 and "start_s" in m else None
    pick = pick or choose_rule(starts, ends, pay, L["target"], L["min"], L["max"], hint)
    if pick is None:
        return None
    s, e = pick
    hook = None
    if style["hook"]["cold_open_share"] >= 0.5:
        if chosen_llm and chosen_llm.get("hook"):
            h = chosen_llm["hook"]
            hs, he = inp.words[h["start_word"]]["start"], inp.words[h["end_word"]]["end"]
        else:  # tease the build-up into the payoff, without the resolution
            hs, he = max(s.t, pay - style["hook"]["hook_s"]), max(s.t + 0.5, pay - 0.15)
        if 1.0 <= he - hs <= 3.0:
            hook = {"start": round(hs, 3), "end": round(he, 3)}
    cuts = dead_air_cuts(inp, s.t, e.t, style["pacing"].get("dead_air_s", 0.4))
    zoom_every = 10 / max(style["pacing"]["zooms_per_10s"], 0.1)
    emph = emphasis(inp, s.t, e.t, pay, zoom_every, chosen_llm.get("emphasis_words") if chosen_llm else None)
    segments = [{"start": hook["start"], "end": hook["end"], "role": "hook"}] if hook else []
    cur = s.t
    for a, b in cuts:
        if a > cur:
            segments.append({"start": round(cur, 3), "end": a, "role": "body"})
        cur = b
    segments.append({"start": round(cur, 3), "end": round(e.t, 3), "role": "body"})
    length = sum(x["end"] - x["start"] for x in segments)
    w_in = [w for w in inp.words if s.t <= w["start"] <= e.t]
    return {
        "version": version,
        "payoff_t": round(pay, 3),
        "payoff_kind": kind,
        "payoff_word": pay_word,
        "start_t": round(s.t, 3),
        "end_t": round(e.t, 3),
        "start_word": s.word,
        "end_word": e.word,
        "start_kind": s.kind,
        "end_kind": e.kind,
        "segments": segments,
        "hook": hook,
        "length": round(length, 3),
        "ending": "hold" if kind in LONG_HOLD else "hard",
        "emphasis_t": emph,
        "dead_air_cuts": cuts,
        "standalone": not backref(inp, s.word),
        "reason_code": (chosen_llm or {}).get("reason_code") or f"{kind}_payoff",
        "decided_by": "llm" if chosen_llm and pick[0].word == chosen_llm.get("start_word") else "rules",
        "words": [w["index"] for w in w_in][:1] + [w["index"] for w in w_in][-1:],
        "transformations": ["hook_text", "captions", "credit"]
        + (["zooms"] if len(emph) >= 2 else [])
        + (["cold_open"] if hook else [])
        + (["context_text"] if kind in EVENT_PRIORITY else []),
    }


def build(inp: Inputs, style_name: str = "house", c=None) -> dict:
    from clipping.style import profiles

    style = profiles.load(style_name)
    plans = {}
    for v in ("short", "long"):
        p = build_version(inp, style, v, c)
        if p:
            plans[v] = p
    return {"style": style_name, "versions": plans, "discarded": None if plans else "no valid boundaries"}


def validate(plan: dict, inp: Inputs, platform_limits: dict | None = None) -> list[str]:
    errs = []
    if plan["start_word"] is not None and not 0 <= plan["start_word"] < len(inp.words):
        errs.append("start_word out of range")
    if plan["end_word"] is not None and not 0 <= plan["end_word"] < len(inp.words):
        errs.append("end_word out of range")
    if not plan["start_t"] < plan["payoff_t"] < plan["end_t"]:
        errs.append("payoff outside clip")
    for seg in plan["segments"]:
        if not 0 <= seg["start"] < seg["end"] <= inp.duration + 1e-6:
            errs.append(f"segment out of window {seg}")
    for name, (lo, hi) in (platform_limits or {}).items():
        if not lo <= plan["length"] <= hi:
            errs.append(f"length {plan['length']} outside {name} {lo}-{hi}")
    return errs


def dumps(plan: dict) -> str:
    return json.dumps(plan, ensure_ascii=False)
