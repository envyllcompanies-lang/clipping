"""OAuth connect flows (docs 17-20, 24, 29): authorize URL with signed state, code exchange, identity read-back,
connect check against the account slot (doc 27), then the encrypted credential store."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse

import httpx

from clipping.core import db, settings

PROVIDERS = {
    "youtube": {
        "auth": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "client": ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"),
        "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly "
        "https://www.googleapis.com/auth/yt-analytics.readonly",
        "extra": {"access_type": "offline", "prompt": "consent"},
    },
    "facebook": {
        "auth": "https://www.facebook.com/v21.0/dialog/oauth",
        "token": "https://graph.facebook.com/v21.0/oauth/access_token",
        "client": ("META_APP_ID", "META_APP_SECRET"),
        "scope": "pages_show_list,pages_read_engagement,pages_manage_posts,publish_video,instagram_basic,instagram_content_publish,"
        "instagram_manage_insights,business_management",
        "extra": {},
    },
    "threads": {
        "auth": "https://threads.net/oauth/authorize",
        "token": "https://graph.threads.net/oauth/access_token",
        "client": ("META_APP_ID", "META_APP_SECRET"),
        "scope": "threads_basic,threads_content_publish,threads_manage_insights",
        "extra": {},
    },
    "tiktok": {
        "auth": "https://www.tiktok.com/v2/auth/authorize/",
        "token": "https://open.tiktokapis.com/v2/oauth/token/",
        "client": ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"),
        "scope": "user.info.basic,video.publish,video.upload,video.list",
        "extra": {},
        "client_param": "client_key",
    },
    "snapchat": {
        "auth": "https://accounts.snapchat.com/login/oauth2/authorize",
        "token": "https://accounts.snapchat.com/login/oauth2/access_token",
        "client": ("SNAP_CLIENT_ID", "SNAP_CLIENT_SECRET"),
        "scope": "snapchat-profile-api",
        "extra": {},
    },
}
PROVIDERS["instagram"] = PROVIDERS[
    "facebook"
]  # Instagram professional accounts connect through Facebook login


def _key() -> bytes:
    return hashlib.sha256(
        ("oauth-state:" + (settings.env("TOKEN_ENCRYPTION_KEY") or "dev")).encode()
    ).digest()


def make_state(platform: str, account_id: int | None, user_id: int) -> str:
    body = json.dumps(
        {"p": platform, "a": account_id, "u": user_id, "t": int(time.time()), "n": secrets.token_hex(4)}
    )
    sig = hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()[:24]
    return urllib.parse.quote(f"{body}|{sig}")


def read_state(state: str) -> dict | None:
    try:
        body, sig = urllib.parse.unquote(state).rsplit("|", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()[:24], sig):
        return None
    d = json.loads(body)
    return d if time.time() - d["t"] < 3600 else None


def redirect_uri(base: str, platform: str) -> str:
    return f"{settings.env('PUBLIC_BASE', base)}/api/oauth/{platform}/callback"


def authorize_url(c, platform: str, account_id: int | None, base: str, user_id: int) -> str:
    p = PROVIDERS[platform]
    cid = settings.env(p["client"][0])
    if not cid:
        return f"/accounts?missing={p['client'][0]}"
    q = {
        p.get("client_param", "client_id"): cid,
        "redirect_uri": redirect_uri(base, platform),
        "response_type": "code",
        "scope": p["scope"],
        "state": make_state(platform, account_id, user_id),
        **p["extra"],
    }
    return p["auth"] + "?" + urllib.parse.urlencode(q)


def exchange(platform: str, code: str, base: str, transport=None) -> dict:
    p = PROVIDERS[platform]
    data = {
        p.get("client_param", "client_id"): settings.env(p["client"][0]),
        "client_secret": settings.env(p["client"][1]),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri(base, platform),
    }
    r = httpx.Client(timeout=30, transport=transport).post(p["token"], data=data)
    r.raise_for_status()
    return r.json()


def identity(platform: str, token: dict, transport=None) -> dict:
    """Read the connected account's identity back (handle/name/id) for the connect check."""
    h = httpx.Client(timeout=30, transport=transport)
    at = token["access_token"]
    if platform == "youtube":
        d = h.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {at}"},
        ).json()
        it = (d.get("items") or [{}])[0]
        return {
            "id": it.get("id"),
            "handle": (it.get("snippet", {}).get("customUrl") or "").lstrip("@"),
            "name": it.get("snippet", {}).get("title"),
        }
    if platform in ("facebook", "instagram"):
        pages = (
            h.get(
                "https://graph.facebook.com/v21.0/me/accounts",
                params={
                    "access_token": at,
                    "fields": "id,name,username,access_token,instagram_business_account{id,username}",
                },
            )
            .json()
            .get("data", [])
        )
        return {"pages": pages}
    if platform == "threads":
        d = h.get(
            "https://graph.threads.net/v1.0/me", params={"access_token": at, "fields": "id,username"}
        ).json()
        return {"id": d.get("id"), "handle": d.get("username")}
    if platform == "tiktok":
        d = (
            h.get(
                "https://open.tiktokapis.com/v2/user/info/",
                params={"fields": "open_id,username,display_name"},
                headers={"Authorization": f"Bearer {at}"},
            )
            .json()
            .get("data", {})
            .get("user", {})
        )
        return {"id": d.get("open_id"), "handle": d.get("username"), "name": d.get("display_name")}
    if platform == "snapchat":
        return {"id": token.get("profile_id"), "handle": token.get("username")}
    return {}


def handle_callback(c, platform: str, query: dict, base: str, transport=None) -> dict:
    st = read_state(query.get("state", ""))
    if not st or st["p"] != platform:
        return {
            "ok": False,
            "message": "This sign-in link expired or was tampered with. Start again from the dashboard.",
        }
    if "error" in query:
        return {
            "ok": False,
            "message": f"{platform} said: {query.get('error_description') or query['error']}",
        }
    token = exchange(platform, query["code"], base, transport)
    ident = identity(platform, token, transport)
    acc_id = st["a"]
    if acc_id is None:  # self-serve user (TikTok audit flow): their own account row
        acc_id = _user_account(c, st["u"], platform)
    try:
        from clipping.accounts import provision

        found, plat_id = provision.connect_check(c, acc_id, platform, ident)
    except ImportError:
        found, plat_id = None, ident.get("id")
    if found is not None and found is not True:
        db.audit(c, "connect_rejected", f"{platform}:{acc_id}", {"found": found})
        return {"ok": False, "message": found}
    from clipping.accounts import credentials

    exp = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=int(token.get("expires_in", 3600)))
    secret = {
        k: v
        for k, v in token.items()
        if k in ("access_token", "refresh_token", "token_type", "open_id", "scope")
    }
    if platform in ("facebook", "instagram") and isinstance(plat_id, dict):
        secret["access_token"] = plat_id.get("page_token") or secret["access_token"]
        plat_id = plat_id.get("id")
    credentials.store(c, acc_id, platform, "oauth", secret, exp, token.get("scope", ""))
    c.execute(
        "UPDATE account SET platform_account_id=%s, handle=COALESCE(%s, handle) WHERE id=%s",
        (plat_id, ident.get("handle"), acc_id),
    )
    return {"ok": True, "message": f"Connected {platform} account {ident.get('handle') or plat_id}."}


def _user_account(c, user_id: int, platform: str) -> int:
    ch = db.scalar(
        c,
        "INSERT INTO channel(key,language,time_zone) VALUES (%s,'en','UTC') ON CONFLICT (key) DO UPDATE SET key=EXCLUDED.key RETURNING id",
        f"user-{user_id}",
    )
    return db.scalar(
        c,
        """INSERT INTO account(channel_id,platform) VALUES (%s,%s) ON CONFLICT (channel_id,platform)
                           DO UPDATE SET platform=EXCLUDED.platform RETURNING id""",
        ch,
        platform,
    )


def refreshers(transport=None) -> dict:
    """platform -> fn(secret) -> (new_secret, expiry) for credentials.refresh_all."""

    def make(platform):
        def fn(secret: dict):
            p = PROVIDERS[platform]
            if platform in ("facebook", "instagram"):
                r = httpx.Client(timeout=30, transport=transport).get(
                    p["token"],
                    params={
                        "grant_type": "fb_exchange_token",
                        "client_id": settings.env(p["client"][0]),
                        "client_secret": settings.env(p["client"][1]),
                        "fb_exchange_token": secret["access_token"],
                    },
                )
            elif platform == "threads":
                r = httpx.Client(timeout=30, transport=transport).get(
                    "https://graph.threads.net/refresh_access_token",
                    params={"grant_type": "th_refresh_token", "access_token": secret["access_token"]},
                )
            else:
                r = httpx.Client(timeout=30, transport=transport).post(
                    p["token"],
                    data={
                        p.get("client_param", "client_id"): settings.env(p["client"][0]),
                        "client_secret": settings.env(p["client"][1]),
                        "grant_type": "refresh_token",
                        "refresh_token": secret.get("refresh_token", ""),
                    },
                )
            r.raise_for_status()
            d = r.json()
            new = dict(
                secret,
                access_token=d["access_token"],
                **({"refresh_token": d["refresh_token"]} if d.get("refresh_token") else {}),
            )
            return new, dt.datetime.now(dt.UTC) + dt.timedelta(seconds=int(d.get("expires_in", 3600)))

        return fn

    return {p: make(p) for p in PROVIDERS}
