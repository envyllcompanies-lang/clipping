# Clipper Component 30 — Backtesting & Evaluation Harness

Nov 18, 2026

The harness lets the system grade itself without a person watching. It replays past streams where the answer is already known (which moments viewers clipped, which of our clips performed), measures every stage against that, and blocks any change that makes the numbers worse. It runs on every code change, nightly on fresh data, and before any learned weights go live.

## Job and boundaries

- **Does:** build and maintain ground-truth datasets, replay them through the pipeline offline, score each stage, compare against the last accepted baseline, and gate merges and weight updates.
- **Doesn't:** post anything, or need platform accounts. Everything runs on recorded data and local renders.

## Ground truth

| Dataset | How it's built | Used to grade |
| --- | --- | --- |
| **Viewer-clip replays** | Past GTA streams (Twitch VODs, Kick VODs where available, YouTube live replays) plus every Twitch clip with `vod_offset` on that VOD. Clips weighted by views mark where the real moments are | Heatmap (05), clip builder boundaries (09) |
| **Reference clips** | Shorts from the style-study channels (13) matched back to their source stream when possible | Boundaries, hook placement, caption style |
| **Audio set** | Windows with in-game radio (labelled by the music detector + spot checks by fingerprint) | Music removal (07) |
| **Transcript set** | Short windows per launch language with high-confidence platform captions | Transcription (06) word accuracy and timing |
| **Event set** | Frames with known HUD events (wasted, wanted level, mission passed) | Game event detection (08) |
| **Render set** | Fixed windows with expected output specs per platform | Render (12), packaging limits (14), gate (15) |
| **Our results** (after launch) | Every posted clip with its 48 h normalized performance (22) | Whole-pipeline ranking: did higher-scored clips perform better |

Datasets are versioned (`eval/datasets/<name>/<version>/` with a manifest of source IDs, timestamps and checksums). Raw video for them follows storage rules: only short windows are kept, not whole streams.

Early access note: GTA VI streams are live before release, so the first GTA 6 datasets are built from early-access VODs and their viewer clips; GTA V streams fill gaps until GTA 6 volume grows.

## Metrics per stage

| Stage | Metric | Starting bar |
| --- | --- | --- |
| Radar (01) | Rank correlation between radar score and next-week hours watched per creator | Spearman ≥ 0.6 |
| Heatmap (05) | Recall@20: share of the top viewer-clipped moments (by views) found in the top 20 windows per 4 h of stream; precision@20 | Recall@20 ≥ 0.7 |
| Clip builder (09) | Boundary IoU with the matching viewer clip; payoff inside clip | IoU ≥ 0.6; payoff included ≥ 95% |
| Transcription (06) | Word error rate per language; median word timing error | WER ≤ 15% (en), ≤ 25% others; timing ≤ 0.15 s |
| Music removal (07) | Music detector score on output; fingerprint match rate | ≥ 95% of radio windows no longer match |
| Game events (08) | Precision/recall per event type | Precision ≥ 0.9 |
| Gameplay moments (31) | Type precision/recall; boundary IoU per type; heatmap recall@20 with vs without the gameplay score | Precision ≥ 0.8 (cutscene, chase, crash, death); recall@20 must improve |
| Creator profiles (32) | Normalized reaction recall@20 vs raw; sponsor/BRB exclusion; catchphrase precision; collab alignment error | Recall improves; exclusion ≥ 99%; alignment < 0.2 s |
| Reframe (10) | Share of frames where the tracked subject stays in the crop; in stacked layout, face fully inside the top panel and captions never over the face | ≥ 95%; 100% caption-clear |
| Captions (11) | Caption timing drift; characters per line within profile | Drift ≤ 0.1 s |
| Render (12) | Output passes each platform spec (codec, size, duration, loudness −14 LUFS ±1) | 100% |
| Packaging (14) | All text within platform limits; language detected = channel language | 100% |
| Gate (15) | Duplicate detection on a seeded duplicate set | ≥ 99% caught |
| Whole pipeline (after launch) | Rank correlation between clip score and 48 h normalized performance | Rising over time; never drops > 0.05 week over week |

Bars live in `eval/thresholds.yaml`. When the system beats a bar consistently for 4 weeks, the bar ratchets up to the new level (never down without the owner).

## How it runs

1. **Unit + fixture tests** (`pytest`): every commit. Small fixture clips per component; fast (< 5 min).
2. **Stage backtests** (`make backtest STAGE=05`): run one stage over its dataset, write a report (`eval/reports/<date>-<stage>.json` + markdown summary).
3. **Full replay** (`make backtest-all`): runs the whole pipeline from recorded windows to rendered clips and packaging, offline. Nightly on the M1 (or the server for non-GPU stages).
4. **Regression gate:** any change to code, config, weights or style profiles must keep every metric within tolerance of the accepted baseline (default: no metric worse by more than 2%). Failing → change is rejected, report shows which metric and which examples got worse.
5. **Weight updates** from analytics (22) and language ranking (28) are backtested on the held-out week before they go live; they ship only if they beat the current weights.
6. **Fresh data:** the nightly job pulls yesterday's top viewer clips and their VOD windows into a rolling "recent" dataset (last 14 days), so the system is always graded on current GTA 6 content, not just old data.

## Self-improvement loop

- When a metric misses its bar, the report lists the worst examples (e.g. moments viewers clipped that the heatmap ranked low) with their signals, so the cause is visible.
- Claude Code (during the build) and the analytics job (after launch) use these reports to tune parameters; every tuning attempt is itself backtested before acceptance.
- All accepted changes and their before/after metrics are written to `eval/CHANGELOG.md` and shown on the dashboard's Analytics screen.

## Data stored

- `eval_run` (id, kind, stage, dataset_version, code_version, config_hash, started_at, finished_at, passed)
- `eval_metric` (run_id, metric, value, baseline, threshold, passed)
- `eval_example` (run_id, example_id, metric, value, notes) for worst-case listings

## Done when

- [ ] Each component built in Phases 1–7 has a dataset and a stage backtest with the metric above.
- [ ] `make backtest-all` runs end to end offline and produces a report.
- [ ] A deliberately worse change (e.g. heatmap weights zeroed) is caught and rejected by the regression gate.
- [ ] Nightly job refreshes the recent dataset and posts the report to the dashboard.

## Open questions

- [ ] Kick VOD availability for building Kick ground truth (Kick keeps no chat history; VOD retention varies by channel).
