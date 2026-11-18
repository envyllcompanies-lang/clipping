"""Settings from environment (.env locally, secret manager in production). Never log secret values."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECRET_NAMES = {
    "TWITCH_CLIENT_SECRET", "KICK_CLIENT_SECRET", "YOUTUBE_API_KEY", "LLM_API_KEY", "GOOGLE_OAUTH_CLIENT_SECRET",
    "META_APP_SECRET", "TIKTOK_CLIENT_SECRET", "SNAP_CLIENT_SECRET", "ALIAS_API_KEY", "OWNER_PHONE",
    "TOKEN_ENCRYPTION_KEY", "BUCKET_SECRET_KEY",
}


def load_dotenv(path: Path | None = None) -> None:
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_dotenv()


def env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def has(*names: str) -> bool:
    return all(env(n) for n in names)


@lru_cache
def database_url() -> str:
    return env("DATABASE_URL", "postgresql:///clipping")


def data_dir() -> Path:
    p = Path(env("CLIPPING_DATA_DIR", str(ROOT / "var")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def redact(text: str) -> str:
    for n in SECRET_NAMES:
        v = env(n)
        if v and len(v) >= 4:
            text = text.replace(v, "***")
    return text
