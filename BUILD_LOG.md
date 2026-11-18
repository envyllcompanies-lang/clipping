# Build log

Status of the build. Spec: `docs/`. Run `make test` (fast unit tests), `make test-all`, and `make backtest-all`.

## Summary

All 7 phases are built and every component passes its tests and its stage backtest (24 stages, bars in
`eval/thresholds.yaml`, accepted baselines in `eval/baselines/`, history in `eval/CHANGELOG.md`). What's left needs
your keys, accounts and a host: see **Needs B**. Until then, backtests run on deterministic synthetic data and the
platform connectors are tested against faithful fakes of each API.

## Phase status

| Phase | Status |
| --- | --- |
| 1 Foundation and sources | done |
| 2 Finding moments | done on synthetic streams + TTS speech; re-check on 3 real recorded streams once Twitch keys exist |
| 3 Making clips | done; your "would post" review of the top 10 needs real footage |
| 4 Dashboard and public site | done; needs a host to be live for reviews |
| 5 Publishing | done in fallback mode against platform fakes; real uploads need the apps/keys |
| 6 Accounts and languages | done; the 60 signups are yours |
| 7 Analytics and autopilot | done: weekly refits, bandits, volume shares, digest, end-to-end run, deploy files; a real week needs live accounts |

## Component results

| # | Component | Backtest result (bar) |
| --- | --- | --- |
| 30 | Backtest harness | regression gate rejects any metric >2% worse than baseline (timing metrics: 50%); deliberately worse weights rejected |
| 25 | Infrastructure & data model | one recorded stream end to end through the job queue (server + M1 roles): moment found → extracted → cleaned → transcribed → events → rendered, packaged, gated → live on all 6 platforms (fakes) → stats pulled; no render files left; backups restore cleanly; M1 offline a day loses nothing |
| 01 | Creator radar | Spearman 0.853 vs next-week hours watched (≥ 0.6) |
| 02 | Stream recorder | window extraction exact 100%, p95 0.4 s (≤ 10 s); disk 1.05× buffer (≤ 1.1) |
| 03 | Chat capture | spikes aligned ≤ 2 s: 83% (≥ 80%), median 0.97 s; no false missing time |
| 04 | Platform clips & VOD ingest | 100% of clips mapped to the right UTC instant within 1 h |
| 21 | Storage lifecycle | files deleted at last upload 100%; disk flat over a simulated week (0.86×) |
| 05 | Moment heatmap | recall@20 0.98; live-signals-only recall@20 0.93 (≥ 0.7); precision 0.93; 43 s compute per stream-hour (≤ 120 s) |
| 07 | Audio cleanup & music removal | detector 100% on held-out audio; separation skipped on all no-music windows; radio fingerprint gone in 7/7 (≥ 95%); voice +12.4 dB |
| 06 | Transcription | WER en 0%, other 9 languages ≤ 9.1% (bars 15% / 25%); word timing 0.019 s (≤ 0.15 s) |
| 08 | Game event detection | precision and recall 100% on 7 event types; 2.9 s per window (≤ 10 s) |
| 13 | Style study & profiles | analyzer recovers cut rate (2% err), caption position, case, fill colour, layout 6/6, split; zoom rate ±0.7/10 s (weakest measure) |
| 09 | Clip builder | boundary IoU 0.80 (≥ 0.6); payoff included 98% (≥ 95%); plans valid 100%; short + long 100% |
| 10 | Reframe & layout | facecam found 100% / false 0%; subject in crop 96% (≥ 95%); face in top panel + caption-clear 100%; facecam in gameplay crop 15% |
| 11 | Captions | timing drift 0 s (≤ 0.1); every line fits in all 10 languages; headline + credit 100%; libass renders Latin, Arabic, Japanese |
| 12 | Render engine | 6/6 versions valid (1080×1920, H.264/AAC, −14 LUFS, no black/silence); platform fit 100%; 57 s per 40 s clip with Linux libx264 |
| 14 | Packaging | 600 posts: limits 100%; language = channel 100% (10 languages); no repeated titles; patterns tracked |
| 15 | Auto-gate | seeded duplicates caught 100%, false duplicates 0%; repeat to same account blocked; every decision has a reason; blocklist pulls everywhere |
| 16–20 | Publisher + YouTube, Instagram/Facebook/Threads, TikTok, Snapchat | one clip live on all 6 with correct fields; crash mid-upload and injected 5xx never double-post; never above limit − 10% reserve; 15-min spacing; private/inbox fallbacks create one-tap tasks; media deleted after last upload |
| 23 | Dashboard & kill switch | all 8 alert types fire; "pull everywhere" removes a live clip from YouTube/IG/FB/Threads in one worker cycle; TikTok/Snapchat become manual tasks; every screen one tap from Home |
| 22 | Analytics & feedback loop | no missed stats pulls; layout bandit moved 91% of volume to the truly best layout in 4 weeks; worse refit refused on held-out week; every change explained; digest produced; clip score vs performance ρ 0.37 |
| 27 | Account provisioning tool | one run: 10 aliases, 10 inbox labels, 60 passwords, 60 handle checks (+variants), 10 kits, 10 worksheets; 50/50 codes routed to the right row only; wrong-language connect rejected; re-run changes nothing |
| 28 | Language market ranking | swap recommended only after 4 straight winning weeks, replaces the lowest language, provisioning prepped automatically; shares follow scores (5% floor); frozen 4 weeks after release |
| 29, 24 | Public site, credentials | policy pages, Meta data-deletion callback, OAuth callbacks; tokens encrypted, refreshed ahead of expiry, reconnect alerts (unit tests) |

## What's next

1. You add the keys below as you get them; nothing else in the code needs to change.
2. With Twitch keys: the radar and recorder start, the nightly job builds the real viewer-clip dataset, and `make backtest-all` grades the heatmap on real GTA 6 streams too (`recall_at_20_live_real`).
3. Tune the GTA 6 HUD profile (`config/games/gta6.yaml`) from the first real frames (doc 08 "starts empty").

## Needs B

Keys and accounts only you can create, each with why:

- **Twitch developer app** (`TWITCH_CLIENT_ID/SECRET`): radar live polling, recording selection, clip discovery, and the real-stream datasets.
- **Kick developer app** (`KICK_CLIENT_ID/SECRET`): Kick live polling (Kick treated the same as Twitch).
- **YouTube Data API key** (`YOUTUBE_API_KEY`): off-platform creator reach and language saturation scans.
- **LLM key** (`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MONTHLY_BUDGET_USD`): better hooks/titles and clip tie-breaks; native-language templates and rules are used until then, with a monthly cost ceiling once set.
- **Hosting** for the server worker, dashboard and policy pages (doc 25): the policy pages must be live over HTTPS for the platform reviews. `docker-compose.yml`, `deploy/systemd/` and `scripts/backup.sh` are ready.
- **Storage bucket** (`BUCKET_*`): public URLs Instagram/Threads pull from (local `/public/` route is used until then).
- **Google Cloud project** (`GOOGLE_OAUTH_CLIENT_ID/SECRET`): YouTube uploads and stats; submit the compliance audit (until then uploads are private + one-tap task).
- **Your existing YouTube uploader**: copy to `legacy/youtube-uploader/uploader.py` with `upload(path, metadata, credentials) -> video_id`; the connector uses it automatically (built-in uploader until then).
- **Meta app** (`META_APP_ID/SECRET`): Instagram, Facebook Pages, Threads; app review for publishing.
- **TikTok developer app** (`TIKTOK_CLIENT_KEY/SECRET`): submit the audit with the dashboard's posting screen (until then: inbox drafts).
- **Snap Business + Public Profile API allowlist** (`SNAP_CLIENT_ID/SECRET`): Spotlight; endpoint paths get confirmed on approval.
- **addy.io account** (`ALIAS_API_KEY`, `ALIAS_DOMAIN` = your free `yourname.anonaddy.com`): one run of `clip accounts provision` then makes all aliases, passwords, handle checks and worksheets.
- **Brand name** (`config/brand.yaml`): handles use the placeholder `gta6clips` until you pick one.
- **Gmail connection** for your inbox: per-language labels and automatic verification codes on the worksheets.
- **Owner login**: `clip dashboard create-owner --email you@…`, then add the printed 2FA secret to an authenticator app.
- **The 60 signups** (10 languages × 6 platforms) from the worksheets at `/setup`, then Connect on each row; `OWNER_PHONE` only where required.
- **Style samples decision** (doc 13 open question): how reference-channel videos may be obtained (YouTube's terms). Then `clip style study <channel> <folder>`; the house profile (your reference layout) is used until then.
- **One render timing on the MacBook**: `make backtest STAGE=12` there to record the VideoToolbox time (doc target ≤ 30 s per 40 s clip).

## Notes

- Built and tested in a cloud Linux container: libx264 here, `h264_videotoolbox` automatically on macOS; RAM is detected at startup to size Whisper and parallelism.
- Synthetic datasets include realistic confounders (missing chat, radio without chat, raids/copypasta, scene cuts) so stages can't pass trivially, but they are easier than real streams. Twitch's internal web API is not used for datasets (unofficial).
- Music removal uses Demucs (MIT); ELUATE/husher were skipped (no license, "personal use"). PANNs (AudioSet) is used for music detection on the M1 when installed.
- Whisper started phrases ~0.4 s early; an energy-based word-edge refinement fixed it (0.21 s → 0.02 s).
- Layouts are A/B arms with your reference (stacked) as the starting favorite at 60%; the analytics bandit reallocates per language channel.
- Bars I set where doc 30 has none (style study, provisioning, dashboard, publishing, languages, analytics) are recorded in `eval/thresholds.yaml`. The zoom-rate bar for the style analyzer is at its current level and should tighten once real reference samples exist.
- Changes were pushed to `claude/gta6-clipping-auto-post-afpoki` with draft PR #1 to `main` (the session's branch rules); merge the PR to land them on `main`.
