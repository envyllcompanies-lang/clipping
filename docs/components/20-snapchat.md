# Clipper Component 20 — Snapchat Connector

Nov 18, 2026

Snapchat Spotlight rounds out the six platforms and has the most gated access. X is deferred until there's revenue. Pinterest and Bluesky were dropped.

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

## X (deferred)

Pay-per-use: about $0.015 per post, $0.20 with a link ([Socialync](https://www.socialync.io/blog/x-api-pricing-and-posting-2026)). The adapter slot exists; turn it on once revenue covers it.

## Done when

- [ ] Snapchat allowlist requested; adapter built against the documented flow and tested once approved.

## Open questions

- [ ] Snapchat approval timeline; whether to use a pre-approved service in the meantime.
