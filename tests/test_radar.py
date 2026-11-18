import datetime as dt

from clipping.core import db
from clipping.radar import scoring, service
from clipping.radar.sources import FakeLiveSource, LiveStream


def _stream(uid, viewers, lang="en", game="g1", sid=None, title="gta 6 chaos"):
    return LiveStream("twitch", uid, f"user{uid}", viewers, lang, "2026-11-18T10:00:00Z", title, game, sid or f"s{uid}")


def test_percentile_ranks_ties_and_single():
    assert scoring.percentile_ranks({1: 5}) == {1: 0.5}
    p = scoring.percentile_ranks({1: 1, 2: 2, 3: 2, 4: 9})
    assert p[1] == 0 and p[4] == 1 and p[2] == p[3]


def test_missing_signal_renormalizes():
    w = {"live_audience": 0.5, "clip_rate": 0.5}
    kick = scoring.CreatorInput(1, "en", [(1, True, 100)], has_clip_data=False)
    tw = scoring.CreatorInput(2, "en", [(1, True, 50)], clips=[(1, 10)])
    out = {s.creator_id: s for s in scoring.score_language([kick, tw], w)}
    assert out[1].signals["clip_rate"] is None
    assert out[1].score == 1.0  # only live audience counts, and it's the top
    assert "clip_rate" in out[2].percentiles


def test_viewbot_flag_downweights():
    w = {"live_audience": 0.9, "clip_rate": 0.1}
    a = scoring.CreatorInput(1, "en", [(1, True, 10000)], clips=[(1, 1)], chat_per_viewer=0.001)
    b = scoring.CreatorInput(2, "en", [(1, True, 500)], clips=[(1, 30)], chat_per_viewer=0.05)
    c = scoring.CreatorInput(3, "en", [(1, True, 400)], clips=[(1, 20)], chat_per_viewer=0.04)
    out = {s.creator_id: s for s in scoring.score_language([a, b, c], w)}
    assert out[1].flags.get("viewbot_suspect")
    assert out[1].score < out[2].score


def test_select_exploit_explore_hysteresis_blocklist():
    sc = [scoring.Scored(i, "en", {"growth": g}, {}, 1 - i / 10, rank=i) for i, g in
          [(1, 0.0), (2, 0.0), (3, 0.0), (4, 0.0), (5, 0.1), (6, 2.0), (7, 0.5)]]
    chosen = scoring.select(sc, 5, blocked={2})
    ids = [s.creator_id for s in chosen]
    assert 2 not in ids and len(ids) == 5
    assert 6 in ids  # highest growth outside top group
    # hysteresis: previously-selected creator 7 keeps slot on first day below cutoff
    sc2 = [scoring.Scored(i, "en", {"growth": 0.0}, {}, 1 - i / 10, rank=i) for i in range(1, 8)]
    chosen2 = scoring.select(sc2, 3, previous={7: {"selected": True, "below_cutoff_days": 0}})
    assert 7 in [s.creator_id for s in chosen2]
    sc3 = [scoring.Scored(i, "en", {"growth": 0.0}, {}, 1 - i / 10, rank=i) for i in range(1, 8)]
    chosen3 = scoring.select(sc3, 3, previous={7: {"selected": True, "below_cutoff_days": 1}})
    assert 7 not in [s.creator_id for s in chosen3]


def test_allocate_slots():
    a = scoring.allocate_slots(10, {"en": 900, "es": 100, "ja": 0})
    assert sum(a.values()) == 10 and all(v >= 1 for v in a.values()) and a["en"] > a["es"]


def test_poll_lists_every_live_creator_and_language_samples(conn):
    src = FakeLiveSource("twitch", streams=[_stream("1", 5000), _stream("2", 300, "es"), _stream("3", 10, "", title="jugando en directo")])
    kick = FakeLiveSource("kick", game_id="k1", streams=[LiveStream("kick", "9", "kicker", 800, "tr", "", "x", "k1", "ks9")])
    seen = service.poll_live(conn, [src, kick], {"twitch": "g1", "kick": "k1"})
    assert len(seen) == 4
    langs = {r["handle"]: r["language"] for r in db.all_(conn, "SELECT handle, language FROM creator")}
    assert langs["user3"] == "es"  # title-language fallback
    assert db.scalar(conn, "SELECT count(*) FROM language_sample") == 3


def test_daily_rank_reproducible_and_recorder_start(conn):
    now = dt.datetime(2026, 11, 18, 12, tzinfo=dt.UTC)
    src = FakeLiveSource("twitch", streams=[_stream(str(i), 100 * i) for i in range(1, 8)])
    for k in range(12):
        service.poll_live(conn, [src], {"twitch": "g1"}, now - dt.timedelta(minutes=10 * k))
    r1 = service.daily_rank(conn, now.date(), slots=3, languages=["en"])
    order1 = [s.creator_id for s in r1["en"]]
    r2 = service.daily_rank(conn, now.date(), slots=3, languages=["en"])
    assert order1 == [s.creator_id for s in r2["en"]]
    assert db.scalar(conn, "SELECT count(*) FROM creator_score WHERE selected") == 3
    assert db.scalar(conn, "SELECT count(*) FROM creator_score WHERE selection_reason IS NOT NULL") >= 3
    service.poll_live(conn, [src], {"twitch": "g1"}, now)
    assert db.scalar(conn, "SELECT count(*) FROM job WHERE type='record_start'") == 3


def test_api_outage_skips_not_zero(conn):
    class Broken(FakeLiveSource):
        def live_streams(self, game_id):
            raise RuntimeError("503")

    service.poll_live(conn, [Broken("twitch")], {"twitch": "g1"})
    assert db.scalar(conn, "SELECT count(*) FROM creator_stat") == 0
    assert db.scalar(conn, "SELECT count(*) FROM alert WHERE kind='radar_source_down'") == 1
