# Build log

Live status of the build. Newest first in "Progress". Spec: `docs/`. Run `make test` and `make backtest-all`.

## Phase status

| Phase | Status |
| --- | --- |
| 1 Foundation and sources | done |
| 2 Finding moments | done (synthetic + TTS data; real-stream check pending keys) |
| 3 Making clips | done (owner's "would post" check on the top 10 pending real footage) |
| 4 Dashboard and public site | done (needs a host to go live: see Needs B) |
| 5 Publishing | done in fallback mode against platform fakes (real uploads need the apps/keys) |
| 6 Accounts and languages | in progress |
| 7 Analytics and autopilot | not started |

## Component results

| # | Component | Tests | Backtest (bar) |
| --- | --- | --- | --- |
| 25 | Data model, job queue | pass | — |
| 30 | Backtest harness | pass | regression gate active |
| 01 | Creator radar | pass | Spearman 0.853 (≥ 0.6) |
| 02 | Stream recorder | pass | extract exact 100%, p95 0.4 s (≤ 10 s), disk 1.05× buffer (≤ 1.1) |
| 21 | Storage lifecycle | pass | deleted promptly 100%, disk growth 0.86× (≤ 1.5) |
| 03 | Chat capture | pass | spikes aligned ≤ 2 s: 83% (≥ 80%), median 0.97 s; no false missing time |
| 04 | Platform clips & VOD ingest | pass | 100% mapped to the right UTC instant within 1 h |
| 05 | Moment heatmap | pass | recall@20 0.98, live-signals-only recall@20 0.93 (≥ 0.7), precision@20 0.93; 43 s compute per stream-hour incl. 1080p60 feature extraction (≤ 120 s) |
| 07 | Audio cleanup & music removal | pass | detector 100% held-out, separation skipped on all no-music windows, radio fingerprint gone in 7/7 windows (≥ 95%), voice +12.4 dB SNR |
| 06 | Transcription | pass | WER en 0%, others ≤ 9.1% (bars 15% / 25%), word timing median 0.019 s (≤ 0.15 s) |
| 08 | Game event detection | pass | precision and recall 100% on all 7 event types, 2.9 s per window (≤ 10 s) |
| 13 | Style study & profiles | pass | analyzer recovers cut rate (2% err), caption position (0.004), caps, fill colour, layout 6/6, split (0.009); zoom rate ±0.7/10 s (weakest) |
| 09 | Clip builder | pass | boundary IoU 0.80 (≥ 0.6), payoff included 98% (≥ 95%), plans valid 100%, short+long 100%, no back-reference openings |
| 10 | Reframe & layout | pass | facecam found 100% / false 0%, subject in crop 96% (≥ 95%), face in top panel and caption-clear 100%, facecam in gameplay crop 15% |
| 11 | Captions | pass | timing drift 0.00 s (≤ 0.1), all lines fit in 10 languages (incl. Arabic, Japanese), headline + credit 100%, libass OK |
| 12 | Render engine | pass | 6/6 versions valid (1080×1920, H.264/AAC, −14 LUFS), platform fit 100%; Linux libx264 57 s per 40 s clip (M1 VideoToolbox target 30 s, to measure) |
| 14 | Packaging | pass | 600 posts: fields within limits 100%, language = channel 100% (10 languages), no repeated titles, patterns tracked |
| 15 | Auto-gate | pass | seeded duplicates caught 100%, false duplicates 0%, repeat to same account blocked, reasons stored, blocklist pulls everywhere |
| 23 | Dashboard & kill switch | pass | all 8 alert types fire on simulated failures; "pull everywhere" removes a live clip from YouTube/IG/FB/Threads in one worker cycle; TikTok/Snapchat deletions become manual tasks; every screen one tap from Home |
| 29 | Public site & policy pages | pass (tests) | /, /privacy, /terms, /data-deletion, Meta signed-request deletion callback, OAuth callbacks |
| 24 | Credential storage | pass (tests) | tokens encrypted, refresh ahead of expiry, failures alert to reconnect, token use audit-logged |
| 16–20 | Publisher framework + YouTube, Meta (IG/FB/Threads), TikTok, Snapchat | pass | one clip live on all 6 (fakes) with correct fields; injected 5xx/crash mid-upload never double-posts; rolling 24 h never above limit minus 10% reserve; 15-min spacing; YouTube private + TikTok inbox fallbacks create tap tasks; file and bucket copy deleted after the last upload |

## Needs B

- **Hosting for the dashboard + policy pages** (docs 25, 29): pick a host (free subdomain is fine) so `/privacy`, `/terms`, `/data-deletion` are live over HTTPS for the platform reviews. Deploy files are in the repo (`Dockerfile`, see docs below).
- **Google Cloud project** (`GOOGLE_OAUTH_CLIENT_ID/SECRET`): YouTube uploads/stats; then submit the API compliance audit (until then uploads go private and show up as one-tap tasks).
- **Your existing YouTube uploader**: copy it to `legacy/youtube-uploader/uploader.py` exposing `upload(path, metadata, credentials) -> video_id`; the connector uses it automatically (built-in uploader is used until then).
- **Meta app** (`META_APP_ID/SECRET`): Instagram, Facebook Pages, Threads; app review for publishing.
- **TikTok developer app** (`TIKTOK_CLIENT_KEY/SECRET`): Content Posting API; submit the audit with the dashboard's posting screen (until then posts go to the inbox as drafts).
- **Snap Business + Public Profile API allowlist** (`SNAP_CLIENT_ID/SECRET`): Spotlight posting; endpoint paths get confirmed on approval.
- **Owner dashboard login**: run `clip dashboard create-owner --email you@...` once and add the printed 2FA secret to an authenticator app.

- **Style samples decision** (doc 13 open question): how to obtain reference-channel videos (YouTube's terms forbid downloading outside its features). Once decided, run `clip style study <channel> <folder>` per channel; until then the house profile (your reference screenshot) is used.
- **Render timing on the MacBook**: run `make backtest STAGE=12` on the M1 once to record the VideoToolbox time (target ≤ 30 s per 40 s clip).

- **Twitch developer app** (`TWITCH_CLIENT_ID/SECRET`): radar live polling, clip discovery and the real viewer-clip datasets. Until then backtests run on synthetic datasets.

## Notes

- `clip run <window.ts>` makes finished clips offline (both versions, captions, hook, titles per platform). The DB pipeline runs the same steps as jobs: extract (server) → audio_clean → transcribe → events → build (M1).
- Layout follows your reference as the starting favorite (stacked 60% / full 25% / small cam 15%), A/B tested later by analytics.

- Phase 2 "done when" asks for 3 real recorded streams. Without Twitch/Kick keys the recorder can't select creators, so Phase 2 was accepted on the synthetic stream model (with confounders) and TTS speech in all 10 languages. Re-run `make backtest-all` once real recordings exist; the nightly job (doc 30) adds a rolling real dataset.
- Music removal uses Demucs (MIT). ELUATE/husher were skipped: no license stated ("personal use"). Music detection: cheap heuristic on the server, PANNs (AudioSet) on the M1 if installed.
- Transcription: faster-whisper here; whisper.cpp (Metal) or mlx-whisper chosen automatically on macOS. Whisper started phrases ~0.4 s early; an energy-based edge refinement fixed it (timing error 0.21 s → 0.02 s).
- GTA 6 HUD (doc 08) is unconfirmed until launch footage: the profile methods are tested on synthetic HUD frames; regions/keywords in `config/games/gta6.yaml` get tuned from real frames.

- Built in a cloud Linux container: encoder falls back to libx264 here; `h264_videotoolbox` is used automatically on macOS.
- Backtests use deterministic synthetic datasets until real ones can be built with the owner's API keys (Twitch's internal web API is not used: unofficial).
