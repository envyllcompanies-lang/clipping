import datetime as dt
import json

from clipping.chat import capture, clients, features
from clipping.core import config, db

UTC = dt.UTC


def test_parse_twitch_privmsg():
    line = (
        "@badge-info=;badges=moderator/1;emotes=25:0-4;mod=1;subscriber=0;tmi-sent-ts=1700000000123;user-id=42 "
        ":nick!nick@nick.tmi.twitch.tv PRIVMSG #chan :Kappa LUL clip it"
    )
    ev = clients.parse_twitch(line, now=1.0)
    assert ev.text == "Kappa LUL clip it" and ev.emote_ids == ["25"] and ev.is_mod and not ev.is_sub
    assert ev.platform_ts == 1700000000.123 and ev.user_hash != "42"
    assert clients.parse_twitch(":tmi.twitch.tv PING") is None


def test_parse_kick_frame():
    frame = json.dumps(
        {
            "event": "App\\Events\\ChatMessageEvent",
            "data": json.dumps(
                {
                    "content": "jaja [emote:123:KEKW]",
                    "sender": {"id": 7, "identity": {"badges": [{"type": "subscriber"}]}},
                }
            ),
        }
    )
    ev = clients.parse_kick(frame, now=2.0)
    assert ev.is_sub and ev.emote_ids == ["123"] and "jaja" in ev.text


def test_bucket_features_and_language_tokens():
    tok = config.chat_tokens("pt")
    msgs = [
        features.Msg(1, "a", "kkkkkk"),
        features.Msg(2, "b", "CLIPA ISSO AGORA"),
        features.Msg(3, "c", "oi"),
        features.Msg(12, "a", "nada"),
    ]
    b = features.bucketize(msgs, 20, tok)
    assert b[0]["msgs"] == 3 and b[0]["unique_chatters"] == 3
    assert b[0]["laugh_share"] > 0.3 and b[0]["caps_share"] > 0.3 and b[0]["hype_share"] > 0.3


def test_every_launch_language_has_token_file():
    for ch in config.channels().values():
        t = config.chat_tokens(ch["stream_language"])
        assert len(t["laugh"]) > len(config.chat_tokens("xx")["laugh"]), ch["code"]


def test_spam_excluded_and_gaps_missing():
    msgs = [features.Msg(i * 0.1, "bot", "buy followers") for i in range(20)] + [features.Msg(5, "u", "hi")]
    b = features.bucketize(msgs, 60, {}, gaps=[(30, 50)])
    assert b[0]["msgs"] == 1
    assert [x["missing"] for x in b] == [False, False, False, True, True, False]
    assert b[3]["velocity_z"] is None


def test_copypasta_detects_near_duplicates():
    assert (
        features.copypasta(["copy this pasta now"] * 5 + ["copy this pasta now!", "random words here"]) > 0.7
    )
    assert features.copypasta(["hello there", "what is up", "nice drive man"]) == 0


def test_velocity_z_spike():
    msgs = [features.Msg(t, f"u{t}", "x") for t in range(0, 600, 5)] + [
        features.Msg(605 + i * 0.05, f"s{i}", "W") for i in range(150)
    ]
    b = features.bucketize(msgs, 700, {})
    assert b[60]["velocity_z"] > 3 and abs(b[30]["velocity_z"]) < 2


def test_calibrate_lag():
    onsets = [104, 305, 507]
    assert features.calibrate_lag(onsets, [100, 300, 503]) == 4.0


def test_capture_flush_buckets_and_silent_alert(conn):
    cr = db.scalar(
        conn,
        "INSERT INTO creator(platform,platform_id,handle,language) VALUES ('kick','1','k','es') RETURNING id",
    )
    t0 = dt.datetime(2026, 11, 18, 12, tzinfo=UTC)
    sid = db.scalar(
        conn,
        "INSERT INTO stream(creator_id,platform_stream_id,started_at,ended_at,language) VALUES (%s,'s',%s,%s,'es') RETURNING id",
        cr,
        t0,
        t0 + dt.timedelta(seconds=60),
    )
    cap = capture.Capture(conn, sid, t0, "es", "kick")
    for i in range(30):
        cap.add(clients.ChatEvent(t0.timestamp() + i, None, f"h{i}", "jajaja", [], False, False))
    cap.gap(t0.timestamp() + 40, t0.timestamp() + 50)
    assert cap.flush() == 30
    assert capture.compute_buckets(conn, sid) == 6
    rows = db.all_(
        conn, "SELECT msgs, missing, laugh_share FROM chat_bucket WHERE stream_id=%s ORDER BY t_start", sid
    )
    assert rows[0]["msgs"] == 10 and rows[4]["missing"] and rows[0]["laugh_share"] == 1.0
    assert cap.check_silent(t0.timestamp() + 30 + 11 * 60, True)
    assert db.scalar(conn, "SELECT count(*) FROM alert WHERE kind='kick_chat_silent'") == 1
