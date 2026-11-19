import datetime as dt
import os
import subprocess

import psycopg

from clipping.core import db, jobs

ROOT = os.path.dirname(os.path.dirname(__file__))


def test_backup_restores_cleanly(conn, tmp_path):
    conn.execute(
        "INSERT INTO creator(platform,platform_id,handle) VALUES ('twitch','1','a'),('kick','2','b')"
    )
    url = db.url()
    out = subprocess.run(
        [f"{ROOT}/scripts/backup.sh", str(tmp_path)],
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=True,
    )
    dump = out.stdout.strip().splitlines()[-1]
    admin = url.rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute("DROP DATABASE IF EXISTS clipping_restore_test")
        a.execute("CREATE DATABASE clipping_restore_test")
    target = url.rsplit("/", 1)[0] + "/clipping_restore_test"
    subprocess.run([f"{ROOT}/scripts/restore.sh", dump, target], check=True, capture_output=True)
    with psycopg.connect(target) as t:
        assert t.execute("SELECT count(*) FROM creator").fetchone()[0] == 2
        assert t.execute("SELECT count(*) FROM schema_version").fetchone()[0] == 1


def test_m1_offline_a_day_loses_nothing(conn, tmp_data):
    """M1 jobs wait in the queue; the server keeps recording/scoring; windows only expire after 48 h."""
    from clipping.storage import files

    jobs.enqueue(conn, "audio_clean", {"window_id": 1}, dedupe_key="clean:1")
    p = files.managed("windows") / "w1.ts"
    p.write_bytes(b"x")
    files.register(conn, p, "window", None, None)
    later = dt.datetime.now(dt.UTC) + dt.timedelta(hours=24)
    assert files.sweep(conn, later) == 0 and p.exists()
    assert db.scalar(conn, "SELECT status FROM job WHERE type='audio_clean'") == "queued"
    assert files.sweep(conn, dt.datetime.now(dt.UTC) + dt.timedelta(hours=49)) == 1
