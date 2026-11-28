"""Dashboard & kill switch (doc 23) + public site (doc 29). Phone-first, server-rendered, auto-refresh every 15 s.

Monitoring and control only: nothing waits on this app. Actions become `command` rows the workers apply."""

from __future__ import annotations

import base64
import html
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from jinja2 import DictLoader, Environment, select_autoescape

from clipping.core import config, db, settings
from clipping.dashboard import auth, commands, site
from clipping.dashboard.templates import PAGES

env = Environment(loader=DictLoader(PAGES), autoescape=select_autoescape(["html"]))
app = FastAPI(title="Clipping dashboard", docs_url=None, redoc_url=None)
NAV = [
    ("/", "Home"),
    ("/live", "Live"),
    ("/clips", "Clips"),
    ("/posted", "Posted"),
    ("/channels", "Channels"),
    ("/creators", "Creators"),
    ("/accounts", "Accounts"),
    ("/setup", "Signups"),
    ("/languages", "Languages"),
    ("/analytics", "Analytics"),
    ("/fallback", "Fallback tasks"),
    ("/storage", "Storage"),
]


def conn():
    c = db.connect()
    try:
        yield c
    finally:
        c.close()


def current_user(request: Request, c=Depends(conn)) -> dict | None:
    uid = auth.unsign(request.cookies.get("session"))
    return db.one(c, "SELECT id, email, is_owner FROM app_user WHERE id=%s", uid) if uid else None


def owner(request: Request, user=Depends(current_user)) -> dict:
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    if not user["is_owner"]:
        raise HTTPException(status_code=403, detail="Owner only")
    return user


def page(name: str, **ctx) -> HTMLResponse:
    ctx.setdefault("nav", NAV)
    ctx.setdefault("refresh", name in ("home.html", "table.html"))
    resp = HTMLResponse(env.get_template(name).render(**ctx))
    return resp


def table(user, heading, cols, rows, note=None, extra="", subtitle=None) -> HTMLResponse:
    return page(
        "table.html",
        user=user,
        heading=heading,
        cols=cols,
        rows=rows,
        note=note,
        extra=extra,
        subtitle=subtitle or heading,
    )


def btn(action: str, label: str, danger: bool = False, **fields) -> str:
    hidden = "".join(
        f'<input type="hidden" name="{k}" value="{html.escape(str(v))}">' for k, v in fields.items()
    )
    return f'<form class="inline" method="post" action="/cmd/{action}">{hidden}<button{" class=danger" if danger else ""}>{label}</button></form>'


# ---------------- auth ----------------
@app.get("/login", response_class=HTMLResponse)
def login_form(error: str | None = None):
    return page("login.html", user=None, error=error)


@app.post("/login")
def login_post(email: str = Form(...), password: str = Form(...), code: str = Form(""), c=Depends(conn)):
    uid = auth.login(c, email, password, code or None)
    if not uid:
        return page("login.html", user=None, error="Wrong email, password or 2FA code.")
    r = RedirectResponse("/", status_code=303)
    r.set_cookie(
        "session",
        auth.sign(uid),
        httponly=True,
        samesite="lax",
        secure=settings.env("COOKIE_SECURE", "1") == "1",
    )
    return r


@app.get("/signup", response_class=HTMLResponse)
def signup_form():
    return page("signup.html", user=None)


@app.post("/signup")
def signup_post(email: str = Form(...), password: str = Form(...), c=Depends(conn)):
    """Multi-user accounts (TikTok audit: the product must work for any user). The owner is created from the CLI."""
    if len(password) < 12 or "@" not in email:
        return page("signup.html", user=None, error="Use a valid email and a password of 12+ characters.")
    if db.one(c, "SELECT 1 FROM app_user WHERE email=%s", email.lower()):
        return page("signup.html", user=None, error="That email already has an account.")
    uid, _ = auth.create_user(c, email, password, owner=False)
    r = RedirectResponse("/me", status_code=303)
    r.set_cookie(
        "session",
        auth.sign(uid),
        httponly=True,
        samesite="lax",
        secure=settings.env("COOKIE_SECURE", "1") == "1",
    )
    return r


@app.get("/logout")
def logout():
    r = RedirectResponse("/login", status_code=303)
    r.delete_cookie("session")
    return r


@app.get("/me", response_class=HTMLResponse)
def me(user=Depends(current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    body = '<p>Connect your TikTok account to publish clips you choose.</p><a class="btn" href="/connect/tiktok">Connect TikTok</a>'
    return page(
        "table.html",
        user=user,
        nav=[("/me", "My account"), ("/logout", "Sign out")],
        heading="Your account",
        cols=[],
        rows=[],
        extra=f'<div class="card">{body}</div>',
    )


# ---------------- owner screens ----------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request, c=Depends(conn), user=Depends(current_user)):
    if not user:
        return page("public.html", title=site.brand()["brand"], body=site.landing(), **site.brand())
    if not user["is_owner"]:
        return RedirectResponse("/me", status_code=303)
    k = db.one(
        c,
        """SELECT (SELECT count(*) FROM post WHERE status='live' AND posted_at::date=current_date) posted_today,
                            (SELECT count(*) FROM post WHERE status IN ('scheduled','retry_wait')) queue,
                            (SELECT count(*) FROM stream WHERE status='recording') recording,
                            (SELECT count(*) FROM clip_version WHERE status='queued') clips_ready""",
    )
    hb = {
        r["role"]: r
        for r in db.all_(
            c,
            "SELECT DISTINCT ON (role) role, seen_at, now()-seen_at age, info FROM worker_heartbeat ORDER BY role, seen_at DESC",
        )
    }

    def h(role, name, limit_s):
        r = hb.get(role)
        if not r:
            return {"name": name, "ok": False, "status": "never seen", "detail": ""}
        ok = r["age"].total_seconds() < limit_s
        return {
            "name": name,
            "ok": ok,
            "status": "running" if ok else "offline",
            "detail": f"last seen {int(r['age'].total_seconds())} s ago",
        }

    disk = db.get_flag(c, "disk_level_server") or {}
    health = [
        h("server", "Recorder & scheduler (VPS)", 300),
        h("m1", "Render worker (MacBook)", 6 * 3600),
        {
            "name": "Disk (server)",
            "ok": disk.get("level", "normal") == "normal",
            "status": disk.get("level", "unknown"),
            "detail": f"{disk.get('free_gb', '?')} GB free",
        },
        {
            "name": "Queue depth",
            "ok": True,
            "status": str(db.scalar(c, "SELECT count(*) FROM job WHERE status='queued'")),
            "detail": "jobs waiting",
        },
    ]
    alerts = db.all_(
        c, "SELECT * FROM alert WHERE resolved_at IS NULL ORDER BY severity, created_at DESC LIMIT 20"
    )
    return page(
        "home.html",
        user=user,
        subtitle="Home",
        kpis=[
            ("Posted today", k["posted_today"]),
            ("Post queue", k["queue"]),
            ("Recording now", k["recording"]),
            ("Clips ready", k["clips_ready"]),
        ],
        health=health,
        alerts=alerts,
        paused=bool(db.get_flag(c, "global_pause")),
    )


@app.get("/live", response_class=HTMLResponse)
def live(c=Depends(conn), user=Depends(owner)):
    rows = []
    for s in db.all_(
        c,
        """SELECT s.*, cr.handle, cr.platform FROM stream s JOIN creator cr ON cr.id=s.creator_id
                           WHERE s.status='recording' OR s.ended_at > now() - interval '3 hours' ORDER BY s.started_at DESC""",
    ):
        curve = db.one(c, 'SELECT "values" FROM heatmap_curve WHERE stream_id=%s', s["id"])
        moms = db.all_(c, "SELECT start_s, end_s FROM moment WHERE stream_id=%s", s["id"])
        rows.append(
            [
                f"{s['handle']} <span class=muted>{s['platform']}</span>",
                s["status"],
                sparkline(curve["values"] if curve else [], moms),
                btn("stop_recording", "Stop", True, stream_id=s["id"]) if s["status"] == "recording" else "",
            ]
        )
    return table(
        user,
        "Streams (recording and recent)",
        ["Creator", "Status", "Heatmap (candidate windows shaded)", ""],
        rows,
    )


def sparkline(values: list[float], moments: list[dict], w: int = 260, h: int = 40) -> str:
    if not values:
        return '<span class="muted">no curve yet</span>'
    n = len(values)
    step = max(1, n // w)
    pts = values[::step]
    mx = max(max(pts), 1e-6)
    path = " ".join(f"{i * w / max(len(pts) - 1, 1):.1f},{h - v / mx * h:.1f}" for i, v in enumerate(pts))
    shades = "".join(
        f'<rect x="{m["start_s"] / n * w:.1f}" y="0" width="{max(1, (m["end_s"] - m["start_s"]) / n * w):.1f}" height="{h}" fill="#ffe11a33"/>'
        for m in moments
    )
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">{shades}<polyline fill="none" stroke="#ffe11a" stroke-width="1.5" points="{path}"/></svg>'


@app.get("/clips", response_class=HTMLResponse)
def clips(c=Depends(conn), user=Depends(owner)):
    rows = []
    for r in db.all_(
        c,
        """SELECT cl.id, cl.status, cl.packaging->>'hook_text' hook, cr.handle, cr.id creator_id, ch.key,
                                  json_agg(json_build_object('v', cv.version_type, 's', cv.status, 'd', cv.duration_s, 'id', cv.id)) versions
                           FROM clip cl JOIN clip_version cv ON cv.clip_id=cl.id LEFT JOIN creator cr ON cr.id=cl.creator_id
                           LEFT JOIN channel ch ON ch.id=cl.channel_id GROUP BY cl.id, cr.handle, cr.id, ch.key ORDER BY cl.id DESC LIMIT 60""",
    ):
        vs = " ".join(
            f'<a href="/clip/{v["id"]}">{v["v"]}</a> <span class=pill>{v["s"]}</span>' for v in r["versions"]
        )
        thumb_id = r["versions"][0]["id"]
        rows.append(
            [
                f'<img class=thumb src="/thumb/{thumb_id}" alt="">',
                html.escape(r["hook"] or ""),
                r["handle"],
                r["key"],
                vs,
                btn("pull_clip", "Pull everywhere", True, clip_id=r["id"])
                + " "
                + btn("requeue_clip", "Re-queue", clip_id=r["id"])
                + " "
                + btn("block_creator", "Block creator", True, creator_id=r["creator_id"]),
            ]
        )
    return table(user, "Clips", ["", "Hook", "Creator", "Channel", "Versions", "Actions"], rows)


@app.get("/clip/{cv_id}", response_class=HTMLResponse)
def clip_detail(cv_id: int, c=Depends(conn), user=Depends(owner)):
    gates = db.all_(
        c,
        "SELECT check_name, passed, reason, created_at FROM gate_result WHERE clip_version_id=%s ORDER BY id",
        cv_id,
    )
    posts = db.all_(
        c, "SELECT platform, status, platform_post_id, error FROM post WHERE clip_version_id=%s", cv_id
    )
    rows = [
        [
            g["check_name"],
            "<span class=ok>pass</span>" if g["passed"] else "<span class=bad>fail</span>",
            html.escape(g["reason"] or ""),
        ]
        for g in gates
    ]
    extra = (
        '<div class="card"><h3>Per platform</h3><table>'
        + "".join(
            f"<tr><td>{p['platform']}</td><td>{p['status']}</td><td class=muted>{html.escape(p['error'] or '')}</td></tr>"
            for p in posts
        )
        + "</table></div>"
    )
    return table(
        user, f"Gate decisions for version {cv_id}", ["Check", "Result", "Reason"], rows, extra=extra
    )


@app.get("/thumb/{cv_id}")
def thumb(cv_id: int, c=Depends(conn), user=Depends(owner)):
    b = db.scalar(c, "SELECT thumbnail FROM clip_version WHERE id=%s", cv_id)
    if not b:
        raise HTTPException(404)
    return HTMLResponse(content=bytes(b), media_type="image/jpeg")


@app.get("/posted", response_class=HTMLResponse)
def posted(c=Depends(conn), user=Depends(owner)):
    rows = []
    for p in db.all_(
        c,
        """SELECT p.*, ch.key, (SELECT views FROM post_stat s WHERE s.post_id=p.id ORDER BY sampled_at DESC LIMIT 1) views,
                                  cf.features->>'performance' perf
                           FROM post p JOIN account a ON a.id=p.account_id JOIN channel ch ON ch.id=a.channel_id
                           LEFT JOIN clip_feature cf ON cf.clip_version_id=p.clip_version_id
                           WHERE p.status IN ('live','processing') ORDER BY p.posted_at DESC NULLS LAST LIMIT 100""",
    ):
        rows.append(
            [
                p["key"],
                p["platform"],
                p["status"],
                p["platform_post_id"] or "",
                p["views"] or 0,
                p["perf"] or "",
                btn("delete_post", "Delete", True, post_id=p["id"]),
            ]
        )
    return table(
        user, "Posted", ["Channel", "Platform", "Status", "Post ID", "Views", "Performance", ""], rows
    )


@app.get("/channels", response_class=HTMLResponse)
def channels(c=Depends(conn), user=Depends(owner)):
    rows = []
    styles = config.style_names()
    for ch in db.all_(
        c,
        """SELECT ch.*, (SELECT count(*) FROM account a WHERE a.channel_id=ch.id AND a.status IN ('connected','verified')) connected,
                                   (SELECT count(*) FROM post p JOIN account a ON a.id=p.account_id WHERE a.channel_id=ch.id
                                    AND p.created_at > now()-interval '24 hours') posts_24h FROM channel ch ORDER BY ch.key""",
    ):
        sel = "".join(
            f"<option {'selected' if s == ch['style_profile'] else ''}>{s}</option>" for s in styles
        )
        prof = (
            f'<form class="inline" method="post" action="/cmd/set_profile"><input type="hidden" name="channel_id" value="{ch["id"]}">'
            f'<select name="profile" onchange="this.form.submit()">{sel}</select></form>'
        )
        rows.append(
            [
                ch["key"],
                ch["language"],
                f"{ch['connected']}/6",
                ch["posts_24h"],
                prof,
                ", ".join((ch["config"] or {}).get("posting_slots", [])),
                btn("resume_channel", "Resume", channel_id=ch["id"])
                if ch["paused"]
                else btn("pause_channel", "Pause", True, channel_id=ch["id"]),
            ]
        )
    return table(user, "Channels", ["Channel", "Lang", "Accounts", "Posts 24h", "Style", "Slots", ""], rows)


@app.get("/creators", response_class=HTMLResponse)
def creators(c=Depends(conn), user=Depends(owner), language: str | None = None):
    rows = []
    for r in db.all_(
        c,
        """SELECT cs.*, cr.handle, cr.platform, cr.blocklisted, cr.pinned FROM creator_score cs JOIN creator cr ON cr.id=cs.creator_id
                           WHERE cs.date=(SELECT max(date) FROM creator_score) AND (%s::text IS NULL OR cs.language=%s)
                           ORDER BY cs.language, cs.rank LIMIT 300""",
        language,
        language,
    ):
        pct = ", ".join(f"{k.replace('_', ' ')} {v:.2f}" for k, v in r["percentiles"].items())
        acts = (
            btn("unpin_creator", "Unpin", creator_id=r["creator_id"])
            if r["pinned"]
            else btn("pin_creator", "Pin", creator_id=r["creator_id"])
        )
        acts += " " + btn("block_creator", "Block", True, creator_id=r["creator_id"])
        rows.append(
            [
                r["language"],
                r["rank"],
                f"{r['handle']} <span class=muted>{r['platform']}</span>",
                f"{r['score']:.3f}",
                "✓" if r["selected"] else "",
                html.escape(r["selection_reason"] or ""),
                f"<span class=muted>{pct}</span>",
                acts,
            ]
        )
    return table(
        user,
        "Creator radar",
        ["Lang", "#", "Creator", "Score", "Rec", "Why", "Percentiles", ""],
        rows,
        note="Statistical ranking (doc 01): weighted percentiles within each language. No AI opinion.",
    )


@app.get("/accounts", response_class=HTMLResponse)
def accounts(c=Depends(conn), user=Depends(owner)):
    from clipping.accounts import credentials

    rows = [
        [
            a["channel"],
            a["platform"],
            a["handle"] or "",
            a["status"],
            a["review_status"],
            a["mode"],
            str(a["expires_at"] or ""),
            f'<a class="btn" href="/connect/{a["platform"]}?account_id={a["id"]}">{"Reconnect" if a["status"] != "disconnected" else "Connect"}</a>',
        ]
        for a in credentials.token_health(c)
    ]
    reviews = db.get_flag(c, "platform_reviews") or {
        "youtube_audit": "pending",
        "meta_app_review": "pending",
        "tiktok_audit": "pending",
        "snap_allowlist": "pending",
    }
    extra = (
        '<div class="card"><h3>Platform reviews</h3>'
        + "".join(f"<p>{k.replace('_', ' ')}: <span class=pill>{v}</span></p>" for k, v in reviews.items())
        + "</div>"
    )
    return table(
        user,
        "Accounts and tokens",
        ["Channel", "Platform", "Handle", "Status", "Review", "Mode", "Token expires", ""],
        rows,
        extra=extra,
    )


@app.get("/languages", response_class=HTMLResponse)
def languages(c=Depends(conn), user=Depends(owner)):
    rows = [
        [
            r["code"],
            str(r["week"]),
            f"{r['audience_hours'] or 0:.0f}",
            r["depth"],
            r["clip_channels"],
            f"{r['opportunity'] or 0:.1f}",
            f"{r['value'] or 0:.2f}",
            f"{r['ours'] or 0:.2f}",
            f"{r['score'] or 0:.3f}",
            r["rank"],
        ]
        for r in db.all_(
            c, "SELECT * FROM language_week WHERE week=(SELECT max(week) FROM language_week) ORDER BY rank"
        )
    ]
    acts = db.all_(c, "SELECT * FROM language_action WHERE status='open' ORDER BY created_at DESC")
    extra = (
        '<div class="card"><h3>Recommendations</h3>'
        + (
            "".join(
                f"<p><span class=pill>{a['action']}</span> {a['code']} {html.escape(a['reason'] or '')}</p>"
                for a in acts
            )
            or "<p class=muted>None.</p>"
        )
        + "</div>"
    )
    return table(
        user,
        "Language market (weekly)",
        [
            "Lang",
            "Week",
            "Audience h",
            "Depth",
            "Clip channels",
            "Opportunity",
            "Value",
            "Ours",
            "Score",
            "Rank",
        ],
        rows,
        extra=extra,
    )


@app.get("/analytics", response_class=HTMLResponse)
def analytics(c=Depends(conn), user=Depends(owner)):
    rows = [
        [
            w["component"],
            w["version"],
            "active" if w["active"] else "",
            f"{w['holdout_score'] or 0:.3f}",
            str(w["fitted_at"])[:16],
            html.escape(w["explanation"] or ""),
            btn("rollback_weights", "Roll back", component=w["component"]) if w["active"] else "",
        ]
        for w in db.all_(c, "SELECT * FROM weights ORDER BY component, version DESC LIMIT 100")
    ]
    dg = db.one(c, "SELECT * FROM digest ORDER BY week DESC LIMIT 1")
    frozen = bool(db.get_flag(c, "learning_frozen"))
    extra = (
        f'<div class="card"><h3>Weekly digest</h3><pre style="white-space:pre-wrap">{html.escape(_digest_text(dg))}</pre></div>'
        f'<div class="card">{btn("freeze_learning", "Unfreeze learning" if frozen else "Freeze learning", frozen="" if frozen else "1")}</div>'
        f'<div class="card"><h3>Backtests</h3>{_eval_summary(c)}</div>'
    )
    return table(
        user,
        "Analytics: weight changes",
        ["Component", "Version", "", "Holdout", "Fitted", "Why", ""],
        rows,
        extra=extra,
    )


def _digest_text(dg) -> str:
    if not dg:
        return "No digest yet (first one after a week of posting)."
    b = dg["body"]
    return b.get("text") or str(b)


def _eval_summary(c) -> str:
    rows = db.all_(
        c,
        """SELECT DISTINCT ON (stage) stage, passed, finished_at FROM eval_run ORDER BY stage, finished_at DESC""",
    )
    return (
        "<table>"
        + "".join(
            f"<tr><td>{r['stage']}</td><td class={'ok' if r['passed'] else 'bad'}>{'pass' if r['passed'] else 'FAIL'}</td>"
            f"<td class=muted>{str(r['finished_at'])[:16]}</td></tr>"
            for r in rows
        )
        + "</table>"
    )


@app.get("/fallback", response_class=HTMLResponse)
def fallback(c=Depends(conn), user=Depends(owner)):
    rows = [
        [
            t["platform"],
            t["kind"].replace("_", " "),
            html.escape(str(t["details"] or "")),
            btn("fallback_done", "Mark done", task_id=t["id"]),
        ]
        for t in db.all_(c, "SELECT * FROM fallback_task WHERE NOT done ORDER BY created_at")
    ]
    return table(
        user,
        "Needs a tap",
        ["Platform", "Task", "Details", ""],
        rows,
        note="YouTube private uploads to publish, TikTok inbox drafts to post, Snapchat deletions to do in the app.",
    )


@app.get("/storage", response_class=HTMLResponse)
def storage(c=Depends(conn), user=Depends(owner)):
    from clipping.storage import files

    rows = [[r["kind"], r["n"], f"{r['bytes'] / 1e9:.2f} GB"] for r in files.usage_by_kind(c)]
    disk = [db.get_flag(c, f"disk_level_{r}") or {} for r in ("server", "m1")]
    extra = (
        f'<div class="card"><p>Server: {disk[0].get("free_gb", "?")} GB free ({disk[0].get("level", "?")}) · '
        f"MacBook: {disk[1].get('free_gb', '?')} GB free ({disk[1].get('level', '?')})</p>{btn('run_sweeper', 'Run sweeper')}</div>"
    )
    return table(user, "Storage", ["Kind", "Files", "Size"], rows, extra=extra)


@app.get("/setup", response_class=HTMLResponse)
def setup(c=Depends(conn), user=Depends(owner), code: str | None = None):
    try:
        from clipping.accounts import provision
    except ImportError:
        return table(user, "Signups", [], [], note="Accounts tool not installed yet.")
    return HTMLResponse(provision.worksheet_html(c, code, reveal=False))


@app.post("/cmd/{kind}")
async def cmd(kind: str, request: Request, c=Depends(conn), user=Depends(owner)):
    form = dict(await request.form())
    args = {k: (int(v) if isinstance(v, str) and v.isdigit() else v) for k, v in form.items()}
    if kind == "freeze_learning":
        args["frozen"] = bool(form.get("frozen"))
    if kind == "set_slots" and isinstance(args.get("slots"), str):
        args["slots"] = [s.strip() for s in args["slots"].split(",") if s.strip()]
    commands.submit(c, kind, args, user["email"])
    return RedirectResponse(request.headers.get("referer", "/"), status_code=303)


# ---------------- TikTok audit posting UX (doc 19/23) ----------------
@app.get("/tiktok/post/{cv_id}", response_class=HTMLResponse)
def tiktok_post_form(cv_id: int, account_id: int, c=Depends(conn), user=Depends(current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    from clipping.publish import tiktok

    info = tiktok.creator_info_for(c, account_id)
    title = (
        db.scalar(
            c,
            """SELECT cl.packaging->'fields'->'tiktok'->>'caption' FROM clip_version cv JOIN clip cl ON cl.id=cv.clip_id
                            WHERE cv.id=%s""",
            cv_id,
        )
        or ""
    )
    return page(
        "tiktok_post.html",
        user=user,
        refresh=False,
        creator=info,
        cv_id=cv_id,
        account_id=account_id,
        title=title,
        preview_url=f"/preview/{cv_id}",
    )


@app.post("/tiktok/post")
def tiktok_post(
    clip_version_id: int = Form(...),
    account_id: int = Form(...),
    title: str = Form(""),
    privacy: str = Form(...),
    allow_comment: str | None = Form(None),
    allow_duet: str | None = Form(None),
    allow_stitch: str | None = Form(None),
    disclose: str | None = Form(None),
    consent: str | None = Form(None),
    c=Depends(conn),
    user=Depends(current_user),
):
    if not user or not consent:
        raise HTTPException(400, "Consent is required")
    from clipping.publish import tiktok

    pid = tiktok.queue_manual_post(
        c,
        clip_version_id,
        account_id,
        {
            "title": title,
            "privacy_level": privacy,
            "disable_comment": not allow_comment,
            "disable_duet": not allow_duet,
            "disable_stitch": not allow_stitch,
            "brand_content_toggle": bool(disclose),
        },
    )
    return page(
        "table.html",
        user=user,
        heading="Posted to TikTok",
        cols=[],
        rows=[],
        extra=f'<div class="card"><p>Your video is being processed (post #{pid}). It can take a few minutes to appear on your profile.</p></div>',
    )


@app.get("/preview/{cv_id}")
def preview(cv_id: int, c=Depends(conn), user=Depends(current_user)):
    if not user:
        raise HTTPException(401)
    p = db.scalar(c, "SELECT path FROM clip_version WHERE id=%s", cv_id)
    if not p or not Path(p).exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4")


# ---------------- public site (doc 29) ----------------
def public(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(env.get_template("public.html").render(title=title, body=body, **site.brand()))


@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    return public("Privacy policy", site.privacy())


@app.get("/terms", response_class=HTMLResponse)
def terms():
    return public("Terms of service", site.terms())


@app.get("/data-deletion", response_class=HTMLResponse)
def data_deletion(code: str | None = None):
    extra = (
        f"<p><b>Deletion confirmation code:</b> {html.escape(code)}. Your data has been deleted.</p>"
        if code
        else ""
    )
    return public("Data deletion", extra + site.data_deletion())


@app.post("/api/meta/data-deletion")
async def meta_deletion(request: Request, c=Depends(conn)):
    form = await request.form()
    res = site.meta_data_deletion(c, str(form.get("signed_request", "")), str(request.base_url).rstrip("/"))
    if res is None:
        return JSONResponse({"error": "invalid signed_request"}, status_code=400)
    return JSONResponse(res)


@app.get("/connect/{platform}")
def connect(
    platform: str,
    request: Request,
    account_id: int | None = None,
    c=Depends(conn),
    user=Depends(current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    from clipping.publish import oauth

    url = oauth.authorize_url(c, platform, account_id, str(request.base_url).rstrip("/"), user["id"])
    return RedirectResponse(url, status_code=303)


@app.get("/api/oauth/{platform}/callback")
def oauth_callback(platform: str, request: Request, c=Depends(conn)):
    from clipping.publish import oauth

    res = oauth.handle_callback(c, platform, dict(request.query_params), str(request.base_url).rstrip("/"))
    return public(
        "Account connected" if res.get("ok") else "Connection rejected",
        f"<p>{html.escape(res.get('message', ''))}</p>",
    )


@app.get("/public/{name}")
def public_file(name: str):
    """Local stand-in for the bucket's public URLs (unguessable names; deleted after platforms finish processing)."""
    from clipping.storage import files

    p = (files.managed("public") / name).resolve()
    if p.parent != files.managed("public").resolve() or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4")


@app.get("/healthz")
def healthz():
    return {"ok": True}


_ = base64
