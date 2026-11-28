import datetime as dt

from clipping.core import db
from clipping.ingest import clips
from clipping.radar.sources import FakeLiveSource

UTC = dt.UTC
NOW = dt.datetime(2026, 11, 18, 12, tzinfo=UTC)


def _api():
    api = FakeLiveSource("twitch")
    api.clip_list = [
        {
            "id": "c1",
            "broadcaster_id": "b1",
            "video_id": "v1",
            "vod_offset": 600,
            "duration": 30,
            "view_count": 900,
            "created_at": "2026-11-18T11:00:00Z",
            "title": "lol",
            "language": "en",
        },
        {
            "id": "c2",
            "broadcaster_id": "b1",
            "video_id": "",
            "vod_offset": None,
            "duration": 20,
            "view_count": 50,
            "created_at": "2026-11-18T11:30:00Z",
            "title": "old",
            "language": "en",
        },
    ]
    api.video_list = [{"id": "v1", "created_at": "2026-11-18T10:00:00Z", "duration": "2h3m4s"}]
    return api


def test_discover_map_and_link_to_recording(conn):
    cr = db.scalar(
        conn, "INSERT INTO creator(platform,platform_id,handle) VALUES ('twitch','b1','b') RETURNING id"
    )
    sid = db.scalar(
        conn,
        "INSERT INTO stream(creator_id,platform_stream_id,started_at) VALUES (%s,'s',%s) RETURNING id",
        cr,
        dt.datetime(2026, 11, 18, 10, 0, 5, tzinfo=UTC),
    )
    api = _api()
    assert clips.discover(conn, api, "g1", now=NOW) == 2
    assert clips.map_to_utc(conn, api) == 1
    r = db.one(conn, "SELECT * FROM platform_clip WHERE clip_id='c1'")
    assert r["abs_utc_start"] == dt.datetime(2026, 11, 18, 10, 10, tzinfo=UTC) and r["stream_id"] == sid
    assert db.one(conn, "SELECT trend_only FROM platform_clip WHERE clip_id='c2'")["trend_only"]
    assert db.scalar(conn, "SELECT count(*) FROM job WHERE type='heatmap_rescore'") == 1
    assert db.scalar(conn, "SELECT duration_s FROM vod WHERE video_id='v1'") == 7384


def test_view_history_and_velocity(conn):
    api = _api()
    clips.discover(conn, api, "g1", now=NOW)
    api.clip_list[0]["view_count"] = 1500
    clips.discover(conn, api, "g1", now=NOW + dt.timedelta(hours=1))
    h = db.scalar(conn, "SELECT views_history FROM platform_clip WHERE clip_id='c1'")
    assert len(h) == 2 and clips.view_velocity(h) == 600


def test_unrecorded_clip_requests_vod_range(conn):
    db.scalar(
        conn, "INSERT INTO creator(platform,platform_id,handle) VALUES ('twitch','b1','b') RETURNING id"
    )
    api = _api()
    clips.discover(conn, api, "g1", now=NOW)
    clips.map_to_utc(conn, api)
    row = db.scalar(conn, "SELECT id FROM platform_clip WHERE clip_id='c1'")
    req = clips.needs_vod(conn, row)
    assert req["video_id"] == "v1" and req["start_s"] == 600 - 45 - 30
    cmd = clips.vod_range_command("v1", req["start_s"], req["duration_s"], "/tmp/x.ts")
    assert "--hls-start-offset 00:08:45" in cmd and "videos/v1" in cmd


def test_no_download_without_authorization():
    class Api:
        def get(self, *a, **k):
            raise RuntimeError("403")

    assert clips.try_download(Api(), "c1", "b1") is None
    assert clips.try_download(object(), "c1", "b1") is None


def test_trending_top_share(conn):
    api = FakeLiveSource("twitch")
    api.clip_list = [
        {
            "id": f"c{i}",
            "broadcaster_id": "x",
            "view_count": i,
            "created_at": "2026-11-18T01:00:00Z",
            "vod_offset": None,
        }
        for i in range(30)
    ]
    clips.discover(conn, api, "g", now=NOW)
    t = clips.trending(conn, dt.date(2026, 11, 18))
    assert [r["view_count"] for r in t] == [29, 28, 27]
