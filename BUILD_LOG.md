# Build log

Status of the build. Spec: `docs/`. Run `make test` (fast unit tests), `make test-all`, and `make backtest-all`.

## Summary

All 7 phases are built and covered by unit tests. **Every quality backtest now runs on real data only**: the synthetic
ground-truth datasets were removed (they made results look far better than real streams do). Stages that grade
quality but have no real labelled data yet are listed under "Pending real data" instead of showing a made-up score.
Platform connectors, storage, the gate, the dashboard and provisioning are checked against faithful fakes of each API
(mechanics, not quality). What's left needs your keys, accounts and a host: see **Needs B**.

## Phase status

| Phase | Status |
| --- | --- |
| 1 Foundation and sources | done; recorder, chat and ingest graded on real Twitch data; radar needs ~2 weeks of live samples to grade |
| 2 Finding moments | done incl. docs 31/32; heatmap graded on 8 real GTA VI VODs (8 languages); transcription/audio/events need labelled real sets |
| 3 Making clips | done; research updates applied (text styles, sentence case, hook patterns, letterbox arm); quality needs real footage + your review |
| 4 Dashboard and public site | done; needs a host to be live for reviews |
| 5 Publishing | done in fallback mode against platform fakes; real uploads need the apps/keys |
| 6 Accounts and languages | done; **launch is English only** (other 9 languages `active: false`, opened when the doc 28 ranking justifies); the 6 English signups are yours |
| 7 Analytics and autopilot | done: refits, bandits (layouts + text arms), digest, deploy files; a real week needs live accounts |

## Real-data datasets

- `eval/datasets/viewer_clips/2026-11-18`: 8 GTA VI VODs (dvniel_play fr, xolixtwitch en, jefe en, cameliaaa92 fr,
  olesha ru, evelone2004 ru, alanzoka pt, montanablack88 de), the 4-hour span with the most viewer clips of each,
  1,331 viewer clips as labels. Built with official Helix (clips, videos) + streamlink VOD ranges (doc 04 route);
  media is deleted after feature extraction, only per-second feature arrays and clip labels are kept (7.5 MB).
  Rebuild: `make datasets` (`clip eval build-real viewer_clips`). VODs carry no chat replay.
- `eval/datasets/live_chat/2026-11-18T2131`: live IRC capture of 3 GTA VI channels (rubius, alanzoka, squeezie) with the
  clips made during capture. Counts and timings only, no usernames or message text.

## Backtest results (real data)

| # | Component | Result |
| --- | --- | --- |
| 02 | Stream recorder | live Twitch recording: started in 3.5 s, window extraction exact 100%, p95 0.28 s (≤ 10 s), disk 1.006× buffer (≤ 1.1) |
| 03 | Chat capture | no false missing time; 37.5% of clip moments have a chat spike within 10 s; spike-to-clip-label alignment within 2 s only 12.5% (median 6.5 s; the doc's 2 s needs on-screen events from 08) |
| 04 | Platform clips & VOD ingest | 1,000 real clips, every clip with a VOD offset mapped to a consistent UTC instant (100%); median 0.77 min from moment to clip |
| 05 | Moment heatmap | **recall@20 0.20** (doc target 0.7, not met), precision 0.46, on the 8 VODs without chat (audio, voice, visual + reaction). The synthetic 0.98 was not real. Chat and viewer clips, which real live streams add, can't be graded on VODs |
| 31 | Gameplay moment analysis | gameplay score **lowers** heatmap recall on both halves of every VOD (−0.05 fit half, −0.0125 test half) → heatmap weight 0; calibration builds a GTA 6 profile from raw VODs. Used in the clip builder (type-specific bounds, payoff anchor, hook style) |
| 32 | Creator profile & reaction | reaction at weight 0.5 raises recall on both halves (+0.0125, +0.025: one or two moments of 80, fragile) → kept, **only for streams without chat** (where it was validated); per-creator normalization did not beat a pooled baseline here (−0.025). Never-clip segments and catchphrases are used by the builder |
| 15 | Auto-gate (mechanics) | repeat to same account blocked; first post allowed; every decision has a reason; blocklist pulls everywhere |
| 16–20 | Publisher + connectors (mechanics vs API fakes) | one clip live on all 6; crash mid-upload / 5xx never double-post; quota reserve; spacing; fallbacks create one-tap tasks |
| 21 | Storage lifecycle | files deleted at last upload; disk flat over a simulated week; no orphans |
| 23 | Dashboard & kill switch (mechanics) | all alert types fire; pull-everywhere works in one worker cycle |
| 27 | Account provisioning (mechanics) | aliases, labels, passwords, handle checks, worksheets; codes routed only to the right row; re-run changes nothing |

Decision rule for docs 31/32 ("keep only what improves heatmap recall@20"): an extra signal's weight is chosen on the
first half of each VOD and must also improve the second half, otherwise it's 0 (`realeval.halves_gain`; backtests 31/32
re-decide on every new dataset). Doc bars that real data can't reach yet are marked `target_only` in
`eval/thresholds.yaml`: reported, but the gate is "no worse than the accepted baseline".

## Pending real data (no score until labelled real sets exist)

01 radar (2 weeks of live samples), 06 transcription WER (human transcripts of GTA streams), 07 music removal
(labelled music minutes), 08 game events (labelled HUD events per type), 09 clip builder boundaries, 10 reframe, 11
captions, 12 render timing on the M1, 13 style study (reference videos: see Needs B), 14 packaging, 22 analytics (a real
week of posts), 25 end-to-end on a live stream with live accounts, 28 language ranking (weeks of data), 31 type
precision / per-type IoU, 32 segment exclusion / catchphrases / collab alignment.

## Repo audit (docs/repos.md)

`scripts/repo_audit.py` checks every repo in `docs/repos.md` for license and activity and writes
[docs/repo-audit.md](docs/repo-audit.md) (82 repos: 61 reuse ok, 9 reuse with care, 3 dependency only, 1 CLI only,
6 study only, 2 dead links). Licenses GitHub can't classify were checked on PyPI or in the license file and are marked
"checked:" with the source.

- **Already built on listed repos:** streamlink (recording, VOD ranges), FFmpeg (as a separate process), Demucs
  (now pinned to the maintained 4.1 release), PANNs, faster-whisper, lingua-py, OpenCV + YuNet, tesseract, libass,
  imagehash. Nothing AGPL (Postiz, Ultralytics, MinIO, addy.io/SimpleLogin source) is imported; those are study-only.
- **Swapped in:** the `emoji` package (BSD, active) replaces two hand-written emoji regexes (headline overlay, chat
  features); one of them had already missed a two-emoji ending.
- **Removed:** piper-tts, pyopenjtalk-plus, pykakasi, fonttools (left over from the deleted synthetic datasets;
  piper pulled in GPL espeak-ng).
- **Kept our own code** where it's small, tested and fits the spec better than a library: the Postgres job queue
  (procrastinate is the listed alternative if it ever needs more), the bandits (repos.md itself says NumPy is enough).
- **Next gaps, by repo:** YouTube as a footage source: yt-dlp (Unlicense) to detect and fetch live streams without
  API quota, plus xenova/chat-downloader (MIT, last release 2025-11) for live chat. Kick clips: KickLib (MIT, C#) as
  the API reference. Better reaction/voice signals: silero-vad (MIT), MediaPipe face landmarks (Apache-2.0).

## Research update (docs/research/gta6-clip-examples.md, Nov 18)

- **Text styles** (11): two headline arms, white rounded box + black text (57%) and white text + black outline (43%),
  drawn as an overlay image so emoji endings keep their colour (libass draws emoji as monochrome outlines).
- **Text modes** (11): hook-only (60%, starting favorite), hook + key lines (25%), full subtitles (15%).
- **Headline case**: sentence case 75% / ALL CAPS 25%; creator names, "GTA 6" and acronyms keep their case.
- **Hook patterns** (14), written natively in all 10 languages: "creator + what happened + in GTA 6 + emoji" (40%) and
  "quote + context" (25%, the creator's own line picked from the transcript), plus the earlier patterns. Emojis match
  the reaction (laughter 😭🤣, shock 😳😨, hype 🔥). Post captions: short reaction line or ALL-CAPS topic + `#fyp #viral
  #gta #gta6 #<creator>`; YouTube titles creator-first with one emoji and a credit line.
- **Raw letterbox layout arm** (10): original 16:9 frame centered, black bars, original corner cam, hook in the top bar;
  8% starting share (stacked stays the favorite at 55%).
- **Music / celebrity moment type** (31) with the `music_subject` exception (07): the original mix is kept, the gate
  routes the clip to Snapchat/TikTok/Instagram/Facebook/YouTube and drops a platform once 3 of its last 5 such posts
  were blocked, muted or claimed. Launch weights: discovery now sits below comedy, crash and fail types.
- **Seed examples** (13): `clip style seed` loads the 7 examples into
  `config/styles/examples/gta6-clip-examples.yaml` with derived priors (box 57%, sentence case 86%, stacked 38K vs
  letterbox 15K mean views, discovery weakest). The style study also measures text mode and text style now.
- Analytics bandits learn text mode, text style and headline case per channel, like layouts.

## Needs B

Keys and accounts only you can create, each with why:

- ~~Twitch developer app~~: done (in `.env` only). Consider rotating the secret since it was pasted in chat.
- **Kick developer app** (`KICK_CLIENT_ID/SECRET`): Kick live polling (Kick treated the same as Twitch).
- **YouTube Data API key** (`YOUTUBE_API_KEY`): off-platform creator reach and language saturation scans.
- **LLM key** (`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MONTHLY_BUDGET_USD`): better hooks/titles; native templates until then.
- **Hosting** for the server worker, dashboard and policy pages (doc 25); policy pages must be live over HTTPS for reviews.
- **Storage bucket** (`BUCKET_*`): public URLs Instagram/Threads pull from.
- **Google Cloud project** (`GOOGLE_OAUTH_CLIENT_ID/SECRET`): YouTube uploads and stats; compliance audit.
- ~~Your existing YouTube uploader~~: reviewed (`legacy/youtube-uploader/`, reference only). It uses the same approach as the built-in connector (OAuth refresh + resumable `videos.insert`), so the built-in one is used.
- **Meta app** (`META_APP_ID/SECRET`), **TikTok developer app**, **Snap Business + Public Profile API allowlist**.
- **addy.io account** (`ALIAS_API_KEY`, `ALIAS_DOMAIN`), **Gmail connection**, **brand name** (`config/brand.yaml`).
- **Owner login** (`clip dashboard create-owner`), **the 6 English signups** from the worksheet at `/setup` (more languages later).
- **Style samples decision** (doc 13): how reference-channel videos may be obtained; then `clip style study <channel> <folder>`.
- **Labelled real sets** to grade the pending stages: a few hours of GTA stream transcripts (06), HUD event marks (08),
  sponsor/BRB minutes and known catchphrases (32), and your "would post" review of the first real clips (09–14).
- **One render timing on the MacBook**: `make backtest STAGE=12` there (VideoToolbox; target ≤ 30 s per 40 s clip).

## Notes

- Built and tested in a cloud Linux container: libx264 here, `h264_videotoolbox` on macOS; RAM detected at startup.
- Twitch's internal web API is never used; datasets use official Helix + streamlink only.
- Box-style headlines use Montserrat ExtraBold (bundled, OFL); a lighter Inter-like font for the box arm can be added later.
- Changes are on `claude/gta6-clipping-auto-post-afpoki` with draft PR #1 to `main`; merge the PR to land them.
