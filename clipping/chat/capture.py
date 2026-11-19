"""Chat capture service: batched inserts (1 s), live 10 s buckets, gaps -> missing buckets, silent-socket alert."""

from __future__ import annotations

import datetime as dt

import psycopg

from clipping.chat import features
from clipping.chat.clients import ChatEvent
from clipping.core import config, db

UTC = dt.UTC


class Capture:
    def __init__(
        self, c: psycopg.Connection, stream_id: int, started_at: dt.datetime, language: str, platform: str
    ):
        self.c, self.stream_id, self.started_at = c, stream_id, started_at
        self.platform, self.language = platform, language
        self.tokens = config.chat_tokens(language)
        self.cfg = config.settings()["chat"]
        self.pending: list[ChatEvent] = []
        self.gaps: list[tuple[float, float]] = []
        self.last_msg_at: float | None = None

    def add(self, ev: ChatEvent) -> None:
        self.pending.append(ev)
        self.last_msg_at = ev.received_at

    def gap(self, a: float, b: float) -> None:
        t0 = self.started_at.timestamp()
        self.gaps.append((a - t0, b - t0))
        self.c.execute(
            "INSERT INTO stream_gap(stream_id,gap_start,gap_end) VALUES (%s,%s,%s)",
            (self.stream_id, dt.datetime.fromtimestamp(a, UTC), dt.datetime.fromtimestamp(b, UTC)),
        )

    def flush(self) -> int:
        if not self.pending:
            return 0
        rows = [
            (
                self.stream_id,
                dt.datetime.fromtimestamp(e.received_at, UTC),
                dt.datetime.fromtimestamp(e.platform_ts, UTC) if e.platform_ts else None,
                e.user_hash,
                e.text,
                e.emote_ids,
                e.is_sub,
                e.is_mod,
            )
            for e in self.pending
        ]
        with self.c.cursor() as cur:
            cur.executemany(
                """INSERT INTO chat_message(stream_id,received_at,platform_ts,user_id_hash,text,emote_ids,is_sub,is_mod)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                rows,
            )
        n = len(self.pending)
        self.pending.clear()
        return n

    def check_silent(self, now: float, live_with_viewers: bool) -> bool:
        lim = self.cfg["silent_alert_min"] * 60
        silent = live_with_viewers and (self.last_msg_at is None or now - self.last_msg_at > lim)
        if silent and self.platform == "kick":
            db.alert(
                self.c,
                "kick_chat_silent",
                f"Kick chat silent {self.cfg['silent_alert_min']}+ min on a live stream",
                str(self.stream_id),
            )
        return silent


def compute_buckets(c: psycopg.Connection, stream_id: int, duration_s: float | None = None) -> int:
    """(Re)compute chat_bucket rows from stored raw messages and logged gaps."""
    s = db.one(c, "SELECT * FROM stream WHERE id=%s", stream_id)
    t0 = s["started_at"]
    end = s["ended_at"] or dt.datetime.now(UTC)
    duration_s = duration_s or (end - t0).total_seconds()
    msgs = [
        features.Msg(
            (r["received_at"] - t0).total_seconds(),
            r["user_id_hash"] or "",
            r["text"] or "",
            len(r["emote_ids"] or []),
        )
        for r in db.all_(
            c,
            "SELECT received_at,user_id_hash,text,emote_ids FROM chat_message WHERE stream_id=%s",
            stream_id,
        )
    ]
    gaps = [
        ((g["gap_start"] - t0).total_seconds(), ((g["gap_end"] or end) - t0).total_seconds())
        for g in db.all_(c, "SELECT * FROM stream_gap WHERE stream_id=%s", stream_id)
    ]
    cfg = config.settings()["chat"]
    bks = features.bucketize(
        msgs,
        duration_s,
        config.chat_tokens(s["language"] or "en"),
        cfg["bucket_s"],
        cfg["baseline_s"],
        gaps,
        cfg["spam_identical_threshold"],
    )
    with c.cursor() as cur:
        cur.executemany(
            """INSERT INTO chat_bucket(stream_id,t_start,msgs,unique_chatters,emote_share,caps_share,laugh_share,
                           hype_share,copypasta_score,velocity_z,missing) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (stream_id,t_start) DO UPDATE SET msgs=EXCLUDED.msgs, unique_chatters=EXCLUDED.unique_chatters,
                           emote_share=EXCLUDED.emote_share, caps_share=EXCLUDED.caps_share, laugh_share=EXCLUDED.laugh_share,
                           hype_share=EXCLUDED.hype_share, copypasta_score=EXCLUDED.copypasta_score,
                           velocity_z=EXCLUDED.velocity_z, missing=EXCLUDED.missing""",
            [
                (
                    stream_id,
                    t0 + dt.timedelta(seconds=b["t"]),
                    b["msgs"],
                    b["unique_chatters"],
                    b["emote_share"],
                    b["caps_share"],
                    b["laugh_share"],
                    b["hype_share"],
                    b["copypasta_score"],
                    b["velocity_z"],
                    b["missing"],
                )
                for b in bks
            ],
        )
    return len(bks)


def purge_raw(c: psycopg.Connection, days: int | None = None) -> int:
    days = days or config.settings()["chat"]["raw_retention_days"]
    return c.execute(
        "DELETE FROM chat_message WHERE received_at < now() - make_interval(days=>%s)", (days,)
    ).rowcount
