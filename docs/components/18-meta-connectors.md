# Clipper Component 18 — Meta Connectors (Instagram, Facebook, Threads)

Nov 18, 2026

One Meta app powers three connectors: Instagram Reels, Facebook Reels and Threads. All three use a create-then-publish pattern with Meta pulling the video from a public URL, so these connectors depend on the temporary public storage in Component 21.

## Shared setup

- **Meta developer app** with Instagram, Facebook Pages and Threads products added.
- **Accounts:** Instagram must be a Professional (Business or Creator) account; Facebook posting works only to Pages, never personal profiles ([Meta](https://developers.facebook.com/documentation/video-api/guides/reels-publishing)); Threads connects through the Instagram login.
- **Development mode:** accounts with a role on the app (admin/tester) can be used before App Review; opening it to other people's accounts needs App Review. Since all accounts are ours, testers may be enough (confirm during setup).
- **Tokens:** long-lived user tokens and Page tokens; refresh before expiry; store encrypted (Component 24).

## Instagram Reels

| Step | Call | Notes |
| --- | --- | --- |
| 1 | `POST /{ig-user-id}/media` with `media_type=REELS`, `video_url`, `caption`, optional `share_to_feed`, cover options | Creates a container |
| 2 | `GET /{container-id}?fields=status_code` until `FINISHED` | Statuses: IN_PROGRESS, FINISHED, PUBLISHED, EXPIRED, ERROR ([guide](https://website-apn.pages.dev/blog/instagram-reels-api-publishing-guide/)) |
| 3 | `POST /{ig-user-id}/media_publish` with `creation_id` | Returns media ID |
| Limit | 100 API posts per rolling 24 h per account per Meta's page; some sections and the `content_publishing_limit` endpoint report 50, so read the endpoint per account | [Meta](https://developers.facebook.com/docs/instagram-platform/content-publishing/) |
| Expiry | Unpublished containers expire after 24 h | Re-create if expired |
| Caption | 2,200 characters max | |

## Facebook Reels (Pages)

| Step | Call | Notes |
| --- | --- | --- |
| 1 | `POST /{page-id}/video_reels` with `upload_phase=start` | Returns `video_id` and upload URL |
| 2 | Upload the file to the returned upload URL (resumable) | Hosted upload, not pull |
| 3 | `POST /{page-id}/video_reels` with `upload_phase=finish`, `video_state=PUBLISHED`, `description` | |
| Limit | 30 API-published Reels per Page per rolling 24 h | [Meta](https://developers.facebook.com/documentation/video-api/guides/reels-publishing) |
| Spec | 3–90 s, 9:16, at least 540×960 | [Ayrshare](https://www.ayrshare.com/facebook-api.md) |

## Threads

| Step | Call | Notes |
| --- | --- | --- |
| 1 | `POST /{threads-user-id}/threads` with `media_type=VIDEO`, `video_url`, `text` | Container |
| 2 | Poll container status until finished (no webhook) | [Postproxy](https://postproxy.dev/platforms/threads/) |
| 3 | `POST /{threads-user-id}/threads_publish` with `creation_id` | |
| Limit | 250 API posts per profile per 24 h; 1,000 replies | [Meta](https://developers.facebook.com/docs/threads/overview) |
| Spec | Text 500 chars; one topic tag; video up to 5 min, 1 GB | [Meta](https://developers.facebook.com/docs/threads/posts/), [Blotato](https://www.blotato.com/tools/social-media-posting-limits) |

## Originality and reach

Instagram removes accounts that mostly repost without material edits from recommendations, evaluated on a rolling 30 days ([Social Media Today](https://www.socialmediatoday.com/news/instagram-expands-originality-reach-penalties/819016/)); Facebook has penalized unoriginal content since 2025. These connectors therefore only accept clips the auto-gate (15) marked as passing the originality layer, and the account-health guard reads Instagram's account status for recommendation eligibility.

## Stats

- Instagram media insights (views/plays, reach, likes, comments, saves, shares; exact metric names changed over time, verify at build).
- Facebook video insights per Reel; Threads insights (views, likes, replies, reposts).
- Pulled hourly for 48 h, then daily.

## Public URL lifecycle

The clip is uploaded to the temporary bucket with an unguessable URL; once Instagram and Threads containers reach FINISHED (and Facebook's hosted upload completes), the bucket copy is deleted (Component 21).

## Errors

- Container `ERROR`: inspect error; usually spec (codec, duration, aspect) → fix render or drop platform.
- Rate limit (error code for Reels rate limit, 613 per [guide](https://website-apn.pages.dev/blog/facebook-graph-api-posting-guide/)): pause per account until window clears.
- Token expired: alert to reconnect.

## Done when

- [ ] One clip publishes to Instagram, Facebook and Threads from the same Meta app.
- [ ] Bucket copies deleted within minutes of processing.
- [ ] Recommendation eligibility monitored per Instagram account.

## Open questions

- [ ] Whether development-mode tester access covers all our accounts or App Review is needed.
