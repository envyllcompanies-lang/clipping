# Claude Code kickoff prompt

Paste this into Claude Code (ultracode mode) from the repo root.

```
You are building the GTA 6 AI clipping and auto-posting system in this repo. The docs are the full spec; your job is to turn them into working, tested software with as little input from me as possible.

READ FIRST
1. CLAUDE.md: decisions and conventions. They override anything else; don't change a decision without asking me.
2. docs/00-build-plan.md: overview, findings, architecture and the "Build phases" section (the build order).
3. All 30 component docs in docs/components/, plus docs/references.md. Read the doc for a component again right before you build it.

HOW TO WORK
- Build strictly in the phase order from "Build phases" (Phase 1 → Phase 7). Don't start a phase until the previous phase's "Done when" test passes.
- Start Phase 1 with the repo skeleton, config files, Postgres in Docker, the data model from doc 25, and the backtesting harness from doc 30, so every later component is graded from day one.
- For each component: write tests first from its "Done when" checklist, implement, then add its dataset and stage backtest to the harness (doc 30). It's done only when tests and its backtest bar pass.
- Backtest on your own: build ground-truth datasets from real streams (GTA VI categories are already live on Twitch and Kick with big streamers playing early; use their VODs and viewer clips with vod_offset; GTA V fills gaps). Run `make backtest-all` after every meaningful change. Never accept a change that makes any metric worse than the baseline; when a metric misses its bar, study the worst examples in the report, fix, and re-run until it passes.
- Work autonomously. When something fails, find the root cause, fix it and re-run. Only stop to ask me if a decision in CLAUDE.md would have to change or you need a key/account only I can create (list exactly what and why, then continue with everything that doesn't depend on it, using mocks).
- Commit after each passing component with a clear message; push to main. Keep a running BUILD_LOG.md (what's done, metrics, what's next, anything blocked on me).
- Layout: test layouts as A/B arms (doc 10). Start with the stacked layout from docs/assets/layout-reference.png (creator top, captions middle, gameplay bottom) as the favorite; let analytics pick winners per language and platform.
- Run locally on my MacBook Pro M1 first. Detect RAM at startup and size models accordingly (doc 06). Use VideoToolbox for encoding (doc 12).
- Secrets only in .env (template: .env.example). Never commit secrets.

WHAT YOU HAVE / WHAT'S PENDING
- Keys in .env: Twitch and Kick developer app credentials (Phase 1). If any are missing, tell me once and keep going with mocks.
- My existing YouTube uploader is in legacy/youtube-uploader/; wrap it for doc 17.
- Platform reviews (YouTube audit, Meta review, TikTok audit, Snap allowlist) are pending; build connectors against the docs and use fallback modes (private uploads, inbox drafts) until approved.
- Social accounts get created by me after the build using the accounts tool (doc 27). Build that tool fully; don't attempt automated platform signups.

START NOW
Begin Phase 1. First reply: a short plan for Phase 1 (components, order, datasets you'll build), then start building immediately without waiting for approval.
```

## Before pasting

- [ ] Repo cloned on the MacBook; Docker installed.
- [ ] `.env` created from `.env.example` with `TWITCH_CLIENT_ID/SECRET` and `KICK_CLIENT_ID/SECRET`.
- [ ] Existing YouTube uploader copied to `legacy/youtube-uploader/`.
