# Clipper Component 28 — Language Market Ranking

Nov 18, 2026

Language Market Ranking decides which language channels the system runs. It launches with a fixed top 10 (from GTA 5 viewership), then measures GTA 6 viewership per stream language across Twitch, Kick and YouTube every week, combines it with how crowded each language's clip market is and how our own channels perform, and flags when a language outside the set should replace one inside it.

## Job and boundaries

- **Does:** weekly per-language market measurement, a market score, swap recommendations, and per-language posting-volume targets for the scheduler.
- **Doesn't:** rank individual creators (Component 01), or create accounts (27). A swap is flagged on the dashboard; the system starts provisioning the new language automatically, but the 6 signups for it are manual.

## Launch set

`en, es, pt, ar, fr, ru, de, ja, tr, vi`: chosen from GTA viewership by language across the three source platforms ([Streams Charts](https://streamscharts.com/specials/gta6), [streamer.guide](https://streamer.guide/guides/kick-vs-twitch-languages)). Watch list: `pl, zh-Hant, th, hi, id, it, ko`.

## Inputs

| Signal | Source | Notes |
| --- | --- | --- |
| Live GTA 6 viewers by language, Twitch | Radar (01) samples of Helix Get Streams (`language` field) | Every 10 min |
| Live GTA 6 viewers by language, Kick | Radar samples of Kick livestreams (language field; title detection fallback) | Every 10 min |
| Live GTA 6 viewers by language, YouTube | YouTube Data API search for live GTA 6 streams; language from `defaultAudioLanguage`, else title/description detection | Hourly (quota-limited) |
| Creator depth | Count of creators per language with ≥ 1,000 average viewers (from 01) | Ensures enough source footage |
| Clip-market saturation | YouTube search for GTA 6 Shorts per language in the last 7 days: number of distinct channels posting and their median views | Weekly |
| Our performance | Analytics (22): normalized performance and follower growth per language channel | After 4 weeks of posting |
| Monetization value | Static config per language: relative RPM tier (e.g. English high; Russian low due to payout limits) | Reviewed quarterly |

## Market score

For each language L, weekly:

1. **Audience** = GTA 6 hours watched in L across all three platforms (sum of samples × interval).
2. **Depth** = number of creators in L above the viewer floor.
3. **Opportunity** = audience ÷ (number of active clip channels in L + 1), so big audiences with few clip pages score higher.
4. **Value** = RPM tier multiplier.
5. **Ours** = our channel's normalized performance in L (0 if not running).

Score = 0.40 × pct(audience) + 0.15 × pct(depth) + 0.20 × pct(opportunity) + 0.10 × value + 0.15 × pct(ours), where pct = percentile rank among all languages measured. Weights live in config and are refit by analytics once there are 8+ weeks of data.

## Swap rule

- A watch-list language whose score beats the lowest-scoring active language for **4 consecutive weeks** triggers a swap recommendation.
- Hysteresis: the active language must also score below the challenger by at least 10 percentile points, to avoid flip-flopping.
- On recommendation: dashboard alert; the provisioning tool (27) creates the new language's alias, handles and worksheet automatically; the radar starts recording that language's top creators so clips are queued before accounts exist.
- The outgoing language is **paused, not deleted**: posting stops, accounts and aliases stay (they can be resumed and keep their followers).
- Expansion instead of swap: if total daily posting capacity allows, the dashboard offers "add" instead of "replace".

## Volume allocation

Weekly, the scheduler (16) gets a target share of daily posts per language proportional to score (with a floor of 5% for every active language so new channels can grow). Platform caps per account still apply.

## Data stored

- `language_sample` (code, platform, ts, viewers, channels)
- `language_week` (code, week, audience_hours, depth, clip_channels, opportunity, value, ours, score, rank)
- `language_action` (code, action: recommend_add/replace/pause, reason, created_at, status)

## Edge cases

- **Mislabelled stream language:** use transcript language detection (06) on recorded windows to correct a creator's language after 3 agreeing detections.
- **Regional variants:** `pt` covers Brazil and Portugal, `es` covers Spain and Latin America; split (e.g. `es-mx`) only if both halves alone would rank in the top 10.
- **Launch week:** GTA 6 data is thin in week 1; swaps are disabled for the first 4 weeks after launch.
- **YouTube quota:** if the live search quota is exhausted, YouTube audience carries forward last week's value with a flag.

## Done when

- [ ] Weekly language table appears on the dashboard with all signals and scores.
- [ ] A simulated challenger that wins 4 weeks in a row triggers a recommendation and automatic provisioning prep.
- [ ] Posting shares per language follow the scores within platform caps.

## Open questions

- [ ] RPM tier values per language (fill from first months of payout data).
