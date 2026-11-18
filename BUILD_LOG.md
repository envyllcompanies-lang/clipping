# Build log

Live status of the build. Newest first in "Progress". Spec: `docs/`. Run `make test` and `make backtest-all`.

## Phase status

| Phase | Status |
| --- | --- |
| 1 Foundation and sources | done |
| 2 Finding moments | in progress |
| 3 Making clips | not started |
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

## Needs B

- **Twitch developer app** (`TWITCH_CLIENT_ID/SECRET`): radar live polling, clip discovery and the real viewer-clip datasets. Until then backtests run on synthetic datasets.

## Notes

- Built in a cloud Linux container: encoder falls back to libx264 here; `h264_videotoolbox` is used automatically on macOS.
- Backtests use deterministic synthetic datasets until real ones can be built with the owner's API keys (Twitch's internal web API is not used: unofficial).
