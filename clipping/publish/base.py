"""Adapter interface every platform connector implements (doc 16)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol


class PublishError(Exception):
    pass


class TransientError(PublishError):
    """Timeouts, 5xx: retry with backoff."""


class RateLimited(TransientError):
    def __init__(self, msg: str, until: dt.datetime | None = None):
        super().__init__(msg)
        self.until = until


class QuotaExceeded(PublishError):
    """Platform/project quota used up: pause this platform (or account) until `until`."""

    def __init__(self, msg: str, until: dt.datetime, scope: str = "account"):
        super().__init__(msg)
        self.until, self.scope = until, scope


class TokenError(PublishError):
    """Token revoked/expired: no retry, alert to reconnect."""


class PermanentError(PublishError):
    """Policy rejection, file spec: no retry."""


@dataclass
class Payload:
    platform: str
    account: dict
    file_path: str
    fields: dict
    public_url: str | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class Result:
    status: str  # uploading | processing | live | failed
    platform_post_id: str | None = None
    upload_session: str | None = None
    error: str | None = None
    fallback: str | None = None  # e.g. "publish_private", "inbox_draft"


class Adapter(Protocol):
    platform: str
    needs_public_url: bool

    def prepare(self, clip: dict, account: dict) -> Payload: ...
    def publish(self, payload: Payload, resume: str | None = None) -> Result: ...
    def check(self, platform_post_id: str, account: dict) -> Result: ...
    def remaining_quota(self, account: dict) -> int | None: ...
    def delete(self, platform_post_id: str, account: dict) -> bool: ...
    def stats(self, platform_post_id: str, account: dict) -> dict: ...
    def find_existing(self, payload: Payload) -> str | None: ...
