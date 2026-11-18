# GTA 6 AI Clipper — Build Plan

Nov 18, 2026 · @B

## Summary

We build a game-agnostic clipping engine that turns long gameplay recordings into short vertical clips, then publishes them to YouTube Shorts, Instagram Reels and TikTok. GTA 6 is the first vertical. Publishing can be close to fully automatic, but each platform has to approve the app first. Until then, uploads land private.

Assumptions this plan makes (change any in Open decisions):

- All footage comes from the top GTA 6 creators on Twitch, Kick and YouTube. No own gameplay. The model is the best clipping channels, replicated and run at scale.
- Start with one brand on all three platforms, built so more channels are a config file, not new code.
- Fully automatic, with no human approval. Automated checks (duplicate, minimum score) decide what gets posted.
- Near-$0 running cost: heavy processing runs locally, and only the scheduler and storage live in the cloud.
- Built in-house in Python with Claude Code in ultracode mode, in the repo github.com/envyllcompanies-lang/clipping. Currently in the planning phase: nothing is built yet.

## Component docs

Every component has its own detailed doc: job and boundaries, inputs, step-by-step design, parameters, data stored, failure handling, done-when checks and open questions. This plan stays the overview; the component docs are the build specs for Claude Code.

| # | Component | Doc |
| --- | --- | --- |
| 01 | Creator Radar | [Open](components/01-creator-radar.md) |
| 02 | Stream Recorder | [Open](components/02-stream-recorder.md) |
| 03 | Chat Capture | [Open](components/03-chat-capture.md) |
| 04 | Platform Clips & VOD Ingest | [Open](components/04-platform-clips-vod-ingest.md) |
| 05 | Moment Heatmap & Scoring | [Open](components/05-moment-heatmap-scoring.md) |
| 06 | Transcription | [Open](components/06-transcription.md) |
| 07 | Audio Cleanup & Music Removal | [Open](components/07-audio-cleanup-music-removal.md) |
| 08 | Game Event Detection (GTA 6 Profile) | [Open](components/08-game-event-detection.md) |
| 09 | Clip Builder (Boundaries & Hooks) | [Open](components/09-clip-builder.md) |
| 10 | Reframe & Layout | [Open](components/10-reframe-layout.md) |
| 11 | Captions & On-screen Text | [Open](components/11-captions-onscreen-text.md) |
| 12 | Render Engine | [Open](components/12-render-engine.md) |
| 13 | Style Study & Style Profiles | [Open](components/13-style-study-profiles.md) |
| 14 | Packaging (Titles, Captions, Hashtags) | [Open](components/14-packaging.md) |
| 15 | Auto-Gate (Quality, Duplicates, Originality) | [Open](components/15-auto-gate.md) |
| 16 | Publisher Framework & Scheduler | [Open](components/16-publisher-framework-scheduler.md) |
| 17 | YouTube Shorts Connector | [Open](components/17-youtube-connector.md) |
| 18 | Meta Connectors (Instagram, Facebook, Threads) | [Open](components/18-meta-connectors.md) |
| 19 | TikTok Connector | [Open](components/19-tiktok-connector.md) |
| 20 | Snapchat Connector | [Open](components/20-snapchat.md) |
| 21 | Storage Lifecycle & File Manager | [Open](components/21-storage-lifecycle.md) |
| 22 | Analytics & Feedback Loop | [Open](components/22-analytics-feedback-loop.md) |
| 23 | Dashboard & Kill Switch | [Open](components/23-dashboard-kill-switch.md) |
| 24 | Accounts, Credentials & Language Pages | [Open](components/24-accounts-credentials-language-pages.md) |
| 25 | Infrastructure, Hosting & Data Model | [Open](components/25-infrastructure-hosting-data-model.md) |

## Findings that change the design

Six things researched on November 18, 2026 that the build has to account for. The biggest: Meta now hides repost-heavy accounts from recommendations, and both YouTube and TikTok gate payouts behind thresholds that favour a few strong channels over many thin ones.

| Finding | What it means for the build |
| --- | --- |
| **Instagram/Facebook originality rules.** Since April 30, 2026, Instagram treats an account as an aggregator if most of its posts in a rolling 30 days are reposts without "material" edits, and removes it from Explore and other recommendation surfaces ([TubeFilter](https://tubefilter.com/2026/04/30/instagram-removes-algorithm-recommendations-repost-content-aggregator), [Social Media Today](https://www.socialmediatoday.com/news/instagram-expands-originality-reach-penalties/819016/)). Watermarks, borders, speed changes and light crops don't count as edits. Facebook has penalized unoriginal content since 2025 | The Edit stage must add real transformation to every clip on Meta platforms: hook text, captions, zooms, commentary or context overlays, ranking/compilation framing. Plain re-cuts will get the accounts buried. Track each account's "recommendation eligibility" in Instagram's account status |
| **YouTube Shorts monetization.** Today: 1,000 subscribers plus 10M qualified Shorts views in 90 days. From February 1, 2027, new applicants need 20M Shorts views in 90 days, and existing members need 10M every 90 days to keep Shorts revenue ([YouTube changes via Tubefilter](https://www.tubefilter.com/?p=193559), [AIR Media-Tech](https://air.io/en/monetization/youtube-partner-program-requirements-2026-the-complete-guide)) | Spreading views across many YouTube channels makes each one miss the threshold. Concentrate on one main YouTube channel per language until it's monetized, then expand. Getting a channel in before February 1, 2027 halves the bar |
| **TikTok Creator Rewards.** 10,000 followers, 100,000 views in 30 days, only original videos over 1 minute earn ([TikTok program terms via Lilach Bullock](https://www.lilachbullock.com/?p=136446)) | Under-60 s clips earn nothing on TikTok. Render a 61–90 s version (compilation or extended moment) for TikTok monetization, alongside short versions for reach. Originality is judged per video |
| **GTA 6 radio and licensed music.** A song playing in the game is not a license to publish it; Rockstar's guidance gives no blanket soundtrack license, and Content ID claims on in-game radio songs are long-standing ([iTechGuides](https://www.itechguides.com/gta-vi-music-what-creators-can-safely-use-in-videos-and-streams), [Kotaku](https://kotaku.com/heres-what-youtube-has-to-say-to-angry-youtubers-1485168478)) | Streamers' radio will be in the source audio. Add music detection plus source separation (split voice and game sound from music) so radio is removed or ducked before render. This protects monetization on every claim-checking platform |
| **Recording cost.** Twitch 1080p60 is about 2.7 GB per hour; Streamlink saves the source without re-encoding, so recording is storage- and bandwidth-bound, not CPU-bound ([space-node](https://space-node.net/blog/record-twitch-stream-automatically-vps-script)) | 10 creators streaming 6 hours a day is about 160 GB a day. Keep only windows around scored moments and delete the rest within 24–48 h. Recording should run on a cheap always-on server, not the MacBook |
| **Multiple accounts.** Multiple accounts are allowed, but near-duplicate accounts posting the same video get flagged as spam, and accounts sharing a device or IP can be linked as a network ([Recurpost](https://recurpost.com/blog/multiple-tiktok-accounts/), [Ayrshare](https://app.ayrshare.com/docs/help-center/technical-support/tiktok_account_restricted)) | Language pages are safe (different content). Several brands on the same platform posting the same clip is a reach risk: give each a different edit or different clips. Each account needs its own email and phone number |

## Still to look into

- [ ] Chat capture: Twitch chat (IRC/EventSub), Kick chat (websocket), YouTube live chat (quota cost) for the chat-velocity signal.
- [ ] Kick: official API scope and how to record Kick streams.
- [ ] Snapchat, Facebook and Threads monetization programs and thresholds.
- [ ] Payouts and taxes: platforms need tax info for payouts; decide whether to register Envy as a formal LLC first.
- [ ] Account setup logistics: an email and phone number per account, devices, warm-up period for new accounts.
- [ ] Compute: transcription and render speed on your MacBook model; when a cloud worker becomes necessary.
- [ ] GTA 6 platform IDs: Twitch game ID and Kick category once launched (November 19, 2026).
- [ ] Brand names and handle availability on all six platforms, per language.
- [ ] Hosting picks: recorder server, database, storage bucket, dashboard host.

## Architecture

Seven stages share one database of sources, clips, channels and posts. Rendering stays on the MacBook, where it costs nothing. The posting checks, publishing and analytics run in the cloud, so scheduled posts still go out with the laptop closed.

&#91;embedded content: pipeline · 7 stages, 1 feedback loop\]

The analytics loop is what makes this more than an editor: each clip's results update the scoring weights the Analyze stage uses.

Stack: Python worker (faster-whisper, PySceneDetect, FFmpeg, an LLM API), Postgres or SQLite, object storage for clip URLs, a Next.js dashboard, and a cron-driven publisher with one adapter per platform. A game profile (vocabulary, moment types, templates) keeps the engine game-agnostic.

## Competitive teardown

The top tools do five things well, and each can be rebuilt from open components. Our advantage is a gaming-specific engine with a score trained on our own post results, not generic "viral" data.

Clean-room rules (not legal advice):

- Learn from public pages, reviews, and the outputs of your own trial accounts.
- Don't decompile or scrape their apps. Don't feed their outputs into our models.
- Don't copy their caption templates, UI, or trademarked names (ClipAnything, Virality Score). Ours get our own designs and names.

| Capability | Who leads | What it does | How we build our version |
| --- | --- | --- | --- |
| Moment detection | [OpusClip](https://thecmo.com/tools/opusclip-review/) | Finds moments from visual, audio and sentiment cues, in any genre | Fused score from transcript sentiment, audio energy spikes, scene cuts, and a vision model on sampled frames |
| Engagement score | [OpusClip](https://www.castmagic.io/software-reviews/opus-clip) | 0–99 per clip, built from hook, flow, value and trend | LLM rubric scoring at first. Later, a small model trained on our own clips' real retention and views. That's the moat |
| Gaming event detection | [Eklipse](https://eklipse.gg/ai-highlights) | Detects kills, clutches, fails and hype moments across 1,000+ games, plus chat spikes and "clip it" voice commands | GTA profile: on-screen HUD events (wanted level, mission complete, death screens) read by OCR or image matching, chat-log spikes, and voice triggers in the transcript. HUD details get confirmed against the real game |
| Reframe to 9:16 | [OpusClip](https://tooliverse.ai/tools/opusclip) | Object tracking keeps moving subjects centered | Object and face detection with smoothed crop paths, plus a split layout when there's a facecam |
| Animated captions | [Submagic](https://www.castmagic.io/blog/opus-clip-alternatives) | Strongest caption styling and polish | Word-level timestamps from faster-whisper, rendered as styled ASS subtitles with keyword highlights. Our own style set |
| Clean clip boundaries | Weak spot across tools | [Reviewers flag](https://tooliverse.ai/tools/opusclip) clips that start or end abruptly | Snap cuts to sentence ends and silence gaps, and add a short lead-in before each peak moment |
| Auto-posting | OpusClip, Vizard and others | Scheduled posting to the major platforms | Already in this plan (Upload automation) |

## Open-source building blocks

Most stages already have a solid open-source starting point, so the build is mostly wiring and tuning, not invention. Check each license before copying code; reading for ideas is always fine.

| Stage | Repo | Why it fits | Notes |
| --- | --- | --- | --- |
| Record live streams | [streamlink](https://github.com/streamlink/streamlink) | Saves Twitch/Kick/YouTube streams without re-encoding, so recording costs disk, not CPU | Runs on a cheap always-on server ([guide](https://space-node.net/blog/record-twitch-stream-automatically-vps-script)) |
| Twitch VOD chat | [TwitchDownloader](https://github.com/lay295/TwitchDownloader) (CLI, MIT), [Twitch-Chat-Downloader](https://github.com/PetterKraabol/Twitch-Chat-Downloader) (Python, MIT) | Full chat replay with timestamps for VODs, so chat velocity works even on streams we didn't watch live | TwitchDownloader's CLI runs on macOS and Linux |
| YouTube live chat | [chat-replay-downloader](https://github.com/xenova/chat-replay-downloader) | Chat from YouTube livestreams and replays, no login needed |  |
| Kick API and chat | [kickpython](https://pypi.org/project/kickpython/), [KickLib](https://github.com/Bukk94/KickLib) (C#, MIT) | Official OAuth API plus the live chat websocket | Kick has no chat history, so chat must be captured live while recording ([source](https://apify.com/devilscrapes/kick-chat-archive/changelog)). The websocket is unofficial |
| Chat spike detection | [josec07/clipper (CTIC)](https://github.com/josec07/clipper), [clippy](https://github.com/hamzaskewl/clippy), [stream-clipper](https://github.com/nirvagold/stream-clipper) | Statistical burst detection on chat, no ML; clippy adds AI classification of spikes; stream-clipper combines audio and chat into one score | Matches our statistics-first heatmap |
| Game-event detection | [Auto-clipper](https://github.com/bendawg2010/Auto-clipper) | Per-game profiles (YOLO detection, pixel analysis) for kills, explosions and combat | Template for a GTA 6 profile (wanted stars, death screens, mission banners) |
| Transcription on M1 | [whisper.cpp](https://github.com/ggml-org/whisper.cpp) (MIT), [mlx-whisper](https://github.com/ml-explore/mlx-examples), [parakeet-mlx](https://pypi.org/project/parakeet-mlx/) | whisper.cpp and MLX use the M1's GPU (Metal) and Neural Engine; faster-whisper is CPU-only on Mac | Parakeet is fastest but English plus 25 European languages; Whisper covers every language ([benchmark](https://github.com/anvanvan/mac-whisper-speedtest)) |
| Music removal | [ELUATE](https://pypi.org/project/eluate/), [husher](https://pypi.org/project/husher/), [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator), [Demucs](https://github.com/facebookresearch/demucs) | Removes background music while keeping dialogue and sound effects, which is exactly the GTA radio problem | ELUATE and husher are video-in, video-out |
| Scene cuts | [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | Cut detection for scoring and for the style study |  |
| Full clippers to study | autoclip, clipper, ClipsAI, Clipify (see reference catalog) | Whole pipelines: transcription, LLM scoring, face tracking, captions |  |
| Posting connectors to study | [Postiz](https://github.com/gitroomhq/postiz-app) | Open-source scheduler with working integrations for Instagram, YouTube, TikTok, Facebook, Threads and more | AGPL-3.0: changing it and running it as a service means publishing our changes. Use as reference for our own connectors |

## Editing playbook

The craft rules from elite human clippers become fixed, measurable rules in the Edit stage, so every clip gets the same treatment automatically. Rules written for podcasts get adjusted for gameplay, where game audio and action matter more than a talking head.

| Rule | How the engine applies it | Gaming adjustment |
| --- | --- | --- |
| Standalone test | The LLM rejects segments that depend on earlier context ("like I said before") | Also reject segments where the payoff happens off-screen |
| Cold-open hook | Move the highest-scoring 1–3 seconds (the crash, the reaction, the punchline) to 0:00, then cut back to the setup | Hook on the visual peak, not just the line |
| One idea, hard ending | End the clip within 0.5 s of the payoff. No trailing chatter | Hold 1 s after an explosion or crash so it lands |
| Dead-air trim | Cut pauses over 0.2 s and filler words | Only when nobody's talking and nothing's happening. Never cut through game action or game audio |
| Pattern interrupt every 3–5 s | Auto 110–120% punch-in zoom on emphasis words and audio spikes. Subtle SFX on cuts | Zoom toward the action, using motion detection |
| Seamless loop | Score candidate end points by how well the last word or frame flows into the first. Pick the best | Loop on a matching camera angle or motion |
| Safe zones | Captions and key action in the middle third. Bottom 20% and right 15% kept clear | Facecam sits top or bottom, never under the buttons |
| Captions | 2–4 words per line, high-contrast sans-serif, power words in an accent color, no word-by-word flashing | Larger text over busy game scenes, with a backing box |
| Audio mix | Dialogue normalized to about -14 LUFS, peaks compressed, any music at -25 to -30 dB underneath | Game audio ducked under speech, never removed |

Two engineering ideas worth taking from the notes:

- **Word-index scoring:** the LLM returns word numbers from the transcript, not timestamps. Our code maps those numbers to exact times, so the model can't invent a timestamp.
- **Non-linear restructuring:** clips can be rebuilt out of order (hook first, setup second), not just cut as one continuous span.

Open-source code to study before writing our own: autoclip (WhisperX, Pyannote, word-index highlights), clipper (faster-whisper, local scoring, YuNet face tracking), and ClipsAI (segmentation and 16:9 to 9:16 resizing). Check each repo's license before reusing any code; reading it for ideas is always fine.

Skipped for now: stock-footage B-roll (it doesn't suit gameplay) and AI voiceover. They can come back later for news or explainer channels.

## Sources: Twitch and Kick clips

Clips viewers have already made are the best free signal: a human picked the moment, and view counts rank it. Use them two ways: as source footage from streamers who've opted in, and as training labels for our moment scorer.

- **Discovery (any streamer):** Twitch's Get Clips endpoint returns top clips for a game ID, sorted by view count, with date filters. Poll it hourly for GTA 6 to see what's trending and which streamers get clipped most.
- **Download (official API):** Twitch's [Get Clips Download](https://dev.twitch.tv/docs/change-log/) endpoint, generally available since late 2025, returns video files only for a channel whose broadcaster or editor has authorized our app. Other channels' clips are cut from our own stream recordings.
- **Labels for the scorer:** a clip's start and end inside the full VOD shows exactly which moment people liked. That teaches our scorer what to find in raw footage nobody has clipped.
- **Kick:** I couldn't find an official clips API, only third-party scrapers. Kick gets the same pipeline as Twitch: record streams, cut our own clips, run the creator radar and the heatmap.
- Avoid unofficial download tricks (rewriting thumbnail URLs, scraping). They break Twitch's terms and stop working without warning.

When a trending clip can't be downloaded, the system doesn't screen-record it. The moment is cut from our own recording of that stream instead.

## Creator radar: who to source, by the numbers

Creators are ranked by a published formula over platform statistics, not by an AI's opinion. The radar recomputes daily. Footage is pulled from the top-ranked creators first.

| Signal | Where it comes from | Why it matters |
| --- | --- | --- |
| Average live viewers in GTA 6 | Twitch Get Streams filtered by the game, sampled every 10 minutes | Size of the audience right now |
| GTA 6 hours streamed per week | Same samples | How much fresh footage they produce |
| Clip rate: clips per stream hour, and views on those clips | Twitch Get Clips by broadcaster | How often their audience finds moments worth saving. The best predictor of clippable content |
| Views per GTA 6 upload, last 30 days | YouTube Data API (search plus video stats) | Reach outside of live streams |
| Growth: change in each signal week over week | Our own stored history | Catches rising creators before they're big |
| Our results from their footage | Our analytics | Watch time and views of clips we already posted from them |

Scoring: each signal becomes a percentile rank within GTA 6 creators. The creator score is a weighted sum of those percentiles. The weights start equal, then a regression fits them to our own post results. 80% of source slots go to the top-ranked creators and 20% go to rising ones, so the system keeps finding new winners without betting everything on them.

## Style study: replicate the best clipping channels

The clipper copies how the top clipping channels edit, measured from their actual videos rather than guessed. This is a one-time study per reference channel (repeated when formats shift), not ongoing stat tracking.

Reference set: top GTA 5 clip channels now. GTA 6 channels replace them once they exist and have history. A channel counts as GTA 6 only if most recent uploads (at least 60% of its last 30 since the November 19, 2026 launch) match GTA 6 terms.

| Dimension | What gets measured | How the clipper uses it |
| --- | --- | --- |
| Pacing | Cuts per 10 s, median shot length, zoom/punch-in frequency | Cut and zoom rhythm of our renders |
| Captions | Coverage, screen position, words per line, all-caps share, fill and outline colours, font style | Caption template |
| Hook | Text on screen and number of cuts in the first 3 s, what moment opens the clip | Cold-open rules |
| Layout | Full-screen gameplay vs facecam stacked over gameplay, divider position, crop | Reframe template |
| Audio | Integrated loudness, loudness range, SFX and spike density, music under speech | Audio mix targets |
| Length and format | Clip duration, vertical vs horizontal, ending style (hard cut, loop) | Length bounds and ending rules |
| Capture and processing | Source type (stream vs submitted clip), facecam present, resolution and frame rate, how much of the original moment is kept | Ingest and cut settings |
| Visual extras | Fonts, emoji, meme overlays, SFX types, read by a vision model on sampled frames | Template details numbers can't capture |

Each reference channel produces a style profile. The editor renders to a profile, and several profiles can run side by side with analytics picking the winner.

GTA 5 reference channels:

- **Clip/compilation:** @RedArcade, @PrestigeClips, @GameSprout, @OnespotGaming, @TopGamingPlaysYT, @gta5ragdollstest187, @Hazardous, @WardGaming. Mostly long-form compilations built from submissions: strong for hooks, captions and moment types, weaker for Shorts pacing.
- **GTA RP clip channels:** @RP\_Clipz, @dailygtarpclips, @infinitygtaclips. Closest to our stream-clipping model.
- **Creators (source footage, go to the creator radar):** @IcyDeluxe, @Ivanowski, @NoughtPointFourLIVE, @VanossGaming, @TGG\_, @DarkViperAU, @putther, @Buggs, @soup.
- **Data source:** [HasRoot](https://nopixel.hasroot.com/) tracks GTA RP stream history, streamers and clips per server.

## Languages and regions

Each language gets its own set of pages (which languages is decided by the data in step 1), filled only with clips from creators who stream in that language. No translated or dubbed clips: the audio, captions, titles and hashtags are all native to the page's language.

1. **Pick languages by numbers:** Twitch's live-streams endpoint reports each stream's language. The radar measures GTA 6 viewers by language, and a YouTube scan of existing GTA 6 clip pages shows which languages already have strong clip pages and which are underserved. New language pages open where demand is high and competition is thin.
2. **A separate radar per language:** each language runs its own creator ranking and heatmap, filtered to creators streaming in that language.
3. **Native captions and copy:** Whisper transcribes in the clip's own language. The LLM writes titles, hooks and hashtags natively in that language, following that region's top clip pages.
4. **One account set per language:** its own brand on each platform, a posting schedule in that region's time zone, and its own analytics and style profile.

Start with the main language plus the one or two languages the data ranks highest, then add more as each proves out in analytics.

## Moment heatmap: where to cut, by the numbers

Inside a creator's VOD, the cut points also come from statistics first. AI only writes titles and breaks ties.

1. **Viewer clip density:** each Twitch clip has a `video_id` and a `vod_offset` (seconds into the VOD). Stacking every clip, weighted by its views, gives a heatmap of the moments the audience reacted to.
2. **Chat velocity:** while a tracked creator is live, we log chat messages per 10 seconds. A spike several times above the rolling baseline (a z-score above 3) marks a moment.
3. **Audio energy and viewer jumps:** loudness spikes from the VOD audio, and jumps in live viewer count from the 10-minute samples.
4. **Fusion:** each signal is normalized and summed with weights fitted by the same regression on our post results. The top windows become clip candidates. Cuts snap to sentence ends and silences.

The heatmap also works for VODs nobody clipped: chat velocity and audio energy carry the score there.

## Upload automation

All three platforms allow fully automatic posting through their official APIs, but each one makes a new app pass a review before its posts can be public. The volume limits are generous, so the reviews are the real bottleneck. Submit all three on day one. YouTube auto-upload is already built, so Instagram and TikTok are what's left.

| Platform | API path | Volume limit | What blocks public posts | Automation before approval |
| --- | --- | --- | --- | --- |
| [YouTube Shorts](https://developers.google.com/youtube/v3/docs/videos/insert) | Data API v3 `videos.insert`, OAuth `youtube.upload` scope | 100 uploads/day per project, in their own quota bucket since June 2026 ([source](https://postproxy.dev/blog/automate-youtube-uploads/)) | Uploads from unverified projects created after 28 July 2020 are locked to private until the project passes Google's compliance audit | Upload as private through the API, then switch to public in Studio with one tap. Locked videos can't be appealed, only re-uploaded, so test on a throwaway channel |
| [Instagram Reels](https://developers.facebook.com/docs/instagram-platform/content-publishing/) | Graph API: create a media container from a public video URL, poll until FINISHED, then `media_publish` | Meta's page says 100 posts per rolling 24h. Some pages and the `content_publishing_limit` endpoint report 50, so check that endpoint for each account | Needs a Professional (Business/Creator) account. Opening access to other people's accounts needs Meta App Review | Your own accounts can be added as app testers while the app is in development mode, so this can be fully automatic from day one (confirm during setup). Containers expire after 24h |
| [TikTok](https://developers.tiktok.com/doc/content-sharing-guidelines) | Content Posting API: Direct Post, or Upload to the creator's inbox as a draft | Typically around 15 Direct Posts per creator account per day, shared across every app | Unaudited apps can only post SELF\_ONLY (private), and only for up to 5 users in 24h. The audit wants an app built for a wide audience and rejects internal tools | Send to the inbox as a draft, then tap Post in the TikTok app. To go fully automatic, pass the audit with the dashboard set up as a multi-user product, or route through an already-audited posting service |

How the publisher is built:

1. One adapter per platform behind a shared `publish(clip, account)` interface, so adding Facebook Reels or X later is one new file.
2. A job queue with states: queued → uploading → processing → live, or failed with a retry. Posts are idempotent, so a crash can never double-post.
3. The scheduler picks posting slots per account from the analytics data and stays under each platform's limit with a margin.
4. Tokens are stored encrypted. Refresh runs on a timer, and expired logins show up on the dashboard, not as silent failures.
5. Fallback per platform: if direct posting isn't approved yet, that adapter switches to private upload or inbox draft, and the dashboard shows a one-tap "finish posting" list.

## More platforms

Six more platforms can take fully automatic video posts, which brings the total to nine. The API ceilings are far above what's worth posting, so the real limit is reach. Each account posts up to its platform's limit, and analytics move volume toward whatever performs.

| Platform | API ceiling | Catch |
| --- | --- | --- |
| [Threads](https://developers.facebook.com/docs/threads/overview) | 250 posts per 24h per profile | Uses the same Meta app as Instagram. Connected through Instagram login |
| [Facebook Reels](https://developers.facebook.com/documentation/video-api/guides/reels-publishing) | 30 Reels per 24h per Page | Pages only, no personal profiles. Clips 3–90 seconds |
| [X](https://www.socialync.io/blog/x-api-pricing-and-posting-2026) | 100 posts per 15 min per user | Deferred until there's revenue. Paid per post: $0.015, or $0.20 with a link |
| [Snapchat Spotlight](https://www.ayrshare.com/snapchat-api.md) | Varies | Built direct on Snap's Public Profile API: apply for the allowlist, set up a Snap Business account and an Ads Manager organization, and encrypt media (AES-256-CBC) before upload. Spotlight takes 9:16 video up to 60 s. Fallback while waiting: a posting service that already has access |

With all nine connected, every clip can go to every platform, each with its own caption.

## Channel protection

These mechanisms keep the channels alive at full volume. None of them stops a clip from being made.

| Mechanism | What it does |
| --- | --- |
| Takedown handling | A creator who objects is blocklisted automatically, and their clips come down across every channel |
| Source tracking | Every clip records its creator and source, so a claim is resolved in one step |
| Edit variation | Hooks, captions and crops rotate per channel, so posts don't read as mass-produced to YouTube or TikTok |
| Music muting | Copyrighted music detected in a stream is muted before rendering, which avoids automatic audio claims |
| Strike monitor | A claim or strike on any channel pauses that source across the network, by rule, until it clears |

## Build phases

Seven phases, in order. Phase 0 starts the platform reviews so they run in the background while phases 1 to 3 get built. Each phase ends with a test you can actually run.

1. **Phase 0 — Accounts and reviews.** Create the brand accounts, a Google Cloud project, a Meta app, a TikTok developer app, a Twitch developer app, and a Snap Business account with a Public Profile API allowlist request. Switch Instagram to Professional. Submit YouTube's compliance audit and TikTok's Content Posting audit.
   - Done when: all three apps exist, your accounts are connected as testers, and both audits are submitted.
2. **Phase 1 — Clipping engine (CLI).** `clip run recording.mp4` produces 10–30 ranked candidate clips, each with a 9:16 render, burned-in captions, a hook, and a JSON file of metadata and scores.
   - Done when: on 3 real recordings, at least half of the top 10 clips are ones you'd actually post.
3. **Phase 2 — Library and monitoring dashboard.** A web app showing what posted and what's queued, with a kill switch to pull a clip or pause a channel, plus source records and channel profiles.
   - Done when: from your phone, you can see everything that posted and pull any clip in one tap.
4. **Phase 3 — Publishers.** YouTube auto-upload is already built: wrap it as the first adapter, then add Instagram and TikTok behind the same interface, with the job queue, retries and token refresh. Fallback modes (private upload, inbox draft) until the audits clear.
   - Done when: one approved clip reaches all three platforms with no manual steps beyond the fallbacks.
5. **Phase 4 — Scheduler and multi-channel.** Posting slots, a config file per channel (template, voice, hashtags, angle), and routing so each clip goes to the channel whose angle fits it best.
   - Done when: a second channel is added by writing a config file, with no code changes.
6. **Phase 5 — Analytics and feedback loop.** A daily stats pull (views, watch time, likes, shares) for each clip. Clip features (hook type, length, moment type, posting time) get linked to results, and the scoring weights update from that.
   - Done when: the dashboard shows which hook types and lengths win, and new clips get ranked using that data.
7. **Phase 6 — Autopilot and new games.** The minimum score for auto-publishing tunes itself from analytics. Weekly digest of results. Add a second game by adding a game profile (vocabulary, moment types, templates).
   - Done when: one full week runs with no manual work beyond the weekly digest.

## Costs

Running cost can stay near $0. The only usage-based cost is the LLM that scores moments and writes captions, and it reads text transcripts, not video. All figures below are approximate. Price them during Phase 1.

| Piece | $0 option | Paid upgrade, if needed |
| --- | --- | --- |
| Transcription | faster-whisper on your MacBook | Hosted Whisper API |
| Cutting, rendering, captions | FFmpeg locally | GPU cloud worker for volume |
| Moment scoring and captions | Free tier of an LLM API, or a small local model | Paid Claude/GPT API (roughly cents per hour of footage, approximate) |
| Frame understanding | Skipped at first (audio + transcript signals only) | A vision model on sampled frames |
| Clip storage and public URLs | A free object-storage tier (needed because Instagram and TikTok pull video from a URL) | Larger bucket |
| Database | SQLite locally, or a free Postgres tier (Supabase) | Paid Postgres |
| Scheduler and publisher | A free cron (GitHub Actions) or a small free-tier host, so posting doesn't need the MacBook on | Always-on host |
| Platform APIs | Free | Pre-audited posting service, as a TikTok/YouTube shortcut |

Rendering happens when the MacBook is on. Publishing runs from the cloud queue, so scheduled posts go out even with the laptop closed.

## Hardware: MacBook Pro M1 (2020)

The M1 handles transcription, music removal and rendering for a moderate volume, if the pipeline only processes the moments that matter rather than whole streams.

- **Transcription:** run whisper.cpp or mlx-whisper on the M1's GPU. Large-v3 runs at roughly 2–3× real time on an M1 ([PromptQuorum](https://www.promptquorum.com/ko/local-llms/apple-silicon-whisper-metal-benchmark)), so only transcribe candidate windows the heatmap picked, never full streams.
- **Rendering:** use FFmpeg's hardware encoder on Apple Silicon (VideoToolbox) for fast, low-heat renders.
- **Recording stays off the laptop:** streams record on a small always-on server; only candidate windows come down to the M1.
- **Open question:** 8 GB or 16 GB of memory. 8 GB means running one heavy model at a time.

## Storage lifecycle

Nothing piles up: every file has a defined end, and the system deletes it permanently, never to the Trash.

1. **Raw recordings:** a rolling buffer on the recorder server. After scoring, only candidate windows (the moment plus about 30 s either side) are kept; the raw stream is deleted within hours.
2. **Candidate windows:** deleted once rendered, or after 48 h if nothing was cut from them.
3. **Rendered clips:** each file keeps a count of its pending uploads, one per target account and platform. It stays until every upload is confirmed live through that platform's API, or has failed for good after the retry window. Then it is deleted.
4. **Public URL copies:** Instagram, Facebook, Threads and TikTok pull video from a URL, so a copy sits in cloud storage. It's deleted as soon as each platform reports it finished processing.
5. **Permanent delete:** the code removes files directly (unlink), which bypasses the macOS Trash, and empties any temp folders it used. Nothing goes through Finder.
6. **Disk guard:** if free space drops below a set floor, recording and rendering pause and the dashboard shows a warning, so the drive can never fill up.
7. **What's kept:** only database records: the source, timestamps, title, post IDs, stats and a fingerprint for the duplicate check. That keeps analytics and lets a moment be re-cut later from its source if needed.

Trade-off: a deleted clip can't be re-posted to a platform added later without re-rendering it from the source.

## Open decisions

- [ ] TikTok route: build the dashboard to pass TikTok's audit, use a pre-audited posting service, or stay on inbox drafts?
- [ ] Number of channels at launch: one brand, or 2–3 angle channels from the start?
- [ ] LLM provider for scoring and captions, and a monthly cost ceiling.
- [ ] Dashboard hosting: local-only, or deployed so you can monitor and pull clips from your phone?
- [ ] Style: copy one reference channel, blend several, or run several profiles and let analytics pick?
- [ ] Style-study samples: how reference videos are obtained (YouTube's terms don't allow downloading outside its own features).
