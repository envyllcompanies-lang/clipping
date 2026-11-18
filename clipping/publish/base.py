"""Shared interface every platform publisher implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class PostStatus(str, Enum):
    QUEUED = "queued"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    LIVE = "live"
    FAILED = "failed"


@dataclass
class ClipPayload:
    path: str              # local file
    public_url: str | None # required by platforms that pull from a URL (Instagram, TikTok)
    title: str
    caption: str
    hashtags: list[str]
    duration_s: float


@dataclass
class PublishResult:
    status: PostStatus
    platform_post_id: str | None = None
    error: str | None = None


class Publisher(ABC):
    """One adapter per platform. Adding a platform = one new subclass."""

    platform: str

    @abstractmethod
    def publish(self, clip: ClipPayload, account: str) -> PublishResult:
        """Start publishing. May return PROCESSING; call check() until LIVE or FAILED."""

    @abstractmethod
    def check(self, platform_post_id: str, account: str) -> PublishResult:
        """Poll an in-flight post."""

    @abstractmethod
    def remaining_quota(self, account: str) -> int | None:
        """Posts left in the platform's rolling window, if the platform reports it."""
