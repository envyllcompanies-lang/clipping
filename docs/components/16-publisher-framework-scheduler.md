# Clipper Component 16 — Publisher Framework & Scheduler

Nov 18, 2026

The Publisher Framework is the shared machinery every platform connector plugs into: a job queue, posting schedule, rate-limit accounting, retries, idempotency and status tracking. It runs in the cloud so posts go out on schedule with the MacBook closed.

## Job and boundaries

- **Does:** turn queued clips into scheduled post jobs per account, run them through platform adapters, track each post to live or failed, enforce platform limits, and signal the storage lifecycle when a file can be deleted.
- **Doesn't:** know platform details. Each platform is one adapter (Components 17–20).

## Adapter interface

Every connector implements the same methods:

- `prepare(clip, account) → payload` (platform-specific fields, file or URL)
- `publish(payload) → {status, platform_post_id?}` (may return `processing`)
- `check(platform_post_id) → {status, error?}` (poll until `live` or `failed`)
- `remaining_quota(account) → int | None` (from the platform's limit endpoint where one exists)
- `delete(platform_post_id)` (for takedowns)
- `stats(platform_post_id) → metrics` (used by analytics)

## Job states

`scheduled → uploading → processing → live`, or `→ retry_wait → …`, or `→ failed_permanent`. Each transition is a database row with timestamp and error text.

**Idempotency:** a unique key on (clip_version, platform, account). A worker that crashes mid-upload resumes by checking the platform for an existing post before retrying, so nothing double-posts. Note that some platforms count failed attempts against daily limits ([Metricool](https://help.metricool.com/daily-posting-limits-on-social-media-sh58j)), so retries are budgeted.

## Scheduling

1. **Slots:** each account has posting slots in its region's time zone, initially spread evenly through waking hours, then shifted by analytics (22) toward times its audience is active.
2. **Volume:** each account posts up to its platform's limit; the scheduler keeps a small reserve for retries (e.g. 10% of the rolling window). Analytics shifts volume toward platforms and slots that perform.
3. **Freshness priority:** trending moments (fresh clips with fast-rising viewer-clip views) jump the queue; older clips fill remaining slots and expire if not posted within 72 h.
4. **Spacing:** posts on one account are at least ~15 minutes apart; different accounts are staggered so a network doesn't post in synchronized bursts.

## Platform limits table (rolling 24 h unless noted)

| Platform | Limit | Source |
| --- | --- | --- |
| YouTube | 100 uploads/day per Google Cloud project (own quota bucket) | [Postproxy](https://postproxy.dev/blog/automate-youtube-uploads/) |
| Instagram | 100 API posts per account (some docs/endpoints show 50; read `content_publishing_limit`) | [Meta](https://developers.facebook.com/docs/instagram-platform/content-publishing/) |
| Facebook Reels | 30 per Page | [Meta](https://developers.facebook.com/documentation/video-api/guides/reels-publishing) |
| Threads | 250 per profile | [Meta](https://developers.facebook.com/docs/threads/overview) |
| TikTok | ~15 Direct Posts per creator/day, shared across apps; 6 upload starts/min per token | [ShortSync](https://www.shortsync.app/resources/social-media-posting-limits-2026) |
| Snapchat | Varies (allowlisted API) | Component 20 |
| Bluesky | Action-point budget per day | Component 20 |

Limits are config values, refreshed from the platforms' limit endpoints where they exist.

## Retries

- Transient errors (timeouts, 5xx, rate-limit responses): exponential backoff 1, 5, 15, 60 minutes, max 4 attempts, all within the clip's freshness window.
- Permanent errors (invalid token, policy rejection, file spec): no retry; token errors raise a dashboard alert to reconnect the account.
- After `failed_permanent` or `live` on every target, the framework tells Component 21 the clip file can be deleted.

## Fallback modes per platform

Until a platform's app review passes, its adapter runs in fallback: YouTube uploads as private (then one-tap publish in Studio), TikTok sends to the creator inbox as a draft. The dashboard lists items needing a tap.

## Done when

- [ ] One approved clip posts to every connected platform with correct per-platform fields.
- [ ] Killing a worker mid-upload never produces a duplicate post.
- [ ] Rate limits are never exceeded; quota usage is visible per account.

## Open questions

- [ ] Queue technology (database-backed queue vs Redis) chosen in Component 25.
