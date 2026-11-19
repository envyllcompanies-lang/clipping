"""Public site & policy pages (doc 29): landing, privacy, terms, data-deletion instructions, Meta data-deletion
callback, OAuth redirect URIs. Text is generated from the brand config; the owner reads it once before reviews."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets

from clipping.core import config, db, settings


def brand() -> dict:
    b = config.brand()
    return {
        "brand": b["name"],
        "contact": settings.env("CONTACT_EMAIL")
        or f"{b['handle_base']}-contact@(alias created by the accounts tool)",
    }


def landing() -> str:
    b = brand()["brand"]
    return f"""<p>{b} is a publishing tool that turns highlights from GTA 6 livestreams into short vertical clips and publishes them
to the operator's own accounts on YouTube, TikTok, Instagram, Facebook, Threads and Snapchat.</p>
<p>Every clip credits the original creator on screen and in the caption. Creators can ask for removal at any time and are removed
from every channel automatically.</p><p><a href="/login">Sign in</a> · <a href="/signup">Create an account</a></p>"""


def privacy() -> str:
    b = brand()
    return f"""<p>Last updated: 2026-11-18. This policy explains what {b["brand"]} collects and why.</p>
<h2>What we collect</h2><ul><li>Account identifiers of the social accounts you connect (user ID, username, page or channel name).</li>
<li>OAuth access and refresh tokens for those accounts, stored encrypted.</li><li>Post metadata: titles, captions, platform post IDs, posting times.</li>
<li>Analytics the platforms return for posts made through the service (views, likes, comments, shares, retention).</li>
<li>Your login email and a hashed password; owners also store a 2FA secret, encrypted.</li></ul>
<h2>Why</h2><p>Only to publish the clips you schedule, show their status and performance, and keep the service secure.</p>
<h2>Retention</h2><ul><li>Tokens: until you disconnect the account or delete your data.</li><li>Video files: deleted as soon as every upload finishes
(usually within hours; at most 72 hours).</li><li>Post records and statistics: kept while your account exists, for analytics.</li></ul>
<h2>Third parties</h2><p>Platform APIs you connect (Google/YouTube, Meta, TikTok, Snap), the hosting provider, the database and storage provider,
and an AI language-model provider used to write titles and captions (it receives transcript text, never your tokens).
We do not sell data.</p>
<h2>Your rights</h2><p>You can disconnect any account at any time and request deletion of all your data (see <a href="/data-deletion">data deletion</a>).
Contact: {b["contact"]}.</p>"""


def terms() -> str:
    b = brand()
    return f"""<p>Last updated: 2026-11-18. By using {b["brand"]} you agree to these terms.</p>
<h2>The service</h2><p>{b["brand"]} lets you publish short clips to social accounts you own or manage through each platform's official API.</p>
<h2>Acceptable use</h2><ul><li>Only connect accounts you are authorized to use.</li><li>Follow each platform's terms and community guidelines.</li>
<li>Do not publish content you don't have the right to publish; honor removal requests from creators.</li></ul>
<h2>Termination</h2><p>You can stop using the service and delete your data at any time. We may suspend accounts that break these terms.</p>
<h2>Liability</h2><p>The service is provided "as is", without warranties. To the extent the law allows, we are not liable for indirect or
consequential losses, platform decisions, or loss of reach or revenue.</p><p>Contact: {b["contact"]}.</p>"""


def data_deletion() -> str:
    b = brand()
    return f"""<h2>Disconnect and delete your data</h2><ol><li>Sign in and open <b>Accounts</b>, then press <b>Disconnect</b> on each account.
Tokens are deleted immediately.</li><li>To delete everything (accounts, post records, statistics), email {b["contact"]} from your login email
with the subject "Delete my data". We confirm within 7 days.</li><li>If you connected through Facebook or Instagram, you can also remove the app in
Facebook Settings → Apps and Websites; Meta notifies us and we delete your data automatically.</li></ol>"""


def parse_signed_request(signed_request: str, app_secret: str) -> dict | None:
    """Meta signed_request: base64url(signature).base64url(payload), HMAC-SHA256 with the app secret."""
    try:
        sig_b64, payload_b64 = signed_request.split(".", 1)
        pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
        sig = base64.urlsafe_b64decode(pad(sig_b64))
        payload = json.loads(base64.urlsafe_b64decode(pad(payload_b64)))
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("algorithm", "").upper() != "HMAC-SHA256":
        return None
    good = hmac.new(app_secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return payload if hmac.compare_digest(sig, good) else None


def meta_data_deletion(c, signed_request: str, base_url: str) -> dict | None:
    secret = settings.env("META_APP_SECRET")
    if not secret:
        return None
    payload = parse_signed_request(signed_request, secret)
    if not payload or not payload.get("user_id"):
        return None
    uid = str(payload["user_id"])
    accs = db.all_(
        c,
        "SELECT id FROM account WHERE platform IN ('instagram','facebook','threads') AND platform_account_id=%s",
        uid,
    )
    for a in accs:
        c.execute("DELETE FROM credential WHERE account_id=%s", (a["id"],))
        c.execute(
            "UPDATE account SET status='disconnected', token_ref=NULL, platform_account_id=NULL WHERE id=%s",
            (a["id"],),
        )
    code = secrets.token_hex(8)
    db.audit(c, "meta_data_deletion", uid, {"accounts": [a["id"] for a in accs], "code": code})
    return {"url": f"{base_url}/data-deletion?code={code}", "confirmation_code": code}
