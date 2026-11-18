"""Real ground-truth builder from Twitch (doc 30 "viewer-clip replays"): GTA VI VODs + every viewer clip on them.

Official Helix endpoints for clips/videos; the VOD range is fetched with streamlink (doc 04 VOD ingest). Media is
processed in 30-minute chunks and deleted; only per-second feature arrays and clip labels are kept
(eval/datasets/viewer_clips/<version>/: manifest.json, vods.json, <video_id>.npz)."""

from __future__ import annotations

import datetime as dt
import io
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np

from clipping.eval import datasets
from clipping.eval.harness import DATASETS
from clipping.radar.sources import TwitchHelix

UTC = dt.UTC
SPAN_S = 4 * 3600
CHUNK_S = 1800
SR = 8000


def _ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def pick_vods(
    h: TwitchHelix, game_id: str, days: int = 7, n: int = 6, min_clips: int = 12, langs_max: int = 2
) -> list[dict]:
    now = dt.datetime.now(UTC)
    clips = []
    for d in range(
        days
    ):  # day windows: Helix caps results per query, widen by windows instead of deep pages (doc 04)
        a, b = now - dt.timedelta(days=d + 1), now - dt.timedelta(days=d)
        clips += h.clips(
            game_id=game_id,
            started_at=a.isoformat().replace("+00:00", "Z"),
            ended_at=b.isoformat().replace("+00:00", "Z"),
            max_items=1000,
        )
    cnt = Counter(c["video_id"] for c in clips if c.get("video_id") and c.get("vod_offset") is not None)
    vids = h.videos([v for v, k in cnt.most_common(60) if k >= min_clips // 2])
    by_lang: Counter = Counter()
    out = []
    for v in sorted(vids, key=lambda v: -cnt[v["id"]]):
        if v.get("type") != "archive":
            continue
        lang = (v.get("language") or "")[:2]
        if by_lang[lang] >= langs_max or any(o["user_id"] == v["user_id"] for o in out):  # distinct creators
            continue
        by_lang[lang] += 1
        out.append(v)
        if len(out) >= n:
            break
    return out


def vod_clips(h: TwitchHelix, vod: dict) -> list[dict]:
    start = _ts(vod["created_at"])
    dur = media_duration(vod["duration"])
    cl = h.clips(
        broadcaster_id=vod["user_id"],
        started_at=start.isoformat().replace("+00:00", "Z"),
        ended_at=(start + dt.timedelta(seconds=dur, hours=48)).isoformat().replace("+00:00", "Z"),
        max_items=1000,
    )
    return [
        {
            "id": c["id"],
            "offset": float(c["vod_offset"]),
            "duration": float(c["duration"]),
            "views": int(c["view_count"]),
            "created_at": c["created_at"],
            "title": c.get("title", ""),
        }
        for c in cl
        if c.get("video_id") == vod["id"] and c.get("vod_offset") is not None
    ]


def media_duration(s: str) -> float:
    from clipping.ingest.clips import parse_twitch_duration

    return parse_twitch_duration(s)


def best_span(clips: list[dict], vod_len: float, span: float = SPAN_S) -> float:
    if vod_len <= span:
        return 0.0
    starts = np.arange(0, vod_len - span + 1, 300)
    score = [sum(np.log1p(c["views"]) for c in clips if s <= c["offset"] < s + span) for s in starts]
    return float(starts[int(np.argmax(score))])


def fetch(video_id: str, start: float, dur: float, quality: str, out: Path) -> Path:
    hms = lambda x: f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d}"  # noqa: E731
    exe = str(Path(sys.executable).with_name("streamlink"))
    subprocess.run(
        [
            exe if Path(exe).exists() else "streamlink",
            "--hls-start-offset",
            hms(start),
            "--hls-duration",
            hms(dur),
            "-f",
            "-o",
            str(out),
            f"https://www.twitch.tv/videos/{video_id}",
            quality,
        ],
        check=True,
        capture_output=True,
        timeout=1800,
    )
    return out


def chunk_features(audio_ts: Path, video_ts: Path, T: int) -> dict[str, np.ndarray]:
    from clipping.heatmap.features import compute

    return compute(audio_ts, video_ts, T)


def build(version: str | None = None, n_vods: int = 6, game: str = "Grand Theft Auto VI", log=print) -> Path:
    h = TwitchHelix.from_env()
    if h is None:
        raise RuntimeError("TWITCH_CLIENT_ID/SECRET not set")
    gid = h.resolve_game([game])
    version = version or dt.date.today().isoformat()
    out_dir = DATASETS / "viewer_clips" / version
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = []
    for vod in pick_vods(h, gid, n=n_vods):
        npz = out_dir / f"{vod['id']}.npz"
        clips = vod_clips(h, vod)
        L = media_duration(vod["duration"])
        s0 = best_span(clips, L)
        span = min(SPAN_S, L - s0)
        T = int(span)
        rel = [dict(c, t_start=c["offset"] - s0) for c in clips if s0 <= c["offset"] < s0 + span]
        log(
            f"vod {vod['id']} {vod['user_login']} ({vod['language']}): {len(clips)} clips, {len(rel)} in span {s0:.0f}+{span:.0f}s"
        )
        if not npz.exists():
            from concurrent.futures import ThreadPoolExecutor

            def do_chunk(k):
                d = min(CHUNK_S, T - k)
                with tempfile.TemporaryDirectory() as tmp:
                    with ThreadPoolExecutor(2) as ex2:  # audio and video in parallel
                        fa = ex2.submit(fetch, vod["id"], s0 + k, d, "audio_only,worst", Path(tmp) / "a.ts")
                        fv = ex2.submit(fetch, vod["id"], s0 + k, d, "160p,worst", Path(tmp) / "v.ts")
                        aud, vid = fa.result(), fv.result()
                    return chunk_features(aud, vid, d)

            with ThreadPoolExecutor(4) as ex:  # four 30-minute chunks at a time
                parts = list(ex.map(do_chunk, range(0, T, CHUNK_S)))
            log(f"  {len(parts)} chunks done")
            feats = {key: [p_[key] for p_ in parts] for key in parts[0]}
            buf = io.BytesIO()
            np.savez_compressed(buf, **{k: np.concatenate(v) for k, v in feats.items()})
            npz.write_bytes(buf.getvalue())
        meta.append(
            {
                "video_id": vod["id"],
                "creator": vod["user_login"],
                "creator_id": vod["user_id"],
                "language": (vod["language"] or "")[:2],
                "vod_created_at": vod["created_at"],
                "span_start_s": s0,
                "duration_s": T,
                "clips": rel,
            }
        )
    files = {"vods.json": meta}
    for m in meta:
        files[f"{m['video_id']}.npz"] = (out_dir / f"{m['video_id']}.npz").read_bytes()
    datasets.write(
        "viewer_clips",
        version,
        files,
        {
            "source": "Twitch Helix clips (vod_offset) + VOD audio/160p via streamlink",
            "game": game,
            "game_id": gid,
            "vods": len(meta),
            "chat": "not available for VODs",
        },
    )
    return out_dir


def load(version: str | None = None) -> tuple[list[dict], dict[str, dict[str, np.ndarray]], str]:
    from clipping.eval.harness import dataset_dir, dsver

    d = dataset_dir("viewer_clips", version)
    meta = datasets.read(d, "vods.json")
    arrays = {}
    for m in meta:
        with np.load(d / f"{m['video_id']}.npz") as z:
            arrays[m["video_id"]] = {k: z[k] for k in z.files}
    return meta, arrays, dsver(d)


if __name__ == "__main__":
    print(json.dumps(str(build(n_vods=int(sys.argv[1]) if len(sys.argv) > 1 else 6))))
