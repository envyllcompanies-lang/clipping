import datetime as dt
import os
import time

import pytest

from clipping.core import db
from tests.synth import windowfx

UTC = dt.UTC


@pytest.mark.slow
def test_window_to_gated_clip_versions(conn, tmp_data, monkeypatch):
    """Full M1 chain on a synthetic window: audio_clean -> transcribe -> events -> build (render + package + gate)."""
    from clipping import pipeline
    from clipping.storage import files

    monkeypatch.setenv("CLIPPING_ASR_MODEL", "small")
    cr = db.scalar(
        conn,
        "INSERT INTO creator(platform,platform_id,handle,language) VALUES ('twitch','1','streamer','en') RETURNING id",
    )
    t0 = dt.datetime.fromtimestamp(int(time.time()) - 3600, UTC)
    sid = db.scalar(
        conn,
        "INSERT INTO stream(creator_id,platform_stream_id,started_at) VALUES (%s,'s',%s) RETURNING id",
        cr,
        t0,
    )
    w = windowfx.make(files.managed("windows") / "w1.ts", seed=5, seconds=135)
    mid = db.scalar(
        conn,
        "INSERT INTO moment(stream_id,start_s,end_s,peak_s,score) VALUES (%s,100,175,%s,0.9) RETURNING id",
        sid,
        70 + w["crash_t"],
    )
    wid = db.scalar(
        conn,
        """INSERT INTO "window"(moment_id,path,start_utc,end_utc,status) VALUES (%s,%s,%s,%s,'extracted') RETURNING id""",
        mid,
        w["path"],
        t0 + dt.timedelta(seconds=70),
        t0 + dt.timedelta(seconds=205),
    )
    files.register(conn, w["path"], "window", "window", wid)
    from clipping.produce import sync_channels

    chans = sync_channels(conn)
    conn.execute("UPDATE account SET status='connected' WHERE channel_id=%s", (chans["en"],))
    pipeline.audio_clean(conn, {"window_id": wid})
    pipeline.transcribe(conn, {"window_id": wid})
    pipeline.events(conn, {"window_id": wid})
    res = pipeline.build(conn, {"window_id": wid})
    assert set(res["versions"]) == {"short", "long"}
    rows = db.all_(conn, "SELECT * FROM clip_version")
    assert all(r["validation"]["passed"] for r in rows)
    assert all(r["status"] in ("queued", "rejected") for r in rows)
    assert db.scalar(conn, "SELECT count(*) FROM gate_result WHERE reason IS NULL") == 0
    short = next(r for r in rows if r["version_type"] == "short")
    assert short["status"] == "queued" and len(short["targets"]) >= 5
    assert not os.path.exists(w["path"])  # window deleted after render
    pk = db.scalar(conn, "SELECT packaging FROM clip")
    assert pk["fields"]["youtube"]["title"] and pk["hook_text"]
