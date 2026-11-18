# Clipper Component 11 — Captions & On-screen Text

Nov 18, 2026

This component turns word timestamps into animated, readable captions and adds hook and context text, styled to match the reference channels. Captions are both a retention tool (most short-form is watched muted) and part of the "material edit" that keeps Meta accounts eligible for recommendations.

## Job and boundaries

- **Does:** group words into caption lines, time them, style them (font, colors, outline, emphasis, animation), add hook text and context labels, and export an ASS subtitle file plus overlay instructions.
- **Doesn't:** transcribe (06) or decide which words are emphasized (09 marks them).

## Text modes (A/B tested)

What's working on current GTA 6 clips is **one hook caption, not subtitles of everything said**: creator on top, a single bold headline in the middle band (e.g. "JASON AND LUCIA REUNITE GTA 6"), gameplay at the bottom, with the creator's audio carrying the rest. So the system supports three text modes, chosen per clip by the A/B bandit (22) like layouts:

| Mode | What's on screen | Starting share |
| --- | --- | --- |
| **Hook only (starting favorite)** | One headline (1–2 lines, all caps, ≤ ~40 characters per line) in the middle band on the seam for the **whole clip**. No spoken subtitles. Optional small creator credit | Largest share at launch |
| Hook + key lines | The headline for the first 2–3 s, then only the 1–3 strongest spoken lines (the punchline, the catchphrase, the reaction) captioned in the same band; silence otherwise | Medium |
| Full subtitles | Headline first, then every spoken word as grouped captions (rules below) | Small; kept for clips that depend on dialogue (NPC comedy, roleplay, chat banter) |

- The style study (13) measures each reference channel's text mode (headline-only vs subtitles) and sets the starting mix; analytics (22) moves volume to whichever mode retains better per language and platform.
- **Hook-only headline rules:** describes the moment or the tease, not a transcript ("HE DIDN'T SEE THE COPS COMING", "LUCIA'S FIRST MISSION GTA 6"); always includes "GTA 6" or the creator's name when it fits; written natively in the channel's language by packaging (14); stays still for the whole clip (a 1-frame pop-in at the start only); must not cover the face or the bottom 20% platform zone.
- When a clip's payoff is a spoken line that's hard to hear, the builder may switch that clip to "hook + key lines" automatically.

## Caption grouping rules (for "full subtitles" and "key lines" modes)

1. 2–4 words per line (style profile can override), one line on screen at a time for the punchy style, two lines max for calmer styles.
2. Break at punctuation and natural phrase boundaries first, then by word count; never split a name or number.
3. Each line shows from its first word's start to its last word's end, extended to bridge gaps under 0.3 s so text doesn't flicker.
4. Minimum on-screen time 0.4 s; if speech is faster, merge lines.
5. Low-confidence words: if one word in a line is low confidence, keep the line only if the line still reads naturally; otherwise drop that line rather than show a wrong word.

## Styling (from the style profile)

| Property | Default (until the style study sets it) |
| --- | --- |
| Font | Heavy sans-serif (e.g. Montserrat ExtraBold, open license) |
| Size | ~6–7% of frame height |
| Fill / outline | Starting style: yellow headline (white for spoken captions when shown), 6–8 px black outline, soft shadow (as in the [reference](../assets/layout-reference.png)); colors are A/B tested and the style study can replace them |
| Emphasis | Emphasis words in an accent color (yellow or green) and 110% scale |
| Case | All caps |
| Position | Middle band, max 2 lines, never covering the face or the bottom 20% platform zone; in stacked layout, centered on the seam between cam and gameplay, with the hook headline there (whole clip in hook-only mode; first, then spoken captions, in the other modes) |
| Animation | Pop-in per line (scale 90%→100% over 80 ms); optional word-by-word highlight karaoke style |
| Speaker colors | Different fill per speaker when diarization is on |

Fonts must be licensed for commercial use; bundle them in the repo with their licenses.

## Rendering format

- Generate an **ASS** subtitle file (styles, positions, karaoke tags, animations) and burn it with FFmpeg's libass filter in Component 12. ASS supports outlines, per-word color changes and simple animations without a separate graphics engine.
- Emoji: optional per style; rendered from an image set, not the font, for consistent look.

## Hook text

- A 1–2 line headline written by Component 14 in the page's language, max ~40 characters per line, in the middle band (on the seam in stacked layout). In **hook-only** mode it stays for the whole clip; in the other modes it shows for the first 1.5–3 s (the cold-open window), then gives way to captions.
- Patterns copied from the style study (question, reaction, number, creator name first).

## Context labels

- Small persistent label with the creator's name (e.g. "@creator on Twitch"), as on-screen credit. This also counts as transformation on Meta platforms and gives the streamer attribution.
- Optional context line when the clip needs setup ("He had 4 stars and one tire").

## Profanity handling

- Per platform/channel setting: show, mask with asterisks, or replace with a symbol. Audio bleeping is separate and optional (some platforms limit reach for heavy profanity in the first seconds).

## Quality checks

- Automated: no caption line exceeds frame width at its font size; no overlap with face boxes or platform UI zones from Component 10.
- Sample check: 20 clips read naturally with sound off.

## Done when

- [ ] All three text modes (hook only, hook + key lines, full subtitles) render from the same pipeline and are selectable per clip.
- [ ] Captions (when shown) match speech within 100 ms on a checked sample.
- [ ] Every clip has hook text and a creator credit.
- [ ] Style is driven entirely by the profile file; switching styles needs no code.

## Open questions

- [ ] Final fonts and accent colors once the style study (13) measures the reference channels.
