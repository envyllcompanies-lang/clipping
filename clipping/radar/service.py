"""Radar service: resolve game IDs, poll live streams every 10 min, daily per-language ranking (doc 01)."""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict

import psycopg

from clipping.core import config, db, jobs
from clipping.radar import scoring
from clipping.radar.sources import LiveStream

LANG_HINTS = {
    "es": r"\b(directo|en vivo|jugando|español)\b",
    "pt": r"\b(ao vivo|jogando|português|br)\b",
    "fr": r"\b(en direct|français|fr)\b",
    "de": r"\b(deutsch|live auf|zocken)\b",
    "ru": r"[а-яё]{3,}",
    "ar": r"[؀-ۿ]{2,}",
    "ja": r"[぀-ヿ]",
    "tr": r"\b(türkçe|canlı|yayın)\b",
    "vi": r"[ăâđêôơư]",
}


def detect_title_language(title: str) -> str | None:
    t = title.lower()
    for code, pat in LANG_HINTS.items():
        if re.search(pat, t):
            return code
    return None


def resolve_game_ids(sources: list, slug: str = "gta6") -> dict[str, str | None]:
    g = config.game(slug)
    out = {}
    changed = False
    for s in sources:
        key = f"{s.platform}_id"
        if not g.get(key):
            gid = s.resolve_game(g["search_names"])
            if gid:
                g[key] = gid
                changed = True
        out[s.platform] = g.get(key)
    if changed:
        config.save(f"games/{slug}.yaml", g)
    return out


def upsert_creator(
    c: psycopg.Connection, platform: str, platform_id: str, handle: str, language: str | None
) -> int:
    return db.scalar(
        c,
        """INSERT INTO creator(platform,platform_id,handle,language) VALUES (%s,%s,%s,%s)
        ON CONFLICT (platform,platform_id) DO UPDATE SET handle=EXCLUDED.handle,
          language=COALESCE(creator.language, EXCLUDED.language) RETURNING id""",
        platform,
        platform_id,
        handle,
        language,
    )


def poll_live(
    c: psycopg.Connection, sources: list, game_ids: dict[str, str | None], now: dt.datetime | None = None
) -> list[dict]:
    """One 10-minute sample: every live GTA 6 creator on each platform. API outages skip samples (never zeros)."""
    now = (now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    seen: list[dict] = []
    lang_view: dict[tuple[str, str], list[int]] = defaultdict(list)
    for src in sources:
        gid = game_ids.get(src.platform)
        if not gid:
            continue
        try:
            streams: list[LiveStream] = src.live_streams(gid)
        except Exception as e:  # noqa: BLE001
            db.alert(c, "radar_source_down", f"{src.platform} live poll failed: {e}", src.platform)
            continue
        db.resolve_alert(c, "radar_source_down", src.platform)
        for s in streams:
            lang = (s.language or "").lower()[:2] or detect_title_language(s.title) or None
            cid = upsert_creator(c, s.platform, s.user_id, s.login, lang)
            c.execute(
                """INSERT INTO creator_stat(creator_id,sampled_at,live,viewer_count,game,title,language,stream_started_at)
                         VALUES (%s,%s,true,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (cid, now, s.viewer_count, s.game_id, s.title, lang, s.started_at or None),
            )
            seen.append(
                {
                    "creator_id": cid,
                    "platform": s.platform,
                    "login": s.login,
                    "stream_id": s.stream_id,
                    "viewers": s.viewer_count,
                    "language": lang,
                    "started_at": s.started_at,
                }
            )
            if lang:
                lang_view[(lang, s.platform)].append(s.viewer_count)
    for (lang, plat), views in lang_view.items():
        c.execute(
            """INSERT INTO language_sample(code,platform,ts,viewers,channels,creators_over_floor) VALUES (%s,%s,%s,%s,%s,%s)
                     ON CONFLICT DO NOTHING""",
            (lang, plat, now, sum(views), len(views), sum(v >= 1000 for v in views)),
        )
    # Selected creators who are live now -> recorder start requests (dedupe per platform stream id).
    sel = {
        r["creator_id"]
        for r in db.all_(
            c,
            """SELECT creator_id FROM creator_score WHERE date=(SELECT max(date) FROM creator_score)
                                               AND selected""",
        )
    }
    live_ids = {s["creator_id"] for s in seen}
    for s in seen:
        if s["creator_id"] in sel:
            jobs.enqueue(c, "record_start", s, dedupe_key=f"{s['platform']}:{s['stream_id']}")
    # Creators that left GTA 6 / went offline while recording -> stop.
    for r in db.all_(c, "SELECT s.id, s.creator_id FROM stream s WHERE s.status='recording'"):
        if r["creator_id"] not in live_ids:
            jobs.enqueue(
                c, "record_stop", {"stream_id": r["id"]}, dedupe_key=f"stop:{r['id']}:{now.isoformat()}"
            )
    return seen


def build_inputs(c: psycopg.Connection, day: dt.date, interval_min: float) -> list[scoring.CreatorInput]:
    end = dt.datetime.combine(day, dt.time(), dt.UTC) + dt.timedelta(days=1)
    start = end - dt.timedelta(days=14)
    creators = db.all_(c, "SELECT * FROM creator WHERE language IS NOT NULL")
    samples = defaultdict(list)
    for r in db.all_(
        c,
        """SELECT creator_id, sampled_at, live, viewer_count FROM creator_stat
                           WHERE sampled_at >= %s AND sampled_at < %s""",
        start,
        end,
    ):
        samples[r["creator_id"]].append(
            ((end - r["sampled_at"]).total_seconds() / 3600, r["live"], r["viewer_count"])
        )
    clips = defaultdict(list)
    for r in db.all_(
        c,
        """SELECT creator_id, created_at, view_count FROM platform_clip
                           WHERE creator_id IS NOT NULL AND created_at >= %s AND created_at < %s""",
        start,
        end,
    ):
        clips[r["creator_id"]].append(((end - r["created_at"]).total_seconds() / 3600, r["view_count"] or 0))
    off = {
        r["creator_id"]: r["median_upload_views"]
        for r in db.all_(
            c,
            """SELECT DISTINCT ON (creator_id) creator_id, median_upload_views FROM creator_offplatform
              WHERE day > %s ORDER BY creator_id, day DESC""",
            day - dt.timedelta(days=30),
        )
    }
    ours = {
        r["creator_id"]: r["perf"]
        for r in db.all_(
            c,
            """
        SELECT cl.creator_id, percentile_cont(0.5) WITHIN GROUP (ORDER BY (cf.features->>'performance')::float) perf
        FROM clip cl JOIN clip_version cv ON cv.clip_id=cl.id JOIN clip_feature cf ON cf.clip_version_id=cv.id
        WHERE cf.features ? 'performance' AND cl.created_at > %s GROUP BY cl.creator_id""",
            end - dt.timedelta(days=30),
        )
    }
    cpv = {
        r["creator_id"]: r["cpv"]
        for r in db.all_(
            c,
            """
        SELECT s.creator_id, sum(b.msgs)::float / NULLIF(avg(cs.viewer_count),0) / NULLIF(count(DISTINCT b.t_start),0) cpv
        FROM chat_bucket b JOIN stream s ON s.id=b.stream_id
        JOIN creator_stat cs ON cs.creator_id=s.creator_id AND cs.sampled_at BETWEEN s.started_at AND COALESCE(s.ended_at, now())
        WHERE b.t_start >= %s AND NOT b.missing GROUP BY s.creator_id""",
            end - dt.timedelta(days=7),
        )
    }
    return [
        scoring.CreatorInput(
            r["id"],
            r["language"],
            samples.get(r["id"], []),
            clips.get(r["id"], []),
            r["platform"] == "twitch",
            off.get(r["id"]),
            ours.get(r["id"]),
            cpv.get(r["id"]),
            r["blocklisted"],
            r["pinned"],
        )
        for r in creators
        if samples.get(r["id"]) or r["pinned"]
    ]


def active_weights(c: psycopg.Connection, component: str, default: dict) -> dict:
    r = db.one(
        c,
        'SELECT "values" FROM weights WHERE component=%s AND active ORDER BY version DESC LIMIT 1',
        component,
    )
    return r["values"] if r else default


def daily_rank(
    c: psycopg.Connection,
    day: dt.date | None = None,
    slots: int | None = None,
    languages: list[str] | None = None,
) -> dict[str, list[scoring.Scored]]:
    """Reproducible: same stored samples in -> same order out."""
    cfg = config.settings()["radar"]
    day = day or dt.date.today()
    slots = slots if slots is not None else config.settings()["recorder"]["slots"]
    languages = languages or [
        ch["stream_language"] for ch in config.channels().values() if ch.get("active", True) or ch.get("prep")
    ]
    weights = active_weights(c, "radar", cfg["weights"])
    inputs = [i for i in build_inputs(c, day, cfg["sample_interval_min"]) if i.language in languages]
    by_lang: dict[str, list] = defaultdict(list)
    for i in inputs:
        by_lang[i.language].append(i)
    audience = {
        lang: sum(scoring.compute_signals(i)["live_audience"] or 0 for i in v) for lang, v in by_lang.items()
    }
    alloc = scoring.allocate_slots(slots, audience)
    prev = {
        r["creator_id"]: r
        for r in db.all_(
            c,
            """SELECT creator_id, selected, below_cutoff_days FROM creator_score
                                                  WHERE date=(SELECT max(date) FROM creator_score WHERE date < %s)""",
            day,
        )
    }
    results = {}
    for lang, items in sorted(by_lang.items()):
        scored = scoring.score_language(items, weights, cfg["sample_interval_min"], cfg["viewbot_chat_ratio"])
        scoring.select(
            scored,
            alloc.get(lang, 0),
            exploit_share=cfg["exploit_share"],
            previous=prev,
            hysteresis_days=cfg["hysteresis_days"],
            blocked={i.creator_id for i in items if i.blocklisted},
            pinned={i.creator_id for i in items if i.pinned},
        )
        for s in scored:
            c.execute(
                """INSERT INTO creator_score(creator_id,date,language,signals,percentiles,score,rank,selected,selection_reason,
                         below_cutoff_days,flags) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                         ON CONFLICT (creator_id,date) DO UPDATE SET signals=EXCLUDED.signals, percentiles=EXCLUDED.percentiles,
                         score=EXCLUDED.score, rank=EXCLUDED.rank, selected=EXCLUDED.selected,
                         selection_reason=EXCLUDED.selection_reason, below_cutoff_days=EXCLUDED.below_cutoff_days, flags=EXCLUDED.flags""",
                (
                    s.creator_id,
                    day,
                    lang,
                    db.j(s.signals),
                    db.j(s.percentiles),
                    s.score,
                    s.rank,
                    s.selected,
                    s.reason or None,
                    s.below_cutoff_days,
                    db.j(s.flags),
                ),
            )
        results[lang] = scored
    return results


def rollup_old_samples(c: psycopg.Connection, keep_days: int = 90) -> int:
    cur = c.execute(
        "DELETE FROM creator_stat WHERE sampled_at < now() - make_interval(days => %s)", (keep_days,)
    )
    return cur.rowcount
