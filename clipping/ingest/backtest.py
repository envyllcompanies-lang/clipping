"""Stage backtest 04 on real Twitch data: the last 24 h of GTA VI clips (Helix) are ingested and mapped to UTC
through their VODs. Every clip with a VOD position must map to an instant inside its VOD that precedes the clip's
creation; clips without one stay trend-only. Needs TWITCH_CLIENT_ID/SECRET."""

from __future__ import annotations

import datetime as dt

from clipping.core import db
from clipping.eval.harness import Example, StageResult, scratch_db, stage
from clipping.ingest import clips
from clipping.radar.sources import TwitchHelix

UTC = dt.UTC


@stage("04", "Platform Clips & VOD Ingest (real)")
def run() -> StageResult:
    h = TwitchHelix.from_env()
    if h is None:
        raise RuntimeError("needs Twitch keys")
    gid = h.resolve_game(["Grand Theft Auto VI"])
    now = dt.datetime.now(UTC)
    ex = []
    with scratch_db() as c:
        n = clips.discover(c, h, gid, hours=24, now=now)
        for r in db.all_(c, "SELECT DISTINCT broadcaster_id FROM platform_clip"):
            c.execute(
                "INSERT INTO creator(platform,platform_id,handle) VALUES ('twitch',%s,%s) ON CONFLICT DO NOTHING",
                (r["broadcaster_id"], r["broadcaster_id"]),
            )
        c.execute(
            "UPDATE platform_clip pc SET creator_id=cr.id FROM creator cr WHERE cr.platform_id=pc.broadcaster_id"
        )
        mapped = clips.map_to_utc(c, h)
        rows = db.all_(
            c,
            """SELECT pc.*, v.created_at vod_start, v.duration_s, v.available FROM platform_clip pc
                             LEFT JOIN vod v ON v.platform=pc.platform AND v.video_id=pc.video_id""",
        )
        with_off = [r for r in rows if r["vod_offset"] is not None and r["video_id"]]
        resolvable = [r for r in with_off if r["available"] and r["vod_start"]]
        consistent = []
        for r in resolvable:
            ok = (
                r["abs_utc_start"] is not None
                and r["vod_start"] <= r["abs_utc_start"]
                and (
                    r["duration_s"] is None
                    or r["abs_utc_start"] <= r["vod_start"] + dt.timedelta(seconds=r["duration_s"] + 60)
                )
                and r["abs_utc_start"] <= r["created_at"] + dt.timedelta(seconds=60)
            )
            consistent.append(ok)
            if not ok:
                ex.append(
                    Example(
                        r["clip_id"],
                        "inconsistent",
                        0,
                        f"abs={r['abs_utc_start']} vod={r['vod_start']} created={r['created_at']}",
                    )
                )
        trend_ok = all(r["trend_only"] for r in rows if r["vod_offset"] is None)
        lag = sorted(
            (r["created_at"] - r["abs_utc_start"]).total_seconds() / 60
            for r in resolvable
            if r["abs_utc_start"]
        )
    return StageResult(
        {
            "mapped_consistent": sum(consistent) / max(len(consistent), 1),
            "mapped_share_of_resolvable": mapped / max(len(resolvable), 1) if resolvable else 0.0,
            "null_offset_trend_only": 1.0 if trend_ok else 0.0,
        },
        ex,
        f"helix-live@{now:%Y-%m-%dT%H}",
        {
            "clips": n,
            "with_vod_offset": len(with_off),
            "vod_available": len(resolvable),
            "median_minutes_moment_to_clip": lag[len(lag) // 2] if lag else None,
        },
    )
