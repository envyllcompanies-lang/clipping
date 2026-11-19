"""Hook headline as an overlay image (doc 11 "Text style" arms, docs/research/gta6-clip-examples.md).

Two starting text styles: **box** (white rounded box, black text: the native TikTok/Snapchat text look) and
**outline** (white text, black outline + soft shadow). Rendered with PIL (raqm shaping for Arabic/Japanese) so the
emoji ending keeps its colour (libass draws emoji as monochrome outlines). Headline case: sentence case is the
starting favorite, ALL CAPS a test arm."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from clipping.captions.ass import font_for

EMOJI_FONT = Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf")
_EMO = "[\U0001f300-\U0001faff\u2600-\u27bf\u2b50\u2b55\u2934\u2935\u3030\u303d\u3297\u3299]"
_MOD = "[\ufe0f\U0001f3fb-\U0001f3ff]*"
EMOJI_RE = re.compile(f"([\U0001f1e6-\U0001f1ff]{{2}}|{_EMO}{_MOD}(?:\u200d{_EMO}{_MOD})*)")
KEEP = re.compile(r"\b(GTA\s?(6|VI)|NPC|NPCs|AI|FIB|LSPD|VCPD|II|III|IV)\b", re.I)
NO_CASE = {"ja", "ar"}


def strip_emoji(text: str) -> str:
    return re.sub(r"\s{2,}", " ", EMOJI_RE.sub("", text)).strip()


def apply_case(text: str, case: str, language: str, keep: list[str] | None = None) -> str:
    """'upper' -> ALL CAPS; 'sentence' -> first letter of each sentence capitalized, the rest lower, except creator
    names, "GTA 6" and acronyms (kept as given). Scripts without case are unchanged."""
    if language in NO_CASE:
        return text
    if case == "upper":
        return text.upper()
    if case != "sentence":
        return text
    keep = [k for k in (keep or []) if k]
    letters = [ch for ch in text if ch.isalpha()]
    mostly_upper = letters and sum(ch.isupper() for ch in letters) / len(letters) > 0.6
    out = text.lower() if mostly_upper else text
    out = re.sub(r"(^|[.!?…]\s+|^[\"“«¿¡]+)(\w)", lambda m: m.group(1) + m.group(2).upper(), out)
    out = re.sub(r"^([\"“«¿¡]+)(\w)", lambda m: m.group(1) + m.group(2).upper(), out)
    for k in keep:
        out = re.sub(re.escape(k), k, out, flags=re.I)
    out = KEEP.sub(lambda m: m.group(0).upper().replace("GTA6", "GTA 6"), out)
    return out


@lru_cache(maxsize=16)
def _font(path: str, size: int):
    return ImageFont.truetype(path, size)


@lru_cache(maxsize=64)
def _emoji(ch: str, px: int) -> Image.Image | None:
    if not EMOJI_FONT.exists():
        return None
    f = ImageFont.truetype(str(EMOJI_FONT), 109)  # CBDT: only the native strike size
    im = Image.new("RGBA", (160, 160))
    ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
    bb = im.getbbox()
    if not bb:
        return None
    im = im.crop(bb)
    return im.resize((max(1, int(px * im.width / im.height)), px), Image.LANCZOS)


def _runs(text: str) -> list[tuple[str, bool]]:
    out, pos = [], 0
    for m in EMOJI_RE.finditer(text):
        if m.start() > pos:
            out.append((text[pos : m.start()], False))
        out.append((m.group(0), True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False))
    return out


def _width(text: str, font, px: int) -> float:
    w = 0.0
    for run, emo in _runs(text):
        w += (px * 1.1 * len(EMOJI_RE.findall(run))) if emo else font.getlength(run)
    return w


def wrap(text: str, font, px: int, max_w: float, max_lines: int = 2) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if cur and _width(trial, font, px) > max_w:
            lines.append(cur)
            cur = wd
        else:
            cur = trial
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1 :])]
    return lines


def render(
    text: str,
    language: str,
    style: str,
    size_px: int,
    max_w: int,
    out_path: Path | str,
    *,
    cfg: dict | None = None,
    emoji: bool = True,
) -> dict:
    """Writes an RGBA PNG of the headline; returns {path, w, h, lines, scale}. Shrinks (down to 60%) to fit two
    lines inside max_w."""
    cfg = cfg or {}
    if not emoji or not EMOJI_FONT.exists():
        text = strip_emoji(text)
    _, fpath = font_for(language)
    rtl = language == "ar"
    for scale in (1.0, 0.9, 0.8, 0.7, 0.6):
        px = int(size_px * scale)
        font = _font(str(fpath), px)
        pad = int(px * cfg.get("pad_pct", 0.28))
        lines = wrap(text, font, px, max_w - 2 * pad)
        if max(_width(ln, font, px) for ln in lines) <= max_w - 2 * pad or scale == 0.6:
            break
    line_h = int(px * 1.25)
    widths = [_width(ln, font, px) for ln in lines]
    W = int(max(widths) + 2 * pad)
    H = int(line_h * len(lines) + pad * 1.2)
    outline = int(cfg.get("outline_px", max(4, px // 9))) if style == "outline" else 0
    margin = outline + 8
    im = Image.new("RGBA", (W + 2 * margin, H + 2 * margin), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    fill = cfg.get("box_fill", "#FFFFFF")
    if style == "box":
        r = int(line_h * cfg.get("radius_pct", 0.32))
        y = margin
        for i, w in enumerate(widths):  # one rounded box per line, hugging the text (native look)
            bw = int(w + 2 * pad)
            x = margin + (W - bw) // 2
            y0 = y + i * line_h
            y1 = y0 + line_h + (int(pad * 1.2) if i == len(widths) - 1 else int(pad * 0.4))
            dr.rounded_rectangle([x, y0, x + bw, y1], radius=r, fill=fill)
    text_fill = cfg.get("box_text", "#000000") if style == "box" else cfg.get("outline_fill", "#FFFFFF")
    shadow = None
    if style == "outline":
        shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    for i, (ln, w) in enumerate(zip(lines, widths, strict=True)):
        x = margin + (W - w) / 2
        y = margin + int(pad * 0.6) + i * line_h
        ym = (
            y + line_h / 2
        )  # vertical center of the line (anchor "lm": scripts with tall ascenders stay centered)
        runs = _runs(ln)
        if rtl:
            runs = runs[::-1]
        for run, emo in runs:
            if emo:
                for ch in EMOJI_RE.findall(run):
                    g = _emoji(ch, int(px * 0.95))
                    if g is not None:
                        im.alpha_composite(g, (int(x + px * 0.05), int(ym - g.height / 2)))
                    x += px * 1.1
                continue
            kw = {"direction": "rtl"} if rtl else {}
            if shadow is not None:
                ImageDraw.Draw(shadow).text(
                    (x + 3, ym + 4),
                    run,
                    font=font,
                    fill=(0, 0, 0, 160),
                    stroke_width=outline,
                    anchor="lm",
                    **kw,
                )
            dr.text(
                (x, ym),
                run,
                anchor="lm",
                font=font,
                fill=text_fill,
                stroke_width=outline,
                stroke_fill=cfg.get("outline_color", "#000000"),
                **kw,
            )
            x += font.getlength(run, **kw)
    if shadow is not None:
        im = Image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3)), im)
    im.save(out_path)
    return {"path": str(out_path), "w": im.width, "h": im.height, "lines": lines, "scale": scale}
