"""Snapchat Spotlight connector (doc 20): Public Profile API (allowlist only). Media is encrypted with AES-256-CBC
(fresh key and IV per upload) before upload, then a Spotlight post references it. Spotlight is 9:16 up to 60 s.
Deleting isn't supported by the API, so takedowns become manual tasks. Endpoint paths follow Snap's Public Profile
API docs; confirm them once the allowlist is granted (the adapter is built and tested against a mock)."""

from __future__ import annotations

import base64
import datetime as dt
import os
from collections.abc import Callable

import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from clipping.core import settings
from clipping.publish.base import Payload, PermanentError, RateLimited, Result, TokenError, TransientError

API = "https://businessapi.snapchat.com/public/v1"
CHUNK = 32 * 1024 * 1024


def encrypt(data: bytes) -> tuple[bytes, bytes, bytes]:
    key, iv = os.urandom(32), os.urandom(16)
    p = padding.PKCS7(128).padder()
    padded = p.update(data) + p.finalize()
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return enc.update(padded) + enc.finalize(), key, iv


def decrypt(blob: bytes, key: bytes, iv: bytes) -> bytes:
    d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = d.update(blob) + d.finalize()
    u = padding.PKCS7(128).unpadder()
    return u.update(padded) + u.finalize()


class Snapchat:
    platform = "snapchat"
    needs_public_url = False

    def __init__(self, token: Callable[[dict], str], transport: httpx.BaseTransport | None = None):
        self.token = token
        self.http = httpx.Client(timeout=300, transport=transport)
        self.base = settings.env("SNAP_API_BASE", API)

    def _req(self, method: str, path: str, acc: dict, **kw) -> dict:
        try:
            r = self.http.request(
                method, f"{self.base}/{path}", headers={"Authorization": f"Bearer {self.token(acc)}"}, **kw
            )
        except httpx.TransportError as e:
            raise TransientError(str(e)) from e
        if r.status_code == 401:
            raise TokenError("Snap token invalid")
        if r.status_code == 429:
            raise RateLimited("Snap rate limit", dt.datetime.now(dt.UTC) + dt.timedelta(minutes=10))
        if r.status_code >= 500:
            raise TransientError(f"Snap {r.status_code}")
        if r.status_code >= 400:
            raise PermanentError(f"Snap {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}

    def prepare(self, clip: dict, account: dict) -> Payload:
        if (clip.get("duration_s") or 0) > 60:
            raise PermanentError("Spotlight takes up to 60 s")
        f = (clip.get("packaging") or {}).get("fields", {}).get("snapchat", {})
        return Payload(
            "snapchat",
            account,
            clip["path"],
            {"description": f.get("text", "")[:160]},
            meta={"cv": clip["id"]},
        )

    def publish(self, payload: Payload, resume: str | None = None) -> Result:
        acc = payload.account
        if resume:
            return self.check(resume, acc)
        prof = acc["platform_account_id"]
        blob, key, iv = encrypt(open(payload.file_path, "rb").read())
        media = self._req(
            "POST",
            f"public_profiles/{prof}/media",
            acc,
            json={
                "type": "VIDEO",
                "name": f"clip-{payload.meta['cv']}",
                "key": base64.b64encode(key).decode(),
                "iv": base64.b64encode(iv).decode(),
            },
        )
        mid = media["media_id"]
        parts = [blob[i : i + CHUNK] for i in range(0, len(blob), CHUNK)] or [b""]
        for n, part in enumerate(parts, 1):
            self._req(
                "POST",
                f"public_profiles/{prof}/media/{mid}/multipart-upload",
                acc,
                params={"action": "UPLOAD_PART"},
                files={"file": (f"part{n}", part)},
                data={"part_number": str(n)},
            )
        self._req(
            "POST", f"public_profiles/{prof}/media/{mid}/multipart-upload", acc, params={"action": "FINALIZE"}
        )
        post = self._req(
            "POST",
            f"public_profiles/{prof}/spotlights",
            acc,
            json={
                "media_id": mid,
                "description": payload.fields["description"],
                "locale": acc.get("locale", "en_US"),
            },
        )
        return Result("processing", post.get("id") or mid, upload_session=post.get("id") or mid)

    def check(self, post_id: str, account: dict) -> Result:
        d = self._req(
            "GET", f"public_profiles/{account['platform_account_id']}/spotlights/{post_id}", account
        )
        st = (d.get("status") or "").upper()
        if st in ("PUBLISHED", "LIVE", "ACTIVE"):
            return Result("live", post_id)
        if st in ("FAILED", "REJECTED"):
            return Result("failed", post_id, error=d.get("reason") or st)
        return Result("processing", post_id)

    def remaining_quota(self, account: dict) -> int | None:
        return None

    def delete(self, post_id: str, account: dict) -> bool:
        raise PermanentError("Snapchat API can't delete posts: manual task in the dashboard")

    def find_existing(self, payload: Payload) -> str | None:
        return None

    def stats(self, post_id: str, account: dict) -> dict:
        d = self._req(
            "GET", f"public_profiles/{account['platform_account_id']}/spotlights/{post_id}/stats", account
        )
        return {"views": d.get("views", 0), "shares": d.get("shares", 0)}
