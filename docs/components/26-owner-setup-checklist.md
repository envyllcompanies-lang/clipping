# Clipper Component 26 — Owner Setup Checklist

Nov 18, 2026

Everything the owner does by hand, in order. Claude Code builds the system; these are the steps only a person can do (signups, verification, reviews, payments). Each step says when it's needed, so nothing blocks the build early.

## Before Phase 1 (needed to start building)

- [ ] Clone the repo on the MacBook and open it in Claude Code.
- [ ] Put the existing YouTube upload code in `legacy/youtube-uploader/` (or tell Claude Code where it lives); doc 17 reuses it.
- [ ] Create a **Twitch developer app** (dev.twitch.tv → Console → Register app). Put the client ID/secret in `.env`.
- [ ] Create a **Kick developer app** (Kick developer settings, OAuth 2.1). Put the client ID/secret in `.env`.
- [ ] Install local tools when Claude Code asks (Python 3.11+, FFmpeg, streamlink, Postgres or Docker).

## Phase 0, in parallel (reviews take weeks; start once there's a working app to show)

- [ ] **Google Cloud project**: enable YouTube Data API v3 and YouTube Analytics API, set up the OAuth consent screen, then submit the **YouTube API compliance audit** (needed for public uploads).
- [ ] **Meta app** (developers.facebook.com): Instagram Graph API, Pages, Threads. Submit **app review** for publishing permissions.
- [ ] **TikTok developer app**: Content Posting API. Submit the **audit** (until approved, posts are private-only). The dashboard (23) includes the screens the audit requires.
- [ ] **Snap Business account** + Ads Manager organization; request **Public Profile API allowlist** access.
- [ ] Privacy policy and terms pages live on the dashboard domain (needed by TikTok and Meta reviews).

## Before signups (after the build works end to end)

- [ ] Pick the **brand name** (one brand, localized per language) and check handle availability; the `accounts` tool (24) does the check and suggests variants.
- [ ] Buy the **domain** and put it on Cloudflare.
- [ ] Run the `accounts` tool: creates `en@`, `es@`, `pt@`, `ar@`, `fr@`, `ru@`, `de@`, `ja@`, `tr@`, `vi@` on the domain (forwarding to your inbox), passwords and the signup worksheets.
- [ ] Set `OWNER_PHONE` in `.env`. It's used only where a platform requires a phone; skip the phone wherever it's optional.
- [ ] For each of the 10 languages, sign up on the 6 platforms (60 accounts) using the worksheet:
  - YouTube channel (under the language's Google account)
  - TikTok creator account
  - Instagram, switched to Professional
  - Facebook Page
  - Threads (through Instagram)
  - Snapchat Public Profile, switched to Professional
- [ ] Turn on 2FA everywhere (authenticator app where offered) and save recovery codes in the encrypted register.
- [ ] Press **connect** for each account in the dashboard (runs the OAuth flow).
- [ ] Ramp up: new accounts post lightly for the first weeks; the scheduler (16) handles the ramp.

## Before going live 24/7

- [ ] Pick and pay for hosting (doc 25): always-on VPS (recording, scheduling, posting), managed Postgres, storage bucket, dashboard host.
- [ ] Put production secrets in the host's secret manager (never in the repo).
- [ ] Choose the LLM provider and a monthly cost ceiling.

## Before payouts

- [ ] Decide on registering Envy as an LLC and opening a business bank account.
- [ ] Add tax and payout details on each platform as each account becomes eligible (YouTube Partner Program, TikTok Creator Rewards, Meta and Snapchat programs). The dashboard tracks progress to each threshold (22).

## Not automated (by decision)

- Social account signups, phone verification and CAPTCHAs are done by hand.
- Clips that can't be downloaded are never screen-recorded; those moments are cut from our own stream recordings.
