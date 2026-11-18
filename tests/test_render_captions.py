import numpy as np

from clipping.captions import ass
from clipping.render import engine


def test_zoom_curve_eases_and_holds():
    z = [{"t": 1.0, "scale": 1.15, "in_s": 0.2, "hold_s": 0.6, "out_s": 0.3, "toward": [100, 100]}]
    assert engine.zoom_factor(z, 0.9)[0] == 1.0
    assert abs(engine.zoom_factor(z, 1.5)[0] - 1.15) < 1e-9
    assert 1.0 < engine.zoom_factor(z, 1.1)[0] < 1.15


def test_output_time_skips_hook_and_cuts():
    segs = [
        {"start": 20, "end": 22, "role": "hook"},
        {"start": 5, "end": 10, "role": "body"},
        {"start": 11, "end": 25, "role": "body"},
    ]
    assert engine.output_time(6, segs) == 2 + 1
    assert engine.output_time(12, segs) == 2 + 5 + 1
    assert ass.map_time(21, segs) == 1  # hook position for a time inside the hook
    assert engine.output_time(10.5, segs) is None  # removed dead air


def test_compose_stacked_canvas():
    frame = np.full((360, 640, 3), 100, np.uint8)
    cp = {
        "canvas": [1080, 1920],
        "zooms": [],
        "panels": [
            {"name": "cam", "dst": [0, 0, 1080, 768], "keyframes": [{"t": 0, "box": [1500, 600, 400, 300]}]},
            {
                "name": "game",
                "dst": [0, 768, 1080, 1152],
                "keyframes": [{"t": 0, "box": [400, 0, 1012, 1080]}],
            },
        ],
    }
    out = engine.compose(frame, 0.0, cp, (3.0, 3.0))
    assert out.shape == (1920, 1080, 3) and out.mean() > 90


def test_caption_grouping_rules():
    w = [
        {"index": i, "word": x, "start": i * 0.5, "end": i * 0.5 + 0.4, "conf": 0.9}
        for i, x in enumerate(["Jason", "Stone", "has", "5", "stars.", "No", "way", "bro"])
    ]
    lines = ass.group(w, (2, 4))
    texts = [" ".join(x["word"] for x in ln.words) for ln in lines]
    assert all(not t.endswith("Jason") for t in texts)  # names stay together
    assert any(t.endswith("stars.") for t in texts)  # punctuation breaks
    assert all(ln.end - ln.start >= 0.4 for ln in lines)


def test_profanity_mask_and_low_confidence_drop():
    assert (
        ass.mask("fucking", "en", "mask").startswith("f*") and ass.mask("fucking", "en", "show") == "fucking"
    )
    w = [
        {"index": i, "word": "x", "start": i, "end": i + 0.5, "conf": c}
        for i, c in enumerate([0.9, 0.2, 0.3])
    ]
    assert ass.drop_low_confidence([ass.Line(0, 3, w)]) == []


def test_whoosh_is_ours_and_short():
    x = engine.whoosh()
    assert 0.2 < len(x) / engine.SR < 0.5 and np.abs(x).max() <= 0.26
