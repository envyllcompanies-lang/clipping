# Clipper Component 22 — Analytics & Feedback Loop

Nov 18, 2026

Analytics collects performance for every post, links it back to every decision that produced the clip, and retunes the system weekly by statistics: which creators, moments, lengths, hooks, styles, platforms and posting times win. This is the moat: competitors' scores are trained on generic data; ours is trained on our own results in GTA 6.

## Job and boundaries

- **Does:** pull stats per post on a schedule, compute normalized performance, store features per clip, fit models, and push updated weights and thresholds to other components.
- **Doesn't:** make creative calls directly; it only changes weights, thresholds, allocations and A/B arms.

## Collection schedule

| Age of post | Pull frequency |
| --- | --- |
| 0–48 h | Hourly |
| 2–14 days | Daily |
| 14–90 days | Weekly |
| 90+ days | Stop (final values kept) |

Per platform metrics come from each connector's `stats()` (Components 17–20): views, likes, comments, shares, saves, followers gained where available, and retention (average view duration / percent viewed) on YouTube and wherever exposed.

## Normalized performance score

Raw views aren't comparable across platforms, accounts and ages. For each post:

1. Views at 48 h (or the latest age matched to 48 h by growth curves).
2. Divide by the account's rolling median 48 h views (relative performance; 1.0 = typical).
3. Combine with retention where available: performance = 0.6 × relative views + 0.4 × relative retention.
4. Log-transform for modelling.

## Features stored per clip

Creator and their radar signals; moment signals at the peak (chat velocity, clip density, audio, events); event type; clip length; cold open yes/no; hook pattern; title style; caption style/profile; layout; zoom rate; language; platform; account; posting hour and weekday; time since moment happened (freshness); trend status.

## What gets learned (weekly)

| Model | Target | Updates |
| --- | --- | --- |
| Heatmap weights | Viewer clip positions, then our performance | Component 05 signal weights |
| Creator weights | Performance by source creator | Component 01 signal weights |
| Score floor | Performance vs moment score | Component 15 minimum score per channel |
| Format effects | Performance by length, hook, cold open, layout (stacked vs full gameplay vs small cam; split ratio), text mode (hook only vs hook + key lines vs full subtitles), caption colors, profile | Components 09, 10, 11, 13 defaults; A/B arm allocation per language channel and platform |
| Posting times | Performance by hour/weekday per account | Component 16 slots |
| Platform mix | Performance and monetization progress per platform | Volume allocation in 16 |

Methods: regularized linear/logistic regression for interpretability; Thompson-sampling bandits for A/B arms (styles, hook patterns); changes ship only if they beat the current setting on a held-out week.

## Monetization progress tracking

- YouTube: subscribers and qualified Shorts views over the last 90 days vs 10M (20M for new applicants from February 1, 2027) ([Tubefilter](https://www.tubefilter.com/?p=193559)).
- TikTok: followers vs 10,000 and views over 30 days vs 100,000, counting only 1-minute-plus videos for earnings ([terms via Lilach Bullock](https://www.lilachbullock.com/?p=136446)).
- Shown per account on the dashboard with projected dates at current pace.

## Weekly digest

Auto-generated summary (in the dashboard and optionally emailed): top 10 clips, what changed in weights and why, accounts at risk (reach drops, claims), monetization progress, best creators this week.

## Done when

- [ ] Every post has stats on schedule with under 2% missing pulls.
- [ ] Weekly refits run automatically with a held-out check and a changelog.
- [ ] The dashboard explains each automatic change in plain language.

## Open questions

- [ ] Minimum data before trusting refits (start: 200 posts per platform).
