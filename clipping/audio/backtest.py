"""Stage backtest 07: music detection on held-out audio, separation skipped when there's no music, radio
fingerprint no longer matching after cleanup (>= 95%), and voice clarity gain."""

from __future__ import annotations

import numpy as np

from clipping.audio import cleanup, fingerprint, music
from clipping.eval import audiofx
from clipping.eval.harness import Example, StageResult, stage

SEEDS = range(100, 116)
MATCH = 5
SR = 16000


def _snr(sig: np.ndarray, est: np.ndarray) -> float:
    return float(10 * np.log10((sig**2).sum() / (((est - sig) ** 2).sum() + 1e-9)))


@stage("07", "Audio Cleanup & Music Removal")
def run() -> StageResult:
    acc, skipped, no_match, gains, ex = [], [], [], [], []
    for seed in SEEDS:
        has_music = seed % 2 == 0
        m = audiofx.mixture(
            seed, 12, music=has_music, music_db=float(np.random.default_rng(seed).uniform(-12, -4))
        )
        p = music.music_prob(m["mix"], SR)
        acc.append(float(np.mean((p > cleanup.THRESH) == has_music)))
        res = cleanup.clean(m["mix"], SR)
        if not has_music:
            skipped.append(not res.separated)
            if res.separated:
                ex.append(
                    Example(f"seed{seed}", "false_separation", float(p.mean()), "no music but separated")
                )
            continue
        ref = audiofx.song(m["song_seed"], 12)
        before = fingerprint.match_score(ref, m["mix"], SR)
        after = fingerprint.match_score(ref, res.clean, SR)
        if before >= MATCH:
            ok = after < MATCH
            no_match.append(ok)
            if not ok:
                ex.append(Example(f"seed{seed}", "still_matches", after, f"before={before:.0f}"))
        gains.append(_snr(m["voice"], res.voice) - _snr(m["voice"], m["mix"]))
    return StageResult(
        {
            "detector_accuracy": float(np.mean(acc)),
            "skip_when_no_music": float(np.mean(skipped)),
            "radio_no_longer_matches": float(np.mean(no_match)) if no_match else 0.0,
            "voice_snr_gain_db": float(np.mean(gains)),
        },
        ex,
        "audiofx@v1",
        {"radio_windows": len(no_match)},
    )
