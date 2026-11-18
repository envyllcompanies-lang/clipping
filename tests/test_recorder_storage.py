import datetime as dt
import os
import time

from clipping.core import db, media
from clipping.eval.fixtures import make_segments, realtime_command
from clipping.recorder import recorder
from clipping.storage import files, guard, refcount

UTC = dt.UTC


def _creator(conn, handle="streamer"):
    return db.one(
        conn,
        "INSERT INTO creator(platform,platform_id,handle,language) VALUES ('twitch','1',%s,'en') RETURNING *",
        handle,
    )


def _stream_with_segments(conn, minutes=6, base=None):
    cr = _creator(conn)
    base = base or int(time.time()) - minutes * 60
    sid = recorder.start_stream(conn, cr["id"], "ps1", dt.datetime.fromtimestamp(base, UTC))
    d = recorder.segment_dir(cr["handle"], sid)
    make_segments(d, minutes, base)
    recorder.register_segments(conn, sid, d, include_last=True)
    return cr, sid, base


def test_record_command_shape(tmp_data):
    cmd = recorder.record_command("https://www.twitch.tv/x", tmp_data, 60)
    assert "streamlink" in cmd and "-c copy" in cmd and "-segment_time 60" in cmd and "%s.ts" in cmd


def test_worker_records_live_pipeline_and_ends(conn, tmp_data):
    cr = _creator(conn)
    sid = recorder.start_stream(conn, cr["id"], "live1")
    w = recorder.Worker(conn, dict(cr), sid, command="true")
    w.command = realtime_command(5, w.dir, 2)
    t0 = time.time()
    w.run(is_live=lambda: False, poll_s=0.5)
    assert time.time() - t0 < 15
    n = db.scalar(conn, "SELECT count(*) FROM segment WHERE stream_id=%s", sid)
    assert n >= 2
    assert db.scalar(conn, "SELECT status FROM stream WHERE id=%s", sid) == "ended"
    assert db.scalar(conn, "SELECT count(*) FROM recorder_lock") == 0


def test_one_worker_per_creator(conn, tmp_data):
    cr = _creator(conn)
    assert recorder.acquire_lock(conn, cr["id"], "w1", None)
    assert not recorder.acquire_lock(conn, cr["id"], "w2", None)
    assert recorder.acquire_lock(conn, cr["id"], "w1", None)


def test_extract_window_exact_copy_fast(conn, tmp_data):
    cr, sid, base = _stream_with_segments(conn, 6)
    mid = db.scalar(
        conn,
        "INSERT INTO moment(stream_id,start_s,end_s,peak_s,score) VALUES (%s,130,200,180,0.9) RETURNING id",
        sid,
    )
    wid = db.scalar(conn, """INSERT INTO "window"(moment_id) VALUES (%s) RETURNING id""", mid)
    t0 = time.time()
    res = recorder.extract_window(conn, wid)
    assert time.time() - t0 < 10
    assert res["status"] == "extracted"
    w = db.one(conn, 'SELECT * FROM "window" WHERE id=%s', wid)
    # covering segments of [100, 230] are 60..240 -> exact span
    assert w["start_utc"] == dt.datetime.fromtimestamp(base + 60, UTC)
    assert abs(media.duration(w["path"]) - (w["end_utc"] - w["start_utc"]).total_seconds()) < 0.2
    assert [s["codec_name"] for s in media.probe(w["path"])["streams"]][0] == "h264"


def test_prune_keeps_requested_windows_and_bounds_disk(conn, tmp_data):
    cr, sid, base = _stream_with_segments(conn, 6, base=int(time.time()) - 5 * 3600)
    mid = db.scalar(
        conn,
        "INSERT INTO moment(stream_id,start_s,end_s,peak_s,score) VALUES (%s,130,150,140,0.9) RETURNING id",
        sid,
    )
    conn.execute("""INSERT INTO "window"(moment_id) VALUES (%s)""", (mid,))
    removed = recorder.prune(conn)
    kept = db.all_(
        conn, "SELECT start_utc FROM segment WHERE stream_id=%s AND NOT deleted ORDER BY start_utc", sid
    )
    assert removed == 4 and len(kept) == 2  # 60-120 and 120-180 cover [100,180]
    assert all(os.path.exists(r["path"]) for r in db.all_(conn, "SELECT path FROM segment WHERE NOT deleted"))
    assert not any(os.path.exists(r["path"]) for r in db.all_(conn, "SELECT path FROM segment WHERE deleted"))


def test_recover_on_restart(conn, tmp_data):
    cr, sid, base = _stream_with_segments(conn, 2)
    conn.execute("DELETE FROM segment")
    assert recorder.recover_on_restart(conn) == [sid]
    assert db.scalar(conn, "SELECT count(*) FROM segment") == 2


def test_register_outside_managed_refused(conn, tmp_data, tmp_path_factory):
    other = tmp_path_factory.mktemp("elsewhere") / "x.bin"
    other.write_bytes(b"x")
    import pytest

    with pytest.raises(ValueError):
        files.register(conn, other, "work")


def test_sweeper_and_reconcile(conn, tmp_data):
    p = files.managed("renders") / "a.mp4"
    p.write_bytes(b"0" * 10)
    files.register(conn, p, "render", expires_at=dt.datetime.now(UTC) - dt.timedelta(seconds=1))
    stray = files.managed("work") / "stray.tmp"
    stray.write_bytes(b"1")
    assert files.sweep(conn) == 1 and not p.exists()
    r = files.reconcile(conn)
    assert r["removed_unknown"] == 1 and not stray.exists()


def test_refcount_deletes_media_at_zero(conn, tmp_data):
    cr = _creator(conn)
    sid = recorder.start_stream(conn, cr["id"], "x")
    mid = db.scalar(
        conn, "INSERT INTO moment(stream_id,start_s,end_s,peak_s,score) VALUES (%s,0,1,0,1) RETURNING id", sid
    )
    clip = db.scalar(conn, "INSERT INTO clip(moment_id) VALUES (%s) RETURNING id", mid)
    f = files.managed("renders") / "c.mp4"
    f.write_bytes(b"v")
    cv = db.scalar(
        conn,
        "INSERT INTO clip_version(clip_id,version_type,path,status) VALUES (%s,'short',%s,'queued') RETURNING id",
        clip,
        str(f),
    )
    files.register(conn, f, "render", "clip_version", cv)
    from clipping.storage import bucket

    url = bucket.put_public(conn, f, cv)
    assert "/public/" in url
    refcount.set_pending(conn, cv, 2)
    assert refcount.post_finished(conn, cv) == 1 and f.exists()
    assert refcount.post_finished(conn, cv) == 0
    assert not f.exists()
    assert not list(files.managed("public").iterdir())
    assert db.scalar(conn, "SELECT status FROM clip_version WHERE id=%s", cv) == "media_deleted"


def test_disk_guard_levels(conn, tmp_data):
    assert guard.level({"free_gb": 100, "free_pct": 50}, "m1") == "normal"
    assert guard.level({"free_gb": 20, "free_pct": 50}, "m1") == "low"
    assert guard.check(conn, "m1", {"free_gb": 8, "total_gb": 100, "free_pct": 8}) == "pause"
    assert db.get_flag(conn, "pause_heavy_m1") is True
    assert db.scalar(conn, "SELECT count(*) FROM alert WHERE kind='disk_guard'") == 1
    assert guard.level({"free_gb": 1, "free_pct": 4}, "server") == "purge"
