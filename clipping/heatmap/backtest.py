"""Stage backtest 05: Recall@20 / precision@20 of top viewer-clipped moments per 4 h of stream.

Two variants: `recall_at_20` uses every signal; `recall_at_20_live` drops the viewer-clip signal, so it can't
"find" clips by looking at them (no label leakage). Both must clear the bar.
"""

from __future__ import annotations

import time
from collections import defaultdict

import numpy as np

from clipping.chat import features
from clipping.core import config
from clipping.eval.harness import Example, StageResult, stage
from clipping.eval.simstream import SimStream, simulate
from clipping.heatmap import fusion, signals

SEEDS = list(range(500, 506))
TOP_K = 10


def stream_signals(s: SimStream, cfg: dict, buckets: list[dict] | None = None) -> dict[str, np.ndarray]:
    T = s.duration_s
    if buckets is None:
        buckets = features.bucketize(s.msgs, T, config.chat_tokens(s.language), gaps=s.gaps)
    vel, mix = signals.from_buckets(buckets, T, lag_s=cfg["reaction_lag_s"])
    return {
        "chat_velocity": vel,
        "chat_reaction": mix,
        "viewer_clips": signals.clip_density(s.clips, T, cfg["clip_kernel_s"]),
        "audio_energy": signals.audio_spikes(s.audio_db, 0.1, T, music=s.music),
        "voice_excitement": s.voice_exc.astype(float),
        "visual_change": signals.per_second_max(s.scene, 2, T),
        "viewer_jump": signals.viewer_jumps(s.viewers, T),
    }


def top_moments(s: SimStream, k: int = TOP_K) -> list[tuple[float, float]]:
    views = defaultdict(int)
    for c in s.clips:
        if c["moment"] is not None:
            views[c["moment"]] += c["views"]
    best = sorted(views.items(), key=lambda kv: -kv[1])[:k]
    return [(s.moments[m]["t"], v) for m, v in best]


def evaluate_stream(sig: dict, s: SimStream, cfg: dict, weights: dict) -> tuple[float, float, list]:
    score = fusion.fuse(sig, weights, cfg["smooth_s"])
    wins = fusion.pick_windows(
        score,
        separation_s=cfg["peak_separation_s"],
        pct=cfg["peak_percentile"],
        floor=cfg["abs_floor"],
        before_s=cfg["window_before_s"],
        after_s=cfg["window_after_s"],
        max_per_hour=cfg["max_per_hour"],
    )
    top20 = wins[: int(20 * s.duration_s / 14400)]
    truth = top_moments(s)
    hit = [any(w.start_s <= t <= w.end_s for w in top20) for t, _ in truth]
    all_t = [m["t"] for m in s.moments]
    prec = [any(w.start_s <= t <= w.end_s for t in all_t) for w in top20]
    misses = [(t, v) for (t, v), h in zip(truth, hit, strict=True) if not h]
    return float(np.mean(hit)), float(np.mean(prec)) if prec else 0.0, misses


@stage("05", "Moment Heatmap")
def run(weights: dict | None = None) -> StageResult:
    cfg = config.settings()["heatmap"]
    w_all = weights or cfg["weights"]
    w_live = {k: v for k, v in w_all.items() if k != "viewer_clips"}
    rec, prec, rec_live, prec_live, ex, fuse_t = [], [], [], [], [], []
    for seed in SEEDS:
        s = simulate(seed, hours=4)
        sig = stream_signals(s, cfg)
        t0 = time.time()
        r, p, miss = evaluate_stream(sig, s, cfg, w_all)
        fuse_t.append((time.time() - t0) / 4)
        rl, pl, miss_l = evaluate_stream(sig, s, cfg, w_live)
        rec.append(r), prec.append(p), rec_live.append(rl), prec_live.append(pl)
        for t, v in miss_l:
            at = int(t)
            notes = " ".join(f"{k}={np.nan_to_num(sig[k][at : at + 8]).max():.2f}" for k in sig)
            ex.append(Example(f"seed{seed}@{t:.0f}s", "missed_live", float(v), notes))
    ex.sort(key=lambda e: -e.value)
    feat_h = feature_cost_per_hour()
    return StageResult(
        {
            "score_s_per_hour": feat_h + float(np.mean(fuse_t)),
            "recall_at_20": float(np.mean(rec)),
            "precision_at_20": float(np.mean(prec)),
            "recall_at_20_live": float(np.mean(rec_live)),
            "precision_at_20_live": float(np.mean(prec_live)),
            "fuse_s_per_hour": float(np.mean(fuse_t)),
        },
        ex,
        "simstream@v1",
    )


def feature_cost_per_hour() -> float:
    """Seconds of compute to extract audio/visual/music features for one hour of 1080p60 recording."""
    import datetime as dt
    import subprocess
    import tempfile
    from pathlib import Path

    from clipping.heatmap import service

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "seg.ts"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=1920x1080:rate=60",
                "-f",
                "lavfi",
                "-i",
                "sine",
                "-t",
                "60",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-g",
                "120",
                "-b:v",
                "6M",
                "-c:a",
                "aac",
                "-f",
                "mpegts",
                str(p),
            ],
            check=True,
        )

        class _NoDB:
            def execute(self, *a):
                return None

        seg = {
            "id": -1,
            "path": str(p),
            "start_utc": dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            "end_utc": dt.datetime(2026, 1, 1, 0, 1, tzinfo=dt.UTC),
        }
        orig = service.db.one
        service.db.one = lambda *a, **k: None
        try:
            t0 = time.time()
            service.segment_features(_NoDB(), seg)
            return (time.time() - t0) * 60
        finally:
            service.db.one = orig
