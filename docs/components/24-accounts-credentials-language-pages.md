# Clipper Component 24 — Accounts, Credentials & Language Pages

Nov 18, 2026

This component covers every account the system posts from and every credential it holds: how language pages are defined, how accounts are created and connected, and how tokens are stored and refreshed. It's mostly setup and safety, and mistakes here (shared phone numbers, leaked tokens, duplicate content across accounts) can sink whole networks.

## Language pages model

- A **channel** = one brand in one language, e.g. `gta6-<lang>`. Each channel has one account per platform it uses.
- Each channel sources only from creators streaming in its language (radar runs per language) and writes all text natively. No translated or dubbed clips.
- **Launch languages (10):** the top ten GTA streaming languages across Twitch, Kick and YouTube, all launched together:

  | Key | Language | Main source platforms | Notes |
  | --- | --- | --- | --- |
  | `en` | English | Twitch, YouTube, Kick | Largest audience, highest pay per view |
  | `es` | Spanish | Twitch, Kick | Huge GTA RP scene (Spain + Latin America) |
  | `pt` | Portuguese (Brazil) | YouTube, Kick, Twitch | Top-tier GTA creators |
  | `ar` | Arabic | Kick | Massive GTA RP, few clip pages |
  | `fr` | French | Twitch | Steady GTA audience |
  | `ru` | Russian | Twitch | Big reach; payouts limited for Russian audiences |
  | `de` | German | Twitch | Twitch's third-largest language |
  | `ja` | Japanese | Twitch, YouTube | Large GTA RP events |
  | `tr` | Turkish | Kick | Strong on Kick |
  | `vi` | Vietnamese | YouTube | One of the strongest GTA RP bases |

- **Re-ranking:** once GTA 6 is live, the radar (01) measures GTA 6 hours watched per language across all three platforms weekly. If a language outside the ten overtakes one inside it for 4 straight weeks (candidates: Polish, Chinese (Traditional, Taiwan/HK), Thai, Hindi, Indonesian, Italian, Korean), the dashboard flags the swap; analytics (22) shifts posting volume toward languages that perform.
- Channel config file (`config/channels/<key>.yaml`): language, time zone, style profile, voice notes, hashtags core set, account handles per platform, posting slots, score floor.
- YouTube focus: one main YouTube channel per language until it's monetized, since spreading views across channels delays each one's 10M-views-in-90-days threshold.

## Creating accounts

| Need | Practice |
| --- | --- |
| One email per language | Each language channel has one email, used for its account on every platform (one `es@` for Spanish TikTok, YouTube, Instagram, etc.). Never reuse that email for a second account on the same platform ([Recurpost](https://recurpost.com/?p=108090)) |
| Account types | Instagram Professional; Facebook Page; TikTok standard creator account; Snapchat Public Profile (Professional); YouTube channel under a Google account |
| Warm-up | New accounts post lightly at first; ramp volume up over the first weeks |
| Device/IP linking | Platforms can link accounts that share a device or IP ([Pixelscan](https://pixelscan.net/blog/can-you-have-multiple-tiktok-accounts/)); posting via official APIs avoids app switching, and staggering post times keeps accounts from looking coordinated |
| Distinct content | Different clips or distinct edits per account; never the same video across same-language brands on one platform |
| Branding | Name, avatar, banner and bio per channel; credit line style consistent within a channel |
| Records | An encrypted account register: platform, handle, email, recovery codes, 2FA method, owner (you) |

## Account provisioning tool (`accounts` package)

Automates everything around signups except the signup itself. Social account signups are done by hand by the owner; the tool does not automate platform registration, phone verification or CAPTCHAs.

**What it automates:**

1. **Emails: created automatically through an alias service (no custom domain).** The tool uses the addy.io API (SimpleLogin as the fallback provider; config chooses) to create one address per language channel on the service's own domain, e.g. `<brand>-en@…`, `<brand>-es@…`. Every address forwards to the owner's main inbox. Adding a language to `config/channels/` creates its address on the next run with no input. That one address signs the channel up on all six platforms.
   - **Fallback per platform:** if a platform rejects alias-service domains at signup, the worksheet marks it and that channel uses a Gmail account for that platform instead (created by hand; Google bans automated Gmail signups).
   - One-time owner step: create the alias-service account and put its API key in `.env` (`ALIAS_API_KEY`).
2. **Passwords.** Generates a unique strong password per account and stores it in the encrypted account register (never in the repo or logs).
3. **Handle check.** For each channel's planned handle, checks availability on each platform where a public profile URL can be queried, and suggests variants (`gta6clips.es`, `gta6_es`, `gta6clipsES`) when taken.
4. **Signup worksheet.** Prints (and shows in the dashboard) one checklist per channel: the email, the handle, the password reveal button, the platform's signup link, account type to choose (Professional/Creator/Page), 2FA to turn on, and a "connect" button that runs the OAuth flow to link the finished account to the system.
5. **Verification codes.** Every alias forwards to the owner inbox; with that inbox connected (Gmail API/IMAP), the dashboard pulls the latest signup or login code per language automatically and shows it next to the account.

**What the owner does by hand per account:** sign up in the platform's app or site with the generated email/handle/password, add the fallback phone only if the platform requires it, turn on 2FA (authenticator app rather than SMS where offered), then press "connect" in the dashboard.

**Phone numbers:** avoid adding a phone number wherever a platform lets you skip it. Where one is required, use the owner's fallback number, read from the `OWNER_PHONE` secret (`.env` locally, secret manager in production; never committed, never written to config or logs). The worksheet marks per platform whether a phone is required or skippable. Reusing one number across several language accounts on the same platform can hit per-number account limits or link those accounts; if that happens, add a dedicated SIM/eSIM line for the affected language.

**Global launch rollout:** the tool reads which languages to launch from config (chosen by the radar's per-language data), so the full set of addresses, handles and worksheets for every language can be created in one run before signups start.

## Developer apps (one each, shared by all channels)

Google Cloud project (YouTube Data + Analytics APIs, OAuth consent screen, compliance audit), Meta app (Instagram, Pages, Threads), TikTok developer app (Content Posting API, audit), Snap Business + Ads Manager org (Public Profile API allowlist), Twitch developer app (Helix, EventSub), Kick developer app (OAuth 2.1).

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
- [ ] Each language channel uses exactly one email across all its platforms; no email is used twice on the same platform.
- [ ] One run of the provisioning tool creates every channel's email alias, passwords and signup worksheets from config with no owner input.
- [ ] Secrets never appear in the repo or logs.

## Open questions

- [ ] Brand names and handle availability per language on all six platforms.
- [ ] LLC registration timing relative to monetization.
