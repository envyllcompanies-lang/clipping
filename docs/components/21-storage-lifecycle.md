# Clipper Component 21 — Storage Lifecycle & File Manager

Nov 18, 2026

The File Manager guarantees storage never fills: every file the system creates has an owner, a purpose and a defined end, and is deleted permanently (never to the Trash) the moment its job is done. A clip lives only until it's fully uploaded everywhere it's going.

## Rules

1. Every file is registered in the `file` table when created: path, kind, size, owner record (stream, window, clip version, job), created_at, expires_at.
2. Nothing writes outside the managed folders: `recordings/`, `windows/`, `work/<job_id>/`, `renders/`, `public/` (bucket).
3. Deletion is direct (`os.unlink` / bucket delete), which bypasses the macOS Trash entirely; Finder is never involved, so nothing lingers in Trash.
4. A sweeper runs every 5 minutes and deletes anything past `expires_at` or orphaned (no live owner).

## Lifecycle by file kind

| Kind | Where | Created by | Deleted when | Hard max age |
| --- | --- | --- | --- | --- |
| Recording segments | Recorder server | 02 | Buffer age passes and no window covers them; or stream ended + 1 h | 3 h buffer (config) |
| Candidate windows | Server, then M1 | 02 | After render of all versions, or not built | 48 h |
| Separation/transcription temp | M1 `work/<job_id>/` | 06, 07 | End of job (success or failure) | 6 h |
| Rendered clip versions | M1 `renders/` | 12 | Every target post `live` or `failed_permanent` (refcount reaches 0) | 72 h (freshness expiry) |
| Public URL copies | Cloud bucket | 16 | Platform reports processing finished (IG/Threads container FINISHED, TikTok pull done) | 24 h |
| Thumbnails | Database blob or small file | 12 | Kept (tiny) for the dashboard | 90 days |
| Logs | Server/M1 | All | Rotated | 14 days |

## Refcount for rendered clips

- When the scheduler (16) creates post jobs, the clip version's `pending_posts` = number of target (platform, account) pairs.
- Each job reaching `live` or `failed_permanent` decrements it atomically.
- At zero, the file and its bucket copy are deleted, and the clip row is marked `media_deleted`.
- Takedown or blocklist sets all pending jobs to cancelled, which also drives the count to zero.

## Disk guard

| Free space | Action |
| --- | --- |
| Above 25 GB (M1) / 20% (server) | Normal |
| Below that | Stop extracting new windows; finish in-flight jobs; sweeper runs immediately |
| Below 10 GB / 10% | Pause recording (server) or rendering (M1); dashboard alert |
| Below 5 GB / 5% | Delete oldest unbuilt windows and lowest-score queued renders first |

Thresholds are config. The guard checks every minute.

## What's kept forever (metadata only)

Database rows: source creator, stream and timestamps, edit plan JSON, titles/captions, post IDs per platform, stats history, perceptual hash and audio fingerprint for duplicate checks. A moment can be re-cut later from its source (VOD or YouTube replay) if needed.

## Crash safety

- On startup, the manager reconciles disk against the `file` table: unknown files in managed folders are deleted; missing files mark their records.
- Renders are written to a temp name and renamed when complete, so half-written files are never posted.

## Done when

- [ ] Disk usage on the M1 stays flat over a week of continuous operation.
- [ ] Every rendered file disappears within 5 minutes of its last upload finishing.
- [ ] Nothing from the system ever appears in the macOS Trash.

## Open questions

- [ ] Bucket provider for public URL copies (Component 25).
