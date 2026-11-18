"""Captions & On-screen Text (doc 11): word timestamps -> ASS subtitles (libass) with hook headline, spoken
captions, emphasis, creator credit and profanity handling. Styling comes entirely from the style profile."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from clipping.core.settings import ROOT

FONTS_DIR = ROOT / "assets" / "fonts"
FONT_FOR = {
    "ar": ("Noto Sans Arabic ExtraBold", "NotoSansArabic-ExtraBold.ttf"),
    "ja": ("Noto Sans JP ExtraBold", "NotoSansJP-ExtraBold.ttf"),
}
DEFAULT_FONT = ("Montserrat ExtraBold", "Montserrat-ExtraBold.ttf")
PUNCT_BREAK = (".", "!", "?", ",", ";", ":", "…", "。", "、", "！", "？", "،")
PROFANITY = {
    "en": ["fuck", "fucking", "shit", "bitch", "asshole", "dick", "cunt", "motherfucker"],
    "es": ["mierda", "puta", "joder", "cabrón", "pendejo", "coño"],
    "pt": ["porra", "caralho", "merda", "puta", "foda"],
    "fr": ["putain", "merde", "connard", "salope"],
    "de": ["scheiße", "scheisse", "fick", "arschloch", "hurensohn"],
    "ru": ["блять", "бля", "сука", "хуй", "пиздец"],
    "tr": ["siktir", "amk", "orospu"],
    "vi": ["địt", "đéo", "vãi lồn"],
    "ar": ["كس", "شرموط"],
    "ja": ["くそ", "ちくしょう"],
}


@dataclass
class Line:
    start: float
    end: float
    words: list[dict]


def font_for(language: str) -> tuple[str, Path]:
    name, file = FONT_FOR.get(language, DEFAULT_FONT)
    return name, FONTS_DIR / file


@lru_cache(maxsize=32)
def _pil_font(path: str, size: int):
    return ImageFont.truetype(path, size)


def text_width(text: str, language: str, size: int) -> float:
    return _pil_font(str(font_for(language)[1]), size).getlength(text)


def map_time(t: float, segments: list[dict]) -> float | None:
    """Source-window time -> output time through the plan's segments (hook first, dead-air cuts removed).
    A time inside the hook maps to the hook position; body times map to the body."""
    out = 0.0
    hit = None
    for seg in segments:
        if seg["start"] <= t <= seg["end"]:
            cand = out + (t - seg["start"])
            if seg["role"] != "hook":
                return cand
            hit = hit if hit is not None else cand
        out += seg["end"] - seg["start"]
    return hit


def keep_together(a: dict, b: dict) -> bool:
    """Never split a name ("Jason Stone") or a number ("5 stars" keeps the number with its noun)."""
    wa, wb = a["word"].strip(), b["word"].strip()
    if wa[-1:] in PUNCT_BREAK:
        return False
    if wa[:1].isupper() and wb[:1].isupper() and wa.isalpha() and not wa.isupper():
        return True
    return bool(re.fullmatch(r"[\d.,%$€]+", wa))


def group(words: list[dict], wpl: tuple[int, int], min_on: float = 0.4, bridge: float = 0.3) -> list[Line]:
    lo, hi = wpl
    lines: list[list[dict]] = []
    cur: list[dict] = []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        brk = nxt is None or len(cur) >= hi or (len(cur) >= lo and w["word"].rstrip()[-1:] in PUNCT_BREAK)
        if nxt is not None and nxt["start"] - w["end"] > 0.7:
            brk = True  # a long pause ends the line
        if brk and nxt is not None and keep_together(w, nxt) and len(cur) < hi + 1:
            brk = False
        if brk:
            lines.append(cur)
            cur = []
    out = [Line(ln[0]["start"], ln[-1]["end"], ln) for ln in lines if ln]
    merged: list[Line] = []
    for ln in out:  # minimum on-screen time: merge too-fast lines
        if (
            merged
            and (ln.end - ln.start < min_on or merged[-1].end - merged[-1].start < min_on)
            and len(merged[-1].words) + len(ln.words) <= hi + 2
        ):
            merged[-1] = Line(merged[-1].start, ln.end, merged[-1].words + ln.words)
        else:
            merged.append(ln)
    for a, b in zip(merged, merged[1:], strict=False):  # bridge small gaps so text doesn't flicker
        if 0 < b.start - a.end < bridge:
            a.end = b.start
    return merged


def drop_low_confidence(lines: list[Line], thresh: float = 0.5) -> list[Line]:
    out = []
    for ln in lines:
        low = [w for w in ln.words if w.get("conf", 1) < thresh]
        if not low:
            out.append(ln)
        elif (
            len(low) == 1
            and len(ln.words) >= 3
            and all(w.get("conf", 1) >= 0.8 for w in ln.words if w not in low)
        ):
            out.append(ln)  # one shaky word among confident neighbours still reads naturally
    return out


def mask(word: str, language: str, mode: str) -> str:
    if mode == "show":
        return word
    core = re.sub(r"\W", "", word.lower())
    if core and any(core.startswith(p) for p in PROFANITY.get(language, []) + PROFANITY["en"]):
        if mode == "mask":
            return word[0] + "*" * max(1, len(word) - 2) + (word[-1] if len(word) > 2 else "")
        return "#!@%"
    return word


def _ass_color(hexrgb: str) -> str:
    h = hexrgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, m = int(t // 3600), int(t % 3600 // 60)
    return f"{h}:{m:02d}:{t % 60:05.2f}"


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def wrap(text: str, language: str, size: int, max_w: float) -> str:
    if text_width(text, language, size) <= max_w:
        return text
    if language in ("ja", "zh") and " " not in text.strip():
        # no spaces: break between characters, preferring just after particles/punctuation, near the middle
        n = len(text)
        prefs = set("、。！？はがをにでとのもへや")
        best = None
        for k in range(1, n):
            a, b = text[:k], text[k:]
            wmax = max(text_width(a, language, size), text_width(b, language, size)) - (
                size * 0.3 if text[k - 1] in prefs else 0
            )
            if best is None or wmax < best[0]:
                best = (wmax, a + "\\N" + b)
        return best[1]
    words = text.split(" ")
    best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        wmax = max(text_width(a, language, size), text_width(b, language, size))
        if best is None or wmax < best[0]:
            best = (wmax, a + "\\N" + b)
    return best[1] if best else text


def fit(
    text: str, language: str, size: int, max_w: float, max_lines: int = 2, min_scale: float = 0.65
) -> tuple[str, float]:
    """Wrap up to max_lines, then shrink the font for this line only; returns (text with \\N, scale)."""
    t = wrap(text, language, size, max_w) if max_lines >= 2 else text
    widest = max(text_width(seg, language, size) for seg in t.split("\\N"))
    if widest <= max_w:
        return t, 1.0
    scale = max_w / widest
    if len(text.split()) == 1 and language not in ("ja", "zh"):
        min_scale = min(min_scale, 0.45)  # one very long compound word: shrink further rather than overflow
    return t, max(min_scale, scale)


def build_ass(
    plan: dict,
    crop_plan: dict,
    words: list[dict],
    style: dict,
    *,
    language: str,
    hook_text: str,
    credit: str,
    profanity: str = "mask",
    emphasis_words: set[int] | None = None,
) -> tuple[str, dict]:
    """Returns (ASS document, report) — report has per-line timing and width checks used by tests/backtests."""
    Wc, Hc = crop_plan["canvas"]
    cap = style["captions"]
    size = int(Hc * cap["size_pct"])
    font, _ = font_for(language)
    band = crop_plan["caption_band"]
    y = (band[0] + band[1]) // 2
    max_w = Wc * 0.80  # inside the right 15% clear zone and a left margin
    accent, fill, head = (
        _ass_color(cap["accent"]),
        _ass_color(cap["fill"]),
        _ass_color(cap.get("headline_fill", cap["accent"])),
    )
    outline, shadow = cap["outline_px"], cap.get("shadow_px", 2)
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {Wc}
PlayResY: {Hc}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{size},{fill},{accent},&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,{outline},{shadow},5,60,60,0,1
Style: Headline,{font},{int(size * 1.05)},{head},{head},&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,{outline},{shadow},5,60,60,0,1
Style: Credit,{font},{int(size * 0.42)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,3,1,7,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    total = sum(s["end"] - s["start"] for s in plan["segments"])
    hook_end = min(style["hook"].get("hook_text_s", 2.5), total)
    head_txt = hook_text.upper() if cap.get("all_caps") and language not in ("ja", "ar") else hook_text
    htxt, hsc = fit(_esc(head_txt), language, int(size * 1.05), max_w, 2)
    events.append(
        f"Dialogue: 2,{_ts(0)},{_ts(hook_end)},Headline,,0,0,0,,{{\\pos({Wc // 2},{y})\\fad(80,120)"
        f"\\fscx{int(hsc * 100)}\\fscy{int(hsc * 100)}}}{htxt}"
    )
    cx, cy = 40, min(band[1] + 30, int(0.78 * Hc) - 40)
    events.append(f"Dialogue: 1,{_ts(0)},{_ts(total)},Credit,,0,0,0,,{{\\pos({cx},{cy})}}{_esc(credit)}")
    body = [
        w
        for w in words
        if any(
            s["role"] == "body" and s["start"] <= w["start"] and w["end"] <= s["end"] + 0.05
            for s in plan["segments"]
        )
    ]
    lines = drop_low_confidence(
        group(
            body, tuple(cap["words_per_line"]), cap.get("min_on_screen_s", 0.4), cap.get("bridge_gap_s", 0.3)
        )
    )
    report = {"lines": [], "max_width_ratio": 0.0, "headline": head_txt, "credit": credit}
    emph = emphasis_words or set()
    pop = "{\\fscx90\\fscy90\\t(0,80,\\fscx100\\fscy100)}" if cap.get("animation") == "pop" else ""
    for ln in lines:
        t0, t1 = map_time(ln.start, plan["segments"]), map_time(ln.end, plan["segments"])
        if t0 is None or t1 is None or t1 <= t0:
            continue
        t0 = max(t0, hook_end)  # headline owns the band during the hook
        if t1 - t0 < 0.2:
            continue
        parts = []
        for w in ln.words:
            txt = mask(w["word"], language, profanity)
            if cap.get("all_caps") and language not in ("ja", "ar"):
                txt = txt.upper()
            sc = int(100 * cap.get("emphasis_scale", 1.1))
            parts.append(
                f"{{\\c{accent}\\fscx{sc}\\fscy{sc}}}{_esc(txt)}{{\\r}}" if w["index"] in emph else _esc(txt)
            )
        plain = " ".join(re.sub(r"\{[^}]*\}", "", p) for p in parts)

        def strip(ps):
            return " ".join(re.sub(r"\{[^}]*\}", "", x) for x in ps)

        def split_to_fit(c0, c1, ps):
            txt, scl = fit(strip(ps), language, size, max_w, cap.get("max_lines", 2))
            too_wide = scl * max(text_width(x, language, size) for x in txt.split("\\N")) > max_w * 1.001
            if not too_wide or len(ps) == 1:
                return [(c0, c1, strip(ps), ps)]
            k = len(ps) // 2  # too wide even at the floor size: split the line in time
            cm = c0 + (c1 - c0) * k / len(ps)
            return split_to_fit(c0, cm, ps[:k]) + split_to_fit(cm, c1, ps[k:])

        chunks = split_to_fit(t0, t1, parts)
        widest = 0.0
        for c0, c1, ptxt, pparts in chunks:
            text, sc = fit(ptxt, language, size, max_w, cap.get("max_lines", 2))
            body_txt = text if "\\N" in text else " ".join(pparts)
            scale_tag = f"\\fscx{int(sc * 100)}\\fscy{int(sc * 100)}" if sc < 1 else ""
            events.append(
                f"Dialogue: 0,{_ts(c0)},{_ts(c1)},Caption,,0,0,0,,{{\\pos({Wc // 2},{y}){scale_tag}}}{pop if not scale_tag else ''}{body_txt}"
            )
            widest = max(widest, sc * max(text_width(seg, language, size) for seg in text.split("\\N")))
        report["max_width_ratio"] = max(report["max_width_ratio"], widest / Wc)
        report["lines"].append(
            {
                "start": round(t0, 3),
                "end": round(t1, 3),
                "first_word": ln.words[0]["index"],
                "src_start": ln.start,
                "n_words": len(ln.words),
                "text": plain,
            }
        )
    return hdr + "\n".join(events) + "\n", report


def credit_line(creator: str, platform: str, template: str = "@{creator} on {platform}") -> str:
    return template.format(
        creator=creator,
        platform={"twitch": "Twitch", "kick": "Kick", "youtube": "YouTube"}.get(platform, platform),
    )
