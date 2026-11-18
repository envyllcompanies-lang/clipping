# Build log

Live status of the build. Newest first in "Progress". Spec: `docs/`. Run `make test` and `make backtest-all`.

## Phase status

| Phase | Status |
| --- | --- |
| 1 Foundation and sources | done |
| 2 Finding moments | done (synthetic + TTS data; real-stream check pending keys) |
| 3 Making clips | in progress |
| 4 Dashboard and public site | not started |
| 5 Publishing | not started |
| 6 Accounts and languages | not started |
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

## Needs B

- **Twitch developer app** (`TWITCH_CLIENT_ID/SECRET`): radar live polling, clip discovery and the real viewer-clip datasets. Until then backtests run on synthetic datasets.

## Notes

- Phase 2 "done when" asks for 3 real recorded streams. Without Twitch/Kick keys the recorder can't select creators, so Phase 2 was accepted on the synthetic stream model (with confounders) and TTS speech in all 10 languages. Re-run `make backtest-all` once real recordings exist; the nightly job (doc 30) adds a rolling real dataset.
- Music removal uses Demucs (MIT). ELUATE/husher were skipped: no license stated ("personal use"). Music detection: cheap heuristic on the server, PANNs (AudioSet) on the M1 if installed.
- Transcription: faster-whisper here; whisper.cpp (Metal) or mlx-whisper chosen automatically on macOS. Whisper started phrases ~0.4 s early; an energy-based edge refinement fixed it (timing error 0.21 s → 0.02 s).
- GTA 6 HUD (doc 08) is unconfirmed until launch footage: the profile methods are tested on synthetic HUD frames; regions/keywords in `config/games/gta6.yaml` get tuned from real frames.

- Built in a cloud Linux container: encoder falls back to libx264 here; `h264_videotoolbox` is used automatically on macOS.
- Backtests use deterministic synthetic datasets until real ones can be built with the owner's API keys (Twitch's internal web API is not used: unofficial).
