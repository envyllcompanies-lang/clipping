# Clipper Component 31 — Gameplay Moment Analysis (GTA 6)

Nov 18, 2026

Gameplay Moment Analysis decides what kind of moment a stretch of GTA 6 footage is, how strong it is as a short, and where a clip of it should start and end. Doc 08 spots point events on the HUD (wasted, wanted stars, mission passed); this doc turns those events, the video itself, the game audio and the creator's reaction into typed moments: cutscene reveals, chases, crashes, firefights, heists, funny NPC chaos, first-look discoveries and more. Each type gets its own detector, scoring and cut rules.

## Why GTA 6 needs its own approach

- **Launch window (first ~6 weeks):** the biggest clips will be first reactions to story cutscenes, characters (Jason and Lucia), Vice City, graphics and physics, and "you can do THAT?" discoveries. Viewers want to see the game for the first time through a creator's reaction.
- **Settled period:** the mix shifts to chaos and skill (chases, crashes, stunts, heists, police escalation, ragdoll physics, NPC weirdness), then to online and roleplay once those arrive. The weighting between types must change over time, driven by data (22), not fixed.
- **Every moment is two halves:** what happens in the game and how the creator reacts. A great clip almost always has both. Gameplay alone is the weakest form, and a pure cutscene with no reaction is closest to reposting Rockstar's footage, so reaction coupling is a core score, not a bonus.

## Job and boundaries

- **Does:** classify candidate windows into moment types; compute a gameplay score per window; detect cutscenes and their key beats; set type-specific clip boundaries and hooks; feed a gameplay signal into the heatmap (05) and boundary hints into the clip builder (09).
- **Doesn't:** read the HUD itself (uses doc 08 events), transcribe (06), or render (12). It runs on candidate windows and their surroundings, not every frame of every stream.

## Moment taxonomy

| Type | What it looks like | Strongest in | Clip value |
| --- | --- | --- | --- |
| **Story cutscene reveal** | Letterboxed or HUD-less cinematic, scripted camera, character dialogue; ends on a twist, death, betrayal or big line | Launch window | Very high when paired with reaction |
| **First-look discovery** | Creator stops, pans the camera, explores a place, mechanic or detail; shocked commentary ("no way you can…") | Launch window | High |
| **Graphics / realism showcase** | Slow camera over a vista, water, crowds, weather, lighting; creator praising | Launch window | Medium-high |
| **Police chase / escalation** | Wanted level rising, sirens, high speed, helicopters, roadblocks | Always | High |
| **Crash / physics chaos** | Sudden deceleration, vehicle flips, ragdoll bodies, debris | Always | Very high (fails travel well) |
| **Firefight / shootout** | Gunfire audio bursts, muzzle flashes, enemies dropping, health dropping | Always | Medium-high |
| **Heist / mission climax** | Mission objective text, music swell, escape sequence, mission passed | Always | High |
| **Stunt / skill** | Big jump, long airtime, near miss, precise driving | Always | High |
| **Death / fail payoff** | Wasted/busted banner after a buildup | Always | Very high (fail compilation staple) |
| **NPC / world comedy** | NPC reacts absurdly, dialogue with strangers, animals, unexpected AI behaviour; creator laughing | Always | High |
| **Duo / social moments** | Jason–Lucia banter, co-op or online interactions | Always; online later | Medium |
| **Roleplay scene** (when RP servers exist) | Character dialogue, scenarios, arrests, court, comedy | Later | Very high (RP clip channels) |
| **Negative spans** | Loading, menus, map, phone, pause, character creator, long driving with no talk, BRB screens | — | Never clip |

The taxonomy lives in `config/games/gta6/moments.yaml` (type, detectors, weights, cut rules), so types can be added without code changes.

## Signals

### Video

| Signal | How | Used for |
| --- | --- | --- |
| **Cutscene state** | Letterbox bar detection (persistent black bars top/bottom), HUD absence (minimap and HUD regions from doc 08 go empty), camera behaviour (smooth scripted moves, shot cuts every 2–6 s), and subtitle band presence | Cutscene start/end, beats |
| **Shot cuts** | PySceneDetect content detector on the game rect | Cutscene beats, montage detection |
| **Motion energy** | Mean optical-flow magnitude on downscaled game frames, 4 fps | Chases, crashes, firefights |
| **Speed proxy** | Flow magnitude in the lower-middle road region + speedometer OCR if the HUD has one | Chases, stunts, crash deceleration |
| **Impact** | Sudden flow reversal or stop + brightness flash + camera shake | Crashes, explosions |
| **Airtime** | Horizon/ground rotation and flow pattern consistent with a vehicle in the air for > 1 s | Stunts |
| **Visual novelty** | CLIP-style image embedding distance from the creator's last 10 minutes of footage | Discovery, new areas, reveals |
| **HUD events** | From doc 08: wanted level, wasted/busted, mission text, health | Escalation, fails, climaxes |
| **Screen state** | Doc 08 negatives: menus, map, loading, phone | Exclusion |

### Game audio (from the separated game stem, doc 07)

| Signal | How |
| --- | --- |
| Sirens | Audio classifier (e.g. YAMNet/PANNs classes: siren, police car) |
| Gunfire, explosions | Same classifier; burst density per second |
| Crash / impact | Transient onsets with broadband energy |
| Score music swell | Music-class energy rising in the game stem (in-game score, not radio) |
| Cutscene dialogue | Speech in the game stem while the creator is quiet |

### Creator reaction

| Signal | How |
| --- | --- |
| Voice energy spike | Loudness and pitch jump in the creator stem relative to their baseline |
| Laughter / screaming | Audio event classifier on the creator stem |
| Reaction words | Transcript (06): "no way", "bro", "what", "oh my god", per-language lists in `config/languages/<code>/reaction_words.txt` |
| Face reaction | Facecam: mouth-open ratio, head motion, hands-to-head (pose landmarks), measured against the creator's baseline |
| Chat and clips | Chat velocity and viewer clip density from 03/04 (already in 05) |

## Detectors per type

Each type has a small rule set over the signals, producing a type confidence 0–1. Examples:

- **Story cutscene reveal:** cutscene state on for ≥ 10 s **and** (game-stem dialogue or music swell) **and** a beat at the end (hard cut, fade, or sudden score change). Reveal strength = creator reaction peak within 10 s after the beat + chat spike.
- **Police chase:** wanted level ≥ 2 (doc 08) or siren density high **and** sustained speed proxy high for ≥ 8 s. Escalation bonus when stars increase within the window; payoff bonus for escape, crash or bust.
- **Crash / physics chaos:** impact signal **and** speed proxy high in the 2 s before. Bonus for ragdoll (sudden body motion detected by person pose on the game frame), multiple impacts, or wasted within 5 s.
- **Firefight:** gunfire burst density over threshold for ≥ 5 s; bonus for health drop + survival, or a death payoff.
- **Stunt:** airtime ≥ 1.5 s or near-miss (very high speed with a sharp flow change but no impact); bonus for clean landing or spectacular fail.
- **First-look discovery:** low player movement + high camera panning + high visual novelty + creator talking with surprise words, typically within the creator's first hours with the game.
- **NPC / world comedy:** creator laughter peak + game-stem speech (NPC dialogue) + low combat signals.
- **Death / fail payoff:** wasted/busted event with any high-intensity type in the preceding 20 s.

Rules start hand-set (from the taxonomy above) and are re-weighted by learned models once labelled data exists (see Learning).

## Vision-model verification (sparing)

For the top windows per stream hour after rule scoring, sample 1 fps frames over the window (max 30) plus 3 facecam frames and ask a vision LLM a fixed multiple-choice question: which moment type is shown, does something notable happen (yes/no), and at which frame index the payoff occurs. Answers are frame indexes, never timestamps (consistent with the word-index rule). Used to confirm types and payoff position, never to invent moments. Budget-capped per day in config.

## Gameplay score

```
gameplay_score = type_confidence × type_weight[type, phase, language]
               × (0.5 + 0.5 × reaction_score)
               × intensity_or_payoff_score
               × novelty_factor (penalize the 5th similar clip from the same creator today)
```

- `type_weight` starts from the taxonomy's clip value and the game phase (launch vs settled), then is learned per language channel by analytics (22).
- `reaction_score` combines creator voice, laughter, words and face (normalized per creator).
- The gameplay score enters the heatmap (05) as one more signal; the heatmap's fusion weights decide how much it counts versus chat and viewer clips.

## Clip boundaries and hooks by type

| Type | Start | End | Hook / cold open |
| --- | --- | --- | --- |
| Story cutscene reveal | 3–6 s before the key beat's setup line (not the whole cutscene) | 2–4 s after the creator's peak reaction | Cold open on the creator's reaction face for 1 s, then the setup; title teases the reveal without spoiling it in the first line |
| Police chase | When stars increase or the chase starts escalating | Escape, crash or bust + reaction | Open on the most intense second (crash or helicopter), then rewind feel ("how it started") |
| Crash / physics | 3–5 s of buildup at speed | 2–3 s after impact + reaction, include slow-mo replay of impact (0.5× for 1–2 s) if the style profile allows | Start fast; the impact must land within the first 8 s |
| Firefight | Start of the exchange | Death/survival payoff + reaction | Open on the payoff shot if the clip is > 30 s |
| Heist / mission climax | Start of the escape or the final objective | Mission passed + reaction | Text hook naming the stake |
| Stunt | Approach (2–3 s) | Landing or fail + reaction; optional replay of the jump | Start at the approach, never before |
| First-look discovery | The moment the creator notices | When commentary moves on | Hook = the creator's surprise line as caption |
| NPC / world comedy | Line before the absurd moment | End of laughter | Caption the NPC line |
| Death / fail payoff | Start of the buildup that leads to it (max 20 s before) | 2 s after the banner + reaction | "Wait for it" style hook only if the style profile uses it |

Length targets per platform and the monetization rule (TikTok clips > 60 s for Creator Rewards) come from docs 09 and 19; these rules decide where inside the moment to cut. Boundaries snap to transcript word edges (06) and scene cuts.

## Cutscene specifics

- Never clip an entire cutscene; clip the beat (setup → reveal → reaction).
- Prefer windows where the facecam is visible during the reveal; if the creator turned off the cam for the cutscene, require a strong voice reaction or drop the type weight by half.
- Story beats are tagged with a `story_beat_id` (perceptual hash of the reveal frame) so the same beat isn't posted many times from different creators on the same channel; the gate (15) allows at most one clip per beat per channel per day, picking the creator with the best reaction score, and allows re-use only from creators in a different language.
- Packaging (14) marks story-reveal clips so titles avoid spoiling the reveal in the first words (viewers scroll past spoilers they didn't choose; teasing performs better).

## Calibration for GTA 6 (self-learning from early-access footage)

The real GTA 6 HUD, cutscene framing and audio are confirmed from footage, not assumed:

1. From the first early-access VODs, sample frames every 5 s and cluster them (image embeddings). Clusters with persistent black bars and no HUD = cutscenes; clusters with consistent corner elements = gameplay HUD; static UI = menus/map/loading.
2. Store the learned templates (letterbox height, HUD regions, minimap location) in `config/games/gta6/profile.yaml` (shared with doc 08).
3. Re-run calibration weekly and after any game update; alert if detection rates shift sharply (HUD changed).

## Learning

- **Labels:** viewer clips (04) mark which moments people chose; the clip's position tells the type detectors where real moments are. After launch, our own clips' performance (22) labels which types and cuts work per language and platform.
- **Models:** a gradient-boosted classifier per type on the signal features replaces hand rules once each type has ≥ 300 labelled examples; type weights and boundary offsets are tuned by the analytics bandits.
- **Backtests (30):** type classification precision/recall on a labelled set; boundary IoU vs viewer clips per type; recall of viewer-clipped moments when the gameplay score is added to the heatmap (it must improve recall@20, or its weight drops to zero).

## Output

`moment.json` per candidate window: `type`, `type_confidence`, `gameplay_score`, `reaction_score`, `payoff_frame`, `beat_frame` (cutscenes), `story_beat_id`, recommended `start_s`/`end_s`, `hook_style`, and the signal values that produced it (for the dashboard's "why this clip" panel).

## Performance budget (M1)

- Motion, scene cuts and letterbox detection at 4 fps on 480p game frames: well under real time.
- Audio classifiers on the separated stems: fast.
- Pose/face landmarks on facecam at 5 fps: fast with MediaPipe.
- Vision LLM: only for top windows, capped per day.
- Everything runs only on candidate windows (± 60 s), not full streams.

## Done when

- [ ] On a labelled set from early-access GTA 6 VODs, type classification precision ≥ 0.8 for cutscene, chase, crash and death types.
- [ ] Adding the gameplay score to the heatmap improves recall@20 of viewer-clipped moments over the heatmap without it (backtest 30).
- [ ] Cutscene clips cut to the beat (setup → reveal → reaction) with boundary IoU ≥ 0.6 against viewer clips of the same beats.
- [ ] Calibration builds a GTA 6 profile from raw VODs without hand-labelling.
- [ ] The dashboard shows each clip's type and the signals behind it.

## Open questions

- [ ] Exact GTA 6 cutscene framing (letterbox or full-frame) and HUD layout, confirmed by calibration on early-access footage.
- [ ] When GTA 6 online and roleplay servers arrive, add their moment types and weights.
