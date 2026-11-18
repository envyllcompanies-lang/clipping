# Clipper Component 04 — Platform Clips & VOD Ingest

Nov 18, 2026

This component pulls clips viewers already made on Twitch (and Kick/YouTube equivalents) and past broadcasts (VODs), so the clipper gets human-picked moments and a second source of footage beyond live recording. Viewer clips serve three roles: markers on the heatmap, training labels for scoring, and, where downloadable, source footage.

## Job and boundaries

- **Does:** list top clips per game and per creator, map each clip to its VOD position, download clip files through official routes where possible, and pull VOD segments for moments missed live.
- **Doesn't:** screen-record clips it can't download; those moments are cut from our own stream recording instead.

## Twitch clips

| Step | Endpoint | Detail |
| --- | --- | --- |
| Discover trending clips | Get Clips with `game_id` = GTA 6, `started_at`/`ended_at` for the last 1–24 h, `first=100`, paginate | Results ordered by view count ([Twitch](https://discuss.dev.twitch.tv/t/top-clips-for-a-game-or-broadcaster-are-now-available-in-the-new-twitch-api/15393)) |
| Per-creator clips | Get Clips with `broadcaster_id` | Same ordering; run hourly for every tracked creator |
| Locate in the VOD | Fields `video_id` + `vod_offset` (seconds from VOD start) ([Twitch docs](https://dev.twitch.tv/docs/api/clips/)) | `vod_offset` can be null for older clips or deleted VODs |
| Download (official) | Get Clips Download, generally available since late 2025 ([changelog](https://dev.twitch.tv/docs/change-log/)) | Returns file URLs only for channels whose broadcaster or editor has authorized our app |

For channels that haven't authorized our app, the clip's `vod_offset` points to the moment and the cut comes from our own recording of that stream (Component 02) or from the VOD (below).

## Mapping clips onto recordings

1. Each recorded stream stores the platform's stream ID and start time.
2. For a clip with `video_id`, look up the VOD's `created_at` (Get Videos) and compute the clip's absolute UTC start = VOD start + `vod_offset`.
3. Find the recording segments covering that UTC range; the heatmap adds a clip-density bump there, weighted by the clip's views.
4. Clips created hours later still count: the recorder's 3-hour buffer plus VOD pulls cover late clips.

## VOD ingest

- **When:** a strong clip or chat spike falls in a time range we didn't record (creator not selected yet, recorder down, or buffer expired).
- **How:** fetch only the needed range, not the whole VOD, using an HLS-aware downloader that supports start/end times (streamlink supports seeking VODs with a start offset and duration; yt-dlp supports section downloads).
- **Twitch VOD retention:** VODs expire after a period set by the creator's account type; pull missed moments within hours, not days.
- **YouTube Live replays:** usually kept indefinitely; good fallback for YouTube creators.

## Kick and YouTube clips

- **Kick:** clips exist on channel pages; official API coverage of clips is limited, so treat Kick clip data as optional input and rely on Kick chat plus audio for its heatmap.
- **YouTube:** YouTube "clips" and Shorts made by viewers aren't exposed as a clean API feed; skip.

## Clip data stored

`platform_clip` table: platform, clip_id, broadcaster_id, video_id, vod_offset, duration, view_count (updated hourly for 48 h), created_at, title, downloaded_path (nullable), absolute_utc_start.

View-count growth per hour after creation is itself a signal: a clip gaining views fast marks a moment the wider audience cares about.

## Use as training labels

Every clip with a VOD position is a labelled example: "viewers thought seconds X to X+duration were worth saving." Component 05 uses these to tune heatmap weights (which signals predict clip positions), and Component 22 compares our own picks to viewer picks.

## Failure handling

- Null `vod_offset`: keep the clip for trend data only.
- VOD deleted or sub-only: mark moment unrecoverable unless our own recording covers it.
- API pagination limits: stop after 1,000 clips per query window; widen windows instead of deeper pages.

## Done when

- [ ] Every GTA 6 clip over a view threshold in the last 24 h is mapped to a UTC position within 1 hour of creation.
- [ ] Moments missed live are recovered from VODs within 2 hours when the VOD exists.
- [ ] Clip positions feed the heatmap and the scoring dataset automatically.

## Open questions

- [ ] View threshold for "trending" per language (start with the top 10% of the day's clips).
