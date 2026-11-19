"""docs/research/gta6-clip-examples.md updates: text styles, sentence case, hook patterns, letterbox arm,
music/celebrity moments with the music_subject exception, and the style-study seed examples."""

import random
import subprocess

import numpy as np
import pytest
from PIL import Image

from clipping.captions import ass, headline
from clipping.moments import analysis as ma
from clipping.packaging import write
from clipping.reframe import layout as rl
from clipping.style import profiles, seed

LANGS = ["en", "es", "pt", "ar", "fr", "ru", "de", "ja", "tr", "vi"]


def test_sentence_case_keeps_names_and_gta6():
    t = headline.apply_case("N3ON SURVIVED A PLANE CRASH IN GTA 6 😭", "sentence", "en", ["N3on"])
    assert t == "N3on survived a plane crash in GTA 6 😭"
    q = headline.apply_case('"i can\'t do it anymore" we taking grandmas now? 😭', "sentence", "en")
    assert q.startswith('"I can')
    assert headline.apply_case("Lacy hears Drake", "upper", "en") == "LACY HEARS DRAKE"
    assert headline.apply_case("ラジオ", "upper", "ja") == "ラジオ"


@pytest.mark.parametrize("style", ["box", "outline"])
def test_headline_png_styles_and_colour_emoji(tmp_path, style):
    r = headline.render("N3on survived a plane crash in GTA 6 😭🔥", "en", style, 72, 972, tmp_path / "h.png")
    im = np.asarray(Image.open(r["path"]).convert("RGBA")).astype(int)
    assert r["w"] <= 972 + 40 and len(r["lines"]) <= 2
    rgb = im[..., :3][im[..., 3] > 200]
    sat = rgb.max(axis=1) - rgb.min(axis=1)
    assert (sat > 80).sum() > 50  # colour emoji pixels survive (libass would draw them monochrome)
    white = (rgb.min(axis=1) > 240).mean()
    assert white > 0.4 if style == "box" else white > 0.1  # box style: mostly white box


def test_headline_two_emojis_kept():
    assert headline.EMOJI_RE.findall("Lacy 😳🔥") == ["😳", "🔥"]


def _plan():
    return {
        "segments": [{"start": 0.0, "end": 12.0, "role": "body"}],
        "payoff_t": 8.0,
    }


def _words():
    txt = "yo what is this bro no way I cant do it anymore look at him go".split()
    return [
        {"word": w, "start": i * 0.7, "end": i * 0.7 + 0.5, "index": i, "probability": 0.99}
        for i, w in enumerate(txt)
    ]


def _cp():
    return {"canvas": [1080, 1920], "caption_band": [700, 840], "layout": "stacked"}


@pytest.mark.parametrize("mode", ["hook_only", "hook_key_lines", "full"])
def test_text_modes(mode):
    style = profiles.load("house")
    doc, rep = ass.build_ass(
        _plan(),
        _cp(),
        _words(),
        style,
        language="en",
        hook_text="Speed got arrested in GTA 6 😭",
        credit="@x on Twitch",
        text_mode=mode,
        headline_overlay=True,
        headline_case="sentence",
        emphasis_words={9, 10},
        key_hints=[8.0],
    )
    captions = [ln for ln in doc.splitlines() if ",Caption," in ln]
    assert ",Headline," not in doc  # drawn as an overlay
    if mode == "hook_only":
        assert not captions and rep["headline_slot"]["t1"] == 12.0
    elif mode == "hook_key_lines":
        assert 1 <= len(rep["lines"]) <= 3 and rep["headline_slot"]["t1"] < 12.0
    else:
        assert len(rep["lines"]) >= 4
    assert rep["headline"] == "Speed got arrested in GTA 6 😭"


def test_letterbox_layout_arm():
    lay = rl.StreamLayout(1920, 1080, (1500, 700, 400, 350), (1600, 750, 150, 200), (0, 0, 1920, 1080), None)
    frames = np.zeros((10, 180, 320, 3), np.uint8)
    cp = rl.plan(frames, 5, lay, "letterbox")
    (panel,) = cp["panels"]
    x, y, w, h = panel["dst"]
    assert (w, h) == (1080, 608) and y == (1920 - 608) // 2 and not cp["zooms"]
    assert cp["caption_band"][1] <= y  # hook text sits in the top bar
    assert cp["face_dst"][1] > y  # original corner cam kept inside the frame
    arms = profiles.layout_arms(profiles.load("house"))
    assert 0 < arms["letterbox"] < 0.15 and arms["stacked"] == max(arms.values())


@pytest.mark.parametrize("lang", LANGS)
def test_hook_patterns_all_languages(lang):
    seen = set()
    for seed_ in range(40):
        pk = write.package(
            _words(),
            {
                "start_t": 0,
                "end_t": 12,
                "payoff_t": 8,
                "payoff_kind": "crash",
                "emphasis_words": [9, 10],
                "moment_type": "crash",
            },
            language=lang,
            creator="N3on",
            platform="twitch",
            seed=seed_,
        )
        assert not write.within_limits(pk), write.within_limits(pk)
        seen.add(pk["features"]["hook_pattern"])
        if pk["features"]["hook_pattern"] == "creator_event":
            assert "N3on" in pk["hook_text"] and ("GTA 6" in pk["hook_text"] or "GTA6" in pk["hook_text"])
            assert headline.EMOJI_RE.search(pk["hook_text"])
        assert "#fyp" in pk["fields"]["snapchat"]["text"] and "#n3on" in pk["fields"]["tiktok"]["caption"]
    assert "creator_event" in seen


def test_quote_hook_uses_creators_line():
    q = write.pick_quote(
        _words(), {"start_t": 0, "end_t": 12, "payoff_t": 6.3, "emphasis_words": [9, 10]}, "en"
    )
    assert q and "cant do it" in q.lower()
    rng = random.Random(1)
    pk = None
    for s in range(60):
        pk = write.package(
            _words(),
            {"start_t": 0, "end_t": 12, "payoff_t": 6.3, "emphasis_words": [9, 10], "moment_type": "comedy"},
            language="en",
            creator="IShowSpeed",
            platform="twitch",
            seed=s + rng.randint(0, 9),
        )
        if pk["features"]["hook_pattern"] == "quote":
            break
    assert pk["features"]["hook_pattern"] == "quote" and pk["hook_text"].startswith('"')


def test_music_celebrity_sets_music_subject():
    T = 60
    from clipping.heatmap.features import KEYS

    f = {k: np.zeros(T, np.float32) for k in KEYS}
    f["music"][10:50] = 0.95
    f["letterbox"][:] = 0.0
    react = np.zeros(T)
    react[25:40] = 4.0
    words = [
        {"word": w, "start": 26 + i * 0.4, "end": 26.3 + i * 0.4}
        for i, w in enumerate("drake on the radio".split())
    ]
    r = ma.analyze_window(f, react, 30, [], words=words)
    assert r.type == "music_celebrity" and r.music_subject
    quiet = ma.analyze_window({**f, "music": np.zeros(T, np.float32)}, react, 30, [])
    assert not quiet.music_subject


def test_music_subject_routing(conn):
    from clipping.gate import checks

    assert checks.music_subject_platforms(conn) == set(checks.MUSIC_SUBJECT_PLATFORMS)


def test_seed_examples_loaded_with_priors():
    ex = seed.parse()
    assert len(ex) == 7 and {e["layout"] for e in ex} == {"stacked", "letterbox"}
    pr = seed.priors(ex)
    assert pr["text_style"]["box"] == pytest.approx(4 / 7, abs=0.01)
    assert pr["mean_views_by_layout"]["stacked"] > pr["mean_views_by_layout"]["letterbox"]
    assert pr["mean_views_by_moment_type"]["discovery"] < pr["mean_views_by_moment_type"]["comedy"]
    house = profiles.load("house")["captions"]
    assert house["text_style_arms"]["box"] == pytest.approx(pr["text_style"]["box"], abs=0.05)
    assert max(house["headline_case_arms"], key=house["headline_case_arms"].get) == "sentence"
    tax = ma.taxonomy()["types"]
    assert tax["discovery"]["weight"]["launch"] < min(
        tax[t]["weight"]["launch"] for t in ("comedy", "crash", "death")
    )


@pytest.mark.slow
def test_render_with_headline_overlay(tmp_path):
    from clipping.render import engine

    src = tmp_path / "src.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=640x360:d=4:r=30",
            "-f",
            "lavfi",
            "-i",
            "sine=f=300:d=4",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(src),
        ],
        check=True,
    )
    wav = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ar", "48000", str(wav)], check=True)
    lay = rl.StreamLayout(640, 360, None, None, (0, 0, 640, 360), None)
    from clipping.core import media

    frames = media.decode_frames(str(src), fps=5, width=320)
    cp = rl.plan(frames, 5, lay, "letterbox")
    plan = {"segments": [{"start": 0.0, "end": 3.0, "role": "body"}], "payoff_t": 2.0}
    h = headline.render("Test clip in GTA 6 😭", "en", "box", 72, 972, tmp_path / "h.png")
    ov = [{"path": h["path"], "x": (1080 - h["w"]) // 2, "y": 400, "t0": 0, "t1": 3}]
    r = engine.render(
        str(src), str(wav), plan, cp, None, str(tmp_path / "o.mp4"), encoder="libx264", sfx=False, overlays=ov
    )
    assert r.validation["passed"]
    png = tmp_path / "f.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", r.path, "-frames:v", "1", str(png)], check=True
    )
    im = np.asarray(Image.open(png).convert("RGB")).astype(int)
    band = im[400 : 400 + h["h"], 200:880]
    assert (band.min(axis=2) > 230).mean() > 0.3  # the white headline box is in the top bar
