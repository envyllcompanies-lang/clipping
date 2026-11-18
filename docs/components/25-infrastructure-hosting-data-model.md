# Clipper Component 25 — Infrastructure, Hosting & Data Model

Nov 18, 2026

The system runs on three machines: a small always-on server that records and schedules, the MacBook Pro M1 that does heavy AI and rendering, and a cloud database plus temporary storage bucket that tie them together. This doc defines where each piece runs, how they talk, and the full data model.

## Topology

| Machine | Runs | Why there |
| --- | --- | --- |
| Always-on server (Linux VPS) | Stream Recorder (02), Chat Capture (03), Radar polling (01), clip/VOD ingest (04), heatmap scoring (05), scheduler and publishers (16–20), analytics pulls (22) | Must run 24/7; light CPU, needs disk and bandwidth |
| MacBook Pro M1 | Music removal (07), transcription (06), game-event detection on windows (08), clip builder (09), reframe (10), captions (11), render (12), style study (13) | GPU/Neural Engine and hardware encoder; runs when on |
| Managed Postgres | Single source of truth for every component | Both machines read/write; free/low tiers exist (e.g. Supabase) |
| Object storage bucket | Window transfer server→M1, rendered clips M1→publishers, public URLs for Meta/TikTok pulls | Short-lived files only (Component 21) |
| Dashboard host | Web app (23) | Can share the VPS or a free web host |

The M1 being off only delays rendering; recording, scheduling and posting of already-rendered clips continue.

## Server sizing (starting point)

- 4 vCPU, 8 GB RAM, 200 GB SSD, unmetered or high-transfer bandwidth: supports roughly 8–10 concurrent 1080p60 recordings with a 3-hour buffer (about 2.7 GB/hour each, [space-node](https://space-node.net/blog/record-twitch-stream-automatically-vps-script)) plus scheduler and scoring.
- Scale by adding recorder nodes; the radar reads total free slots.

## Communication

- Every component reads and writes Postgres; work moves through **job tables** (`job` with type, payload, status, attempts, locked_by, locked_until), using `SELECT … FOR UPDATE SKIP LOCKED` so multiple workers can pull safely. No separate queue service needed at first.
- Files move through the bucket with signed URLs; the database stores paths and checksums.
- The M1 runs a worker daemon (launchd) that pulls `extract_done` windows, processes them and uploads renders; it reports heartbeat every minute.

## Data model (core tables)

| Table | Key columns | Owner |
| --- | --- | --- |
| `game` | slug, name, platform IDs, profile path | Config |
| `channel` | key, language, time zone, style profile, score floor | 24 |
| `account` | channel_id, platform, handle, token_ref, status, review_status | 24 |
| `creator` | platform, platform_id, handle, language, blocklisted | 01 |
| `creator_stat` / `creator_score` | samples; daily signals, percentiles, score, selected | 01 |
| `stream` | creator_id, platform_stream_id, started_at, ended_at, status | 02 |
| `segment` | stream_id, path, start_utc, end_utc, size | 02 |
| `chat_bucket` | stream_id, t_start, msgs, unique_chatters, shares, velocity_z, missing | 03 |
| `platform_clip` | platform, clip_id, video_id, vod_offset, views, abs_utc_start | 04 |
| `moment` | stream_id, start_s, end_s, peak_s, signals, score, status | 05 |
| `window` | moment_id, path, status | 02/21 |
| `transcript` | window_id, words JSON (index, word, start, end, conf, speaker) | 06 |
| `game_event` | stream_id, t_s, type, confidence, details | 08 |
| `clip` / `clip_version` | moment_id, channel_id, edit_plan, crop_plan, version type, path, hash, fingerprint, pending_posts, status | 09–12 |
| `gate_result` | clip_version_id, check, passed, reason | 15 |
| `post` | clip_version_id, account_id, platform_post_id, status, scheduled_at, posted_at, error (unique on clip_version+account) | 16 |
| `post_stat` | post_id, sampled_at, views, likes, comments, shares, saves, retention | 22 |
| `weights` | component, version, values JSON, fitted_at, holdout_score, active | 22 |
| `file` | path, kind, size, owner, expires_at | 21 |
| `command` / `alert` | dashboard actions; alerts raised | 23 |

## Reliability

- Workers are idempotent and restartable; every external call is retried with backoff (16).
- Daily database backups; the bucket holds nothing irreplaceable.
- Health checks: recorder slots, M1 heartbeat, queue depths, token health → dashboard and alerts.

## Security

- Secrets in the host's secret manager; encrypted token columns; least-privilege database roles per machine.
- Dashboard behind auth with 2FA; server firewall allowing only needed ports.

## Codebase layout (for Claude Code)

One Python monorepo in `envyllcompanies-lang/clipping`: a package per component (`radar`, `recorder`, `chat`, `ingest`, `heatmap`, `transcribe`, `audio`, `events`, `builder`, `reframe`, `captions`, `render`, `style`, `packaging`, `gate`, `publish/*`, `storage`, `analytics`), a `dashboard/` web app, `config/` for games, channels, styles and token lists, and `tests/` with fixture clips.

## Done when

- [ ] Server and M1 workers process a stream end to end through the database and bucket.
- [ ] M1 offline for a day causes no data loss, only delay.
- [ ] Backups restore cleanly in a test.

## Open questions

- [ ] VPS provider and region (close to Twitch ingest/edge for stable recording).
- [ ] Bucket provider (cheap egress matters because platforms pull from it).
