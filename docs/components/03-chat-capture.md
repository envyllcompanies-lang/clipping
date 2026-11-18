# Clipper Component 03 — Chat Capture

Nov 18, 2026

Chat Capture records every chat message for each recorded stream, timestamped on the same clock as the video, because chat velocity is the strongest free signal of a good moment. It runs live for every recorded stream and, for Twitch and YouTube, can also backfill chat from past broadcasts.

## Job and boundaries

- **Does:** connect to chat for each recorded stream, store messages with server-UTC timestamps, compute per-10-second counts and features, and backfill VOD chat where available.
- **Doesn't:** decide moments (Component 05 reads its features) or post anything to chat. Read-only, always.

## Per-platform method

| Platform | Live method | Backfill (past streams) | Notes |
| --- | --- | --- | --- |
| Twitch | IRC over WebSocket (read-only, anonymous login works for reading public chat) or EventSub `channel.chat.message` | VOD chat replay via [TwitchDownloader](https://github.com/lay295/TwitchDownloader) CLI or [Twitch-Chat-Downloader](https://github.com/PetterKraabol/Twitch-Chat-Downloader) | IRC is simplest and needs no per-channel permission for reading |
| Kick | Pusher WebSocket used by Kick's own site (unofficial); official webhook `chat.message.sent` exists but targets broadcasters who authorize an app | None: Kick keeps no chat history ([source](https://apify.com/devilscrapes/kick-chat-archive/changelog)) | Must run live or the signal is lost; libraries: [kickpython](https://pypi.org/project/kickpython/), [KickLib](https://github.com/Bukk94/KickLib) |
| YouTube Live | Live chat via the Data API `liveChatMessages` (costs quota) or [chat-replay-downloader](https://github.com/xenova/chat-replay-downloader) (no login) | Replay chat via chat-replay-downloader | Prefer the downloader to save API quota |

## What gets stored

Per message (raw, kept 7 days): `stream_id`, `received_at` (server UTC, ms), `platform_ts` (platform's own timestamp when given), `user_id_hash`, `text`, `emote_ids`, `is_sub/mod` flags.

Per 10-second bucket (kept as long as the stream's moments are kept):

| Feature | Definition |
| --- | --- |
| `msgs` | Message count |
| `unique_chatters` | Distinct users |
| `emote_share` | Share of messages that are mostly emotes |
| `caps_share` | Share of messages mostly in capitals |
| `laugh_share` | Messages matching laugh tokens (LUL, KEKW, OMEGALUL, lol, xD, jaja, хаха, kkkk) per language |
| `hype_share` | Matches for "clip it", "CLIP", "W", "no way", "POG" and per-language equivalents |
| `copypasta_score` | How many messages are near-duplicates of each other (fuzzy match), a classic spike pattern |
| `velocity_z` | (msgs − rolling median of previous 5 min) / rolling MAD, computed live |

Token lists live in `config/chat_tokens/<language>.yaml` so new languages are a config change.

## Clock alignment

- Video segments and chat both stamp server UTC on receipt. Live HLS has a delay of several seconds, so chat often arrives *before* the matching video frame reaches the recorder, while viewers react a few seconds *after* the moment happens on screen.
- Calibrate a per-platform offset: compare the stream's HLS program-date-time (when present) with chat timestamps, then shift chat so a spike lines up with the on-screen cause. Start with a default reaction lag of 3–6 s and refine it using viewer clips (Component 04), whose `vod_offset` marks where viewers say the moment is.

## Scale

- Big streams can exceed 50 messages per second. Store raw messages in batched inserts (every 1 s) and compute buckets in memory.
- One process can hold dozens of IRC connections; Kick sockets are lighter. Reconnect with exponential backoff and log gaps so the heatmap knows a bucket is missing rather than quiet.

## Privacy and retention

- Store hashed user IDs, not usernames, except for counting unique chatters.
- Delete raw messages after 7 days; keep only bucket features tied to moments.

## Failure handling

- **Disconnect:** auto-reconnect; buckets during the gap are marked `missing`, which the heatmap excludes instead of reading as zero.
- **Kick socket protocol changes:** the unofficial socket can change without notice. Detect zero messages for 10 minutes on a live channel with viewers and raise a dashboard alert.
- **Bot spam:** messages from accounts posting identical text above a threshold are excluded from features.

## Done when

- [ ] Every recorded stream has chat buckets with under 1% missing time.
- [ ] Chat spikes line up with on-screen moments within 2 seconds after calibration.
- [ ] Adding a language means adding one token file, no code.

## Open questions

- [ ] IRC versus EventSub for Twitch at scale.
- [ ] Whether YouTube live chat is worth quota, or chat-replay-downloader covers it.
