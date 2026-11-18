"""Stage backtest 11: caption timing drift (<= 0.1 s), every line fits the frame, every clip has hook text and a
creator credit, ASS parses in libass, profile switch changes styling with no code."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np

from clipping.builder import backtest as bb
from clipping.builder import plan as bp
from clipping.captions import ass
from clipping.eval.harness import Example, StageResult, stage
from clipping.style import profiles

SAMPLES = {
    "en": "unbelievable absolutely incredible getaway driving",
    "es": "increíblemente espectacular persecución policial",
    "pt": "inacreditável perseguição policial absurdamente",
    "fr": "incroyablement spectaculaire poursuite policière",
    "de": "unglaublicherweise Verfolgungsjagd Polizeihubschrauber",
    "ru": "невероятно эффектная полицейская погоня",
    "tr": "inanılmaz muhteşem polis kovalamacası",
    "vi": "không thể tin được cuộc rượt đuổi cảnh sát",
    "ar": "مطاردة الشرطة المذهلة بشكل لا يصدق",
    "ja": "信じられないほど壮大な警察の追跡劇",
}


def crop_stub(layout: str = "stacked") -> dict:
    band = [768 - 120, 768 + 120] if layout == "stacked" else [1056 - 120, 1056 + 120]
    return {
        "canvas": [1080, 1920],
        "caption_band": band,
        "face_dst": [300, 120, 480, 480] if layout == "stacked" else None,
        "safe_zones": {"bottom_clear": [0, 1536, 1080, 384], "right_clear": [918, 0, 162, 1920]},
    }


@stage("11", "Captions & On-screen Text")
def run() -> StageResult:
    style = profiles.load("house")
    drift, width_ok, has_parts, ex = [], [], [], []
    for seed in range(1100, 1130):
        inp, _ = bb.synth_window(seed)
        lang = list(SAMPLES)[seed % len(SAMPLES)]
        words = [dict(w) for w in inp.words]
        long_words = SAMPLES[lang].split()
        for k, w in enumerate(words):  # stress widths with real words in each language
            if k % 3 == 0:
                w["word"] = long_words[k % len(long_words)]
        inp.words = words
        p = bp.build(inp)["versions"]["short"]
        doc, rep = ass.build_ass(
            p,
            crop_stub(),
            words,
            style,
            language=lang,
            hook_text=SAMPLES[lang],
            credit=ass.credit_line("streamer", "twitch"),
        )
        has_parts.append("Headline" in doc and "Credit" in doc and bool(rep["lines"]))
        width_ok.append(rep["max_width_ratio"] <= 0.80 + 1e-6)
        hook_end = style["hook"]["hook_text_s"]
        for ln in rep["lines"]:
            want = ass.map_time(ln["src_start"], p["segments"])
            if want is not None and want >= hook_end:
                drift.append(abs(ln["start"] - want))
        if rep["max_width_ratio"] > 0.8:
            ex.append(Example(f"seed{seed}:{lang}", "width", rep["max_width_ratio"], ""))
    # libass parse + render one frame per script family
    parsed = []
    with tempfile.TemporaryDirectory() as d:
        for lang in ("en", "ar", "ja"):
            inp, _ = bb.synth_window(1100)
            p = bp.build(inp)["versions"]["short"]
            doc, _ = ass.build_ass(
                p,
                crop_stub(),
                inp.words,
                style,
                language=lang,
                hook_text=SAMPLES[lang],
                credit="@x on Twitch",
            )
            f = Path(d) / f"{lang}.ass"
            f.write_text(doc, encoding="utf-8")
            r = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=gray:s=1080x1920:d=3",
                    "-vf",
                    f"ass={f}:fontsdir={ass.FONTS_DIR}",
                    "-frames:v",
                    "1",
                    "-f",
                    "null",
                    "-",
                ],
                capture_output=True,
                text=True,
            )
            parsed.append(r.returncode == 0 and "fontselect" not in r.stderr.lower())
            if not parsed[-1]:
                ex.append(Example(lang, "libass", 0, r.stderr[-200:]))
    alt = dict(style, captions=dict(style["captions"], fill="#00FF00"))
    doc2, _ = ass.build_ass(p, crop_stub(), inp.words, alt, language="en", hook_text="x", credit="c")
    return StageResult(
        {
            "timing_drift_max_s": float(np.max(drift)),
            "lines_fit": float(np.mean(width_ok)),
            "hook_and_credit": float(np.mean(has_parts)),
            "libass_ok": float(np.mean(parsed)),
            "profile_driven": 1.0 if "&H0000FF00" in doc2 else 0.0,
        },
        ex,
        "synthetic@v1",
        {"lines": len(drift)},
    )
