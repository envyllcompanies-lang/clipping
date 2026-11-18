"""Alert checks (doc 23): token expired, strike/claim, reach restriction, disk guard, recorder down, M1 offline >6 h,
posting failures over threshold, Kick chat silent. Alerts land in the `alert` table; optional push via a webhook
(ALERT_WEBHOOK_URL, e.g. an ntfy topic) and email (SMTP_* settings)."""

from __future__ import annotations

import psycopg

from clipping.core import db, settings


def run_checks(c: psycopg.Connection) -> list[str]:
    fired = []
    m1 = db.one(c, "SELECT max(seen_at) seen FROM worker_heartbeat WHERE role='m1'")
    if m1 and m1["seen"] is not None and db.scalar(c, "SELECT %s < now() - interval '6 hours'", m1["seen"]):
        db.alert(
            c, "m1_offline", "MacBook worker offline for over 6 hours (rendering delayed, nothing lost)", "m1"
        )
        fired.append("m1_offline")
    elif m1 and m1["seen"] is not None:
        db.resolve_alert(c, "m1_offline", "m1")
    srv = db.one(c, "SELECT max(seen_at) seen FROM worker_heartbeat WHERE role='server'")
    if (
        srv
        and srv["seen"] is not None
        and db.scalar(c, "SELECT %s < now() - interval '5 minutes'", srv["seen"])
    ):
        db.alert(c, "recorder_down", "Recorder/scheduler server stopped reporting", "server", "critical")
        fired.append("recorder_down")
    elif srv and srv["seen"] is not None:
        db.resolve_alert(c, "recorder_down", "server")
    for r in db.all_(
        c,
        """SELECT account_id, count(*) n FROM post WHERE status='failed_permanent' AND created_at > now() - interval '24 hours'
                          GROUP BY account_id HAVING count(*) >= 3""",
    ):
        db.alert(
            c,
            "posting_failures",
            f"{r['n']} permanent posting failures in 24 h on account {r['account_id']}",
            str(r["account_id"]),
        )
        fired.append("posting_failures")
    for r in db.all_(c, "SELECT id FROM account WHERE (health->>'restricted')::boolean"):
        db.alert(
            c,
            "reach_restricted",
            f"Account {r['id']} shows a recommendation restriction",
            str(r["id"]),
            "critical",
        )
        fired.append("reach_restricted")
    return fired


def deliver(c: psycopg.Connection) -> int:
    """Push undelivered alerts to the webhook / email if configured."""
    url = settings.env("ALERT_WEBHOOK_URL")
    rows = db.all_(
        c,
        """SELECT a.* FROM alert a WHERE resolved_at IS NULL AND NOT EXISTS
                         (SELECT 1 FROM audit_log l WHERE l.action='alert_sent' AND l.subject=a.id::text)""",
    )
    n = 0
    for a in rows:
        sent = False
        if url:
            import httpx

            try:
                httpx.post(url, content=f"[{a['severity']}] {a['message']}".encode(), timeout=10)
                sent = True
            except httpx.HTTPError:
                pass
        if settings.has("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "OWNER_FORWARD_EMAIL"):
            import smtplib
            from email.message import EmailMessage

            msg = EmailMessage()
            msg["Subject"], msg["From"], msg["To"] = (
                f"Clipping alert: {a['kind']}",
                settings.env("SMTP_USER"),
                settings.env("OWNER_FORWARD_EMAIL"),
            )
            msg.set_content(a["message"])
            try:
                with smtplib.SMTP_SSL(settings.env("SMTP_HOST"), int(settings.env("SMTP_PORT", "465"))) as s:
                    s.login(settings.env("SMTP_USER"), settings.env("SMTP_PASSWORD"))
                    s.send_message(msg)
                sent = True
            except OSError:
                pass
        if sent:
            db.audit(c, "alert_sent", str(a["id"]))
            n += 1
    return n
