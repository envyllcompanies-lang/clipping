"""HTTP with retry/backoff for every external call (docs 16, 25)."""

from __future__ import annotations

import time
from typing import Any

import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}


class HttpError(Exception):
    def __init__(self, status: int, body: str, url: str = ""):
        super().__init__(f"HTTP {status} {url}: {body[:300]}")
        self.status = status
        self.body = body


def request(client: httpx.Client, method: str, url: str, *, retries: int = 4, base_delay: float = 1.0,
            sleep=time.sleep, **kw: Any) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = client.request(method, url, **kw)
        except (httpx.TransportError, httpx.TimeoutException) as e:
            last = e
        else:
            if r.status_code not in RETRY_STATUS:
                if r.status_code >= 400:
                    raise HttpError(r.status_code, r.text, url)
                return r
            last = HttpError(r.status_code, r.text, url)
            ra = r.headers.get("Retry-After")
            if ra and ra.isdigit():
                sleep(min(int(ra), 60))
                continue
        if attempt < retries:
            sleep(base_delay * (2**attempt))
    assert last is not None
    raise last
