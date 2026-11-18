# Clipper Component 13 — Style Study & Style Profiles

Nov 18, 2026

The Style Study measures how the best clipping channels edit, from their actual videos, and writes each channel's habits into a style profile the editor follows. It is a one-time study per reference channel, repeated when formats shift, not ongoing tracking.

## Job and boundaries

- **Does:** analyze sample videos per reference channel, produce a style profile (numbers plus visual notes), and let the editor render to any profile.
- **Doesn't:** track channel stats over time, or copy any channel's branding, logos, fonts that aren't licensed, or exact templates.

## Reference channels

- **Clip/compilation:** @RedArcade, @PrestigeClips, @GameSprout, @OnespotGaming, @TopGamingPlaysYT, @gta5ragdollstest187, @Hazardous, @WardGaming.
- **GTA RP clip channels (closest to our model):** @RP_Clipz, @dailygtarpclips, @infinitygtaclips.
- GTA 6-era channels replace GTA 5 references once they exist (a channel counts if 60%+ of its last 30 uploads since launch match GTA 6 terms).

## Sample set per channel

- 20–30 videos: the most viewed and the most recent, mixing Shorts and long-form where the channel has both.
- Shorts are weighted more heavily for pacing targets; long-form informs hooks, captions and moment types.
- **Open question:** how sample files are obtained. YouTube's terms don't allow downloading outside its own features; this needs a decision before the study runs.

## What gets measured per video

| Dimension | Measurement | Method |
| --- | --- | --- |
| Length | Duration; Shorts vs long-form | ffprobe |
| Pacing | Cuts per 10 s, median shot length | Histogram-distance cut detection at 10 fps (PySceneDetect or equivalent) |
| Zooms | Punch-ins per 10 s, typical zoom amount | Feature matching between frames (scale estimate), ignoring static overlay points |
| Captions | Coverage, vertical position, words per line, all-caps share, fill color, outline, font class | OCR (tesseract) on frames at 1 fps; color clustering inside word boxes; line grouping by y-position |
| Hook | Text on screen in first 3 s, cuts in first 3 s, whether the payoff is teased first | OCR + cut times + vision check |
| Layout | Full gameplay vs stacked facecam, split ratio | Persistent full-width horizontal divider detection; face detection |
| Audio | Integrated loudness, loudness range, SFX/spike density, music under speech | ffmpeg ebur128; RMS spike detection; music classifier |
| Ending | Hard cut, loop, call-to-action card | Last 2 s analysis |
| Visual extras | Emoji, meme overlays, sticker use, font style | Vision model on 5–10 sampled frames per video, fixed checklist questions |
| Credits | How creators are credited on screen and in descriptions | OCR + description text |

## Profile format

`config/styles/<channel>.yaml` holds, per dimension: the median as the target, the min–max range, and the share of videos using each boolean feature (e.g. 85% use cold opens). Visual notes from the vision model are stored as a short structured list (font class, accent color family, emoji frequency).

## How the editor uses profiles

- Clip Builder (09): target lengths, cold-open use, ending style.
- Reframe (10): starting layout mix and split ratio, zoom rate. The owner's reference layout (stacked: creator top, captions on the seam, gameplay bottom; `docs/assets/layout-reference.png`) always gets the largest starting share; analytics (22) then reallocates by performance.
- Captions (11): words per line, position, case, colors, animation style.
- Render (12): loudness target, SFX density.

## Blending and testing

- Profiles can be blended (weighted average of numbers, majority vote of booleans) into a house style.
- Each channel can run 2–3 profiles in parallel on different clips; analytics (22) picks the winner per platform after enough posts (e.g. 30 clips per arm), then reallocates.

## Originality guard

Profiles copy *habits* (pacing, caption sizing, hook timing), never identifiable assets. Our fonts, colors, intro stingers and credit design stay distinct so channels don't look like clones of the references.

## Done when

- [ ] Profiles exist for all 11 reference clip channels.
- [ ] A rendered test clip from each profile visibly matches the reference style on pacing and captions.
- [ ] Profile switching is pure config.

## Open questions

- [ ] How sample videos are obtained (see above).
- [ ] Whether to start with one blended house style or test several from day one.
