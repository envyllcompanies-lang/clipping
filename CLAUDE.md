# CLAUDE.md — Clipping

Fully automated AI clipping and multi-platform posting system for GTA 6 short-form clips.

Start with `docs/00-build-plan.md`, then the component doc for whatever you're building in `docs/components/` (01–29). The docs are the spec; follow them. Doc 26 lists what the owner does by hand; `docs/references.md` holds reference channels and repos.

## Decisions (don't revisit without the owner)

- Fully automatic: no human approval step anywhere in the pipeline. The dashboard monitors and controls; it never gates.
- Creator selection is statistical (radar signals and percentiles), not LLM opinion.
- Footage comes from top GTA 6 creators' streams and platform clip sections on Twitch, Kick and YouTube. Kick is treated the same as Twitch. No owner gameplay.
- Never screen-record clips that can't be downloaded.
- Language pages: one channel per language, sourced from native-language creators. No translation or dubbing. Launch with the top 10 GTA streaming languages (en, es, pt, ar, fr, ru, de, ja, tr, vi); weekly re-ranking and swaps in doc 28.
- Platforms: YouTube Shorts, Instagram, Facebook Reels, Threads, TikTok, Snapchat. Pinterest and Bluesky are dropped. X is deferred until revenue.
- YouTube auto-upload code already exists from a previous project; reuse it in the YouTube connector (17).
- Style is replicated from studying top GTA clipping channels' videos (format, captions, editing), stored as style profiles (13).
- Topology: an always-on VPS records, scores and schedules; the MacBook Pro M1 renders; Postgres + a short-lived bucket connect them (25).
- Storage: a clip is held only until every upload finishes, then deleted directly (never to the Trash) (21).
- Accounts and API credentials are created and linked by the owner after the build; the `accounts` tool automatically creates one email alias per language (addy.io API, no custom domain), passwords, handle checks and signup worksheets, and pulls verification codes, but platform signups themselves are manual (24, 27).

## Conventions

- Python 3.11+, one package per component (see layout in doc 25), `ruff` for lint/format, `pytest` for tests with fixture clips.
- LLMs return word indexes into the transcript, never raw timestamps.
- Work moves through Postgres job tables (`FOR UPDATE SKIP LOCKED`); workers are idempotent and restartable.
- Secrets live in `.env` locally and the host's secret manager in production. Never commit secrets or tokens.
- Each component doc ends with a "Done when" checklist; a component is done when those pass.
