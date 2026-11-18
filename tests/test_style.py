from clipping.style import analyze, profiles


def test_house_profile_has_reference_layout_as_favorite():
    p = profiles.load("house")
    arms = profiles.layout_arms(p)
    assert max(arms, key=arms.get) == "stacked" and abs(sum(arms.values()) - 1) < 1e-9
    assert p["layout"]["stacked"]["cam_ratio"] == 0.40 and p["captions"]["position"] == "seam"
    assert p["captions"]["headline_fill"].upper() == "#FFE11A"


def test_blend_numbers_and_majority(monkeypatch):
    a = profiles.load("house")
    b = {
        **a,
        "pacing": {**a["pacing"], "cuts_per_10s": 4.0},
        "captions": {**a["captions"], "all_caps": False},
    }
    monkeypatch.setattr(profiles.config, "style", lambda n: {"a": a, "b": b, "c": a}[n])
    out = profiles.blend(["a", "b", "c"])
    assert abs(out["pacing"]["cuts_per_10s"] - (2 + 4 + 2) / 3) < 1e-3
    assert out["captions"]["all_caps"] is True


def test_profile_from_measurements():
    m = {
        "duration": 30,
        "vertical": True,
        "cuts_per_10s": 2.0,
        "median_shot_s": 3,
        "zooms_per_10s": 1.0,
        "zoom_amount": 1.12,
        "captions": {
            "coverage": 0.9,
            "position_y": 0.4,
            "words_per_line": 3,
            "all_caps_share": 0.9,
            "fill": "#FFFFFF",
        },
        "hook": {"text_first_3s": True, "cuts_first_3s": 1},
        "layout": {"type": "stacked", "split": 0.4},
        "audio": {"lufs": -14, "lra": 5},
        "ending": {"loop": False},
    }
    p = analyze.profile_from([m, {**m, "layout": {"type": "full", "split": None}}], "x", "test")
    assert p["layout"]["arms"] == {"stacked": 0.5, "full": 0.5} and p["captions"]["all_caps"]
