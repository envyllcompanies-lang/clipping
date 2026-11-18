# Clipper Component 05 — Moment Heatmap & Scoring

Nov 18, 2026

The heatmap turns a long stream into a ranked list of candidate moments by fusing cheap statistical signals second by second, so the expensive steps (transcription, rendering) only ever touch the best few minutes of each hour. Every signal is measured, normalized against that stream's own baseline, and combined with weights fitted to real results.

## Job and boundaries

- **Does:** produce a per-second score curve for each stream, pick candidate windows, and send them to the recorder for extraction.
- **Doesn't:** decide exact clip boundaries or edits (Component 09), or transcribe whole streams.

## Signals (computed per 1-second step)

| Signal | Source | Computation | Cost |
| --- | --- | --- | --- |
| Chat velocity | Component 03 buckets | Robust z-score of messages per 10 s vs the previous 5 min (median and MAD), interpolated to 1 s | Free |
| Chat reaction mix | Component 03 | Weighted sum of laugh, hype, caps and copypasta shares | Free |
| Viewer clip density | Component 04 | Kernel density of clip start positions, each clip weighted by log(views+1), Gaussian kernel of 10 s width | Free |
| Audio energy | Recording audio (decoded at 8 kHz mono) | RMS in 50 ms windows → dB; spike = jump of 10+ dB over the previous 1 s median | Very low |
| Creator reaction (normalized) | Component 32 | Reaction z-score vs this creator's own baseline (voice, laughter, face, catchphrases); replaces raw voice excitement once the profile exists | Low |
| Voice excitement | Same audio | Pitch variance and speech rate in voice frequency band, z-scored against the streamer's baseline | Low |
| Scene/visual change | Recording video at 2 fps, 240 px wide | Histogram distance between frames (cuts, explosions, screen flashes) | Low |
| Game events | Component 08 | Detected HUD events (death screen, wanted level change, mission banner) as point events | Medium, run only around candidate peaks |
| Gameplay moment score | Component 31 | Typed moment score (cutscene reveal, chase, crash, discovery, etc.) × creator reaction, around candidate peaks; second-pass re-rank | Medium, candidate windows only |
| Viewer count jump | Component 01 samples | Change in viewers over 10 min, spread across that interval | Free |

Each signal is normalized per stream to a 0–1 range using that stream's own distribution (percentile within the stream), so a quiet streamer's big moment ranks as high as a loud streamer's.

## Fusion

1. Score(t) = Σ weightᵢ × signalᵢ(t), with missing signals (e.g. Kick has no clip data) dropped and weights renormalized.
2. Smooth with a 5-second moving average.
3. **Starting weights** (before data): chat velocity 0.25, viewer clips 0.25, audio energy 0.15, voice excitement 0.10, chat reaction mix 0.10, game events 0.10, visual change 0.05.
4. **Learned weights:** after enough data, fit a logistic regression where the label is "a viewer clip starts within 15 s" (from Component 04), then later "our clip from this moment beat median retention" (from Component 22). Refit weekly; keep the old weights if the new fit is worse on a held-out week.

## Picking candidate windows

1. Find peaks in the smoothed score with a minimum separation of 45 s.
2. Keep peaks above the stream's 95th percentile score *and* above an absolute floor (so a dull stream doesn't produce forced clips).
3. For each peak, the candidate window is peak − 45 s to peak + 30 s (lead-up matters more than aftermath).
4. Merge overlapping windows.
5. Cap at roughly 10 candidates per stream hour; the strongest go first.
6. Send window requests to the recorder (Component 02) and queue them for transcription (Component 06).

## Live versus after-the-fact

- **Live mode:** chat, audio and viewer counts score in near real time, so windows extract within minutes of a moment and clips can post while the moment is trending.
- **Late signals:** viewer clips arrive minutes to hours later; when a new clip lands on an unflagged moment, the window is re-scored and extracted if the recorder buffer still has it, otherwise pulled from the VOD (Component 04).

## Outputs

`moment` table: stream_id, start_s, end_s, peak_s, every signal value at the peak, score, rank in stream, status (candidate, extracted, built, discarded).

## Quality checks

- **Backtest:** on recorded streams, measure the share of top viewer clips (by views) that fall inside our candidate windows. Target 70%+ recall at 10 windows per hour.
- **Per-language tuning:** chat behaviour differs by language; weights are fit per language once data allows.

## Failure handling

- Missing chat (disconnect): drop chat signals for that span, not the stream.
- Music-heavy streams: audio energy gets noisy when radio is loud; voice excitement (voice band) is more reliable there. Component 07's music detector can down-weight audio energy where music dominates.

## Done when

- [ ] 70%+ of the top viewer clips fall inside candidate windows on backtests.
- [ ] Scoring a 1-hour stream takes under 2 minutes of compute on the server.
- [ ] Weights refit weekly from labelled data with a held-out check.

## Open questions

- [ ] The absolute score floor per language, set after the first week of GTA 6 data.
