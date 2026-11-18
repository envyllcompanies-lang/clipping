# Clipper Component 17 — YouTube Shorts Connector

Nov 18, 2026

The YouTube connector uploads Shorts through the YouTube Data API, reusing the auto-upload code already built in a previous project, wrapped in the shared adapter interface. Quota is no longer the bottleneck; the compliance audit is, because uploads from unaudited projects stay private.

## Starting point

- Existing YouTube upload code (previous project, different accounts) becomes this adapter. New channels authorize once via OAuth.
- Open item: confirm whether the existing Google Cloud project has passed the API compliance audit (if its uploads went public, it has).

## API facts (verify at build)

| Item | Value | Source |
| --- | --- | --- |
| Upload endpoint | `videos.insert`, resumable upload, OAuth scope `youtube.upload` | [YouTube docs](https://developers.google.com/youtube/v3/docs/videos/insert) |
| Upload quota | 100 `videos.insert` calls per day per project, in its own bucket since June 2026 | [Postproxy](https://postproxy.dev/blog/automate-youtube-uploads/) |
| Other calls | 10,000 units/day pool: `videos.update`/`thumbnails.set` 50 units, `videos.list` 1 | [Postproxy](https://postproxy.dev/blog/automate-youtube-uploads/) |
| Unaudited projects | Uploads from unverified projects created after July 28, 2020 are locked private; locked videos can't be appealed, only re-uploaded | [YouTube docs](https://developers.google.com/youtube/v3/docs/videos/insert), [singhamandeep](https://singhamandeep.com/?p=1462) |
| Channel limits | Separate per-channel rolling upload ceiling (`uploadLimitExceeded`) | [singhamandeep](https://singhamandeep.com/uploadlimitexceeded/) |
| Shorts | Vertical or square video up to 3 minutes | [Eklipse](https://blog.eklipse.gg/creator/gta-youtubers.html) |

## Upload flow

1. `prepare`: title (≤100 chars), description with credit and hashtags, tags, `categoryId` 20 (Gaming), `defaultLanguage` and `defaultAudioLanguage` set to the page's language, `madeForKids=false`, privacy `public` (or `private` in fallback).
2. **AI disclosure:** set the altered/synthetic content flag only when it applies; our clips are real footage, so normally not set (keep the field explicit in config).
3. `publish`: resumable upload in chunks (e.g. 8 MB) with retry on chunk failures; store the upload session URI so a crash resumes instead of restarting.
4. `check`: `videos.list` (part=status,processingDetails) until processing succeeded; record `uploadStatus` and any rejection reason.
5. Thumbnail: Shorts thumbnails are limited; skip custom thumbnails for Shorts unless verified to apply.
6. Done: mark live; signal storage lifecycle.

## Multiple channels

- One Google Cloud project can hold OAuth tokens for many channels, but the 100 uploads/day bucket is per project, shared across all of them.
- Monetization math favors concentrating views: Shorts revenue requires 10M qualified Shorts views in 90 days, and from February 1, 2027 new applicants need 20M ([Tubefilter](https://www.tubefilter.com/?p=193559)). Start with one main channel per language.

## Stats (for analytics)

- `videos.list` (statistics): views, likes, comments, hourly for 48 h then daily.
- YouTube Analytics API (channel-owner OAuth, scope `yt-analytics.readonly`): average view duration, average percentage viewed, Shorts-specific engagement where available.

## Takedowns

`videos.delete` (50 units) for creator objections; record removal.

## Errors to handle

| Error | Meaning | Action |
| --- | --- | --- |
| `quotaExceeded` | Project daily bucket used | Pause YouTube jobs until reset (midnight Pacific) |
| `uploadLimitExceeded` | Channel's own rolling cap | Pause that channel 24 h |
| `invalid_grant` / 401 | Token revoked/expired | Alert to reconnect |
| Private-only behavior | Project unaudited | Fallback mode + audit application |

## Done when

- [ ] Existing upload code wrapped as the adapter and passing a test upload to a new channel.
- [ ] Public uploads confirmed (audit status known).
- [ ] Stats pulled hourly into analytics.

## Open questions

- [ ] Audit status of the existing project.
- [ ] Whether to use a second project for language channels once the first nears 100 uploads/day (check YouTube's terms on multiple projects first).
