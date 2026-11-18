import datetime as dt

from clipping.core import crypto, db, hardware, jobs


def test_schema_and_flags(conn):
    db.set_flag(conn, "global_pause", True)
    assert db.get_flag(conn, "global_pause") is True


def test_job_queue_skip_locked_and_retry(conn):
    a = jobs.enqueue(conn, "t", {"x": 1}, dedupe_key="k1")
    assert jobs.enqueue(conn, "t", {"x": 1}, dedupe_key="k1") is None  # idempotent enqueue
    from clipping.core.db import connect

    c2 = connect()
    j1 = jobs.claim(conn, ["t"], "w1")
    assert j1["id"] == a
    assert jobs.claim(c2, ["t"], "w2") is None  # locked
    assert jobs.fail(conn, j1, "boom") == "retry"
    row = db.one(conn, "SELECT status, run_after > now() AS later FROM job WHERE id=%s", a)
    assert row["status"] == "queued" and row["later"]
    c2.close()


def test_expired_lease_reclaimed(conn):
    jid = jobs.enqueue(conn, "t", {})
    jobs.claim(conn, ["t"], "dead-worker", lease_s=1)
    conn.execute("UPDATE job SET locked_until = now() - interval '1 second' WHERE id=%s", (jid,))
    again = jobs.claim(conn, ["t"], "w2")
    assert again and again["id"] == jid and again["attempts"] == 2


def test_run_one_marks_dead_after_permanent(conn):
    jobs.enqueue(conn, "p", {})

    def h(c, p):
        raise jobs.PermanentError("bad token")

    assert jobs.run_one(conn, {"p": h}, "w")
    assert db.scalar(conn, "SELECT status FROM job") == "dead"


def test_hardware_profile_sizes_models():
    small = hardware.profile(8 * 1024**3, "Darwin")
    big = hardware.profile(16 * 1024**3, "Darwin")
    assert small.whisper_model == "small" and not small.diarization and small.parallel_heavy == 1
    assert big.whisper_model == "large-v3-turbo" and big.diarization
    assert small.encoder == "h264_videotoolbox"
    assert hardware.profile(16 * 1024**3, "Linux").encoder == "libx264"
    assert hardware.total_ram_bytes() > 0


def test_crypto_roundtrip_and_password():
    assert crypto.decrypt(crypto.encrypt("s3cret")) == "s3cret"
    pw = crypto.password()
    assert len(pw) == 24 and any(c.isdigit() for c in pw)


def test_alert_dedupes(conn):
    db.alert(conn, "disk", "low", "m1")
    db.alert(conn, "disk", "low", "m1")
    assert db.scalar(conn, "SELECT count(*) FROM alert") == 1
    db.resolve_alert(conn, "disk", "m1")
    assert db.scalar(conn, "SELECT count(*) FROM alert WHERE resolved_at IS NULL") == 0
    assert dt.datetime.now()
