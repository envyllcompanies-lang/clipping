"""YAML config loaders: games, channels, chat tokens, styles, brand, platforms."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from clipping.core.settings import ROOT

CONFIG = ROOT / "config"


def load(rel: str) -> Any:
    return yaml.safe_load((CONFIG / rel).read_text())


def save(rel: str, data: Any) -> None:
    (CONFIG / rel).write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


@lru_cache
def settings() -> dict:
    return load("settings.yaml")


def game(slug: str = "gta6") -> dict:
    return load(f"games/{slug}.yaml")


def channels() -> dict[str, dict]:
    out = {}
    for p in sorted((CONFIG / "channels").glob("*.yaml")):
        d = yaml.safe_load(p.read_text())
        out[d["code"]] = d
    return out


def chat_tokens(language: str) -> dict:
    p = CONFIG / "chat_tokens" / f"{language}.yaml"
    base = yaml.safe_load((CONFIG / "chat_tokens" / "_common.yaml").read_text())
    if p.exists():
        extra = yaml.safe_load(p.read_text()) or {}
        for k, v in extra.items():
            base[k] = list(dict.fromkeys(base.get(k, []) + v))
    return base


def style(name: str) -> dict:
    return load(f"styles/{name}.yaml")


def style_names() -> list[str]:
    return sorted(p.stem for p in (CONFIG / "styles").glob("*.yaml"))


def brand() -> dict:
    return load("brand.yaml")


def platforms() -> dict:
    return load("platforms.yaml")


def config_hash(paths: list[Path] | None = None) -> str:
    h = hashlib.sha256()
    for p in sorted(paths or CONFIG.rglob("*.yaml")):
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()
