# clipping — project guide

Automated clipping + multi-platform posting system. Owner builds solo with Claude.
Build plan (source of truth for scope and phases): https://claude.ai/artifact/N2uvncc7puJkJ3irXQJ5Tk

## Decisions already made

- Fully automatic: no human approval step. Automated gates are duplicate check + minimum score.
- Footage comes from top creators (Twitch, Kick, YouTube). No owner gameplay.
- Creator and moment selection is statistical first (radar, heatmap); the LLM writes titles and breaks ties.
- Language pages: each language gets its own accounts, sourced only from creators streaming in that language. No translation or dubbing.
- Platforms: YouTube, Instagram, TikTok, Facebook, Threads, Snapchat, Bluesky, Pinterest. X deferred until revenue.
- Existing YouTube upload code from a previous project gets wrapped as the first publisher adapter.
- Near-$0 running cost: rendering runs locally on the MacBook; scheduler/publisher runs in the cloud.
- Never screen-record clips that can't be downloaded; cut the moment from our own stream recording instead.

## Conventions

- Python 3.11+, type hints, `ruff` for lint/format, `pytest` for tests.
- One subpackage per pipeline stage under `clipping/`. Stages talk through the database, not imports of each other's internals.
- Every publisher implements `clipping.publish.base.Publisher`.
- LLM output that points into a transcript uses word indices, never raw timestamps.
- Secrets live in `.env` (never committed). Game-specific settings live in `config/games/<game>.yaml`.
