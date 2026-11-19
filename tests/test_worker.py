from clipping import worker
from clipping.core import db, jobs


def test_worker_once_runs_job_and_heartbeats(conn, tmp_data):
    cr = db.scalar(
        conn, "INSERT INTO creator(platform,platform_id,handle) VALUES ('twitch','1','x') RETURNING id"
    )
    sid = db.scalar(
        conn,
        "INSERT INTO stream(creator_id,platform_stream_id,started_at) VALUES (%s,'s',now()) RETURNING id",
        cr,
    )
    jobs.enqueue(conn, "record_stop", {"stream_id": sid})
    worker.PERIODIC["server"], saved = [], worker.PERIODIC["server"]
    try:
        worker.loop("server", once=True)
    finally:
        worker.PERIODIC["server"] = saved
    assert db.scalar(conn, "SELECT status FROM stream WHERE id=%s", sid) == "ended"
    assert db.scalar(conn, "SELECT count(*) FROM worker_heartbeat WHERE role='server'") == 1
