# Clipper Component 23 — Dashboard & Kill Switch

Nov 18, 2026

The dashboard is the phone-friendly control room: it shows what the system is doing and what it posted, and gives one-tap controls to pull a clip, pause a channel or reconnect an account. Nothing waits on it (there's no approval step), and it doubles as the multi-user product TikTok's audit requires.

## Job and boundaries

- **Does:** monitoring, controls, alerts, setup flows (connect accounts, add channels), and explanations of automatic decisions.
- **Doesn't:** gate posting. The pipeline runs without anyone opening it.

## Screens

| Screen | Shows | Actions |
| --- | --- | --- |
| Home | Today's posts, queue size, system health (recorder, M1, scheduler), alerts | Global pause |
| Live | Streams recording now, heatmap curve per stream with candidate windows marked | Stop a recording |
| Clips | Built clips with preview, gate decisions and reasons, target platforms, status per platform | Pull clip everywhere, re-queue, block creator |
| Posted | Per post: platform links, stats curve, performance score | Delete from one or all platforms |
| Channels | Each language/brand channel: accounts per platform, quota used, posting slots, style profile, monetization progress | Pause channel, change profile, edit slots |
| Creators | Radar ranking with every signal and percentile, why selected, clips sourced and their results | Blocklist, pin, unpin |
| Accounts | Token status, review/audit status per platform (YouTube audit, TikTok audit, Meta app, Snap allowlist) | Reconnect, re-authorize |
| Analytics | Weekly digest, weight changes with explanations, A/B arms | Freeze learning, roll back weights |
| Fallback tasks | Items needing a tap (YouTube private uploads to publish, TikTok inbox drafts, Snapchat manual deletions) | Mark done |
| Storage | Disk free on server and M1, files by kind, sweeper log | Run sweeper |

## Kill switch

- **Clip level:** "Pull everywhere" cancels pending jobs and calls each connector's `delete()`; platforms without API delete (Snapchat) land in Fallback tasks.
- **Channel level:** pause stops new posts for that channel on all platforms; in-flight uploads finish.
- **Global:** pause halts scheduler and rendering; recording can continue so no moments are lost.

## Alerts (push and email)

Token expired, strike or claim received, account reach restriction detected, disk guard triggered, recorder down, M1 offline over 6 h, posting failures over threshold, Kick chat socket silent while live.

## Tech

- Next.js (or similar) web app, deployed on the cloud host (25), mobile-first layout.
- Auth: email login with 2FA for the owner; multi-user accounts for the TikTok audit flow.
- Reads the same database as the pipeline; actions write commands to a `command` table the workers consume.
- Real-time updates via server-sent events or polling every 15 s.

## TikTok audit requirements built in

Sign-up/login for any user, connect-TikTok flow, a posting screen showing the creator's nickname, privacy choice from allowed options, comment/duet/stitch toggles, content disclosure, preview and explicit consent, plus privacy policy and terms pages (Component 19).

## Done when

- [ ] Every component's status visible from a phone in under 3 taps.
- [ ] Kill switch removes a clip from every API-deletable platform within 5 minutes.
- [ ] All alerts fire on simulated failures.

## Open questions

- [ ] Domain name for the dashboard and policy pages.
