"""Gameplay Moment Analysis (doc 31): typed GTA 6 moments from video/audio cues + the creator's reaction (doc 32),
a gameplay score for the heatmap, and type-specific cut rules for the clip builder."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import yaml

from clipping.core import config

PROFILE = config.CONFIG / "games" / "gta6" / "profile.yaml"


def taxonomy() -> dict:
    return config.load("games/gta6/moments.yaml")


def phase(today: dt.date | None = None) -> str:
    rel = dt.date(2026, 11, 19)
    days = ((today or dt.date.today()) - rel).days
    return "launch" if days < taxonomy()["phase_switch_days_after_release"] else "settled"


# ---------------- calibration (self-learning from raw VODs) ----------------
def calibrate(feature_sets: list[dict[str, np.ndarray]], save: bool = True) -> dict:
    """Learn cutscene framing from footage, no hand labels: letterbox ratio is bimodal (gameplay ~0, cutscene bars
    high). Threshold = valley between the modes (Otsu on the per-second ratio). Also the typical shot-cut rate
    inside letterboxed spans."""
    lb = np.concatenate([f["letterbox"] for f in feature_sets])
    hist, edges = np.histogram(lb, bins=50, range=(0, 1))
    p = hist / max(hist.sum(), 1)
    best, thr = -1.0, 0.5
    for k in range(1, 50):
        w0, w1 = p[:k].sum(), p[k:].sum()
        if w0 == 0 or w1 == 0:
            continue
        m0 = (p[:k] * edges[:k]).sum() / w0
        m1 = (p[k:] * edges[k:-1]).sum() / w1
        between = w0 * w1 * (m0 - m1) ** 2
        if between > best:
            best, thr = between, float(edges[k])
    share = float((lb > thr).mean())
    cuts = []
    for f in feature_sets:
        cs = f["letterbox"] > thr
        if cs.sum() > 60:
            cuts.append(float((f["scene"][cs] > 0.25).mean()))
    prof = {
        "letterbox_threshold": round(max(thr, 0.2), 3),
        "cutscene_share": round(share, 4),
        "cutscene_cut_rate": round(float(np.median(cuts)), 4) if cuts else None,
        "calibrated_on_seconds": int(len(lb)),
        "calibrated_at": dt.date.today().isoformat(),
    }
    if save:
        old = yaml.safe_load(PROFILE.read_text()) if PROFILE.exists() else {}
        PROFILE.write_text(yaml.safe_dump({**(old or {}), **prof}, sort_keys=False))
    return prof


def profile() -> dict:
    return (yaml.safe_load(PROFILE.read_text()) if PROFILE.exists() else None) or {"letterbox_threshold": 0.5}


# ---------------- signals ----------------
def _z(x: np.ndarray) -> np.ndarray:
    med = np.nanmedian(x)
    return (x - med) / (np.nanmedian(np.abs(x - med)) * 1.4826 + 1e-6)


def _smooth(x: np.ndarray, k: int) -> np.ndarray:
    return np.convolve(x, np.ones(k) / k, mode="same")


def derived(f: dict[str, np.ndarray], prof: dict | None = None) -> dict[str, np.ndarray]:
    prof = prof or profile()
    T = len(f["voice"])
    cut = (f["letterbox"] > prof["letterbox_threshold"]).astype(float)
    cut_state = (_smooth(cut, 10) > 0.6).astype(float)
    motion_z = _z(f["motion"])
    bright_jump = np.r_[0, np.clip(np.diff(f["bright"]), 0, None)]
    impact = (
        np.clip(_z(bright_jump), 0, None) * (np.r_[0, np.diff(f["motion"])] > 0)
        + np.clip(_z(f["onsets"]), 0, None) * 0.5
    )
    speed = _smooth(np.clip(motion_z, 0, None), 4)
    combat = _smooth(np.clip(_z(f["onsets"]), 0, None), 5)
    music_swell = np.clip(np.r_[np.zeros(5), f["music"][5:] - f["music"][:-5]], 0, None)
    novelty = _smooth(np.clip(_z(f["scene"]), 0, None), 5)
    # cutscene beat: the last seconds of a cutscene span (hard cut / fade / score change)
    beat = np.zeros(T)
    ends = np.nonzero(np.diff(cut_state) < 0)[0]
    starts = np.nonzero(np.diff(cut_state) > 0)[0]
    for e in ends:
        s = starts[starts < e]
        if len(s) and e - s[-1] >= 10:
            beat[max(0, e - 3) : e + 1] = 1.0
    return {
        "cutscene": cut_state,
        "beat": beat,
        "speed": speed,
        "impact": impact,
        "combat": combat,
        "music_swell": music_swell,
        "music": f["music"].astype(float),
        "novelty": novelty,
        "motion_z": motion_z,
    }


def type_confidences(
    d: dict[str, np.ndarray], reaction: np.ndarray, events: list[dict] | None = None
) -> dict[str, np.ndarray]:
    """Rule detectors per type (doc 31), confidence 0-1 per second."""
    T = len(reaction)
    r = np.clip(reaction / 4, 0, 1)
    sq = lambda x: np.clip(x / 3, 0, 1)  # noqa: E731
    sustained = lambda x, k: (_smooth((x > 1.0).astype(float), k) > 0.7).astype(float)  # noqa: E731
    conf = {
        "cutscene_reveal": d["beat"] * np.maximum(r, sq(d["music_swell"] * 10)),
        "chase": sustained(d["speed"], 8) * sq(d["speed"]),
        "crash": sq(d["impact"]) * (np.roll(d["speed"], 2) > 0.8),
        "firefight": sustained(d["combat"], 5) * sq(d["combat"]),
        "discovery": (d["motion_z"] < 0) * sq(d["novelty"]) * r * (1 - d["cutscene"]),
        # music/celebrity (doc 31): a song carries the stretch (sustained music) and the creator reacts over it
        "music_celebrity": sustained(d["music"] * 2, 6) * np.clip(d["music"], 0, 1) * r * (1 - d["cutscene"]),
    }
    song = sustained(d["music"] * 2, 6)
    # a reaction over a song is a music moment, not NPC comedy: comedy yields where a song carries the stretch
    conf["comedy"] = r * (d["combat"] < 0.5) * (1 - d["cutscene"]) * (d["speed"] < 1.0) * (1 - 0.6 * song)
    death = np.zeros(T)
    for e in events or []:
        if e["type"] in ("death", "arrest"):
            a = int(e["t"])
            death[max(0, a - 2) : min(T, a + 3)] = e.get("confidence", 0.9)
    conf["death"] = death
    return {k: np.clip(v, 0, 1) for k, v in conf.items()}


def gameplay_score(
    f: dict[str, np.ndarray],
    reaction: np.ndarray,
    events: list[dict] | None = None,
    today: dt.date | None = None,
    prof: dict | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-second gameplay score and best type index (doc 31 formula; novelty penalty applied at selection time)."""
    tax = taxonomy()["types"]
    ph = phase(today)
    d = derived(f, prof)
    conf = type_confidences(d, reaction, events)
    names = list(conf)
    w = np.array([tax.get(n, {"weight": {ph: 0.5}})["weight"][ph] for n in names])[:, None]
    stack = np.vstack([conf[n] for n in names]) * w
    best = stack.argmax(axis=0)
    intensity = 0.5 + 0.5 * np.clip((d["speed"] + d["impact"] + d["combat"]) / 6, 0, 1)
    score = stack.max(axis=0) * (0.5 + 0.5 * np.clip(reaction / 4, 0, 1)) * intensity
    return _smooth(score, 3), best


@dataclass
class MomentResult:
    type: str
    type_confidence: float
    gameplay_score: float
    reaction_score: float
    anchor_s: float
    start_s: float
    end_s: float
    hook_style: str
    beat_s: float | None = None
    music_subject: bool = False  # doc 07 exception: the song is the moment, keep it


def analyze_window(
    f: dict[str, np.ndarray],
    reaction: np.ndarray,
    peak_s: float,
    events: list[dict] | None = None,
    today: dt.date | None = None,
    words: list[dict] | None = None,
) -> MomentResult:
    """Type a candidate window around its heatmap peak and recommend type-specific bounds (doc 31 cut rules)."""
    tax = taxonomy()["types"]
    d = derived(f)
    conf = type_confidences(d, reaction, events)
    T = len(reaction)
    lo, hi = max(0, int(peak_s) - 30), min(T, int(peak_s) + 15)
    best_t, best_c, at = "comedy", 0.0, int(peak_s)
    if words:  # creator names the song/artist/radio: strong evidence the music is the subject
        said = " ".join(w["word"].lower() for w in words if lo <= w.get("start", 0) < hi)
        if any(k in said for k in taxonomy().get("music_keywords", [])):
            conf["music_celebrity"] = np.clip(conf["music_celebrity"] * 1.6, 0, 1)
    for name, c in conf.items():
        seg = c[lo:hi]
        if len(seg) and seg.max() > best_c:
            best_t, best_c, at = name, float(seg.max()), lo + int(seg.argmax())
    rule = tax.get(best_t, tax["comedy"])
    gs, _ = gameplay_score(f, reaction, events, today)
    react_after = reaction[at : min(T, at + 10)]
    peak_react = at + int(np.argmax(react_after)) if len(react_after) else at
    end_anchor = peak_react if best_t in ("cutscene_reveal", "comedy", "discovery") else at
    start = at + rule["start"][0]
    end = end_anchor + rule["end"][1]
    return MomentResult(
        best_t,
        round(best_c, 3),
        round(float(gs[lo:hi].max()) if hi > lo else 0.0, 4),
        round(float(reaction[lo:hi].max()) if hi > lo else 0.0, 3),
        float(at),
        float(max(0, start)),
        float(min(T, end)),
        rule["hook"],
        float(at) if best_t == "cutscene_reveal" else None,
        bool(rule.get("music_subject")) and best_c >= 0.5,
    )
