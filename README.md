# Clipping

Fully automated AI clipping and posting for GTA 6: finds the top GTA 6 streamers on Twitch, Kick and YouTube, records their streams, finds the best moments by the numbers, edits them into vertical clips in the style of the best clip channels, and posts them to YouTube Shorts, TikTok, Instagram, Facebook Reels, Threads and Snapchat, with one set of pages per language (10 at launch).

## Docs

- [Build plan](docs/00-build-plan.md): overview, research findings, architecture, phases
- [Component docs](docs/components/): one detailed spec per component (01–30)
- [Owner setup checklist](docs/components/26-owner-setup-checklist.md): what has to be done by hand, and when
- [References](docs/references.md): reference channels, guides and open-source projects
- [Kickoff prompt](docs/KICKOFF.md): paste into Claude Code to start the build
- [CLAUDE.md](CLAUDE.md): decisions and conventions for building with Claude Code

## Status

All 7 build phases are implemented and tested; what remains needs the owner's keys and accounts (see `BUILD_LOG.md` → Needs B).

## Quick start

```bash
uv venv -p 3.11 .venv && uv pip install -e ".[asr,dev]"   # plus ".[audio]" on the MacBook for Demucs/PANNs
cp .env.example .env                                       # fill in keys as you get them; set TOKEN_ENCRYPTION_KEY
clip db migrate
clip dashboard create-owner --email you@example.com        # prints the 2FA secret for your authenticator app
clip worker server      # VPS: radar, recorder, chat, clips, heatmap, scheduler, publishers, analytics
clip worker m1          # MacBook: audio cleanup, transcription, events, build/render
clip dashboard serve    # phone-friendly dashboard + public policy pages
clip accounts provision # aliases, passwords, handle checks, worksheets for the 60 accounts
clip run window.ts      # make clips from one window file, offline
make test               # unit tests (fast); make test-all includes the slow end-to-end test
make backtest-all       # every stage backtest against eval/thresholds.yaml and the accepted baselines
```

Deployment: `docker-compose.yml` (VPS), `deploy/systemd/` units, `deploy/launchd/com.clipping.m1.plist` (MacBook), `scripts/backup.sh` / `restore.sh`.
