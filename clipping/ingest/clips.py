"""Platform Clips & VOD Ingest (doc 04). Official endpoints only; clips that can't be downloaded are never
screen-recorded: those moments are cut from our own recording or the VOD instead."""

from __future__ import annotations

import datetime as dt
import shlex

import psycopg

from clipping.core import config, db, jobs

UTC = dt.UTC


def _ts(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def upsert_clip(
    c: psycopg.Connection, clip: dict, platform: str = "twitch", now: dt.datetime | None = None
) -> int:
    now = now or dt.datetime.now(UTC)
    cid = db.scalar(
        c, "SELECT id FROM creator WHERE platform=%s AND platform_id=%s", platform, clip.get("broadcaster_id")
    )
    off = clip.get("vod_offset")
    hist_point = [now.isoformat(timespec="seconds"), int(clip.get("view_count", 0))]
    return db.scalar(
        c,
        """
        INSERT INTO platform_clip(platform,clip_id,broadcaster_id,creator_id,video_id,vod_offset,duration,view_count,views_history,
                                  created_at,title,language,trend_only)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (platform,clip_id) DO UPDATE SET view_count=EXCLUDED.view_count,
          views_history = CASE WHEN platform_clip.created_at > %s - interval '48 hours'
                               THEN platform_clip.views_history || EXCLUDED.views_history ELSE platform_clip.views_history END,
          vod_offset=COALESCE(platform_clip.vod_offset, EXCLUDED.vod_offset), video_id=COALESCE(platform_clip.video_id, EXCLUDED.video_id),
          creator_id=COALESCE(platform_clip.creator_id, EXCLUDED.creator_id),
          trend_only = (COALESCE(platform_clip.vod_offset, EXCLUDED.vod_offset) IS NULL)
        RETURNING id""",
        platform,
        clip["id"],
        clip.get("broadcaster_id"),
        cid,
        clip.get("video_id") or None,
        off,
        clip.get("duration"),
        int(clip.get("view_count", 0)),
        db.j([hist_point]),
        _ts(clip.get("created_at")),
        clip.get("title"),
        clip.get("language"),
        off is None,
        now,
    )


def map_to_utc(c: psycopg.Connection, api, platform: str = "twitch") -> int:
    """abs_utc_start = VOD created_at + vod_offset; link to our recorded stream covering that instant."""
    rows = db.all_(
        c,
        """SELECT id, video_id, vod_offset FROM platform_clip WHERE platform=%s AND abs_utc_start IS NULL
                         AND vod_offset IS NOT NULL AND video_id IS NOT NULL""",
        platform,
    )
    need = sorted(
        {r["video_id"] for r in rows}
        - {v["video_id"] for v in db.all_(c, "SELECT video_id FROM vod WHERE platform=%s", platform)}
    )
    if need:
        for v in api.videos(need):
            dur = v.get("duration")
            c.execute(
                """INSERT INTO vod(platform,video_id,created_at,duration_s) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (platform, v["id"], _ts(v["created_at"]), parse_twitch_duration(dur) if dur else None),
            )
        for vid in need:
            if not db.one(c, "SELECT 1 FROM vod WHERE platform=%s AND video_id=%s", platform, vid):
                c.execute(
                    "INSERT INTO vod(platform,video_id,available) VALUES (%s,%s,false) ON CONFLICT DO NOTHING",
                    (platform, vid),
                )
    n = 0
    for r in rows:
        v = db.one(c, "SELECT * FROM vod WHERE platform=%s AND video_id=%s", platform, r["video_id"])
        if not v or not v["created_at"]:
            continue
        abs_start = v["created_at"] + dt.timedelta(seconds=float(r["vod_offset"]))
        sid = db.scalar(
            c,
            """SELECT st.id FROM stream st JOIN platform_clip pc ON pc.creator_id=st.creator_id WHERE pc.id=%s
                              AND st.started_at <= %s AND COALESCE(st.ended_at, now()) >= %s ORDER BY st.started_at DESC LIMIT 1""",
            r["id"],
            abs_start,
            abs_start,
        )
        c.execute(
            "UPDATE platform_clip SET abs_utc_start=%s, stream_id=%s WHERE id=%s", (abs_start, sid, r["id"])
        )
        if sid:
            jobs.enqueue(
                c, "heatmap_rescore", {"stream_id": sid}, dedupe_key=f"rescore:{sid}:{abs_start:%Y%m%d%H%M}"
            )
        else:
            jobs.enqueue(c, "vod_fetch_check", {"clip_row": r["id"]}, dedupe_key=f"vodchk:{r['id']}")
        n += 1
    return n


def parse_twitch_duration(s: str) -> float:
    total, num = 0.0, ""
    for ch in s:
        if ch.isdigit() or ch == ".":
            num += ch
        else:
            total += float(num or 0) * {"h": 3600, "m": 60, "s": 1}.get(ch, 0)
            num = ""
    return total


def discover(
    c: psycopg.Connection, api, game_id: str, hours: int = 24, now: dt.datetime | None = None
) -> int:
    now = now or dt.datetime.now(UTC)
    clips = api.clips(
        game_id=game_id,
        started_at=(now - dt.timedelta(hours=hours)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        ended_at=now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        max_items=config.settings()["ingest"]["max_clips_per_query"],
    )
    for cl in clips:
        upsert_clip(c, cl, now=now)
    return len(clips)


def per_creator(c: psycopg.Connection, api, now: dt.datetime | None = None) -> int:
    n = 0
    for cr in db.all_(
        c,
        """SELECT DISTINCT cr.platform_id FROM creator cr JOIN creator_score cs ON cs.creator_id=cr.id
                           WHERE cr.platform='twitch' AND cs.date >= current_date - 1 AND cs.selected""",
    ):
        for cl in api.clips(broadcaster_id=cr["platform_id"], max_items=200):
            upsert_clip(c, cl, now=now)
            n += 1
    return n


def trending(c: psycopg.Connection, day: dt.date | None = None, language: str | None = None) -> list[dict]:
    """Top share of the day's clips by views (default top 10%), optionally per language."""
    share = config.settings()["ingest"]["trend_top_share"]
    day = day or dt.date.today()
    rows = db.all_(
        c,
        """SELECT * FROM platform_clip WHERE created_at::date=%s AND (%s::text IS NULL OR language=%s)
                         ORDER BY view_count DESC""",
        day,
        language,
        language,
    )
    return rows[: max(1, int(len(rows) * share))] if rows else []


def view_velocity(history: list) -> float:
    """Views gained per hour over the last two samples (fast-rising clips mark moments the wider audience cares about)."""
    if len(history) < 2:
        return 0.0
    (t0, v0), (t1, v1) = history[-2], history[-1]
    hours = (dt.datetime.fromisoformat(t1) - dt.datetime.fromisoformat(t0)).total_seconds() / 3600
    return (v1 - v0) / hours if hours > 0 else 0.0


def try_download(api, clip_id: str, broadcaster_id: str) -> str | None:
    """Official Get Clips Download: only works for broadcasters who authorized our app. Never scrape or screen-record."""
    get = getattr(api, "get", None)
    if get is None:
        return None
    try:
        d = get("clips/downloads", {"broadcaster_id": broadcaster_id, "clip_id": clip_id}).get("data", [])
    except Exception:  # noqa: BLE001 - unauthorized broadcaster: fall back to our own recording
        return None
    return (d[0].get("landscape_download_url") or d[0].get("portrait_download_url")) if d else None


def vod_range_command(video_id: str, start_s: float, duration_s: float, out_ts: str) -> str:
    """Fetch only the needed VOD range (streamlink seeks HLS VODs), saved without re-encoding."""
    hms = lambda x: f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d}"  # noqa: E731
    return (
        f"streamlink --hls-start-offset {hms(max(0, start_s))} --hls-duration {hms(duration_s)} "
        f"-o {shlex.quote(out_ts)} https://www.twitch.tv/videos/{shlex.quote(video_id)} best"
    )


def needs_vod(c: psycopg.Connection, clip_row: int) -> dict | None:
    """A strong clip outside any recording -> VOD pull request (window around the clip), if the VOD exists."""
    r = db.one(
        c,
        """SELECT pc.*, v.created_at vod_start, v.available FROM platform_clip pc JOIN vod v
                     ON v.platform=pc.platform AND v.video_id=pc.video_id WHERE pc.id=%s""",
        clip_row,
    )
    if not r or not r["available"] or r["stream_id"]:
        return None
    pad = config.settings()["recorder"]["window_pad_s"]
    return {
        "video_id": r["video_id"],
        "start_s": max(0.0, r["vod_offset"] - 45 - pad),
        "duration_s": (r["duration"] or 30) + 75 + 2 * pad,
        "creator_id": r["creator_id"],
        "vod_start": r["vod_start"].isoformat(),
    }
