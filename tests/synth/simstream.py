"""Synthetic livestream model for chat (03) and heatmap (05) backtests.

True moments produce: a chat burst after a reaction lag, laugh/hype tokens, an audio spike and excited voice,
sometimes a scene flash, and viewer clips weighted by intensity. Confounders: chat-only bursts (raids, giveaway
copypasta), loud music-only stretches, random scene cuts, chat disconnects, slow baseline drift, and a few viewer
clips on non-moments. Deterministic per seed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from clipping.chat.features import Msg

WORDS = [
    "bro",
    "what",
    "lol",
    "gg",
    "nice",
    "the",
    "cops",
    "car",
    "go",
    "left",
    "right",
    "money",
    "chat",
    "why",
    "ok",
    "yes",
    "no",
    "run",
    "drive",
    "heist",
    "jason",
    "lucia",
    "stars",
    "wanted",
    "crazy",
    "dude",
    "man",
    "wait",
]


@dataclass
class SimStream:
    seed: int
    duration_s: int
    language: str
    msgs: list[Msg]
    audio_db: np.ndarray  # 10 Hz
    voice_exc: np.ndarray  # 1 Hz, z-scored-ish
    scene: np.ndarray  # 2 fps histogram distance
    music: np.ndarray  # 1 Hz music probability
    viewers: list[tuple[int, int]]  # (t, viewers) every 600 s
    moments: list[dict]  # true moments
    clips: list[dict]  # viewer clips {t_start, duration, views}
    gaps: list[tuple[float, float]] = field(default_factory=list)


def simulate(seed: int, hours: float = 4, language: str = "en", chat_scale: float = 1.0) -> SimStream:
    rng = np.random.default_rng(seed)
    T = int(hours * 3600)
    base = float(np.exp(rng.normal(np.log(3), 0.8))) * chat_scale
    drift = base * (
        1
        + 0.35 * np.sin(np.arange(T) / T * 2 * np.pi * rng.uniform(1, 3))
        + np.cumsum(rng.normal(0, 0.004, T))
    )
    drift = np.clip(drift, base * 0.3, base * 3)
    rate = drift.copy()
    laugh_p = np.full(T, 0.04)
    hype_p = np.full(T, 0.03)
    paste = np.zeros(T)
    db10 = rng.normal(-32, 2.5, T * 10)
    voice = rng.normal(0, 1, T)
    scene = np.abs(rng.normal(0.05, 0.03, T * 2))
    music = np.clip(rng.normal(0.05, 0.03, T), 0, 1)
    n_mom = rng.poisson(6 * hours)
    times = np.sort(rng.uniform(120, T - 120, n_mom))
    moments, clips = [], []
    for t in times:
        t = float(t)
        inten = float(np.exp(rng.normal(0, 0.6)))
        kind = rng.choice(["fail", "funny", "action"])
        lag = float(np.clip(rng.normal(4.5, 1.2), 1.5, 9))
        k0 = int(t + lag)
        # Some moments have a weak chat reaction (quiet chat, or reaction-free visuals): forces signal fusion.
        chat_mult = float(rng.choice([0.25, 1.0, 1.0, 1.0]))
        mag = drift[k0] * inten * rng.uniform(1.5, 5) * chat_mult
        span = np.arange(k0, min(T, k0 + 40))
        rate[span] += mag * np.exp(-(span - k0) / 8)
        if kind == "funny":
            laugh_p[span] = np.maximum(laugh_p[span], 0.5)
        else:
            hype_p[span] = np.maximum(hype_p[span], 0.45)
        caps_dur = int(rng.uniform(1, 3) * 10)
        audio_mult = float(rng.choice([0.3, 1.0, 1.0]))
        db10[int(t * 10) : int(t * 10) + caps_dur] += rng.uniform(10, 20) * audio_mult
        vs = np.arange(int(t) - 3, min(T, int(t) + 8))
        voice[vs] += rng.uniform(1.5, 3.5) * inten**0.5
        if kind == "action" or rng.random() < 0.3:
            scene[int(t * 2) : int(t * 2) + 3] += rng.uniform(0.4, 0.9)
        moments.append({"t": t, "intensity": inten, "kind": str(kind), "lag": lag})
        for _ in range(rng.poisson(1 + 3 * inten)):
            dur = float(rng.choice([26, 30, 30, 45, 60]))
            start = t - rng.uniform(0.5, 0.8) * dur
            clips.append(
                {
                    "t_start": round(start, 1),
                    "duration": dur,
                    "views": int(np.exp(rng.normal(np.log(200 * inten), 0.9))) + 1,
                    "moment": len(moments) - 1,
                }
            )
    # Confounders
    for _ in range(rng.poisson(3 * hours)):  # chat-only bursts: raids, giveaways, copypasta
        k0 = int(rng.uniform(60, T - 60))
        span = np.arange(k0, min(T, k0 + 30))
        rate[span] += drift[k0] * rng.uniform(1.5, 4) * np.exp(-(span - k0) / 10)
        paste[span] = 0.7
    for _ in range(rng.poisson(3 * hours)):  # loud music stretches (radio)
        a = int(rng.uniform(0, T - 90))
        d = int(rng.uniform(20, 90))
        db10[a * 10 : (a + d) * 10] += rng.uniform(8, 16)
        music[a : a + d] = np.clip(rng.normal(0.85, 0.05, d), 0, 1)
    for _ in range(rng.poisson(20 * hours)):  # random scene cuts
        scene[int(rng.uniform(0, T * 2 - 1))] += rng.uniform(0.3, 0.8)
    for _ in range(rng.poisson(2 * hours)):  # stray viewer clips
        s = float(rng.uniform(60, T - 60))
        clips.append(
            {"t_start": s, "duration": 30.0, "views": int(np.exp(rng.normal(3, 1))) + 1, "moment": None}
        )
    gaps = []
    for _ in range(rng.integers(0, 3)):
        a = float(rng.uniform(300, T - 600))
        gaps.append((a, a + float(rng.uniform(60, 240))))
    users = [f"u{seed}_{i}" for i in range(int(400 * max(base, 0.5)))]
    counts = rng.poisson(np.clip(rate, 0, None))
    for a, b in gaps:
        counts[int(a) : int(b)] = 0
    lt, ht = ["LUL", "KEKW", "lol", "LMAO", "😂"], ["W", "no way", "POG", "clip it", "WTF"]
    secs = np.repeat(np.arange(T), counts)
    n = len(secs)
    r = rng.random(n)
    pp, lp, hp = paste[secs], laugh_p[secs], hype_p[secs]
    li, hi, wi = rng.integers(0, len(lt), n), rng.integers(0, len(ht), n), rng.integers(0, len(WORDS), (n, 6))
    nw = rng.integers(1, 7, n)
    up = rng.random(n) < 0.5
    ui = rng.integers(0, len(users), n)
    ts = secs + rng.random(n)
    msgs = []
    for k in range(n):
        if r[k] < pp[k]:
            text = "!giveaway join the giveaway now NOW"
        elif r[k] < pp[k] + lp[k]:
            text = lt[li[k]] + " " + WORDS[wi[k, 0]]
        elif r[k] < pp[k] + lp[k] + hp[k]:
            text = ht[hi[k]].upper() if up[k] else ht[hi[k]]
        else:
            text = " ".join(WORDS[w] for w in wi[k, : nw[k]])
        msgs.append(Msg(float(ts[k]), users[ui[k]], text, 0))
    viewers = [(t, int(base * 300 * (1 + 0.2 * np.sin(t / 3000)))) for t in range(0, T, 600)]
    return SimStream(
        seed,
        T,
        language,
        msgs,
        db10.astype(np.float32),
        voice.astype(np.float32),
        scene.astype(np.float32),
        music.astype(np.float32),
        viewers,
        moments,
        clips,
        gaps,
    )
