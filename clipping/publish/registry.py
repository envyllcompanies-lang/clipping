"""Adapter registry: one adapter per platform, tokens from the encrypted credential store (doc 24)."""

from __future__ import annotations

import psycopg

from clipping.publish import meta, snapchat, tiktok, youtube


def token_provider(c: psycopg.Connection):
    from clipping.accounts import credentials

    def tok(acc: dict) -> str:
        sec = credentials.load(c, acc["id"]) or {}
        if "access_token" not in sec:
            from clipping.publish.base import TokenError

            raise TokenError(f"no token for account {acc['id']}")
        return sec["access_token"]

    return tok


def adapters(c: psycopg.Connection, transport=None) -> dict:
    tok = token_provider(c)
    return {
        "youtube": youtube.YouTube(tok, transport),
        "instagram": meta.Instagram(tok, transport),
        "facebook": meta.Facebook(tok, transport),
        "threads": meta.Threads(tok, transport),
        "tiktok": tiktok.TikTok(tok, transport),
        "snapchat": snapchat.Snapchat(tok, transport),
    }
