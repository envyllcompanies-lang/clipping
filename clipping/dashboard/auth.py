"""Dashboard auth: scrypt password hashes, TOTP 2FA (RFC 6238) for the owner, HMAC-signed session cookies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time

from clipping.core import crypto, db, settings


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        _, s, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(s), n=2**14, r=8, p=1)
        return hmac.compare_digest(got, base64.b64decode(h))
    except ValueError:
        return False


def new_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def totp(secret: str, t: float | None = None, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = int((t or time.time()) // step)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[o : o + 4])[0] & 0x7FFFFFFF) % 10**digits
    return str(code).zfill(digits)


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    now = time.time()
    return any(
        hmac.compare_digest(totp(secret, now + k * 30), code.strip()) for k in range(-window, window + 1)
    )


def _key() -> bytes:
    return hashlib.sha256(
        ("session:" + (settings.env("TOKEN_ENCRYPTION_KEY") or "dev-only")).encode()
    ).digest()


def sign(user_id: int, ttl_s: int = 7 * 86400) -> str:
    payload = f"{user_id}:{int(time.time()) + ttl_s}"
    sig = hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}:{sig}"


def unsign(token: str | None) -> int | None:
    if not token:
        return None
    try:
        uid, exp, sig = token.split(":")
    except ValueError:
        return None
    good = hmac.new(_key(), f"{uid}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(good, sig) or int(exp) < time.time():
        return None
    return int(uid)


def create_user(c, email: str, password: str, owner: bool = False) -> tuple[int, str | None]:
    secret = new_totp_secret() if owner else None
    uid = db.scalar(
        c,
        "INSERT INTO app_user(email,password_hash,totp_secret_enc,is_owner) VALUES (%s,%s,%s,%s) RETURNING id",
        email.lower(),
        hash_password(password),
        crypto.encrypt(secret) if secret else None,
        owner,
    )
    return uid, secret


def login(c, email: str, password: str, code: str | None) -> int | None:
    u = db.one(c, "SELECT * FROM app_user WHERE email=%s", email.lower())
    if not u or not check_password(password, u["password_hash"]):
        return None
    if u["totp_secret_enc"]:
        if not code or not verify_totp(crypto.decrypt(u["totp_secret_enc"]), code):
            return None
    return u["id"]
