"""Analytics & feedback loop (doc 22): stats on schedule, normalized performance, features per clip, weekly refits
with a held-out check, Thompson-sampling bandits for A/B arms, monetization progress and the weekly digest.
It only changes weights, thresholds, allocations and arms; never creative calls."""

from __future__ import annotations

import datetime as dt
import math
import statistics

import numpy as np
import psycopg

from clipping.core import db

UTC = dt.UTC
YT_THRESHOLD = 10_000_000
YT_THRESHOLD_NEW_2027 = 20_000_000
TT_FOLLOWERS, TT_VIEWS = 10_000, 100_000


# ---------------- collection ----------------
def pull_interval(age: dt.timedelta) -> dt.timedelta | None:
    if age < dt.timedelta(hours=48):
        return dt.timedelta(hours=1)
    if age < dt.timedelta(days=14):
        return dt.timedelta(days=1)
    if age < dt.timedelta(days=90):
        return dt.timedelta(days=7)
    return None


def due_posts(c: psycopg.Connection, now: dt.datetime) -> list[dict]:
    rows = db.all_(
        c,
        """SELECT p.*, (SELECT max(sampled_at) FROM post_stat s WHERE s.post_id=p.id) last FROM post p
                         WHERE p.status='live' AND p.posted_at IS NOT NULL AND p.platform_post_id IS NOT NULL""",
    )
    out = []
    for r in rows:
        iv = pull_interval(now - r["posted_at"])
        if iv is not None and (r["last"] is None or now - r["last"] >= iv - dt.timedelta(minutes=5)):
            out.append(r)
    return out


def pull_stats(c: psycopg.Connection, adapters: dict, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(UTC)
    ok = miss = 0
    for p in due_posts(c, now):
        acc = db.one(c, "SELECT * FROM account WHERE id=%s", p["account_id"])
        try:
            s = adapters[p["platform"]].stats(p["platform_post_id"], acc)
        except Exception:  # noqa: BLE001 - a missed pull is counted, retried at the next interval
            miss += 1
            db.audit(c, "stats_missed", str(p["id"]))
            continue
        c.execute(
            """INSERT INTO post_stat(post_id,sampled_at,views,likes,comments,shares,saves,retention,followers_gained)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (
                p["id"],
                now,
                s.get("views"),
                s.get("likes"),
                s.get("comments"),
                s.get("shares"),
                s.get("saves"),
                s.get("retention"),
                s.get("followers_gained"),
            ),
        )
        ok += 1
    return {"pulled": ok, "missed": miss}


# ---------------- normalized performance ----------------
def views_at_48h(c: psycopg.Connection, post: dict) -> float | None:
    rows = db.all_(
        c,
        "SELECT sampled_at, views FROM post_stat WHERE post_id=%s AND views IS NOT NULL ORDER BY sampled_at",
        post["id"],
    )
    if not rows:
        return None
    at48 = [r for r in rows if r["sampled_at"] - post["posted_at"] >= dt.timedelta(hours=47)]
    if at48:
        return float(at48[0]["views"])
    last = rows[-1]
    age_h = max(1.0, (last["sampled_at"] - post["posted_at"]).total_seconds() / 3600)
    # growth curve: short-form views grow roughly with log(age); scale the latest sample to 48 h
    return float(last["views"]) * math.log1p(48) / math.log1p(age_h)


def performance(c: psycopg.Connection, post_id: int) -> float | None:
    """0.6 x views relative to the account's rolling median 48 h views + 0.4 x relative retention; log-transformed."""
    p = db.one(c, "SELECT * FROM post WHERE id=%s", post_id)
    v = views_at_48h(c, p)
    if v is None:
        return None
    peers = [
        views_at_48h(c, q)
        for q in db.all_(
            c,
            """SELECT * FROM post WHERE account_id=%s AND status='live' AND posted_at IS NOT NULL
                                                     AND posted_at > %s - interval '30 days' ORDER BY posted_at DESC LIMIT 60""",
            p["account_id"],
            p["posted_at"],
        )
    ]
    peers = [x for x in peers if x is not None]
    med = statistics.median(peers) if peers else v
    rel_v = v / med if med > 0 else 1.0
    ret = db.scalar(
        c,
        "SELECT retention FROM post_stat WHERE post_id=%s AND retention IS NOT NULL ORDER BY sampled_at DESC LIMIT 1",
        post_id,
    )
    if ret is not None:
        rets = [
            r["retention"]
            for r in db.all_(
                c,
                """SELECT DISTINCT ON (s.post_id) s.retention FROM post_stat s JOIN post q ON q.id=s.post_id
                                                     WHERE q.account_id=%s AND s.retention IS NOT NULL ORDER BY s.post_id, s.sampled_at DESC""",
                p["account_id"],
            )
        ]
        rel_r = ret / statistics.median(rets) if rets and statistics.median(rets) > 0 else 1.0
        perf = 0.6 * rel_v + 0.4 * rel_r
    else:
        perf = rel_v
    return math.log(max(perf, 1e-3))


def features(c: psycopg.Connection, clip_version_id: int) -> dict:
    r = db.one(
        c,
        """SELECT cv.version_type, cv.duration_s, cl.packaging, cl.edit_plan, cl.crop_plan, cl.style_profile, cl.creator_id, cl.channel_id,
                            m.signals, m.score, m.created_at moment_at, ch.language
                     FROM clip_version cv JOIN clip cl ON cl.id=cv.clip_id JOIN moment m ON m.id=cl.moment_id
                     LEFT JOIN channel ch ON ch.id=cl.channel_id WHERE cv.id=%s""",
        clip_version_id,
    )
    plan = ((r["edit_plan"] or {}).get("versions") or {}).get(r["version_type"], {})
    pk = r["packaging"] or {}
    return {
        "creator_id": r["creator_id"],
        "channel_id": r["channel_id"],
        "language": r["language"],
        "moment_score": r["score"],
        "signals": r["signals"],
        "event_type": plan.get("payoff_kind"),
        "length": r["duration_s"],
        "cold_open": bool(plan.get("hook")),
        "hook_pattern": (pk.get("features") or {}).get("hook_pattern"),
        "title_style": (pk.get("features") or {}).get("title_style"),
        "style_profile": r["style_profile"],
        "layout": (r["crop_plan"] or {}).get("layout"),
        "text_mode": (r["crop_plan"] or {}).get("text_mode"),
        "text_style": (r["crop_plan"] or {}).get("text_style"),
        "headline_case": (r["crop_plan"] or {}).get("headline_case"),
        "moment_type": (r["crop_plan"] or {}).get("moment_type"),
        "version": r["version_type"],
    }


def update_features(c: psycopg.Connection) -> int:
    """Per clip version: features plus mean performance across its posts (by platform too)."""
    n = 0
    for cv in db.all_(c, "SELECT DISTINCT clip_version_id id FROM post WHERE status='live'"):
        perfs = {}
        for p in db.all_(
            c, "SELECT id, platform, posted_at FROM post WHERE clip_version_id=%s AND status='live'", cv["id"]
        ):
            v = performance(c, p["id"])
            if v is not None:
                perfs[p["platform"]] = v
                hour = p["posted_at"].hour if p["posted_at"] else None
                perfs[f"hour:{p['platform']}"] = hour
        if not any(k for k in perfs if not k.startswith("hour:")):
            continue
        f = features(c, cv["id"]) | {
            "performance": statistics.fmean(v for k, v in perfs.items() if not k.startswith("hour:")),
            "per_platform": perfs,
        }
        c.execute(
            "INSERT INTO clip_feature VALUES (%s,%s) ON CONFLICT (clip_version_id) DO UPDATE SET features=EXCLUDED.features",
            (cv["id"], db.j(f)),
        )
        n += 1
    return n


# ---------------- bandits ----------------
def bandit_update(c: psycopg.Connection, experiment: str, arm: str, success: bool) -> None:
    c.execute(
        """INSERT INTO bandit_arm(experiment,arm,alpha,beta,pulls) VALUES (%s,%s,%s,%s,1)
                 ON CONFLICT (experiment,arm) DO UPDATE SET alpha=bandit_arm.alpha+%s, beta=bandit_arm.beta+%s, pulls=bandit_arm.pulls+1""",
        (experiment, arm, 1 + success, 1 + (not success), int(success), int(not success)),
    )


def bandit_shares(
    c: psycopg.Connection,
    experiment: str,
    arms: dict[str, float],
    draws: int = 4000,
    floor: float = 0.05,
    seed: int = 0,
) -> dict[str, float]:
    """Thompson sampling: share of draws each arm wins (prior = starting mix as pseudo-counts), with a floor so
    every arm keeps learning."""
    rng = np.random.default_rng(seed)
    rows = {r["arm"]: r for r in db.all_(c, "SELECT * FROM bandit_arm WHERE experiment=%s", experiment)}
    names = list(arms)
    a = np.array([rows[n]["alpha"] if n in rows else 1 + 2 * arms[n] for n in names])
    b = np.array([rows[n]["beta"] if n in rows else 1 + 2 * (1 - arms[n]) for n in names])
    wins = (
        np.bincount(
            np.argmax(rng.beta(a[:, None], b[:, None], (len(names), draws)), axis=0), minlength=len(names)
        )
        / draws
    )
    sh = np.maximum(wins, floor)
    sh = sh / sh.sum()
    return {n: round(float(s), 4) for n, s in zip(names, sh, strict=True)}


def update_bandits(c: psycopg.Connection, since: dt.datetime) -> dict:
    """Reward = clip beat its account median (performance > 0 in log space). Per channel+platform, per experiment."""
    n = 0
    for r in db.all_(
        c,
        """SELECT cf.features, p.platform, p.id post_id FROM clip_feature cf JOIN post p ON p.clip_version_id=cf.clip_version_id
                           WHERE p.status='live' AND p.posted_at >= %s AND NOT EXISTS (SELECT 1 FROM audit_log l WHERE l.action='bandit_counted'
                           AND l.subject=p.id::text)""",
        since,
    ):
        f = r["features"]
        perf = (f.get("per_platform") or {}).get(r["platform"])
        if perf is None:
            continue
        for exp, arm in (
            ("layout", f.get("layout")),
            ("text_mode", f.get("text_mode")),
            ("text_style", f.get("text_style")),
            ("headline_case", f.get("headline_case")),
            ("hook", f.get("hook_pattern")),
            ("style", f.get("style_profile")),
        ):
            if arm:
                bandit_update(c, f"{exp}:{f.get('channel_id')}:{r['platform']}", str(arm), perf > 0)
        db.audit(c, "bandit_counted", str(r["post_id"]))
        n += 1
    return {"rewards": n}


# ---------------- refits (held-out check) ----------------
def ship(
    c: psycopg.Connection,
    component: str,
    values: dict,
    holdout: float,
    current: float | None,
    explanation: str,
) -> bool:
    """New weights go live only if they beat the current setting on the held-out week (and learning isn't frozen)."""
    if db.get_flag(c, "learning_frozen"):
        return False
    ver = (db.scalar(c, "SELECT max(version) FROM weights WHERE component=%s", component) or 0) + 1
    better = current is None or holdout > current
    c.execute(
        """INSERT INTO weights(component,version,"values",holdout_score,active,explanation) VALUES (%s,%s,%s,%s,false,%s)""",
        (
            component,
            ver,
            db.j(values),
            holdout,
            explanation + ("" if better else f" — kept old ({current:.3f} >= {holdout:.3f})"),
        ),
    )
    if better:
        c.execute("UPDATE weights SET active=(version=%s) WHERE component=%s", (ver, component))
    return better


def refit_layouts(c: psycopg.Connection, default_arms: dict[str, float], exp: str = "layout") -> dict:
    """Render-time A/B arms per language channel (pooled over platforms): layout, or a caption text arm
    (text_mode / text_style / headline_case, doc 11)."""
    out = {}
    for ch in db.all_(c, "SELECT id FROM channel"):
        exps = db.all_(
            c, "SELECT DISTINCT experiment FROM bandit_arm WHERE experiment LIKE %s", f"{exp}:{ch['id']}:%"
        )
        if not exps:
            continue
        pooled: dict[str, list[float]] = {}
        for e in exps:
            for k, v in bandit_shares(c, e["experiment"], default_arms).items():
                pooled.setdefault(k, []).append(v)
        sh = {k: round(statistics.fmean(v), 4) for k, v in pooled.items()}
        cur = db.one(c, """SELECT "values" FROM weights WHERE component=%s AND active""", f"{exp}:{ch['id']}")
        best = max(sh, key=sh.get)
        if not db.get_flag(c, "learning_frozen"):
            ver = (
                db.scalar(c, "SELECT max(version) FROM weights WHERE component=%s", f"{exp}:{ch['id']}") or 0
            ) + 1
            c.execute(
                """INSERT INTO weights(component,version,"values",active,explanation) VALUES (%s,%s,%s,true,%s)""",
                (
                    f"{exp}:{ch['id']}",
                    ver,
                    db.j(sh),
                    f"Thompson sampling favours '{best}' ({sh[best]:.0%} of renders)",
                ),
            )
            c.execute("UPDATE weights SET active=(version=%s) WHERE component=%s", (ver, f"{exp}:{ch['id']}"))
        out[ch["id"]] = {"shares": sh, "previous": cur["values"] if cur else None}
    return out


def refit_score_floor(c: psycopg.Connection) -> dict:
    """Raise a channel's floor if its low-score clips underperform; lower it if the queue ran dry."""
    out = {}
    for ch in db.all_(c, "SELECT * FROM channel"):
        rows = db.all_(
            c,
            """SELECT (cf.features->>'moment_score')::float s, (cf.features->>'performance')::float p FROM clip_feature cf
                             WHERE (cf.features->>'channel_id')::int=%s""",
            ch["id"],
        )
        floor = float(ch["score_floor"])
        if len(rows) >= 20:
            q = np.quantile([r["s"] for r in rows], 0.25)
            low = [r["p"] for r in rows if r["s"] <= q]
            if low and statistics.fmean(low) < -0.3:
                floor = min(0.9, max(floor, float(q)) + 0.02)
        queued = db.scalar(
            c,
            """SELECT count(*) FROM clip_version cv JOIN clip cl ON cl.id=cv.clip_id WHERE cl.channel_id=%s
                                 AND cv.status IN ('queued','scheduled')""",
            ch["id"],
        )
        if queued == 0 and len(rows) >= 5:
            floor = max(0.0, floor - 0.03)
        if abs(floor - ch["score_floor"]) > 1e-9 and not db.get_flag(c, "learning_frozen"):
            c.execute("UPDATE channel SET score_floor=%s WHERE id=%s", (floor, ch["id"]))
            db.audit(c, "score_floor", ch["key"], {"from": ch["score_floor"], "to": floor})
        out[ch["key"]] = floor
    return out


def refit_posting_times(c: psycopg.Connection, min_posts: int = 30) -> dict:
    """Shift each channel's slots toward its best hours (same number of slots)."""
    out = {}
    for ch in db.all_(c, "SELECT * FROM channel"):
        rows = db.all_(
            c,
            """SELECT EXTRACT(hour FROM p.posted_at AT TIME ZONE %s)::int h, (cf.features->'per_platform'->>p.platform)::float perf
                             FROM post p JOIN clip_feature cf ON cf.clip_version_id=p.clip_version_id JOIN account a ON a.id=p.account_id
                             WHERE a.channel_id=%s AND p.status='live'""",
            ch["time_zone"],
            ch["id"],
        )
        rows = [r for r in rows if r["perf"] is not None]
        if len(rows) < min_posts:
            continue
        by_h: dict[int, list[float]] = {}
        for r in rows:
            by_h.setdefault(r["h"], []).append(r["perf"])
        slots = (ch["config"] or {}).get("posting_slots", [])
        best = sorted(by_h, key=lambda h: -statistics.fmean(by_h[h]))[: len(slots)]
        new = [f"{h:02d}:{(17 + 7 * i) % 60:02d}" for i, h in enumerate(sorted(best))]
        if new and not db.get_flag(c, "learning_frozen"):
            c.execute(
                "UPDATE channel SET config = config || %s WHERE id=%s",
                (db.j({"posting_slots": new}), ch["id"]),
            )
        out[ch["key"]] = new
    return out


def refit_creators(c: psycopg.Connection, holdout_days: int = 7) -> dict | None:
    """Radar weights by regression of creator percentiles on our clips' performance; held-out week decides."""
    rows = db.all_(
        c,
        """SELECT cs.percentiles, (cf.features->>'performance')::float perf, cl.created_at FROM clip_feature cf
                         JOIN clip_version cv ON cv.id=cf.clip_version_id JOIN clip cl ON cl.id=cv.clip_id
                         JOIN creator_score cs ON cs.creator_id=cl.creator_id AND cs.date=cl.created_at::date""",
    )
    if len(rows) < 40:
        return None
    from scipy.stats import spearmanr

    from clipping.core import config
    from clipping.radar.scoring import SIGNALS

    cut = max(r["created_at"] for r in rows) - dt.timedelta(days=holdout_days)
    tr = [r for r in rows if r["created_at"] < cut]
    ho = [r for r in rows if r["created_at"] >= cut]
    if len(tr) < 20 or len(ho) < 10:
        return None
    X = np.array([[r["percentiles"].get(s, 0.5) for s in SIGNALS] for r in tr])
    y = np.array([r["perf"] for r in tr])
    coef, *_ = np.linalg.lstsq(np.c_[X, np.ones(len(X))], y, rcond=None)
    w = np.clip(coef[:-1], 0, None)
    if w.sum() <= 0:
        return None
    w = w / w.sum()
    new = {s: round(float(v), 4) for s, v in zip(SIGNALS, w, strict=True)}
    cur_w = (db.one(c, """SELECT "values" FROM weights WHERE component='radar' AND active""") or {}).get(
        "values"
    ) or config.settings()["radar"]["weights"]

    def score(wd, r):
        return sum(wd.get(s, 0) * r["percentiles"].get(s, 0.5) for s in SIGNALS)

    ho_new = spearmanr([score(new, r) for r in ho], [r["perf"] for r in ho]).statistic
    ho_cur = spearmanr([score(cur_w, r) for r in ho], [r["perf"] for r in ho]).statistic
    top = max(new, key=new.get)
    shipped = ship(
        c,
        "radar",
        new,
        float(ho_new),
        float(ho_cur),
        f"Creator weights refit: '{top.replace('_', ' ')}' now matters most",
    )
    return {"weights": new, "holdout_new": ho_new, "holdout_current": ho_cur, "shipped": shipped}


# ---------------- monetization progress ----------------
def monetization(c: psycopg.Connection, now: dt.datetime | None = None) -> list[dict]:
    now = now or dt.datetime.now(UTC)
    out = []
    for a in db.all_(
        c,
        "SELECT a.*, ch.key FROM account a JOIN channel ch ON ch.id=a.channel_id WHERE a.platform IN ('youtube','tiktok')",
    ):
        days = 90 if a["platform"] == "youtube" else 30
        latest = db.all_(
            c,
            """SELECT DISTINCT ON (s.post_id) s.views, p.posted_at, cv.duration_s FROM post_stat s JOIN post p ON p.id=s.post_id
                               JOIN clip_version cv ON cv.id=p.clip_version_id WHERE p.account_id=%s AND p.posted_at > %s
                               ORDER BY s.post_id, s.sampled_at DESC""",
            a["id"],
            now - dt.timedelta(days=days),
        )
        if a["platform"] == "tiktok":
            latest = [r for r in latest if (r["duration_s"] or 0) > 60]  # only 1-minute-plus videos earn
        views = sum(int(r["views"] or 0) for r in latest)
        target = YT_THRESHOLD if a["platform"] == "youtube" else TT_VIEWS
        if (
            a["platform"] == "youtube"
            and now.date() >= dt.date(2027, 2, 1)
            and a["review_status"] != "monetized"
        ):
            target = YT_THRESHOLD_NEW_2027
        span = max(
            1.0, min(days, (now - min((r["posted_at"] for r in latest), default=now)).total_seconds() / 86400)
        )
        pace = views / span
        eta = (
            None
            if pace <= 0 or views >= target
            else (now + dt.timedelta(days=(target - views) / pace)).date().isoformat()
        )
        out.append(
            {
                "account": a["id"],
                "channel": a["key"],
                "platform": a["platform"],
                "views": views,
                "target": target,
                "progress": round(views / target, 4),
                "projected": eta,
            }
        )
    return out


# ---------------- weekly ----------------
def weekly(
    c: psycopg.Connection, week: dt.date | None = None, default_layout_arms: dict | None = None
) -> dict:
    from clipping.style import profiles

    week = week or (dt.date.today() - dt.timedelta(days=dt.date.today().weekday()))
    since = dt.datetime.combine(week - dt.timedelta(days=7), dt.time(), UTC)
    update_features(c)
    upd = update_bandits(c, since)
    arms = default_layout_arms or profiles.layout_arms(profiles.load("house"))
    lay = refit_layouts(c, arms)
    house = profiles.load("house")
    text = {k: refit_layouts(c, profiles.text_arms(house, k), k) for k in profiles.TEXT_ARMS}
    floors = refit_score_floor(c)
    slots = refit_posting_times(c)
    cr = refit_creators(c)
    top = db.all_(
        c,
        """SELECT cf.clip_version_id, (cf.features->>'performance')::float perf, cl.packaging->>'hook_text' hook
                        FROM clip_feature cf JOIN clip_version cv ON cv.id=cf.clip_version_id JOIN clip cl ON cl.id=cv.clip_id
                        ORDER BY 2 DESC NULLS LAST LIMIT 10""",
    )
    risk = db.all_(
        c,
        "SELECT id, platform, health FROM account WHERE (health->>'restricted')::boolean OR (health->>'claims_7d')::int >= 2",
    )
    changes = db.all_(
        c, "SELECT component, explanation FROM weights WHERE fitted_at >= %s ORDER BY fitted_at", since
    )
    mon = monetization(c)
    best_creators = db.all_(
        c,
        """SELECT cr.handle, avg((cf.features->>'performance')::float) p FROM clip_feature cf
                                  JOIN creator cr ON cr.id=(cf.features->>'creator_id')::int GROUP BY cr.handle ORDER BY 2 DESC LIMIT 5""",
    )
    lines = [f"Week of {week}", "", "Top clips:"] + [
        f"  {i + 1}. {t['hook']} (performance {t['perf']:+.2f})" for i, t in enumerate(top)
    ]
    lines += ["", "What changed and why:"] + [f"  - {ch['explanation']}" for ch in changes] or ["  - nothing"]
    lines += ["", "Accounts at risk:"] + (
        [f"  - account {r['id']} ({r['platform']}): {r['health']}" for r in risk] or ["  - none"]
    )
    lines += ["", "Monetization:"] + [
        f"  - {m['channel']} {m['platform']}: {m['views']:,}/{m['target']:,} ({m['progress']:.1%})"
        + (f", on pace for {m['projected']}" if m["projected"] else "")
        for m in mon
    ]
    lines += ["", "Best creators this week:"] + [f"  - {b['handle']} ({b['p']:+.2f})" for b in best_creators]
    body = {
        "text": "\n".join(lines),
        "top": top,
        "changes": changes,
        "risk": [dict(r) for r in risk],
        "monetization": mon,
        "layout": {str(k): v for k, v in lay.items()},
        "text_arms": {kind: {str(k): v for k, v in r.items()} for kind, r in text.items()},
        "floors": floors,
        "slots": slots,
        "creators": cr,
        "bandit_rewards": upd,
    }
    c.execute(
        "INSERT INTO digest(week,body) VALUES (%s,%s) ON CONFLICT (week) DO UPDATE SET body=EXCLUDED.body",
        (week, db.j(body)),
    )
    return body
