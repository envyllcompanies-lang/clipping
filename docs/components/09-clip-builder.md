# Clipper Component 09 — Clip Builder (Boundaries & Hooks)

Nov 18, 2026

The Clip Builder turns a candidate window into an exact edit plan: where the clip starts and ends, what opens it, and which versions to render. It combines hard rules (cut on sentence ends and silences, payoff within the clip) with an LLM that picks among rule-valid options using word indices, never timestamps.

## Job and boundaries

- **Inputs:** window file, transcript with word indices (06), clean audio and music map (07), game events (08), heatmap curve (05), style profile (13).
- **Output:** an `edit_plan` JSON per version: segments to include (in order), hook segment, ending type, target length, emphasis words for captions/zooms.
- **Doesn't:** render pixels (12) or write titles (14).

## Step 1 — Find the payoff

The payoff is the second the moment lands: the crash, the death banner, the punchline word, the chat spike peak (shifted back by reaction lag). Priority: game event > audio spike aligned with chat peak > LLM-identified punchline word.

## Step 2 — Candidate boundaries (rules)

- **Start candidates:** sentence starts (from transcript punctuation), silence gaps over 0.3 s, and scene cuts, between 8 and 50 s before the payoff.
- **End candidates:** 0.5–2 s after the payoff (hold longer after explosions so they land), at a sentence end or silence. No trailing chatter: end within one sentence after the payoff.
- **Standalone test:** reject starts that begin with a back-reference ("like I said", "that guy again") unless the setup sentence is included.
- **Length targets** come from the style profile (e.g. 15–45 s for short versions) and platform rules: a 61–90 s version for TikTok monetization, which pays only on videos over 1 minute ([TikTok terms](https://www.lilachbullock.com/?p=136446)); Facebook Reels via API must be 3–90 s; Snapchat Spotlight up to 60 s.

## Step 3 — LLM choice (tie-break and hook)

The LLM receives: numbered words with speaker labels, markers for game events and audio spikes at word positions, the rule-valid start/end candidates as word indices, and the channel's style notes. It returns JSON:

```json
{"start_word": 112, "end_word": 187, "hook": {"start_word": 160, "end_word": 171}, "payoff_word": 168, "emphasis_words": [140, 162, 168], "standalone": true, "reason_code": "fail_payoff"}
```

Code validates every index against the candidate sets; invalid output is retried once, then the rule-only best option is used. The LLM never sees or emits times.

## Step 4 — Cold-open hook

- If the style profile uses cold opens (most top clip channels do), the 1–3 s hook segment (the most intense line or the payoff's first frames, *without* the full resolution) is placed at 0:00, then the clip jumps back to the setup.
- A short transition (hard cut plus a whoosh or a "rewind" effect per style) marks the jump.
- If there's no speech, the hook is the visual peak with on-screen hook text written in Component 14.

## Step 5 — Dead-air and pacing

- Remove pauses over 0.4 s *only* when nothing is happening on screen (low motion, no game audio events); never cut through action or game audio.
- Keep cuts on word boundaries; apply small audio crossfades (20–40 ms) to avoid clicks.
- Mark emphasis words for punch-in zooms (Component 10) at the style profile's zoom rate.

## Step 6 — Versions

| Version | Length | Used for |
| --- | --- | --- |
| Short | Style target (e.g. 15–45 s) | YouTube Shorts, Instagram, Facebook, Threads, Snapchat, Bluesky, Pinterest |
| Long | 61–90 s (extended setup, or 2–3 related moments from the same stream as a mini-compilation) | TikTok monetization |
| Loop variant (optional) | Short version with an ending chosen to flow into the start | A/B tests on loop-friendly platforms |

## Step 7 — Originality layer (Meta rules)

Instagram removes accounts that mostly repost without material edits from recommendations ([TubeFilter](https://tubefilter.com/2026/04/30/instagram-removes-algorithm-recommendations-repost-content-aggregator)). Every plan must include transformation beyond a re-cut: a written hook line, context text (who/what/why), captions, zooms, and where the style supports it a ranking or compilation frame. The auto-gate (15) checks this.

## Failure handling

- No valid start within limits: discard the window (logged with reason).
- Payoff too close to window edge: request a wider window from the recorder if still buffered.

## Done when

- [ ] 80%+ of built clips pass a manual "makes sense to a cold viewer" check on a 30-clip sample.
- [ ] Every plan validates (indices in range, lengths within platform limits).
- [ ] Both short and long versions produced for every accepted moment.

## Open questions

- [ ] Which LLM (local vs API) for the tie-break, and cost per clip.
