"""Stage backtest 28: weekly table with every signal; a challenger winning 4 straight weeks (post-release) triggers
a recommendation and provisioning prep, a broken streak doesn't; shares follow scores with a floor; swaps stay
frozen for 4 weeks after release."""

from __future__ import annotations

import datetime as dt

import numpy as np

from clipping.core import config, db
from clipping.eval.harness import Example, StageResult, scratch_db, stage
from clipping.languages import market

UTC = dt.UTC
LAUNCH = ["en", "es", "pt", "ar", "fr", "ru", "de", "ja", "tr", "vi"]


def seed_week(c, week: dt.date, pl_hours: float, base: dict[str, float]):
    ts = dt.datetime.combine(week, dt.time(12), UTC)
    for code, h in {**base, "pl": pl_hours}.items():
        viewers = int(h * 60 / market.SAMPLE_MIN)  # one sample row carrying the week's hours
        c.execute(
            "INSERT INTO language_sample(code,platform,ts,viewers,channels) VALUES (%s,'twitch',%s,%s,%s)",
            (code, ts, viewers, 5),
        )
        c.execute(
            "INSERT INTO language_sample(code,platform,ts,viewers,channels) VALUES (%s,'youtube_shorts',%s,0,%s)",
            (code, ts, 40 if code in ("en", "es") else 6),
        )


@stage("28", "Language Market Ranking")
def run() -> StageResult:
    ex = []
    pl_file = config.CONFIG / "channels" / "pl.yaml"
    existed = pl_file.exists()
    rng = np.random.default_rng(28)
    base = {
        c_: float(h)
        for c_, h in zip(LAUNCH, [9000, 6000, 5000, 3000, 2500, 2400, 2200, 1800, 1500, 300], strict=True)
    }
    recs_by_week: list = []
    try:
        with scratch_db() as c:
            start = dt.date(2026, 12, 21)  # after the 4-week post-release freeze
            plan = [4000, 4200, 4100, 200, 4300, 4400, 4500, 4600]  # week 3 breaks the streak
            for k, ph in enumerate(plan):
                wk = start + dt.timedelta(weeks=k)
                seed_week(c, wk, ph, {c_: v * float(rng.uniform(0.95, 1.05)) for c_, v in base.items()})
                res = market.weekly(c, wk)
                recs_by_week.append([r["code"] for r in res["recommendations"]])
            fired_at = next((k for k, r in enumerate(recs_by_week) if "pl" in r), None)
            streak_ok = fired_at == 7  # needs weeks 4, 5, 6, 7 in a row
            if not streak_ok:
                ex.append(
                    Example(
                        "pl", "fired_at_week", fired_at if fired_at is not None else -1, str(recs_by_week)
                    )
                )
            act = db.one(c, "SELECT * FROM language_action WHERE code='pl'")
            prepped = (
                pl_file.exists() and db.scalar(c, "SELECT count(*) FROM account_slot WHERE code='pl'") == 6
            )
            replaces_lowest = act is not None and act["replaces"] == "vi"
            table = db.all_(c, "SELECT * FROM language_week WHERE week=%s", start + dt.timedelta(weeks=7))
            complete = len(table) >= 11 and all(
                r["score"] is not None and r["audience_hours"] is not None and r["value"] is not None
                for r in table
            )
            sh = db.get_flag(c, "language_shares")
            scores = {r["code"]: r["score"] for r in table}
            floor_ok = (
                abs(sum(sh.values()) - 1) < 1e-6 and min(sh.values()) >= market.cfg()["share_floor"] - 1e-9
            )
            order_ok = all(sh[a] >= sh[b] - 1e-9 for a in sh for b in sh if scores[a] > scores[b])
        if pl_file.exists() and not existed:
            pl_file.unlink()
        with scratch_db() as c:  # frozen during the first 4 weeks after release
            early = dt.date(2026, 11, 23)
            for k in range(4):
                seed_week(c, early + dt.timedelta(weeks=k), 9999, base)
                market.weekly(c, early + dt.timedelta(weeks=k))
            frozen_ok = db.scalar(
                c, "SELECT count(*) FROM language_action"
            ) == 0 and not market.swaps_enabled(early + dt.timedelta(weeks=3))
    finally:
        if not existed and pl_file.exists():
            pl_file.unlink()
    return StageResult(
        {
            "weekly_table_complete": 1.0 if complete else 0.0,
            "four_week_streak_required": 1.0 if streak_ok else 0.0,
            "recommendation_replaces_lowest": 1.0 if replaces_lowest else 0.0,
            "provisioning_prepped": 1.0 if prepped else 0.0,
            "shares_follow_scores": 1.0 if floor_ok and order_ok else 0.0,
            "frozen_after_release": 1.0 if frozen_ok else 0.0,
        },
        ex,
        "synthetic@v1",
        {"recs_by_week": recs_by_week},
    )
