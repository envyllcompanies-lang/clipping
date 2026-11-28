import numpy as np

from clipping.creators import profile as cp
from clipping.moments import analysis as ma


def _feats(T=600, seed=0):
    rng = np.random.default_rng(seed)
    f = {
        "audio_db10": rng.normal(-35, 2, T * 10).astype(np.float32),
        "voice": rng.normal(0, 1, T).astype(np.float32),
        "music": np.zeros(T, np.float32),
        "centroid": rng.normal(900, 50, T).astype(np.float32),
        "flux": rng.normal(0.5, 0.05, T).astype(np.float32),
        "hiband": rng.normal(0.15, 0.01, T).astype(np.float32),
        "onsets": rng.poisson(0.5, T).astype(np.float32),
        "motion": rng.normal(15, 2, T).astype(np.float32),
        "bright": rng.normal(80, 3, T).astype(np.float32),
        "scene": np.abs(rng.normal(0.07, 0.02, T)).astype(np.float32),
        "letterbox": np.zeros(T, np.float32),
        "edges": rng.normal(9, 1, T).astype(np.float32),
    }
    return f


def test_reaction_is_relative_to_each_creator():
    loud, quiet = _feats(seed=1), _feats(seed=2)
    loud["audio_db10"] += 15
    loud["audio_db10"][3000:3020] += 6  # screamer's bump
    quiet["audio_db10"] = quiet["audio_db10"] * 0.2 - 40
    quiet["audio_db10"][3000:3020] += 6  # deadpan raises the voice by the same amount
    rl = cp.reaction_score(cp.components(loud), cp.baseline(cp.components(loud)))
    rq = cp.reaction_score(cp.components(quiet), cp.baseline(cp.components(quiet)))
    assert rq[300] >= rl[300] * 0.8 and rq.argmax() in range(295, 306)


def test_segments_never_clip_brb_and_sponsor():
    f = _feats()
    f["motion"][:120] = 0.1
    f["scene"][:120] = 0.0
    words = [
        {"word": w, "start": 300 + i, "end": 300.5 + i}
        for i, w in enumerate("use code gta at checkout".split())
    ]
    labs = {s["start_s"]: s["label"] for s in cp.segment_labels(f, words)}
    assert labs[0.0] == "brb" and labs[300.0] == "sponsor"
    assert cp.never_clip_mask(cp.segment_labels(f, words), 600)[:120].all()


def test_catchphrases_mined_from_top_windows():
    top = ["let him cook bro no way", "chat let him cook", "he said let him cook", "random words here"]
    bg = ["what is up chat", "driving to the city", "let us go", "nice car"] * 5
    assert "let him cook" in cp.mine_phrases(top, bg)


def test_collab_alignment_recovers_offset():
    rng = np.random.default_rng(3)
    env = np.abs(rng.normal(0, 1, 4000))
    a, b = env[100:3100], env[130:3130]  # b is 30 samples (3 s at 10 Hz) ahead
    off, corr = cp.align_offset(a, b, 10.0)
    assert abs(abs(off) - 3.0) < 0.2 and corr > 0.5


def test_calibration_and_cutscene_reveal_type():
    f = _feats(T=900)
    f["letterbox"][200:300] = 0.9  # a 100 s cutscene
    prof = ma.calibrate([f], save=False)
    assert 0.2 <= prof["letterbox_threshold"] < 0.9
    f["audio_db10"][2990:3050] += 12  # creator reacts at the beat
    react = cp.reaction_score(cp.components(f), cp.baseline(cp.components(f)))
    res = ma.analyze_window(f, react, 300)
    assert res.type == "cutscene_reveal" and res.start_s < 300 < res.end_s
