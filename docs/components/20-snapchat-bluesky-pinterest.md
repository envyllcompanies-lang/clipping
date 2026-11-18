# Clipper Component 20 — Snapchat, Bluesky & Pinterest Connectors

Nov 18, 2026

Three smaller connectors round out the eight platforms. Snapchat has the most gated access, Bluesky is fully open, and Pinterest needs account warm-up; X is deferred until there's revenue.

## Snapchat Spotlight

| Item | Detail | Source |
| --- | --- | --- |
| API | Public Profile API, part of Snap's Marketing API; access is allowlist-only and requires submitting the account for review | [Ayrshare](https://www.ayrshare.com/blog/complete-guide-to-snapchat-api-integration/) |
| Setup | Snap Business account plus an organization in Ads Manager; the OAuth app is created from the Business Dashboard (not the Developer Portal, whose client IDs don't work here) | [Snap docs](https://developers.snap.com/marketing-api/Public-Profile-API/GetStarted), [Zernio](https://changelog.zernio.com/snapchat) |
| Account type | Public Profile (free to create in the app), switched to a Professional Profile; personal accounts can't post via API | [Ayrshare](https://www.ayrshare.com/snapchat-api.md) |
| Media | Upload is encrypted with AES-256-CBC before upload | [Zernio](https://changelog.zernio.com/snapchat) |
| Spotlight spec | Vertical 9:16, up to 60 s; deleting posts isn't supported via the API (must delete in app) | [Zernio](https://changelog.zernio.com/snapchat), [Sprout](https://support.sproutsocial.com/hc/en-us/articles/45438828017805-Guide-to-Snapchat-Publishing-Spotlights) |
| Post types | Stories, Saved Stories, Spotlight | [Ayrshare](https://www.ayrshare.com/snapchat-api.md) |

**Flow:** OAuth token → create media (encryption key and IV generated per upload) → upload encrypted chunks → finalize → create Spotlight post referencing the media → poll status.

**Plan:** apply for the allowlist in Phase 0. Until approved, either skip Snapchat or use a posting service that already has access. Because API deletes aren't supported, the takedown handler (15) adds Snapchat removals to a manual list in the dashboard.

## Bluesky

| Item | Detail | Source |
| --- | --- | --- |
| API | AT Protocol, open; authenticate with handle + app password (or OAuth) | [getlate](https://cdn.jsdelivr.net/gh/getlate-dev/social-media-api-best-practices@main/SKILL.md) |
| Video | Standard video up to 3 minutes | [Ayrshare](https://www.ayrshare.com/use-cases/video-content-platforms/) |
| Limits | Daily action-point budget (posts cost points) | [Orshot](https://orshot.com/docs/publish/social-posting-guidelines) |
| Text | 300 characters | |

**Flow:** create session → upload video blob through Bluesky's video service (processing job; poll until done) → create post record with the video embed, text, language tag and alt text.

Small audience today, but free and fully automatable; low priority in scheduling until analytics shows traction.

## Pinterest

| Item | Detail | Source |
| --- | --- | --- |
| API | Pinterest API v5: register media upload, upload video, create pin with board ID | |
| Limits | Standard access ~100 write requests per minute per user per app | [ShortSync](https://www.shortsync.app/resources/social-media-posting-limits-2026) |
| Warm-up | New accounts should be warmed up manually for 2–3 weeks (1 pin/day rising slowly) before automated posting | [Blotato](https://help.blotato.com/settings/social-accounts) |
| Requirements | Every pin needs a board; video specs 4 s–15 min | [bundle.social](https://info.bundle.social/api-reference/limits) |

**Flow:** `POST /v5/media` (register) → upload to returned URL → poll media status → `POST /v5/pins` with `board_id`, title, description, `media_source` video ID and cover image.

Pinterest suits evergreen, searchable clips (secrets, locations, how-to) better than reaction clips; packaging (14) writes keyword-rich titles for it.

## X (deferred)

Pay-per-use: about $0.015 per post, $0.20 with a link ([Socialync](https://www.socialync.io/blog/x-api-pricing-and-posting-2026)). The adapter slot exists; turn it on once revenue covers it.

## Done when

- [ ] Bluesky posts automatically with video.
- [ ] Pinterest posts automatically after warm-up.
- [ ] Snapchat allowlist requested; adapter built against the documented flow and tested once approved.

## Open questions

- [ ] Snapchat approval timeline; whether to use a pre-approved service in the meantime.
