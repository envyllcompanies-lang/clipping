"""Stage backtest 04: hourly clip polling over a simulated day; every clip with a VOD position is mapped to the
right UTC instant within 1 hour of creation; clips without vod_offset stay trend-only."""

from __future__ import annotations

import datetime as dt

import numpy as np

from clipping.core import db
from clipping.eval.harness import Example, StageResult, scratch_db, stage
from clipping.ingest import clips
from clipping.radar.sources import FakeLiveSource

UTC = dt.UTC


@stage("04", "Platform Clips & VOD Ingest")
def run() -> StageResult:
    rng = np.random.default_rng(4)
    day0 = dt.datetime(2026, 11, 18, tzinfo=UTC)
    api = FakeLiveSource("twitch")
    truth = {}
    for v in range(12):
        vstart = day0 + dt.timedelta(minutes=int(rng.integers(0, 600)))
        api.video_list.append(
            {"id": f"v{v}", "created_at": vstart.isoformat().replace("+00:00", "Z"), "duration": "6h"}
        )
        for k in range(40):
            off = float(rng.uniform(0, 6 * 3600))
            created = vstart + dt.timedelta(seconds=off + float(rng.uniform(30, 3 * 3600)))
            null = rng.random() < 0.05
            cid = f"v{v}c{k}"
            api.clip_list.append(
                {
                    "id": cid,
                    "broadcaster_id": f"b{v}",
                    "video_id": "" if null else f"v{v}",
                    "vod_offset": None if null else off,
                    "duration": 30,
                    "view_count": int(rng.lognormal(5, 1.3)),
                    "created_at": created.isoformat().replace("+00:00", "Z"),
                    "_created": created,
                }
            )
            truth[cid] = (None if null else vstart + dt.timedelta(seconds=off), created)
    ex, mapped_ok, latency_ok, trend_ok = [], [], [], []
    with scratch_db() as c:
        for v in range(12):
            db.scalar(
                c,
                "INSERT INTO creator(platform,platform_id,handle) VALUES ('twitch',%s,%s) RETURNING id",
                f"b{v}",
                f"b{v}",
            )
        seen_at = {}
        all_clips = api.clip_list
        for hour in range(1, 40):
            now = day0 + dt.timedelta(hours=hour)
            api.clip_list = [x for x in all_clips if x["_created"] <= now]
            clips.discover(c, api, "g", hours=24, now=now)
            clips.map_to_utc(c, api)
            for r in db.all_(c, "SELECT clip_id FROM platform_clip WHERE abs_utc_start IS NOT NULL"):
                seen_at.setdefault(r["clip_id"], now)
        rows = {r["clip_id"]: r for r in db.all_(c, "SELECT * FROM platform_clip")}
    for cid, (want, created) in truth.items():
        r = rows.get(cid)
        if want is None:
            trend_ok.append(bool(r and r["trend_only"]))
            continue
        ok = bool(r and r["abs_utc_start"] and abs((r["abs_utc_start"] - want).total_seconds()) < 1)
        mapped_ok.append(ok)
        lat = (seen_at.get(cid, created + dt.timedelta(days=9)) - created).total_seconds()
        latency_ok.append(lat <= 3600)
        if not ok or lat > 3600:
            ex.append(Example(cid, "map", float(lat), f"ok={ok}"))
    return StageResult(
        {
            "mapped_correct": float(np.mean(mapped_ok)),
            "mapped_within_1h": float(np.mean(latency_ok)),
            "null_offset_trend_only": float(np.mean(trend_ok)),
        },
        ex,
        "synthetic@v1",
    )
