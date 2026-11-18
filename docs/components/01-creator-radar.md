# Clipper Component 01 — Creator Radar

Nov 18, 2026

The Creator Radar decides whose streams the clipper records, using a published formula over platform statistics. It runs every 10 minutes for live data and once a day for the ranking, and its output is an ordered list of creators per language that the Stream Recorder (Component 02) follows.

## Job and boundaries

- **Does:** discover every creator streaming GTA 6, sample their live stats, score them, rank them per language, and hand the top N to the recorder.
- **Doesn't:** record, download, or judge individual moments. That is Components 02, 04 and 05.
- **Statistics first:** no AI opinion goes into the ranking. An LLM is never asked "who is good".

## Inputs

| Source | Endpoint / method | What we take | Cadence |
| --- | --- | --- | --- |
| Twitch live streams | Helix Get Streams filtered by the GTA 6 `game_id` (and optionally `language`) | `user_id`, `user_login`, `viewer_count`, `language`, `started_at`, `title`, `tags` | Every 10 min, paginate until results run out |
| Twitch clips | Helix Get Clips by `broadcaster_id` (and by `game_id` for discovery), sorted by view count | Clip count, total clip views, `created_at`, `vod_offset` | Hourly per tracked creator; hourly for the game |
| Twitch channel | Helix Get Channel Followers (count) / Get Users | Follower count, account age | Daily |
| Kick live streams | Kick public API (`api.kick.com/public/v1`, OAuth 2.1, 2-hour tokens) for channel/livestream info; category listing for GTA 6 | Viewer count, language, live status | Every 10 min |
| YouTube creators | Data API: `search.list` (100 units/call) for GTA 6 uploads, then `videos.list` (1 unit) for stats, `channels.list` (`forHandle`) for IDs | Views per GTA 6 upload over 30 days, subscriber count, live status | Daily (search is expensive; cache results) |
| HasRoot | Public pages per RP server | Who streams on which RP server, stream history | Daily, for RP creators |
| Our own analytics (Component 22) | Database | Avg watch time, views, shares of clips made from each creator | Daily |

GTA 6 IDs (Twitch `game_id`, Kick category) are filled in at launch (November 19, 2026) and stored in `config/games/gta6.yaml`.

## Signals and formula

Each signal is computed per creator over a rolling window, then converted to a percentile rank among all GTA 6 creators in the same language (0 = lowest, 1 = highest). Percentiles stop one giant streamer from flattening everyone else.

| Signal | Definition | Window | Starting weight |
| --- | --- | --- | --- |
| Live audience | Mean `viewer_count` across 10-min samples while live in GTA 6 | 7 days | 0.20 |
| Footage volume | Hours streamed in GTA 6 | 7 days | 0.10 |
| Clip rate | Clips created per stream hour | 7 days | 0.20 |
| Clip reach | Median views of their clips | 7 days | 0.15 |
| Off-platform reach | Median views per GTA 6 YouTube upload | 30 days | 0.10 |
| Growth | Week-over-week change in live audience and clip rate | 2 weeks | 0.10 |
| Our performance | Median retention-weighted views of our clips sourced from them | 30 days | 0.15 (0 until we have data) |

Creator score = sum of weight × percentile. Weights renormalize when a signal is missing (a Kick creator has no Twitch clip data, so its clip weights spread over the remaining signals). Once 4+ weeks of our own post data exist, Component 22 refits the weights by regression on which creators' clips actually performed.

## Ranking and selection

1. Rank creators per language by score.
2. **Exploit/explore split:** 80% of recorder slots go to the top-ranked; 20% go to the highest-growth creators outside the top group, so the system finds rising streamers before competitors.
3. **Slot count** comes from capacity: recorder concurrency (Component 25) and M1 processing throughput (Component 06). The radar never schedules more creators than the pipeline can process.
4. **Hysteresis:** a creator must fall below the cutoff for 2 consecutive days before being dropped, so the list doesn't churn hourly.
5. **Blocklist:** creators who object are blocklisted by the takedown handler (Component 15) and never re-enter.

## Data stored

- `creator` (platform, platform_id, handle, language, blocklisted, first_seen)
- `creator_stat` (creator_id, sampled_at, live, viewer_count, game, title)
- `creator_score` (creator_id, date, each signal value, each percentile, score, rank, selected)

All raw samples are kept 90 days for refitting, then rolled up into daily aggregates.

## Edge cases

- **Category switching:** a creator who leaves GTA 6 mid-stream stops counting from that sample; the recorder is told to stop.
- **Viewbotting:** flag creators whose viewer count is far above their chat activity and clip rate (chats per viewer far below the language median). Down-weight live audience for them.
- **Co-streams / duplicate rooms:** two creators in the same RP scene produce overlapping moments. The duplicate check (Component 15) handles the clip side; the radar just records both.
- **API outages:** missing samples are skipped, never filled with zeros.
- **Language tags wrong:** fall back to detecting language from the stream title and, later, from transcripts (Component 06).

## Rate limits and costs

- Twitch Helix has a per-app request budget (verify current value in the console); 10-minute polling of one game plus hourly clip pulls for ~100 creators fits comfortably.
- YouTube `search.list` is the expensive call at 100 units from the 10,000-unit daily pool; cap discovery searches at about 30 per day.
- Kick tokens expire every 2 hours; refresh automatically and back off on 429s.

## Done when

- [ ] The radar lists every live GTA 6 creator on Twitch and Kick within 10 minutes of them going live.
- [ ] Daily ranking per language is reproducible from stored samples (same inputs give the same order).
- [ ] The dashboard (Component 23) shows each creator's signals, percentiles and why they were selected.

## Open questions

- [ ] Exact Helix rate budget and whether EventSub `stream.online` webhooks should replace polling for known creators.
- [ ] How many recorder slots the first server supports (sets the top N).
