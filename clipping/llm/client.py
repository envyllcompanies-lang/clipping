"""LLM access for tie-breaks and writing (docs 09, 14). Provider from LLM_PROVIDER (anthropic default), key from
LLM_API_KEY, monthly ceiling LLM_MONTHLY_BUDGET_USD. Without a key every call returns None and callers use their
rule-based fallback, so the pipeline never blocks on the LLM."""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx

from clipping.core import settings
from clipping.core.http import request

PRICES = {
    "claude-sonnet-5-5": (3.0, 15.0),
    "claude-haiku-5-5": (1.0, 5.0),
    "claude-opus-5-5": (5.0, 25.0),
}  # USD per Mtok in/out


def model() -> str:
    return settings.env("LLM_MODEL", "claude-sonnet-5-5")


def available() -> bool:
    return bool(settings.env("LLM_API_KEY"))


def _spent_this_month(c) -> float:
    from clipping.core import db

    return float(
        db.scalar(
            c,
            "SELECT coalesce(sum((details->>'usd')::float),0) FROM audit_log WHERE action='llm_call' "
            "AND at >= date_trunc('month', now())",
        )
        or 0
    )


def call_json(
    prompt: str,
    system: str = "",
    max_tokens: int = 1500,
    c=None,
    transport: httpx.BaseTransport | None = None,
) -> dict | None:
    if not available():
        return None
    budget = float(settings.env("LLM_MONTHLY_BUDGET_USD", "0") or 0)
    if c is not None and budget > 0 and _spent_this_month(c) >= budget:
        return None
    provider = settings.env("LLM_PROVIDER", "anthropic")
    client = httpx.Client(timeout=120, transport=transport)
    if provider == "anthropic":
        r = request(
            client,
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.env("LLM_API_KEY"),
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model(),
                "max_tokens": max_tokens,
                "system": system + "\nReply with one JSON object only.",
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        d = r.json()
        text = "".join(b.get("text", "") for b in d.get("content", []))
        usage = d.get("usage", {})
        tin, tout = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    else:  # OpenAI-compatible chat completions
        r = request(
            client,
            "POST",
            settings.env("LLM_BASE_URL", "https://api.openai.com/v1") + "/chat/completions",
            headers={"Authorization": f"Bearer {settings.env('LLM_API_KEY')}"},
            json={
                "model": model(),
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            },
        )
        d = r.json()
        text = d["choices"][0]["message"]["content"]
        tin, tout = d.get("usage", {}).get("prompt_tokens", 0), d.get("usage", {}).get("completion_tokens", 0)
    pin, pout = PRICES.get(model(), (3.0, 15.0))
    usd = tin / 1e6 * pin + tout / 1e6 * pout
    if c is not None:
        from clipping.core import db

        db.audit(
            c,
            "llm_call",
            model(),
            {"usd": round(usd, 5), "in": tin, "out": tout, "at": dt.datetime.now(dt.UTC).isoformat()},
        )
    return parse_json(text)


def parse_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
