# Clipper Component 29 — Public Site & Policy Pages

Nov 18, 2026

The public site is the small set of pages platform reviewers require before they grant publishing access: privacy policy, terms of service, data-deletion instructions and callback, and a landing page describing the app. TikTok's Content Posting audit and Meta's app review both check these. It's hosted on a free subdomain, so no custom domain is needed.

## Job and boundaries

- **Does:** static legal and info pages, the Meta data-deletion callback endpoint, OAuth redirect URIs for every platform, and the TikTok audit demo entry point.
- **Doesn't:** host the operational dashboard's private screens (Component 23), though both can share one deployment.

## Pages

| Path | Content | Required by |
| --- | --- | --- |
| `/` | What the app does (automated clip publishing to the owner's own accounts), contact email, links to policies | Meta, TikTok, Google OAuth consent screen |
| `/privacy` | Data collected (account identifiers, tokens, post metadata, analytics), purpose, retention (tokens until disconnect; clips deleted after upload per doc 21), third parties (platform APIs, LLM provider, hosting), user rights, contact | Meta, TikTok, Google, Snap |
| `/terms` | Service terms, acceptable use, termination, liability limits | TikTok, Meta |
| `/data-deletion` | How a user disconnects and requests deletion | Meta (data deletion instructions URL) |
| `POST /api/meta/data-deletion` | Signed-request callback: parse `signed_request`, delete that user's tokens and records, return `{url, confirmation_code}` | Meta (data deletion callback) |
| `/api/oauth/<platform>/callback` | OAuth redirect URIs for Google, Meta, TikTok, Snap, Twitch, Kick | All apps |

Page text is generated from templates with the brand name and contact email filled in; the owner should read them once before submitting reviews. Pages are in English (reviewers' language).

## Hosting

- Default: deploy with the dashboard on a free host subdomain (e.g. `<brand>.vercel.app`), HTTPS included.
- Google's OAuth consent screen may ask for authorized domains; a host subdomain works for testing, and verification may later require a domain the owner controls (re-check at audit time).
- TikTok URL pulls need a verified domain; without one, the TikTok connector (19) uses `FILE_UPLOAD`, so no domain is needed.

## Contact email

Uses a dedicated alias created by the provisioning tool (27): `<handle_base>-contact@…`, labelled `Clipping/Contact`.

## Done when

- [ ] All pages live over HTTPS on the free subdomain.
- [ ] Meta's data-deletion callback passes Meta's test tool and deletes the test user's data.
- [ ] Every platform app's redirect URI points at a working callback route.

## Open questions

- [ ] Whether Google verification requires an owned domain for this app's scopes (check during the audit).
