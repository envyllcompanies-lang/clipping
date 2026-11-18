# Clipper Component 15 — Auto-Gate (Quality, Duplicates, Originality)

Nov 18, 2026

The Auto-Gate replaces human approval: every rendered clip passes a fixed set of automated checks before it can be queued for posting. It protects reach and monetization (duplicates, unoriginal reposts, music claims) and handles takedowns automatically, without stopping clips from being made.

## Job and boundaries

- **Does:** score and check each rendered version; pass, hold for re-edit, or reject; record the reason; handle creator objections and platform claims.
- **Doesn't:** require a person. The dashboard (23) shows decisions and offers a kill switch, but nothing waits for review.

## Checks, in order

| # | Check | Rule | Fail action |
| --- | --- | --- | --- |
| 1 | Technical | Render validation passed (12): duration, resolution, codecs, loudness, no black/silent gaps | Re-render once, then reject |
| 2 | Minimum score | Moment score (05) above the channel's floor; floor auto-tunes from analytics (22) | Reject |
| 3 | Duplicate (internal) | Perceptual video hash + audio fingerprint distance to every clip posted on the same platform in the last 90 days; also same source moment (overlapping UTC range from same stream) | Reject if same moment already posted to this account; allow a different edit on a different language channel |
| 4 | Duplicate (external) | Same moment already posted by us on another brand on the same platform | Require a distinct edit (different hook, crop, length) or route to another channel |
| 5 | Originality layer | Plan includes hook text, captions, credit and at least one more transformation (zooms, context text, compilation framing) | Send back to Clip Builder for a richer edit |
| 6 | Music risk | Residual music probability (07) below threshold across the clip | Mute flagged spans if under 2 s total; otherwise reject |
| 7 | Platform fit | Length, aspect, size within each target platform's limits | Drop that platform from targets, keep others |
| 8 | Blocklist | Creator not blocklisted; no paused source | Reject |
| 9 | Safety | Text fields free of slurs/personal info; no gore-only clips that platforms restrict | Reject or regenerate text |

A clip that passes gets `status = queued` with its list of target accounts; each check result is stored for analytics.

## Why the originality check matters

Since April 30, 2026, Instagram treats accounts as aggregators when most posts in a rolling 30 days are reposts without material edits, and removes them from recommendation surfaces; watermarks, borders, speed changes and light crops don't count ([Social Media Today](https://www.socialmediatoday.com/news/instagram-expands-originality-reach-penalties/819016/)). TikTok and YouTube judge originality per video for monetization. The gate keeps every account's mix clearly transformed.

## Account health guard

- Daily per account: share of posts flagged as unoriginal by the platform (where status APIs or account status pages expose it), claims received, and reach trend.
- If an account shows a recommendation restriction or 2+ claims in 7 days, the gate raises that account's score floor and originality requirements automatically until it recovers.

## Takedown and claim handling

1. **Creator objection** (email, DM or platform report forwarded to the dashboard): one action blocklists the creator; all their clips are unpublished across every platform via each connector's delete endpoint where available; pending clips are dropped.
2. **Copyright claim on a post:** the source and moment are recorded; the clip is removed or muted per the claim; that source is paused network-wide until the cause is understood (music missed by 07, creator objection, etc.).
3. **Strike:** the affected account's posting pauses automatically, and the dashboard alerts.

## Thresholds and tuning

- Every threshold lives in config per channel and platform.
- Analytics (22) adjusts the score floor weekly: raise it if low-score clips underperform, lower it if the queue runs dry.

## Done when

- [ ] No clip reaches a platform without passing all checks; every decision has a stored reason.
- [ ] Zero exact duplicates posted to the same account.
- [ ] Blocklisting a creator removes their clips everywhere within 1 hour.

## Open questions

- [ ] Starting score floor per channel (set after the first week of data).
