import datetime as dt

import httpx
import pytest

from clipping.publish import base, oauth, snapchat, tiktok, youtube


def test_snap_aes_roundtrip():
    blob, key, iv = snapchat.encrypt(b"video-bytes" * 100)
    assert len(key) == 32 and len(iv) == 16 and blob != b"video-bytes" * 100
    assert snapchat.decrypt(blob, key, iv) == b"video-bytes" * 100


def _yt(status, body):
    t = httpx.MockTransport(lambda r: httpx.Response(status, json=body))
    return youtube.YouTube(lambda a: "t", t)


def test_youtube_error_mapping():
    with pytest.raises(base.QuotaExceeded) as e:
        _yt(403, {"error": {"errors": [{"reason": "quotaExceeded"}]}}).check("v", {})
    assert e.value.scope == "project"
    with pytest.raises(base.QuotaExceeded):
        _yt(400, {"error": {"errors": [{"reason": "uploadLimitExceeded"}]}}).check("v", {})
    with pytest.raises(base.TokenError):
        _yt(401, {"error": {"errors": [{"reason": "authError"}]}}).check("v", {})
    with pytest.raises(base.TransientError):
        _yt(503, {}).check("v", {})


def test_youtube_fields_and_private_fallback():
    y = youtube.YouTube(lambda a: "t")
    clip = {
        "id": 9,
        "path": "/x.mp4",
        "language": "es",
        "packaging": {"fields": {"youtube": {"title": "T" * 150, "description": "d", "tags": ["a"]}}},
    }
    p = y.prepare(clip, {"mode": "fallback"})
    sn = p.fields["snippet"]
    assert (
        len(sn["title"]) == 100
        and sn["categoryId"] == "20"
        and sn["defaultLanguage"] == "es"
        and "cv9" in sn["tags"]
    )
    assert (
        p.fields["status"]["privacyStatus"] == "private"
        and p.fields["status"]["selfDeclaredMadeForKids"] is False
    )


def test_tiktok_unaudited_goes_to_inbox(tmp_path):
    from clipping.eval.fakeplatforms import FakePlatforms

    f = tmp_path / "v.mp4"
    f.write_bytes(b"0" * 1000)
    fake = FakePlatforms()
    t = tiktok.TikTok(lambda a: "t", fake.transport())
    r = t.publish(
        base.Payload("tiktok", {"mode": "direct"}, str(f), {"title": "x"}, meta={"cv": 1, "duration": 30})
    )
    assert r.fallback == "inbox_draft" and r.status == "processing"


def test_oauth_state_signed_and_expiring(monkeypatch):
    s = oauth.make_state("tiktok", 5, 1)
    assert oauth.read_state(s)["a"] == 5
    assert oauth.read_state(s.replace("tiktok", "youtube")) is None


def test_framework_backoff_schedule(conn, tmp_data):
    from clipping.publish import backtest as pb
    from clipping.publish import framework, registry

    fake = __import__("clipping.eval.fakeplatforms", fromlist=["FakePlatforms"]).FakePlatforms()
    fake.fail_next = {"tt:/v2/post/publish/creator_info/query/": [500, 500, 500, 500, 500]}
    ch, accs, (cv,) = pb.seed(conn, mode="direct")
    conn.execute(
        "UPDATE clip_version SET targets = jsonb_path_query_array(targets, '$[*] ? (@.platform == \"tiktok\")')"
    )
    now = dt.datetime.now(dt.UTC)
    framework.schedule(conn, now)
    ads = registry.adapters(conn, fake.transport())
    pid = conn.execute("SELECT id FROM post").fetchone()["id"]
    t = now + dt.timedelta(days=2)
    states = []
    for _ in range(6):
        states.append(framework.run_post(conn, pid, ads, t))
        t += dt.timedelta(hours=2)
    assert states[0] == "retry_wait" and states[-1] == "failed_permanent"
