"""Offline clip run for one window (`clip run <window>`): cleanup -> transcribe -> events -> build -> reframe ->
captions -> render (-> packaging -> gate when available). The DB pipeline calls the same steps."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from clipping.audio import cleanup
from clipping.builder import plan as bp
from clipping.captions import ass
from clipping.core import media
from clipping.events import detect
from clipping.reframe import layout as rl
from clipping.render import engine
from clipping.style import profiles
from clipping.transcribe import engine as asr


def run_window(
    window: str,
    out_dir: str,
    *,
    language: str = "en",
    creator: str = "streamer",
    platform: str = "twitch",
    style_name: str = "house",
    stream_scale: float | None = None,
    peak_t: float | None = None,
    layout: str | None = None,
    seed: int = 0,
    words: list[dict] | None = None,
    hook_text: str | None = None,
    packaging_fn=None,
    stream_layout: rl.StreamLayout | None = None,
) -> dict:
    t_all = time.time()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    style = profiles.load(style_name)
    timings = {}
    t = time.time()
    audio16 = media.decode_audio(window, 16000)
    cl = cleanup.clean(audio16, 16000)
    sf.write(out / "voice.wav", cl.voice, 16000)
    sf.write(out / "clean_raw.wav", cl.clean, 16000)
    cleanup.loudnorm(out / "clean_raw.wav", out / "clean_mix.wav")
    timings["audio"] = time.time() - t
    t = time.time()
    tr = None
    if words is None:
        tr = asr.transcribe(cl.voice, 16000, language=language, prompt=asr.prompt_for(creator))
        words = tr.words
    timings["transcribe"] = time.time() - t
    t = time.time()
    dur = media.duration(window)
    ev_frames = media.decode_frames(window, fps=2, width=320)
    ev_times = np.arange(len(ev_frames)) / 2
    lay_frames = media.decode_frames(window, fps=1, width=640)
    if stream_layout is None:
        stream_layout = rl.detect_layout(lay_frames[:: max(1, len(lay_frames) // 30)])
    evs = detect.detect(ev_frames, ev_times, language=language, mask=None)
    timings["events"] = time.time() - t
    t = time.time()
    activity = np.zeros(int(dur) + 2)
    inp = bp.Inputs(
        dur,
        words,
        [e.__dict__ for e in evs if not e.details.get("negative")],
        peak_t,
        [],
        activity,
        detect.negative_spans(evs),
        language,
        creator,
    )
    plans = bp.build(inp, style_name)
    timings["build"] = time.time() - t
    results = {"plans": plans, "events": [e.__dict__ for e in evs], "words": len(words), "versions": {}}
    if not plans["versions"]:
        results["discarded"] = plans["discarded"]
        return results
    full = media.decode_frames(window, fps=5, width=640)
    scale = stream_scale or (1920 / full.shape[2])
    L = stream_layout
    lay = rl.StreamLayout(
        int(L.width * scale),
        int(L.height * scale),
        tuple(int(v * scale) for v in L.facecam) if L.facecam else None,
        tuple(int(v * scale) for v in L.face) if L.face else None,
        tuple(int(v * scale) for v in L.game),
        L.overlay_mask,
    )
    chosen_layout = layout or rl.choose_layout(
        lay, profiles.layout_arms(style), random.Random(seed), source_height=lay.height
    )
    pk = (packaging_fn or default_packaging)(words, plans["versions"]["short"], language, creator, platform)
    for vname, p in plans["versions"].items():
        t = time.time()
        cp = rl.plan(
            full,
            5,
            lay,
            chosen_layout,
            emphasis_t=p["emphasis_t"],
            zoom_amount=style["pacing"]["zoom_amount"],
            cam_ratio=style["layout"]["stacked"]["cam_ratio"],
            caption_size_pct=style["captions"]["size_pct"],
        )
        doc, rep = ass.build_ass(
            p,
            cp,
            words,
            style,
            language=language,
            hook_text=hook_text or pk["hook_text"],
            credit=ass.credit_line(
                creator, platform, style.get("credit", {}).get("template", "@{creator} on {platform}")
            ),
        )
        (out / f"{vname}.ass").write_text(doc, encoding="utf-8")
        (out / f"{vname}.plan.json").write_text(json.dumps({"edit": p, "crop": cp}, default=str))
        r = engine.render(
            window,
            str(out / "clean_mix.wav"),
            p,
            cp,
            str(out / f"{vname}.ass"),
            str(out / f"{vname}.mp4"),
            fonts_dir=str(ass.FONTS_DIR),
        )
        results["versions"][vname] = {
            "path": r.path,
            "duration": r.duration,
            "validation": r.validation,
            "phash": r.phash,
            "encoder": r.encoder,
            "layout": chosen_layout,
            "render_s": round(time.time() - t, 2),
            "caption_lines": len(rep["lines"]),
            "caption_clear": rl.caption_clear(cp),
            "crop": cp,
            "plan": p,
        }
        (out / f"{vname}.jpg").write_bytes(r.thumbnail_jpg)
    results["packaging"] = pk
    results["timings"] = {k: round(v, 2) for k, v in timings.items()} | {
        "total": round(time.time() - t_all, 2)
    }
    results["music_risk"] = cl.music_risk
    return results


def default_packaging(words, plan, language, creator, platform) -> dict:
    try:
        from clipping.packaging import write

        return write.package(words, plan, language=language, creator=creator, platform=platform)
    except ImportError:
        return {"hook_text": "WAIT FOR IT"}
