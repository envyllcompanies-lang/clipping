# Clipper Component 32 — Creator Profile & Reaction Analysis

Nov 18, 2026

Every streamer reacts differently: one screams at everything, another goes quiet when something's actually shocking; one has catchphrases their audience clips every time, another is funniest when reading chat. This component builds a living profile per creator so the system judges each reaction against that creator's own normal, recognizes their signature bits, skips their dead air and ad reads, and knows how to credit and title them. Doc 01 decides *which* creators to record (statistics); doc 31 types the *game* moment; this doc understands the *person*.

## Job and boundaries

- **Does:** per-creator baselines (voice, face, chat), signature-moment learning (catchphrases, recurring bits, running jokes), segment classification of the stream (gameplay, cutscene-watching, chatting, sponsor read, donation reactions, BRB, IRL), collab detection and multi-POV pairing, naming/credit data, and a per-creator reaction score used by docs 05, 09, 31 and 14.
- **Doesn't:** decide which creators get recorded (01), or judge the creator's opinions or content. Profiles are built from public stream data only.

## Profile contents (`creator_profile`)

| Section | What's stored | How it's learned |
| --- | --- | --- |
| **Identity** | Display name per platform, linked handles (Twitch, Kick, YouTube, TikTok, Instagram, X), language and dialect, usual stream hours, typical stream length | Platform APIs (01), links in channel panels/bios, name matching |
| **Voice baseline** | Median loudness, loudness spread, pitch median and range, speech rate, laughter rate per hour | Creator audio stem (07) over the first 3 recorded hours, rolling update |
| **Face baseline** | Facecam box position, typical head motion, mouth-open ratio distribution, whether the cam is often off or hidden | MediaPipe face/pose landmarks on the facecam at 2 fps, sampled |
| **Chat baseline** | Normal chat velocity, emote vocabulary, which emotes mean laughter/hype/shock in this community (e.g. channel-specific emotes) | Chat (03) over several streams; emote → reaction mapping learned from co-occurrence with laughter and viewer clips |
| **Reaction style** | Type: loud/expressive, deadpan, commentator, screamer, quiet-then-explode; how the strongest reactions look (voice, face, words) | Clustering features at the peaks of their most-viewed viewer clips |
| **Signature moments** | Catchphrases, recurring bits, nicknames, running jokes, sound alerts they react to | Repeated n-grams and phrases in transcripts around their top viewer clips (≥ 3 occurrences in top-clipped windows); stored per language |
| **What their audience clips** | Distribution of moment types (31) in their top viewer clips: e.g. 40% fails, 30% cutscene reactions, 20% NPC comedy | Doc 04 clips joined with doc 31 types |
| **Our results** | How clips of this creator perform on each of our language channels and platforms | Analytics (22) |
| **Collab graph** | Who they stream with, how often, on which servers | Co-occurring names in titles, voices (speaker embedding), cross-referenced streams overlapping in time |
| **Negative patterns** | Their sponsor-read phrases, ad-break messages, donation TTS voice, BRB screens, music segments, usual IRL segment times | Transcript patterns + doc 08 screen states + audio (TTS voice signature) |

Profiles are created automatically the first time the radar selects a creator and are refined every stream.

## Reaction score (per second, per creator)

Every reaction signal is converted to "how unusual is this for this person":

```
reaction_z = robust z-score against the creator's own baseline
             (voice loudness, pitch jump, laugh probability, speech-rate change,
              face motion, mouth-open ratio, reaction words)
reaction_score = weighted sum by reaction style
```

- A deadpan creator's raised voice scores as high as a screamer's scream.
- Style weights come from what preceded their own most-clipped moments (e.g. for "quiet-then-explode" creators, a sudden silence after high activity followed by a spike is weighted up).
- Reaction words are per-language lists (`config/languages/<code>/reaction_words.txt`) plus the creator's own catchphrases.
- Output feeds the heatmap (05), the gameplay score's reaction term (31), and the cold-open choice in the builder (09: open on the creator's peak face).

## Stream segment classification

Each minute of the stream gets a segment label so the system knows where to look and where never to clip:

| Segment | Signals | Use |
| --- | --- | --- |
| Gameplay | HUD present (08), game audio active | Clip normally |
| Cutscene watching | Cutscene state (31), creator mostly quiet or reacting | Cutscene-beat clips |
| Chatting / reading chat | Game idle or menu, creator talking continuously, chat velocity high | Lower weight; keep only GTA-relevant strong moments |
| Donation / alert reactions | Alert overlay detected, TTS voice in audio | Keep only if the reaction is about the game; never clip the TTS message itself |
| Sponsor read / ads | Sponsor phrases, ad-break screen, "use code" patterns | Never clip |
| BRB / starting soon / ending | Static screens (08) | Never clip |
| IRL / off-topic | No game, camera full-screen, non-game talk | Excluded (pages are GTA-only) |
| Collab call | Multiple voices (diarization), Discord overlay | Normal, flag for multi-POV pairing |

## Signature moments

- When a catchphrase or recurring bit is detected in a candidate window, the moment's score gets a bonus and the builder includes the line (bits are what fans clip and share).
- Captions highlight the catchphrase as an emphasis word (11).
- Packaging (14) can reference the bit in the title in the channel's language (e.g. the creator's known phrase in quotes) when the style profile allows.
- Signature lists are refreshed weekly; phrases that stop appearing in top clips decay out.

## Multi-POV collabs

- When two or more recorded creators are in the same session (overlapping time, same server/activity, each other's voices), their timelines are aligned by audio cross-correlation of shared voice chat.
- For a strong moment, the builder (09) can make a split-reaction clip (both creators' cams + one gameplay view) or pick the creator with the stronger reaction for each language channel.
- The gate (15) treats the same moment from different POVs as one beat per channel per day (shared with doc 31's `story_beat_id` logic).

## Naming and credit

- Titles and captions use the creator's display name as their audience knows it (from profile identity), in the channel's language/script.
- The credit line and tags use the creator's handle on the target platform when known (e.g. their TikTok @ on TikTok posts); fall back to the source platform name.
- Packaging never invents a handle; unknown handles fall back to the plain display name.

## Language and dialect

- The profile records the creator's language and regional dialect (e.g. Mexican vs Spain Spanish, Brazilian vs European Portuguese, Gulf vs Maghrebi Arabic), detected from transcripts.
- Language channels (24/28) pull creators whose language matches; dialect is passed to packaging so titles and slang match the audience.

## Learning loop

- Weekly, per creator: re-fit reaction weights against which of their moments were clipped by viewers and which of our clips performed best (22).
- Creators whose clips consistently underperform on our channels, despite strong radar stats, get a lower `creator_clip_weight` (passed back to radar 01 as a signal, not a block).

## Backtests (30)

- Reaction score alone vs viewer-clip positions: recall@20 per creator.
- Segment classification accuracy on a labelled sample (sponsor reads and BRB must be ≥ 99% excluded).
- Catchphrase detection precision on top creators.
- Multi-POV alignment error < 0.2 s on known collab sessions.

## Data stored

- `creator_profile` (creator_id, identity JSON, baselines JSON, reaction_style, signature_phrases JSON per language, moment_type_mix JSON, negative_patterns JSON, dialect, updated_at)
- `creator_segment` (stream_id, start_s, end_s, label, confidence)
- `creator_collab` (creator_a, creator_b, stream_overlap, sessions, last_seen)

## Performance budget

- Baselines and segment labels use signals already computed for docs 05, 07, 08 and 31; the extra cost is facecam landmarks at 2 fps on sampled minutes and periodic phrase mining on transcripts of top-clipped windows.

## Done when

- [ ] Every recorded creator has an auto-built profile after their first 3 hours of footage.
- [ ] Per-creator normalized reaction score improves heatmap recall@20 over raw (un-normalized) reaction signals in the backtest.
- [ ] Sponsor reads, ad breaks and BRB screens never appear in built clips on the labelled test set.
- [ ] Catchphrases are detected for at least the top 20 creators and show up as emphasis in captions.
- [ ] Two-creator collab sessions align and produce a split-reaction clip.

## Open questions

- [ ] Which reaction styles exist among the top GTA 6 creators (learned after the first weeks of early-access and launch footage).
