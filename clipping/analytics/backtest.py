"""Stage backtest 22: four simulated weeks whose performance follows hidden true effects. Stats are pulled on
schedule; the layout bandit moves volume to the truly better arm; a worse refit is refused on the held-out week;
every change is explained; the digest is produced; clip score correlates with performance."""

from __future__ import annotations

import datetime as dt

import numpy as np
from scipy.stats import spearmanr

from clipping.analytics import loop
from clipping.core import db
from clipping.eval.harness import Example, StageResult, scratch_db, stage

UTC = dt.UTC
TRUE_LAYOUT = {"stacked": 0.35, "full": -0.25, "small_cam": -0.05}
TRUE_HOOK = {"reaction": 0.15, "question": 0.0, "number": -0.1, "creator_first": 0.05}


class StatsAdapter:
    """Returns views from the hidden model for the post's age."""

    def __init__(self, truth: dict, now_ref: list):
        self.truth, self.now = truth, now_ref

    def stats(self, pid, acc):
        t = self.truth[pid]
        age_h = max(1.0, (self.now[0] - t["posted"]).total_seconds() / 3600)
        return {"views": int(t["v48"] * np.log1p(age_h) / np.log1p(48)), "likes": 10, "retention": t["ret"]}


@stage("22", "Analytics & Feedback Loop")
def run() -> StageResult:
    rng = np.random.default_rng(22)
    ex = []
    with scratch_db() as c:
        ch = db.scalar(
            c,
            "INSERT INTO channel(key,language,time_zone,score_floor,config) VALUES ('gta6-en','en','UTC',0.2,%s) RETURNING id",
            db.j({"posting_slots": ["09:00", "12:00", "15:00", "18:00", "21:00"]}),
        )
        acc = db.scalar(
            c,
            "INSERT INTO account(channel_id,platform,status,platform_account_id) VALUES (%s,'youtube','connected','x') RETURNING id",
            ch,
        )
        cr = db.scalar(
            c, "INSERT INTO creator(platform,platform_id,handle) VALUES ('twitch','1','c') RETURNING id"
        )
        st = db.scalar(
            c,
            "INSERT INTO stream(creator_id,platform_stream_id,started_at) VALUES (%s,'s',now()) RETURNING id",
            cr,
        )
        truth, now_ref = {}, [dt.datetime(2027, 1, 4, tzinfo=UTC)]
        ad = {"youtube": StatsAdapter(truth, now_ref)}
        start = now_ref[0]
        share_hist, due_total, missed_total, scores, perfs = [], 0, 0, [], []
        arms = {"stacked": 0.6, "full": 0.25, "small_cam": 0.15}
        for week in range(4):
            cur = loop.bandit_shares(c, f"layout:{ch}:youtube", arms, seed=week) if week else arms
            share_hist.append(cur)
            for k in range(70):  # 10 posts/day
                posted = start + dt.timedelta(days=week * 7 + k // 10, hours=9 + (k % 10))
                layout = rng.choice(list(cur), p=np.array(list(cur.values())) / sum(cur.values()))
                hook = rng.choice(list(TRUE_HOOK))
                score = float(rng.uniform(0.3, 1.0))
                eff = (
                    TRUE_LAYOUT[layout] + TRUE_HOOK[hook] + 0.8 * (score - 0.65) + float(rng.normal(0, 0.35))
                )
                v48 = 5000 * float(np.exp(eff))
                mid = db.scalar(
                    c,
                    "INSERT INTO moment(stream_id,start_s,end_s,peak_s,score) VALUES (%s,0,75,45,%s) RETURNING id",
                    st,
                    score,
                )
                clip = db.scalar(
                    c,
                    """INSERT INTO clip(moment_id,channel_id,creator_id,packaging,crop_plan,style_profile,edit_plan)
                                       VALUES (%s,%s,%s,%s,%s,'house',%s) RETURNING id""",
                    mid,
                    ch,
                    cr,
                    db.j(
                        {
                            "features": {"hook_pattern": hook, "title_style": 0},
                            "hook_text": f"clip {week}-{k}",
                        }
                    ),
                    db.j({"layout": str(layout)}),
                    db.j({"versions": {"short": {"payoff_kind": "crash", "hook": {}}}}),
                )
                cv = db.scalar(
                    c,
                    "INSERT INTO clip_version(clip_id,version_type,duration_s,status) VALUES (%s,'short',30,'scheduled') RETURNING id",
                    clip,
                )
                pid = db.scalar(
                    c,
                    """INSERT INTO post(clip_version_id,account_id,platform,status,scheduled_at,posted_at,platform_post_id)
                                      VALUES (%s,%s,'youtube','live',%s,%s,%s) RETURNING id""",
                    cv,
                    acc,
                    posted,
                    posted,
                    f"v{cv}",
                )
                truth[f"v{cv}"] = {
                    "posted": posted,
                    "v48": v48,
                    "ret": float(np.clip(0.45 + 0.1 * eff, 0.05, 0.95)),
                }
                scores.append(score)
                perfs.append((pid, eff))
            # hourly pulls through the week (+2 days so every post reaches 48 h)
            for h in range(0, 7 * 24 + 48, 1):
                now_ref[0] = start + dt.timedelta(days=week * 7, hours=h)
                due_total += len(loop.due_posts(c, now_ref[0]))
                res = loop.pull_stats(c, ad, now_ref[0])
                missed_total += res["missed"]
            body = loop.weekly(c, (start + dt.timedelta(days=week * 7 + 7)).date(), default_layout_arms=arms)
        final = loop.bandit_shares(c, f"layout:{ch}:youtube", arms, seed=99)
        perf_actual = [loop.performance(c, pid) for pid, _ in perfs]
        rho = spearmanr(scores, perf_actual).statistic
        # a deliberately worse refit must be refused on the held-out check
        shipped_bad = loop.ship(
            c,
            "heatmap",
            {"chat_velocity": 0.0},
            holdout=0.10,
            current=0.85,
            explanation="deliberately worse weights",
        )
        explained = db.scalar(
            c, "SELECT bool_and(explanation IS NOT NULL AND explanation <> '') FROM weights"
        )
        digest_ok = bool(db.one(c, "SELECT 1 FROM digest")) and "Top clips" in body["text"]
        layout_w = db.one(c, """SELECT "values" FROM weights WHERE component=%s AND active""", f"layout:{ch}")
    learned = final["stacked"] > 0.6 and final["stacked"] == max(final.values())
    if not learned:
        ex.append(Example("layout", "final_share_stacked", final["stacked"], str(share_hist)))
    return StageResult(
        {
            "stats_missing_share": missed_total / max(due_total, 1),
            "bandit_finds_best_layout": 1.0 if learned else 0.0,
            "worse_refit_refused": 0.0 if shipped_bad else 1.0,
            "changes_explained": 1.0 if explained else 0.0,
            "digest_produced": 1.0 if digest_ok else 0.0,
            "score_performance_spearman": float(rho),
            "layout_weights_written": 1.0 if layout_w else 0.0,
        },
        ex,
        "simulated@v1",
        {"final_layout_shares": final, "history": share_hist},
    )
