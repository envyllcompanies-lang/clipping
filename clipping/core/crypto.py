"""Encryption for tokens, passwords and recovery codes (TOKEN_ENCRYPTION_KEY, Fernet)."""

from __future__ import annotations

import base64
import hashlib
import secrets
import string

from cryptography.fernet import Fernet

from clipping.core import settings


def _key() -> bytes:
    k = settings.env("TOKEN_ENCRYPTION_KEY")
    if not k:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not set")
    try:
        raw = base64.urlsafe_b64decode(k)
        if len(raw) == 32:
            return k.encode()
    except Exception:  # noqa: BLE001
        pass
    return base64.urlsafe_b64encode(hashlib.sha256(k.encode()).digest())


def encrypt(plain: str) -> bytes:
    return Fernet(_key()).encrypt(plain.encode())


def decrypt(token: bytes) -> str:
    return Fernet(_key()).decrypt(bytes(token)).decode()


def new_key() -> str:
    return Fernet.generate_key().decode()


def password(length: int = 24, symbols: str = "!@#$%^&*-_") -> str:
    alphabet = string.ascii_letters + string.digits + symbols
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
            and (not symbols or any(c in symbols for c in pw))
        ):
            return pw


def hash_user(uid: str) -> str:
    return hashlib.sha256(("chat:" + uid).encode()).hexdigest()[:16]
