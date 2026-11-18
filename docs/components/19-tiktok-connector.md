# Clipper Component 19 — TikTok Connector

Nov 18, 2026

The TikTok connector posts through TikTok's Content Posting API. The blocker isn't code: until TikTok audits the app, every post is private (SELF_ONLY) and only 5 users can post per day, so the plan is to build the full flow now and pass the audit as early as possible.

## API facts (verify at build)

| Item | Value | Source |
| --- | --- | --- |
| Modes | Direct Post (publishes) or Upload to the creator's inbox as a draft | [Vorp Labs](https://vorplabs.com/agent-tools/tiktok-content-posting-api) |
| Unaudited apps | All posts restricted to private (SELF_ONLY); up to 5 users can post in 24 h; accounts must be private at posting time | [TikTok guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines) |
| Audit | Reviews intended use and a required posting UX; apps must be for a wide audience, internal tools get rejected; review may take several days to two weeks | [AdaptlyPost](https://adaptlypost.com/blog/why-does-my-app-need-approval-post-tiktok) |
| Posting cap | Typically around 15 Direct Posts per creator per day, shared across all apps | [AdaptlyPost](https://adaptlypost.com/blog/tiktok-post-limit-per-day) |
| Rate | 6 upload starts per minute per token | [ShortSync](https://www.shortsync.app/resources/social-media-posting-limits-2026) |
| Pull from URL | Requires a verified domain (`url_ownership_unverified` error otherwise) | [PostPeer](https://www.postpeer.dev/errors/tiktok) |
| Monetization | Creator Rewards: 10,000 followers, 100,000 views in 30 days, only original videos over 1 minute earn | [TikTok terms via Lilach Bullock](https://www.lilachbullock.com/?p=136446) |

## Post flow (Direct Post)

1. **Query creator info** for the account first (privacy options allowed, max video duration, whether comments/duet/stitch can be set). TikTok's UX rules require the posting interface to respect these values.
2. **Init:** `POST /v2/post/publish/video/init/` with `post_info` (title/caption, privacy level from the allowed list, disable_comment/duet/stitch flags, cover timestamp) and `source_info` (`FILE_UPLOAD` with chunk sizes, or `PULL_FROM_URL` with a URL on our verified domain).
3. **Upload** chunks to the returned upload URL (FILE_UPLOAD), or let TikTok pull.
4. **Status:** poll the publish status endpoint until published or failed; store `publish_id` and final post ID.

## Versions

- **Long version (61–90 s)** for monetization eligibility.
- **Short version** for reach tests; analytics decides the mix per account.

## Audit strategy

TikTok rejects internal-only tools, so the dashboard (Component 23) must be built as a real multi-user product to pass:

- A sign-up/login and "connect your TikTok" flow for any user.
- A posting screen that shows the creator's nickname, lets the user choose privacy from the allowed options, toggles for comments/duet/stitch, a content-disclosure option, a preview, and explicit consent before posting, matching TikTok's posting UX guidelines.
- Privacy policy and terms pages on our domain; verified domain for URL pulls.
- Demo video of the flow for the audit submission.

Alternatives if the audit fails or stalls: inbox-draft mode (each post finished with a tap in the TikTok app), or an already-audited posting service.

## Multiple accounts

TikTok allows multiple accounts but treats near-duplicate accounts reposting the same video as spam, and can link accounts by device and IP ([Recurpost](https://recurpost.com/blog/multiple-tiktok-accounts/)). Each language account gets its own clips and its own email and phone; API posting avoids device switching, but posting times stay staggered.

## Stats

- Video query endpoint for views, likes, comments, shares per post (needs the `video.list` scope); hourly for 48 h then daily.

## Errors

| Error | Action |
| --- | --- |
| `unaudited_client_can_only_post_to_private_accounts` | Fallback to inbox drafts; push audit |
| Spam/risk flags | Pause the account 24–48 h, lower its volume, vary captions |
| Daily cap reached | Stop until rolling window clears |
| `url_ownership_unverified` | Verify domain or switch to FILE_UPLOAD |

## Done when

- [ ] Full Direct Post flow works in private mode on our accounts.
- [ ] Audit submitted with a compliant posting UX.
- [ ] After approval, public posts go out automatically with long versions.

## Open questions

- [ ] Our domain for TikTok verification and policy pages.
