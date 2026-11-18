# Clipper Component 11 — Captions & On-screen Text

Nov 18, 2026

This component turns word timestamps into animated, readable captions and adds hook and context text, styled to match the reference channels. Captions are both a retention tool (most short-form is watched muted) and part of the "material edit" that keeps Meta accounts eligible for recommendations.

## Job and boundaries

- **Does:** group words into caption lines, time them, style them (font, colors, outline, emphasis, animation), add hook text and context labels, and export an ASS subtitle file plus overlay instructions.
- **Doesn't:** transcribe (06) or decide which words are emphasized (09 marks them).

## Caption grouping rules

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
| Fill / outline | Yellow fill (#FFE135-ish) for the hook/headline and white for spoken captions, 6–8 px black outline, soft drop shadow (see [reference](../assets/layout-reference.png)) |
| Emphasis | Emphasis words in an accent color (yellow or green) and 110% scale |
| Case | All caps |
| Position | Centered on the seam between the creator panel (top) and gameplay (bottom), max 2 lines, never covering the face or the bottom 20% platform zone. The hook headline (e.g. "JASON AND LUCIA REUNITE GTA 6") sits here first, then spoken captions take the same band |
| Animation | Pop-in per line (scale 90%→100% over 80 ms); optional word-by-word highlight karaoke style |
| Speaker colors | Different fill per speaker when diarization is on |

Fonts must be licensed for commercial use; bundle them in the repo with their licenses.

## Rendering format

- Generate an **ASS** subtitle file (styles, positions, karaoke tags, animations) and burn it with FFmpeg's libass filter in Component 12. ASS supports outlines, per-word color changes and simple animations without a separate graphics engine.
- Emoji: optional per style; rendered from an image set, not the font, for consistent look.

## Hook text

- A 1–2 line headline shown for the first 1.5–3 s (the cold-open window): written by Component 14 in the page's language, max ~40 characters per line, top third of the frame.
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

- [ ] Captions match speech within 100 ms on a checked sample.
- [ ] Every clip has hook text and a creator credit.
- [ ] Style is driven entirely by the profile file; switching styles needs no code.

## Open questions

- [ ] Final fonts and accent colors once the style study (13) measures the reference channels.
