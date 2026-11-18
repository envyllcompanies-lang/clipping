# clipping

Automated short-form clipping and multi-platform posting. GTA 6 is the first game.

The system finds the top creators in a game by the numbers, records their streams, scores
moments statistically, cuts vertical clips, and publishes them to every connected platform
with no human approval step.

Full build plan: [GTA 6 AI Clipper — Build Plan](https://claude.ai/artifact/N2uvncc7puJkJ3irXQJ5Tk)

## Pipeline

```
ingest → analyze → edit → package → auto-gate → publish → analytics
   ↑                                                         │
   └──────── radar + tracker ◄──── results re-weight scoring ┘
```

| Stage | Package | What it does |
| --- | --- | --- |
| Radar | `clipping/radar` | Ranks creators (Twitch, Kick, YouTube stats) and tracks top clip channels |
| Ingest | `clipping/ingest` | Records streams, pulls VODs and clips |
| Analyze | `clipping/analyze` | Transcribes, builds the moment heatmap (clip density, chat velocity, audio), scores windows |
| Edit | `clipping/edit` | Cold-open hook, 9:16 reframe, captions, audio mix, render |
| Package | `clipping/package` | Titles, hashtags and captions per platform and language |
| Publish | `clipping/publish` | One adapter per platform behind a shared interface |
| Scheduler | `clipping/scheduler` | Posting slots per account, platform limits, retries |
| Analytics | `clipping/analytics` | Pulls stats, fits scoring weights |

## Platforms

YouTube Shorts · Instagram Reels · TikTok · Facebook Reels · Threads · Snapchat Spotlight ·
Bluesky · Pinterest. X is deferred until there's revenue.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in API credentials
```

Requires FFmpeg on the PATH.

## Layout

```
clipping/        Python package (one subpackage per stage)
config/          Game profiles and channel configs
db/              Database schema
dashboard/       Monitoring dashboard (web)
tests/
```
