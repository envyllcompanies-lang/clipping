# Clipper Component 02 — Stream Recorder

Nov 18, 2026

The Stream Recorder captures the live streams of creators the Radar selects, on a small always-on server, and keeps only a rolling buffer so storage never fills. It saves the original stream without re-encoding, which makes recording cheap on CPU and bound by disk and bandwidth instead.

## Job and boundaries

- **Does:** start recording when a selected creator goes live in GTA 6, write segmented files, keep a rolling buffer, extract candidate windows on request, and delete everything else.
- **Doesn't:** score moments (Component 05) or capture chat (Component 03), though it runs alongside the chat capturer for the same stream.
- **Runs on:** a Linux server, never the MacBook. The M1 only receives small candidate windows.

## Tooling

- **streamlink** pulls the HLS stream for Twitch, Kick and YouTube and pipes it to FFmpeg, which writes fixed-length segments with `-c copy` (no re-encode).
- **FFmpeg segment muxer:** 60-second `.ts` or fragmented `.mp4` segments named `{creator}/{stream_id}/{epoch_start}.ts`, so any window can be stitched by concatenating segments.
- Twitch ad breaks: use streamlink's ad-skipping option so mid-roll filler doesn't pollute the buffer.

## Lifecycle of one stream

1. Radar marks creator selected; live detection fires (Radar poll or a platform webhook such as Twitch EventSub `stream.online`).
2. Recorder starts a worker: `streamlink <url> best -O | ffmpeg -i - -c copy -f segment -segment_time 60 -reset_timestamps 1 ...`.
3. Chat Capture (Component 03) starts for the same stream with the same clock reference (server UTC), so chat timestamps line up with segment times.
4. Every minute, the worker records each finished segment in the `segment` table (path, start UTC, end UTC, size).
5. Heatmap (Component 05) scores the stream continuously. When it marks a candidate window, the recorder concatenates the covering segments plus 30 s padding either side into one window file and queues it for transfer to the M1.
6. Segments older than the buffer age (default 3 hours) with no candidate window touching them are deleted.
7. When the stream ends (stream goes offline or the creator switches category), the worker stops, scoring finishes, the last windows are extracted, and the remaining segments are deleted after a 1-hour grace period.

## Quality settings

| Setting | Value | Why |
| --- | --- | --- |
| Quality | `best`, capped at 1080p60 | Source quality for clean 9:16 crops |
| Container | MPEG-TS segments | Survives crashes mid-file; concatenates cleanly |
| Segment length | 60 s | Small enough to delete fine-grained, large enough to keep file count sane |
| Buffer age | 3 h (configurable) | Long enough for slow scoring and late viewer clips; short enough to cap disk |

## Storage budget

Twitch 1080p60 runs about 2.7 GB per hour ([space-node](https://space-node.net/blog/record-twitch-stream-automatically-vps-script)). With a 3-hour rolling buffer, each concurrent stream needs about 8 GB of live disk plus extracted windows. Ten concurrent streams need roughly 100 GB of working space. The disk guard (Component 21) pauses new recordings below a free-space floor.

## Concurrency

- Recording one stream needs little CPU; about 1 vCPU per parallel stream is a safe rule from published setups.
- Network: each 1080p60 stream pulls about 6 Mbps; 10 streams need about 60 Mbps sustained download.
- The recorder exposes its free slots to the Radar, which never schedules more creators than slots.

## Platform specifics

- **Twitch:** stable HLS; sub-only or age-gated streams may need an authenticated token; skip them at first.
- **Kick:** HLS playback URL from the channel's livestream data; Kick has no chat history, so the chat capturer must run live alongside.
- **YouTube Live:** streamlink supports it; YouTube also keeps a full replay after the stream, which can be used if a live recording fails.

## Failure handling

- **Stream drops/reconnects:** the worker restarts streamlink within 10 s and continues the same `stream_id`; a gap row records the missing interval.
- **Disk full:** recording pauses (guard), the dashboard alerts, and oldest unflagged segments are deleted first.
- **Server crash:** segments on disk are recovered at restart from the `segment` table; workers restart for any creator still live.
- **Duplicate starts:** one active worker per creator, enforced by a lock row in the database.

## Transfer to the M1

- Candidate windows (typically 1–3 minutes, 30–90 MB at source bitrate) are pulled by the M1 when it's online, over an authenticated HTTPS endpoint or object storage.
- After the M1 confirms receipt, the server deletes its copy.
- If the M1 is offline for over 48 hours, unpulled windows expire and are deleted (moments are logged so they can be re-cut from a YouTube replay if one exists).

## Done when

- [ ] A selected creator going live starts recording within 1 minute.
- [ ] A 6-hour stream never uses more than buffer-age worth of disk.
- [ ] A requested window is extracted in under 10 seconds with no re-encode and exact timestamps.

## Open questions

- [ ] Server choice and disk size (Component 25).
- [ ] Whether to record at 720p60 for lower storage when the creator has no facecam detail worth keeping.
