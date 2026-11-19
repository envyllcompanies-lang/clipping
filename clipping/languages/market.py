"""Language Market Ranking (doc 28): weekly market score per language, swap recommendations with a 4-week streak
and hysteresis, automatic provisioning prep, and posting-volume shares for the scheduler."""

from __future__ import annotations

import datetime as dt

import psycopg
import yaml

from clipping.core import config, db
from clipping.radar.scoring import percentile_ranks

UTC = dt.UTC
SAMPLE_MIN = 10


def cfg() -> dict:
    return config.load("languages.yaml")


def active_codes() -> list[str]:
    return [ch["stream_language"] for ch in config.channels().values() if ch.get("active", True)]


def measure_week(c: psycopg.Connection, week: dt.date) -> dict[str, dict]:
    """Raw signals per language for the week starting `week` (Monday)."""
    a, b = (
        dt.datetime.combine(week, dt.time(), UTC),
        dt.datetime.combine(week + dt.timedelta(days=7), dt.time(), UTC),
    )
    out: dict[str, dict] = {}
    for r in db.all_(
        c,
        """SELECT code, sum(viewers)::float * %s / 60 hours, max(channels) mx FROM language_sample
                           WHERE ts >= %s AND ts < %s AND platform IN ('twitch','kick','youtube') GROUP BY code""",
        SAMPLE_MIN,
        a,
        b,
    ):
        out.setdefault(r["code"], {})["audience_hours"] = r["hours"]
    for r in db.all_(
        c,
        """SELECT cr.language code, count(*) n FROM (SELECT creator_id, avg(viewer_count) v FROM creator_stat
                           WHERE sampled_at >= %s AND sampled_at < %s AND live GROUP BY creator_id) x JOIN creator cr ON cr.id=x.creator_id
                           WHERE x.v >= %s GROUP BY cr.language""",
        a,
        b,
        cfg()["viewer_floor"],
    ):
        out.setdefault(r["code"], {})["depth"] = r["n"]
    for r in db.all_(
        c,
        """SELECT code, max(channels) ch FROM language_sample WHERE platform='youtube_shorts' AND ts >= %s AND ts < %s
                           GROUP BY code""",
        a,
        b,
    ):
        out.setdefault(r["code"], {})["clip_channels"] = r["ch"]
    for r in db.all_(
        c,
        """SELECT ch.language code, avg((cf.features->>'performance')::float) perf FROM clip_feature cf
                           JOIN clip_version cv ON cv.id=cf.clip_version_id JOIN clip cl ON cl.id=cv.clip_id JOIN channel ch ON ch.id=cl.channel_id
                           WHERE cf.features ? 'performance' AND cl.created_at >= %s AND cl.created_at < %s GROUP BY ch.language""",
        a,
        b,
    ):
        out.setdefault(r["code"], {})["ours"] = r["perf"]
    return out


def value_of(code: str) -> float:
    for ch in config.channels().values():
        if ch["stream_language"] == code:
            return float(ch.get("rpm_tier", 0.3))
    return float(cfg()["watch_list"].get(code, {}).get("rpm_tier", 0.3))


def score_week(c: psycopg.Connection, week: dt.date, raw: dict[str, dict] | None = None) -> list[dict]:
    raw = raw if raw is not None else measure_week(c, week)
    w = cfg()["weights"]
    universe = set(active_codes()) | set(cfg()["watch_list"]) | set(raw)
    rows = {}
    for code in universe:
        r = raw.get(code, {})
        aud = float(r.get("audience_hours", 0) or 0)
        ch_n = int(r.get("clip_channels", 0) or 0)
        rows[code] = {
            "code": code,
            "audience_hours": aud,
            "depth": int(r.get("depth", 0) or 0),
            "clip_channels": ch_n,
            "opportunity": aud / (ch_n + 1),
            "value": value_of(code),
            "ours": float(r.get("ours", 0) or 0),
        }
    pct = {
        k: percentile_ranks({c_: rows[c_][k] for c_ in rows})
        for k in ("audience_hours", "depth", "opportunity", "ours")
    }
    for code, r in rows.items():
        r["score"] = round(
            w["audience"] * pct["audience_hours"][code]
            + w["depth"] * pct["depth"][code]
            + w["opportunity"] * pct["opportunity"][code]
            + w["value"] * r["value"]
            + w["ours"] * pct["ours"][code],
            4,
        )
    ranked = sorted(rows.values(), key=lambda x: (-x["score"], x["code"]))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
        c.execute(
            """INSERT INTO language_week(code,week,audience_hours,depth,clip_channels,opportunity,value,ours,score,rank)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (code,week) DO UPDATE SET audience_hours=EXCLUDED.audience_hours,
                     depth=EXCLUDED.depth, clip_channels=EXCLUDED.clip_channels, opportunity=EXCLUDED.opportunity, value=EXCLUDED.value,
                     ours=EXCLUDED.ours, score=EXCLUDED.score, rank=EXCLUDED.rank""",
            (
                r["code"],
                week,
                r["audience_hours"],
                r["depth"],
                r["clip_channels"],
                r["opportunity"],
                r["value"],
                r["ours"],
                r["score"],
                r["rank"],
            ),
        )
    return ranked


def swaps_enabled(week: dt.date) -> bool:
    rel = cfg()["release_date"]
    rel = rel if isinstance(rel, dt.date) else dt.date.fromisoformat(str(rel))
    return week >= rel + dt.timedelta(weeks=cfg()["swaps_disabled_weeks_after_release"])


def recommend(c: psycopg.Connection, week: dt.date, capacity_allows_add: bool = False) -> list[dict]:
    """A watch-list language that beats the lowest active language for N straight weeks, by >= hysteresis, triggers
    a recommendation (replace, or add when capacity allows). The outgoing language is paused, never deleted."""
    if not swaps_enabled(week):
        return []
    n, hyst = cfg()["streak_weeks"], cfg()["hysteresis"]
    active = set(active_codes())
    weeks = [week - dt.timedelta(weeks=k) for k in range(n)]
    out = []
    for cand in cfg()["watch_list"]:
        if cand in active:
            continue
        streak, victim = True, None
        for wk in weeks:
            rows = {
                r["code"]: r["score"]
                for r in db.all_(c, "SELECT code, score FROM language_week WHERE week=%s", wk)
            }
            act = {k: v for k, v in rows.items() if k in active}
            if cand not in rows or not act:
                streak = False
                break
            low = min(act, key=act.get)
            if rows[cand] < act[low] + hyst:
                streak = False
                break
            victim = victim or low
        if streak and not db.one(c, "SELECT 1 FROM language_action WHERE code=%s AND status='open'", cand):
            action = "recommend_add" if capacity_allows_add else "recommend_replace"
            reason = f"beat {victim} by >= {hyst:.2f} for {n} straight weeks"
            c.execute(
                "INSERT INTO language_action(code,action,reason,replaces) VALUES (%s,%s,%s,%s)",
                (cand, action, reason, None if capacity_allows_add else victim),
            )
            db.alert(c, "language_swap", f"{cand}: {action.replace('_', ' ')} ({reason})", cand)
            prepare_language(c, cand)
            out.append({"code": cand, "action": action, "replaces": victim})
    return out


def prepare_language(c: psycopg.Connection, code: str) -> dict:
    """Write the channel config (inactive, radar 'prep' on) and run the provisioning tool for it, so clips queue up
    before the 6 manual signups."""
    w = cfg()["watch_list"][code]
    path = config.CONFIG / "channels" / f"{code}.yaml"
    if not path.exists():
        base = next(iter(config.channels().values()))
        ch = dict(
            base,
            code=code,
            key=f"gta6-{code}",
            language=w["language"],
            native_name=w["native_name"],
            flag=w["flag"],
            time_zone=w["time_zone"],
            stream_language=w.get("stream_language", code),
            rpm_tier=w["rpm_tier"],
            active=False,
            prep=True,
        )
        path.write_text(yaml.safe_dump(ch, sort_keys=False, allow_unicode=True))
    from clipping.accounts import provision

    return provision.provision(c, codes=[code], check_handles=False, include_inactive=True)


def shares(rows: list[dict], floor: float | None = None) -> dict[str, float]:
    """Daily posting share per active language proportional to score, with a floor for every active language."""
    floor = cfg()["share_floor"] if floor is None else floor
    act = [r for r in rows if r["code"] in set(active_codes())]
    if not act:
        return {}
    tot = sum(max(r["score"], 1e-6) for r in act)
    raw = {r["code"]: max(r["score"], 1e-6) / tot for r in act}
    k = len(raw)
    if floor * k >= 1:
        return {c_: 1 / k for c_ in raw}
    low = {c_ for c_, v in raw.items() if v < floor}
    while True:
        rest = 1 - floor * len(low)
        tot_hi = sum(v for c_, v in raw.items() if c_ not in low)
        out = {c_: (floor if c_ in low else v / tot_hi * rest) for c_, v in raw.items()}
        new_low = {c_ for c_, v in out.items() if v < floor - 1e-12}
        if not new_low - low:
            return out
        low |= new_low


def weekly(c: psycopg.Connection, week: dt.date | None = None) -> dict:
    week = week or (dt.date.today() - dt.timedelta(days=dt.date.today().weekday()))
    rows = score_week(c, week)
    rec = recommend(c, week)
    sh = shares(rows)
    db.set_flag(c, "language_shares", sh)
    return {"week": str(week), "rows": rows, "recommendations": rec, "shares": sh}


def carry_youtube(c: psycopg.Connection, week: dt.date) -> None:
    """YouTube quota exhausted: carry last week's YouTube audience forward with a flag (doc 28)."""
    prev = week - dt.timedelta(weeks=1)
    for r in db.all_(
        c,
        """SELECT code, sum(viewers) v, max(channels) ch FROM language_sample WHERE platform='youtube'
                           AND ts >= %s AND ts < %s GROUP BY code""",
        dt.datetime.combine(prev, dt.time(), UTC),
        dt.datetime.combine(week, dt.time(), UTC),
    ):
        c.execute(
            "INSERT INTO language_sample(code,platform,ts,viewers,channels) VALUES (%s,'youtube',%s,%s,%s) ON CONFLICT DO NOTHING",
            (r["code"], dt.datetime.combine(week, dt.time(), UTC), int(r["v"]), r["ch"]),
        )
        c.execute(
            "UPDATE language_week SET flags = flags || '{\"youtube_carried\": true}' WHERE code=%s AND week=%s",
            (r["code"], week),
        )
