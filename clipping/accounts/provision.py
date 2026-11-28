"""Account Provisioning Tool (doc 27). Prepares everything for the 60 accounts (10 languages x 6 platforms) so the
owner only signs up, verifies and presses Connect. It never registers social accounts, solves CAPTCHAs or verifies
phones. Every identifier carries the language code and English name, from one template, so nothing can be mixed up."""

from __future__ import annotations

import datetime as dt
import email
import html
import re
from email.utils import parseaddr
from pathlib import Path

import httpx
import psycopg

from clipping.core import config, crypto, db, settings
from clipping.core.settings import ROOT

UTC = dt.UTC
WORKSHEETS = ROOT / "var" / "worksheets"
KITS = ROOT / "var" / "profile_kits"
CODE_TTL = dt.timedelta(minutes=10)
CODE_RE = {
    "youtube": [r"\b(G-\d{6})\b", r"\b(\d{6})\b"],
    "tiktok": [r"\b(\d{6})\b"],
    "instagram": [r"\b(\d{6})\b", r"\b(\d{8})\b"],
    "facebook": [r"\b(FB-\d{5,8})\b", r"\b(\d{5,8})\b"],
    "threads": [r"\b(\d{6})\b"],
    "snapchat": [r"\b(\d{6})\b"],
}
SENDER_PLATFORM = {
    "google.com": "youtube",
    "youtube.com": "youtube",
    "accounts.google.com": "youtube",
    "tiktok.com": "tiktok",
    "account.tiktok.com": "tiktok",
    "mail.instagram.com": "instagram",
    "instagram.com": "instagram",
    "facebookmail.com": "facebook",
    "threads.net": "threads",
    "snapchat.com": "snapchat",
}


# ---------------- naming (one template) ----------------
def names(ch: dict, platform: str, brand: dict | None = None) -> dict:
    b = brand or config.brand()
    code, lang = ch["code"], ch["language"].lower()
    rules = config.platforms()[platform]["handle"]
    if rules.get("dot"):
        handle = f"{b['handle_base']}.{code}"
    elif rules.get("underscore"):
        handle = f"{b['handle_base']}_{code}"
    else:
        handle = f"{b['handle_base']}{code}"
    return {
        "alias_local": f"{b['handle_base']}-{code}-{lang}",
        "handle": handle,
        "display": f"{b['display_base']} {ch['native_name']}",
        "label": f"Clipping/{code.upper()} {ch['language']}",
        "slot": f"{code}:{platform}",
        "description": f"GTA6 clips · {ch['language']} ({code}) · "
        + ", ".join(config.platforms()[p]["label"] for p in ch["platforms"]),
    }


def handle_variants(base: str, code: str, platform: str) -> list[str]:
    rules = config.platforms()[platform]["handle"]
    cands = [
        f"{base}.{code}",
        f"{base}_{code}",
        f"{base}{code}",
        f"{base}clips.{code}",
        f"{base}.{code}.gta6",
        f"{base}_{code}_clips",
    ]
    return [h for h in dict.fromkeys(cands) if valid_handle(h, rules)]


def valid_handle(h: str, rules: dict) -> bool:
    if not rules["min"] <= len(h) <= rules["max"]:
        return False
    if "." in h and not rules.get("dot") or "_" in h and not rules.get("underscore"):
        return False
    return re.fullmatch(f"[{rules['chars']}]+", h) is not None


# ---------------- alias providers ----------------
class Addy:
    base = "https://app.addy.io/api/v1"

    def __init__(self, key: str, domain: str, transport=None):
        self.h = httpx.Client(
            timeout=30,
            transport=transport,
            headers={
                "Authorization": f"Bearer {key}",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
            },
        )
        self.domain = domain

    def find(self, local: str) -> dict | None:
        r = self.h.get(f"{self.base}/aliases", params={"filter[search]": local, "page[size]": 100})
        r.raise_for_status()
        for a in r.json().get("data", []):
            if a.get("local_part") == local and a.get("domain") == self.domain:
                return {"id": a["id"], "address": a["email"]}
        return None

    def create(self, local: str, description: str) -> dict:
        r = self.h.post(
            f"{self.base}/aliases",
            json={"domain": self.domain, "format": "custom", "local_part": local, "description": description},
        )
        if r.status_code in (402, 403, 429):
            raise ProviderLimit(f"addy.io refused ({r.status_code}): {r.text[:120]}")
        r.raise_for_status()
        a = r.json()["data"]
        return {"id": a["id"], "address": a["email"]}


class SimpleLogin:
    base = "https://app.simplelogin.io/api"

    def __init__(self, key: str, transport=None):
        self.h = httpx.Client(timeout=30, transport=transport, headers={"Authentication": key})

    def find(self, local: str) -> dict | None:
        r = self.h.get(f"{self.base}/v2/aliases", params={"page_id": 0, "query": local})
        r.raise_for_status()
        for a in r.json().get("aliases", []):
            if a["email"].split("@")[0].startswith(local):
                return {"id": str(a["id"]), "address": a["email"]}
        return None

    def create(self, local: str, description: str) -> dict:
        opts = self.h.get(f"{self.base}/v5/alias/options").json()
        suffix = opts["suffixes"][0]
        r = self.h.post(
            f"{self.base}/v3/alias/custom/new",
            json={
                "alias_prefix": local,
                "signed_suffix": suffix["signed_suffix"],
                "note": description,
                "mailbox_ids": [opts.get("mailbox_id", 1)],
            },
        )
        if r.status_code in (402, 403, 429):
            raise ProviderLimit(f"SimpleLogin refused ({r.status_code})")
        r.raise_for_status()
        a = r.json()
        return {"id": str(a["id"]), "address": a["email"]}


class ProviderLimit(Exception):
    pass


def provider(transport=None):
    key = settings.env("ALIAS_API_KEY")
    if not key:
        return None
    if settings.env("ALIAS_PROVIDER", "addy") == "simplelogin":
        return SimpleLogin(key, transport)
    return Addy(key, settings.env("ALIAS_DOMAIN", f"{config.brand()['handle_base']}.anonaddy.com"), transport)


# ---------------- Gmail (labels + codes) ----------------
class Gmail:
    base = "https://gmail.googleapis.com/gmail/v1/users/me"

    def __init__(self, token: str, transport=None):
        self.h = httpx.Client(timeout=30, transport=transport, headers={"Authorization": f"Bearer {token}"})

    def ensure_label(self, name: str) -> str:
        labels = self.h.get(f"{self.base}/labels").json().get("labels", [])
        for lb in labels:
            if lb["name"] == name:
                return lb["id"]
        return self.h.post(
            f"{self.base}/labels",
            json={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
        ).json()["id"]

    def ensure_filter(self, alias: str, label_id: str, skip_inbox: bool = False) -> None:
        filters = self.h.get(f"{self.base}/settings/filters").json().get("filter", [])
        if any(f.get("criteria", {}).get("to") == alias for f in filters):
            return
        action = {"addLabelIds": [label_id]} | ({"removeLabelIds": ["INBOX"]} if skip_inbox else {})
        self.h.post(f"{self.base}/settings/filters", json={"criteria": {"to": alias}, "action": action})

    def recent_raw(self, after_ts: int) -> list[bytes]:
        import base64

        ids = (
            self.h.get(
                f"{self.base}/messages", params={"q": f"after:{after_ts} label:Clipping", "maxResults": 50}
            )
            .json()
            .get("messages", [])
        )
        out = []
        for m in ids:
            raw = self.h.get(f"{self.base}/messages/{m['id']}", params={"format": "raw"}).json()["raw"]
            out.append(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        return out


def gmail_client(c, transport=None) -> Gmail | None:
    r = db.one(c, "SELECT id FROM credential WHERE platform='gmail' ORDER BY id DESC LIMIT 1")
    if not r:
        return None
    import json as _json

    tok = _json.loads(crypto.decrypt(db.scalar(c, "SELECT secret_enc FROM credential WHERE id=%s", r["id"])))[
        "access_token"
    ]
    return Gmail(tok, transport)


# ---------------- handle check ----------------
def check_handle(platform: str, handle: str, client: httpx.Client | None = None) -> str:
    """404 = likely free, 200 = taken, anything else = unknown (doc 27)."""
    url = config.platforms()[platform]["profile_url"].format(handle=handle)
    client = client or httpx.Client(
        timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (handle check)"}
    )
    try:
        r = client.get(url)
    except httpx.HTTPError:
        return "unknown"
    return {404: "free", 200: "taken"}.get(r.status_code, "unknown")


# ---------------- profile kit ----------------
BIO = {
    "en": "Daily GTA 6 clips from the best streams. Credit to every creator.",
    "es": "Clips diarios de GTA 6 de los mejores directos. Crédito a cada creador.",
    "pt": "Clipes diários de GTA 6 das melhores lives. Crédito a cada criador.",
    "fr": "Des clips GTA 6 chaque jour, tirés des meilleurs lives. Crédit à chaque créateur.",
    "de": "Täglich GTA 6 Clips aus den besten Streams. Credits an jeden Creator.",
    "ru": "Ежедневные клипы GTA 6 с лучших стримов. Автор указан в каждом клипе.",
    "tr": "En iyi yayınlardan her gün GTA 6 klipleri. Her yayıncıya kredi.",
    "vi": "Clip GTA 6 mỗi ngày từ các buổi stream hay nhất. Ghi nguồn mọi streamer.",
    "ar": "مقاطع GTA 6 يومياً من أفضل البثوث. الحقوق محفوظة لكل صانع محتوى.",
    "ja": "人気配信者のGTA6名場面を毎日投稿。配信者クレジット付き。",
}


def profile_kit(c, ch: dict) -> dict:
    from PIL import Image, ImageDraw, ImageFont

    code = ch["code"]
    bio = {
        p: BIO.get(ch["stream_language"], BIO["en"])[: config.platforms()[p]["bio_max"]]
        for p in ch["platforms"]
    }
    KITS.mkdir(parents=True, exist_ok=True)
    font = ROOT / "assets" / "fonts" / "Montserrat-Black.ttf"
    b = config.brand()
    paths = {}
    for kind, size in (("avatar", (800, 800)), ("banner", (2560, 1440))):
        img = Image.new("RGB", size, (14, 17, 22))
        d = ImageDraw.Draw(img)
        f = ImageFont.truetype(str(font), int(size[1] * (0.22 if kind == "avatar" else 0.12)))
        txt = "GTA6" if kind == "avatar" else b["display_base"]
        w = d.textlength(txt, font=f)
        d.text(((size[0] - w) / 2, size[1] * 0.36), txt, font=f, fill=(255, 225, 26))
        badge = int(size[1] * 0.18)  # language corner badge (code + English name, never ambiguous)
        d.rectangle([size[0] - badge * 2, size[1] - badge, size[0], size[1]], fill=(255, 225, 26))
        fb = ImageFont.truetype(str(font), int(badge * 0.55))
        d.text(
            (size[0] - badge * 2 + badge * 0.3, size[1] - badge * 0.85),
            code.upper(),
            font=fb,
            fill=(14, 17, 22),
        )
        p = KITS / f"{code}-{ch['language'].lower()}-{kind}.png"
        img.save(p)
        paths[kind] = str(p)
    c.execute(
        """INSERT INTO profile_kit(code,bio_per_platform,avatar_path,banner_path) VALUES (%s,%s,%s,%s)
                 ON CONFLICT (code) DO UPDATE SET bio_per_platform=EXCLUDED.bio_per_platform, avatar_path=EXCLUDED.avatar_path,
                 banner_path=EXCLUDED.banner_path""",
        (code, db.j(bio), paths["avatar"], paths["banner"]),
    )
    return {"bio": bio, **paths}


# ---------------- the one command ----------------
def provision(
    c: psycopg.Connection,
    *,
    alias_api=None,
    gmail=None,
    http: httpx.Client | None = None,
    check_handles: bool = True,
    codes: list[str] | None = None,
    include_inactive: bool = False,
) -> dict:
    """Creates every missing alias, label, password, handle check, profile kit and worksheet. Idempotent."""
    stats = {
        "aliases_created": 0,
        "aliases_adopted": 0,
        "labels": 0,
        "passwords": 0,
        "handles_checked": 0,
        "kits": 0,
        "worksheets": 0,
        "skipped_filled": 0,
        "alias_errors": [],
    }
    alias_api = alias_api if alias_api is not None else provider()
    chans = {
        k: v
        for k, v in config.channels().items()
        if (v.get("active", True) or include_inactive) and (not codes or k in codes)
    }
    b = config.brand()
    for code, ch in sorted(chans.items()):
        n0 = names(ch, ch["platforms"][0], b)
        al = db.one(c, "SELECT * FROM alias WHERE code=%s", code)
        if not al and alias_api is not None:
            try:
                found = alias_api.find(n0["alias_local"])
                if found:
                    stats["aliases_adopted"] += 1
                else:
                    found = alias_api.create(n0["alias_local"], n0["description"])
                    stats["aliases_created"] += 1
                c.execute(
                    "INSERT INTO alias(provider,provider_id,address,code) VALUES (%s,%s,%s,%s)",
                    (settings.env("ALIAS_PROVIDER", "addy"), str(found["id"]), found["address"], code),
                )
                db.audit(c, "alias_created", code, {"address": found["address"]})
                al = db.one(c, "SELECT * FROM alias WHERE code=%s", code)
            except ProviderLimit as e:
                db.alert(c, "alias_provider", f"Alias provider refused: {e}. Existing aliases kept.", "alias")
                stats["alias_errors"].append(code)
        if al and gmail is not None:
            lid = gmail.ensure_label(n0["label"])
            gmail.ensure_filter(al["address"], lid)
            stats["labels"] += 1
        for platform in ch["platforms"]:
            n = names(ch, platform, b)
            slot = db.one(c, "SELECT * FROM account_slot WHERE code=%s AND platform=%s", code, platform)
            if slot and slot["status"] in ("signed_up", "connected", "verified"):
                stats["skipped_filled"] += (
                    1  # one account per slot: never a second email/password for a filled slot
                )
                continue
            if not slot:
                pw = crypto.password(24, "" if platform == "facebook" else "!@#$%^&*-_")
                c.execute(
                    """INSERT INTO account_slot(code,platform,alias_id,email,handle_planned,display_name,password_enc,
                             phone_used) VALUES (%s,%s,%s,%s,%s,%s,%s,false)""",
                    (
                        code,
                        platform,
                        al["id"] if al else None,
                        al["address"] if al else None,
                        n["handle"],
                        n["display"],
                        crypto.encrypt(pw),
                    ),
                )
                stats["passwords"] += 1
                slot = db.one(c, "SELECT * FROM account_slot WHERE code=%s AND platform=%s", code, platform)
            elif al and not slot["email"]:
                c.execute(
                    "UPDATE account_slot SET alias_id=%s, email=%s WHERE id=%s",
                    (al["id"], al["address"], slot["id"]),
                )
            if check_handles and not slot["handle_status"]:
                final, status = None, "unknown"
                for h in handle_variants(b["handle_base"], code, platform):
                    status = check_handle(platform, h, http)
                    if status == "free":
                        final = h
                        break
                    if status == "unknown":
                        final = final or h
                c.execute(
                    "UPDATE account_slot SET handle_final=%s, handle_status=%s, updated_at=now() WHERE id=%s",
                    (final or n["handle"], status, slot["id"]),
                )
                stats["handles_checked"] += 1
        if not db.one(c, "SELECT 1 FROM profile_kit WHERE code=%s", code):
            profile_kit(c, ch)
            stats["kits"] += 1
        path = WORKSHEETS / f"{code}-{ch['language'].lower()}.html"
        WORKSHEETS.mkdir(parents=True, exist_ok=True)
        doc = worksheet_html(c, code, reveal=False)
        if not path.exists() or path.read_text() != doc:
            path.write_text(doc)
            stats["worksheets"] += 1
    return stats


def worksheet_html(c, code: str | None, reveal: bool = False) -> str:
    """One page per language (or an index). Passwords masked unless revealed in the dashboard (2FA, audit-logged)."""
    chans = config.channels()
    if not code:
        rows = "".join(
            f'<li><a href="/setup?code={k}">{v["flag"]} {v["language"]} ({k})</a> — '
            f"{db.scalar(c, 'SELECT count(*) FROM account_slot WHERE code=%s AND status IN (%s,%s)', k, 'connected', 'verified')}/6 connected</li>"
            for k, v in sorted(chans.items())
        )
        return f"<!doctype html><meta name=viewport content='width=device-width'><title>Signups</title><body style='font-family:system-ui;padding:16px'><h1>Signup worksheets</h1><ul>{rows}</ul>"
    ch = chans[code]
    kit = db.one(c, "SELECT * FROM profile_kit WHERE code=%s", code) or {"bio_per_platform": {}}
    rows = []
    for s in db.all_(c, "SELECT * FROM account_slot WHERE code=%s ORDER BY platform", code):
        p = config.platforms()[s["platform"]]
        pw = crypto.decrypt(s["password_enc"]) if reveal and s["password_enc"] else "••••••••"
        codes_ = db.all_(
            c,
            "SELECT code FROM verification_code WHERE slot_code=%s AND platform=%s AND expires_at > now()",
            code,
            s["platform"],
        )
        phone = "required: use OWNER_PHONE" if p["phone"] == "required" else "skip if offered"
        rows.append(
            f"<tr><td><b>{p['label']}</b><br><a href='{p['signup']}'>sign up</a><br><small>{p['account_type']}</small></td>"
            f"<td>{html.escape(s['email'] or '(alias pending: set ALIAS_API_KEY)')}</td><td>{html.escape(s['handle_final'] or s['handle_planned'])}"
            f"<br><small>{s['handle_status'] or 'unchecked'}</small></td><td>{html.escape(s['display_name'] or '')}</td><td><code>{html.escape(pw)}</code></td>"
            f"<td><small>{html.escape((kit['bio_per_platform'] or {}).get(s['platform'], ''))}</small></td><td>{phone}<br>2FA: authenticator app</td>"
            f"<td>{s['status'].replace('_', ' ')}<br>{''.join('<b>' + html.escape(x['code']) + '</b> ' for x in codes_)}</td>"
            f"<td><a href='/connect/{s['platform']}?slot={code}:{s['platform']}'>Connect</a></td></tr>"
        )
    return (
        f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>{code} {ch['language']}</title>"
        f"<body style='font-family:system-ui;padding:16px'><h1>{ch['flag']} {ch['native_name']} · {ch['language']} ({code})</h1>"
        "<p>Sign up on each platform with exactly these details, turn on 2FA, then press Connect. Every row is for this language only.</p>"
        "<div style='overflow-x:auto'><table border=1 cellpadding=6 style='border-collapse:collapse;font-size:14px'><tr><th>Platform</th><th>Email</th>"
        "<th>Handle</th><th>Display name</th><th>Password</th><th>Bio</th><th>Phone / 2FA</th><th>Status / codes</th><th></th></tr>"
        + "".join(rows)
        + "</table></div>"
    )


def reveal_password(c, code: str, platform: str, actor: str) -> str:
    s = db.one(c, "SELECT password_enc FROM account_slot WHERE code=%s AND platform=%s", code, platform)
    db.audit(c, "password_reveal", f"{code}:{platform}", actor=actor)
    return crypto.decrypt(s["password_enc"])


# ---------------- verification codes ----------------
def route_code(c, raw: bytes, now: dt.datetime | None = None) -> dict | None:
    """Alias the mail was sent to -> language; sender domain -> platform; regex -> code. Unmatched sender shows under
    'Unmatched' on that language's page; never in another language's rows."""
    now = now or dt.datetime.now(UTC)
    msg = email.message_from_bytes(raw)
    to_addrs = [
        parseaddr(v)[1].lower() for k in ("Delivered-To", "X-Original-To", "To") for v in msg.get_all(k, [])
    ]
    alias = db.one(c, "SELECT * FROM alias WHERE lower(address) = ANY(%s)", to_addrs)
    if not alias:
        return None
    sender = parseaddr(msg.get("From", ""))[1].lower().split("@")[-1]
    platform = next(
        (p for dom, p in SENDER_PLATFORM.items() if sender == dom or sender.endswith("." + dom)), None
    )
    body = ""
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_type() in ("text/plain", "text/html"):
            body += (part.get_payload(decode=True) or b"").decode(errors="ignore")
    text = msg.get("Subject", "") + " " + re.sub(r"<[^>]+>", " ", body)
    code = None
    for pat in CODE_RE.get(platform or "", [r"\b(\d{6})\b"]):
        m = re.search(pat, text)
        if m:
            code = m.group(1)
            break
    if not code:
        return None
    c.execute(
        "INSERT INTO verification_code(slot_code,platform,code,expires_at) VALUES (%s,%s,%s,%s)",
        (alias["code"], platform or "unmatched", code, now + CODE_TTL),
    )
    return {"code": alias["code"], "platform": platform or "unmatched", "value": code}


def purge_codes(c) -> int:
    return c.execute("DELETE FROM verification_code WHERE expires_at <= now()").rowcount


# ---------------- connect check ----------------
def connect_check(c, account_id: int, platform: str, ident: dict) -> tuple[bool | str, object]:
    """The connected account's handle must match this slot's planned/recorded handle and carry its language code.
    Returns (True, platform_id) or (message, None)."""
    acc = db.one(
        c, "SELECT a.*, ch.key FROM account a JOIN channel ch ON ch.id=a.channel_id WHERE a.id=%s", account_id
    )
    code = (acc["key"] or "").split("-")[-1]
    slot = db.one(c, "SELECT * FROM account_slot WHERE code=%s AND platform=%s", code, platform)
    if not slot:
        return True, ident.get("id")  # self-serve users (audit flow) have no slot
    if platform in ("facebook", "instagram"):
        pages = ident.get("pages", [])
        want = {slot["handle_final"], slot["handle_planned"]} - {None}
        for pg in pages:
            ig = pg.get("instagram_business_account") or {}
            h = ig.get("username") if platform == "instagram" else (pg.get("username") or pg.get("name"))
            if h and (h in want or (h.lower().endswith(code) and code in h.lower())):
                c.execute(
                    "UPDATE account_slot SET status='connected', handle_final=%s, connected_account_id=%s WHERE id=%s",
                    (h, account_id, slot["id"]),
                )
                return True, {
                    "id": ig.get("id") if platform == "instagram" else pg["id"],
                    "page_token": pg.get("access_token"),
                }
        found = (
            ", ".join(
                filter(
                    None,
                    (
                        (pg.get("instagram_business_account") or {}).get("username") or pg.get("name")
                        for pg in pages
                    ),
                )
            )
            or "no page"
        )
        db.audit(c, "connect_mismatch", slot["code"] + ":" + platform, {"found": found})
        return (
            f"This is {found}, not {code}:{platform} ({slot['handle_final'] or slot['handle_planned']}).",
            None,
        )
    found = (ident.get("handle") or "").lower()
    want = {(slot["handle_final"] or "").lower(), (slot["handle_planned"] or "").lower()} - {""}
    if found in want or (code in found and re.search(rf"[._]?{code}$|[._]{code}[._]", found)):
        c.execute(
            "UPDATE account_slot SET status='connected', handle_final=%s, connected_account_id=%s WHERE id=%s",
            (ident.get("handle"), account_id, slot["id"]),
        )
        return True, ident.get("id")
    db.audit(c, "connect_mismatch", f"{code}:{platform}", {"found": found})
    return (
        f"This is {ident.get('handle') or 'an unknown account'}, not {code}:{platform} ({slot['handle_final'] or slot['handle_planned']}).",
        None,
    )


def mark_verified(c, code: str, platform: str) -> None:
    c.execute(
        "UPDATE account_slot SET status='verified' WHERE code=%s AND platform=%s AND status='connected'",
        (code, platform),
    )
    c.execute(
        """UPDATE account SET status='verified' WHERE id=(SELECT connected_account_id FROM account_slot WHERE code=%s AND platform=%s)""",
        (code, platform),
    )


def archive_language(c, code: str) -> None:
    """Language swapped out (doc 28): slots archived, aliases kept so recovery mail still arrives."""
    c.execute("UPDATE account_slot SET archived=true WHERE code=%s", (code,))


_ = Path
