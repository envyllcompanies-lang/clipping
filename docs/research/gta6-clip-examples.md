# GTA 6 clip examples — what's working (Nov 18, 2026, early access)

Seed data for the style study (13), captions (11), packaging (14) and layout tests (10). Seven Snapchat Spotlight clips from one clip account ("GTA 6 Daily") captured by the owner, compared with YouTube Shorts titles from other GTA 6 clip channels. **Small sample (7 clips, one account, views after < 1 day): use as starting priors only; the A/B system decides.**

## Snapchat examples (account: GTA 6 Daily)

| # | Screenshot | Creator | Moment type (31) | Layout | On-screen text | Views |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | [snap-gta6daily-3](../assets/examples/snap-gta6daily-3.png) | IShowSpeed | NPC/world comedy (taking grandma's mobility scooter) | Stacked: cam top ~38%, gameplay bottom, no border | White rounded box, black sentence-case text, creator **quote** + punchline + 😭: "I can't do it anymore" we taking grandmas out the wheelchair now? | **56K** |
| 2 | [snap-gta6daily-7](../assets/examples/snap-gta6daily-7.png) | Lacy | Music/discovery (in-game Drake radio) | Stacked: cam top ~37%, gameplay bottom | White text, black outline, sentence case, emojis: Lacy listens to the Drake Radio on GTA VI 😳🔥 | **50K** |
| 3 | [snap-gta6daily-4](../assets/examples/snap-gta6daily-4.png) | N3on | Crash/physics (survived a plane crash) | Stacked with a glowing purple divider line | White rounded box, black text: N3on survived a plane crash in GTA 6 😭 | **45K** |
| 4 | [snap-gta6daily-6](../assets/examples/snap-gta6daily-6.png) | Lacy | Fail / sports mechanic ("better than 2K") | Raw 16:9 stream frame centered, black bars top/bottom, original corner facecam + chat overlay visible | White outlined text over gameplay, **quote** + emojis: "Better mechanics than 2k.." 😭💔🥀 | 36K |
| 5 | [snap-gta6daily-5](../assets/examples/snap-gta6daily-5.png) | IShowSpeed | Arrest (first time arrested) | Raw 16:9 centered, black bars, corner cam; emoji row above | White box, black condensed ALL CAPS: SPEED GOT ARRESTED FOR THE FIRST TIME WHILE PLAYING GTA 6 | 8.6K |
| 6 | [snap-gta6daily-2](../assets/examples/snap-gta6daily-2.png) | Adin Ross | Discovery/limitation (can't enter airports) | Raw 16:9 centered, black bars, small corner cam | White text on black, no emoji: Adin Ross reveals you can't go inside airports in GTA 6 | 1.5K |
| 7 | [snap-gta6daily-1](../assets/examples/snap-gta6daily-1.png) | IShowSpeed | Discovery (in-game phone apps) | Stacked | White box, black text, emojis: You can actually check Social media whether news and fitness app in GTA 6 😍😨 | 693 |

Post captions under each video: a short reaction line or ALL-CAPS topic + `#fyp #viral #gta #gta6 #<creator>` (e.g. "Oh hell nah lmao 🤣 #gta #fyp #viral #ishowspeed #gta6"; "DRAKE IN GTA6 #fyp #viral #gta #gta6 #lacy").

## YouTube Shorts comparison (titles from other GTA 6 clip channels)

Views and visuals weren't visible from here, so this compares titling only:

- "Speed and Kai Cenat Watch the GTA 6 Final Trailer Together" (description credits the source clip account)
- "Kai Cenat & JasonTheWeen Are Already Finding Glitches & Bugs In GTA 6! 😭"
- "KAI CENAT LEAKED GTA 6 INFO!🚨🚘(PART 3)" (multi-part series)
- "Streamers Who Got Early Access To GTA VI!😲" (credits the creators in the description)
- "IShowSpeed Will Not Be Rushing GTA 6! 👀"

Same formula as Snapchat: **creator name first + what happened + "GTA 6" + one emoji**, with creator hashtags. YouTube adds ALL-CAPS titles, "PART N" series and a credit line in the description.

## Takeaways (starting priors, to be tested)

1. **Layout:** the three stacked clips with funny/chaos/music moments did 45–56K; the three raw 16:9 letterboxed clips did 36K, 8.6K and 1.5K. Stacked stays the starting favorite; raw letterbox is kept only as a low-share test arm (cheapest to make, and #4 shows it can still work when the moment is strong).
2. **Moment type matters more than format:** chaos/comedy, crashes and celebrity/music moments led; "you can/can't do X" discovery clips were weakest (1.5K, 693) even with good layout. Feed this into doc 31's launch-window weights: discovery stays in the mix but below comedy, crash and fail types until our own data says otherwise.
3. **Text = one hook caption, no subtitles.** All 7 use a single headline. Two styles appear: **white rounded box with black text** (native TikTok/Snap text look; 4 of 7) and **white text with black outline** (3 of 7). Both become caption-style arms.
4. **Sentence case beats ALL CAPS here** (the ALL-CAPS boxed clip was the lowest of the arrests/fails). Test sentence case as the starting favorite for the headline, ALL CAPS as an arm.
5. **Quote hooks work:** the top clip and #4 put the creator's own line in quotes, then the context. Add a "quote + context" headline pattern.
6. **Emoji endings:** 6 of 7 end the headline with 1–3 emojis (😭 most common, also 😳🔥💔🥀😍😨). Default: one or two emojis matching the reaction (laughter → 😭/🤣, shock → 😳/😨, hype → 🔥).
7. **Creator name first, "GTA 6" in the line:** every headline names the creator (Speed, Lacy, N3on, Adin Ross) or quotes them, and includes "GTA 6"/"GTA VI".
8. **Music as the subject:** the Drake radio clip (50K) kept the licensed song because the song *was* the moment; Snapchat tagged it "Contains: NOKIA - Drake". Our default music removal (07) would ruin this kind of clip, so doc 07/31 gets a "music is the subject" exception (see there).
9. **Post caption format:** short reaction line or ALL-CAPS topic, then `#fyp #viral #gta #gta6 #<creator>`.

## Watch list

Re-capture 20–50 examples per platform per language weekly during launch (doc 13 does this automatically from the reference channels); this file is the first manual seed.
