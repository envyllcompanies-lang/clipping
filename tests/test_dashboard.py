import base64
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from clipping.core import crypto, db
from clipping.dashboard import auth, commands


@pytest.fixture
def client(conn, monkeypatch, tmp_data):
    monkeypatch.setenv("COOKIE_SECURE", "0")
    from clipping.dashboard.app import app

    return TestClient(app)


def _owner(conn, client):
    uid, secret = auth.create_user(conn, "owner@example.com", "correct horse battery", owner=True)
    r = client.post(
        "/login",
        data={"email": "owner@example.com", "password": "correct horse battery", "code": auth.totp(secret)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    client.cookies.set("session", r.cookies["session"])
    return uid


def test_public_pages(client):
    for path in ("/", "/privacy", "/terms", "/data-deletion", "/healthz"):
        assert client.get(path).status_code == 200
    assert "tokens" in client.get("/privacy").text.lower()


def test_login_requires_2fa_for_owner(conn, client):
    auth.create_user(conn, "o@example.com", "pw-long-enough-1", owner=True)
    r = client.post(
        "/login", data={"email": "o@example.com", "password": "pw-long-enough-1", "code": "000000"}
    )
    assert "Wrong" in r.text


def test_owner_screens_render_within_one_tap(conn, client):
    _owner(conn, client)
    home = client.get("/").text
    from clipping.dashboard.app import NAV

    for href, _ in NAV:
        assert f'href="{href}"' in home
        assert client.get(href).status_code == 200, href


def test_kill_switch_and_commands(conn, client):
    _owner(conn, client)
    client.post("/cmd/global_pause", follow_redirects=False)
    assert db.get_flag(conn, "global_pause") is True
    ch = db.scalar(
        conn, "INSERT INTO channel(key,language,time_zone) VALUES ('gta6-en','en','UTC') RETURNING id"
    )
    commands.submit(conn, "pause_channel", {"channel_id": ch})
    assert db.scalar(conn, "SELECT paused FROM channel WHERE id=%s", ch)


def test_non_owner_cannot_control(conn, client):
    r = client.post(
        "/signup", data={"email": "user@example.com", "password": "a-long-password"}, follow_redirects=False
    )
    client.cookies.set("session", r.cookies["session"])
    assert client.post("/cmd/global_pause").status_code == 403
    assert client.get("/me").status_code == 200


def test_meta_data_deletion_callback(conn, client, monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", "s3cret")
    ch = db.scalar(
        conn, "INSERT INTO channel(key,language,time_zone) VALUES ('gta6-en','en','UTC') RETURNING id"
    )
    acc = db.scalar(
        conn,
        "INSERT INTO account(channel_id,platform,platform_account_id,status) VALUES (%s,'instagram','777','connected') RETURNING id",
        ch,
    )
    conn.execute(
        "INSERT INTO credential(platform,account_id,kind,secret_enc) VALUES ('instagram',%s,'oauth',%s)",
        (acc, crypto.encrypt("{}")),
    )
    payload = (
        base64.urlsafe_b64encode(json.dumps({"algorithm": "HMAC-SHA256", "user_id": "777"}).encode())
        .decode()
        .rstrip("=")
    )
    sig = (
        base64.urlsafe_b64encode(hmac.new(b"s3cret", payload.encode(), hashlib.sha256).digest())
        .decode()
        .rstrip("=")
    )
    r = client.post("/api/meta/data-deletion", data={"signed_request": f"{sig}.{payload}"})
    assert r.status_code == 200 and r.json()["confirmation_code"]
    assert db.scalar(conn, "SELECT count(*) FROM credential") == 0
    bad = client.post("/api/meta/data-deletion", data={"signed_request": f"xx.{payload}"})
    assert bad.status_code == 400


def test_totp_roundtrip():
    s = auth.new_totp_secret()
    assert auth.verify_totp(s, auth.totp(s))
