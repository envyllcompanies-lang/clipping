import numpy as np

from clipping.audio import cleanup, fingerprint, music
from tests.synth import audiofx


def test_spans_merge_and_pad():
    m = np.array([0, 1, 1, 0, 0, 0, 1, 0, 0, 0], bool)
    assert cleanup.spans(m) == [(0, 4), (5, 8)]


def test_no_music_skips_separation():
    x = audiofx.mixture(3, 8, music=False)["mix"]

    def boom(*a):
        raise AssertionError("separator must not run")

    r = cleanup.clean(x, 16000, separator=boom)
    assert not r.separated and not r.music_risk


def test_music_spans_use_separated_stems():
    m = audiofx.mixture(4, 8, music=True, music_db=-4)
    calls = []

    def fake(a, sr):
        calls.append(1)
        return {
            "vocals": m["voice"],
            "other": 0.5 * m["sfx"],
            "drums": np.zeros_like(a),
            "bass": np.zeros_like(a),
        }

    r = cleanup.clean(m["mix"], 16000, separator=fake)
    assert calls and r.separated
    ref = audiofx.song(m["song_seed"], 8)
    assert fingerprint.match_score(ref, m["mix"], 16000) >= 5
    assert fingerprint.match_score(ref, r.clean, 16000) < 5


def test_music_detector_separates_classes():
    assert music.music_prob(audiofx.song(9, 6), 16000).mean() > 0.7
    assert music.music_prob(audiofx.mixture(9, 6, music=False)["voice"], 16000).mean() < 0.4


def test_loudnorm_hits_target(tmp_path):
    from clipping.core import media

    x = audiofx.mixture(5, 10, music=False)["mix"] * 0.1
    src = audiofx.write_wav(tmp_path / "a.wav", x, 16000)
    cleanup.loudnorm(src, tmp_path / "b.wav")
    assert abs(media.loudness(tmp_path / "b.wav")["integrated"] + 14) <= 1.0
