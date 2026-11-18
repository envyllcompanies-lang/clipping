# Clipper Component 24 — Accounts, Credentials & Language Pages

Nov 18, 2026

This component covers every account the system posts from and every credential it holds: how language pages are defined, how accounts are created and connected, and how tokens are stored and refreshed. It's mostly setup and safety, and mistakes here (shared phone numbers, leaked tokens, duplicate content across accounts) can sink whole networks.

## Language pages model

- A **channel** = one brand in one language, e.g. `gta6-<lang>`. Each channel has one account per platform it uses.
- Each channel sources only from creators streaming in its language (radar runs per language) and writes all text natively. No translated or dubbed clips.
- **Which languages:** decided by data: GTA 6 viewer share by stream language on Twitch/Kick and how crowded existing clip pages in that language are. Start with the main language plus the one or two the data ranks highest; add more as each proves out.
- Channel config file (`config/channels/<key>.yaml`): language, time zone, style profile, voice notes, hashtags core set, account handles per platform, posting slots, score floor.
- YouTube focus: one main YouTube channel per language until it's monetized, since spreading views across channels delays each one's 10M-views-in-90-days threshold.

## Creating accounts

| Need | Practice |
| --- | --- |
| Unique identity per account | Each account gets its own email and phone number; platforms don't allow reusing them across accounts ([Recurpost](https://recurpost.com/?p=108090)) |
| Account types | Instagram Professional; Facebook Page; TikTok standard creator account; Snapchat Public Profile (Professional); YouTube channel under a Google account; Pinterest business account; Bluesky handle (custom domain optional) |
| Warm-up | New accounts post lightly at first; Pinterest explicitly needs 2–3 weeks of manual warm-up ([Blotato](https://help.blotato.com/settings/social-accounts)) |
| Device/IP linking | Platforms can link accounts that share a device or IP ([Pixelscan](https://pixelscan.net/blog/can-you-have-multiple-tiktok-accounts/)); posting via official APIs avoids app switching, and staggering post times keeps accounts from looking coordinated |
| Distinct content | Different clips or distinct edits per account; never the same video across same-language brands on one platform |
| Branding | Name, avatar, banner and bio per channel; credit line style consistent within a channel |
| Records | An encrypted account register: platform, handle, email, recovery codes, 2FA method, owner (you) |

## Developer apps (one each, shared by all channels)

Google Cloud project (YouTube Data + Analytics APIs, OAuth consent screen, compliance audit), Meta app (Instagram, Pages, Threads), TikTok developer app (Content Posting API, audit), Snap Business + Ads Manager org (Public Profile API allowlist), Pinterest app, Twitch developer app (Helix, EventSub), Kick developer app (OAuth 2.1), Bluesky app passwords.

## Credential storage

- Secrets (client secrets, refresh tokens, app passwords) encrypted at rest in the database with a key held in the host's secret manager (never in the repo; `.env` only for local dev).
- Least privilege: only the scopes each connector needs.
- Token refresh jobs run ahead of expiry (Kick tokens last 2 hours; others vary); failures raise an alert to reconnect.
- Audit log of every token use and every post, tied to the account.
- 2FA on every account; recovery codes stored in the encrypted register.

## Payouts and taxes

Monetization payouts require tax and payment details on each platform. Decide whether Envy becomes a registered LLC before connecting payout methods, so payouts land in a business account from the start.

## Done when

- [ ] Every channel defined in config, with each platform account connected and tokens healthy on the dashboard.
- [ ] No two accounts share an email or phone number.
- [ ] Secrets never appear in the repo or logs.

## Open questions

- [ ] Brand names and handle availability per language on all eight platforms.
- [ ] LLC registration timing relative to monetization.
