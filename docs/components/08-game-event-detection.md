# Clipper Component 08 — Game Event Detection (GTA 6 Profile)

Nov 18, 2026

Game Event Detection reads what's happening on screen in GTA 6 (deaths, police escalation, mission results, crashes) and turns it into point events for the heatmap and the clip builder. It is built as a swappable game profile, so adding another game later means writing a new profile, not new code.

## Job and boundaries

- **Does:** detect GTA 6 HUD and screen events in sampled frames around candidate peaks; emit timestamped events with confidence.
- **Doesn't:** classify whole moments (cutscene, chase, crash, discovery); that's Component 31, which uses these events as inputs. Doesn't run on every frame of every stream (too expensive). It runs on frames near heatmap peaks and inside candidate windows.
- **Starts empty:** GTA 6 HUD details are unknown until launch (November 19, 2026). The profile is filled in during the first week from real footage.

## Event types to detect (to confirm against the real HUD)

| Event | Likely visual cue | Detection method | Clip value |
| --- | --- | --- | --- |
| Death | Full-screen "wasted"-style banner, desaturation | Template match + OCR on banner text; frame-wide color saturation drop | High: classic fail payoff |
| Arrest | "Busted"-style banner | Same as death | High |
| Wanted level change | Star icons in a HUD corner | Template matching on the star region; count filled stars | Medium-high: escalation and chases |
| Mission passed/failed | Large center text | OCR on center band | Medium |
| Big crash / explosion | Sudden brightness flash, camera shake, debris | Frame brightness spike + motion magnitude spike | High |
| Money/score popups | Text popups | OCR | Low-medium |
| Phone/menu screens | Large static UI covering view | Template match | Negative: skip these spans |
| Loading screens | Static art + spinner | Template match / low motion | Negative: never clip |

## Methods

1. **Region templates:** each HUD element gets a screen region (as fraction of frame) and template images. Matching with normalized cross-correlation at 2–4 fps is cheap.
2. **OCR:** tesseract or a lightweight OCR model on banner regions only, matched against the profile's keyword list per language (banner text may be localized).
3. **Pixel statistics:** global brightness, saturation and motion energy for flashes, crashes and death desaturation.
4. **Object detection (later):** a small YOLO model fine-tuned on GTA 6 frames for police cars, helicopters and explosions, following the per-game profile approach in [Auto-clipper](https://github.com/bendawg2010/Auto-clipper). Only if templates and pixel stats aren't enough.
5. **Vision LLM (sparingly):** for ambiguous high-score moments, send 3–5 frames to a vision model asking a fixed multiple-choice question ("which of these events is shown?"). Never free-form; never for every moment.

## Handling streamer overlays

- Streamers put facecams, alerts and chat boxes over the game. Each creator gets an overlay mask learned automatically: regions that stay static across the stream but aren't game HUD are excluded from detection.
- HUD positions are relative to the game area, which may be scaled or cropped inside the stream layout; the profile stores positions relative to the detected game rectangle.

## Profile file

`config/games/gta6.yaml` holds: HUD regions, template image paths, OCR keywords per language, event weights for the heatmap, and negative spans (menus, loading). A new game = a new YAML plus templates.

## Building the profile (week one after launch)

1. Collect 50–100 screenshots of each event type from recorded streams.
2. Crop templates; measure regions; record banner text per language.
3. Validate on 2 hours of held-out footage; target 90%+ precision on deaths, arrests and wanted changes.
4. Ship; refine monthly or after game updates change the HUD.

## Outputs

`game_event` table: stream_id, t_s, type, confidence, details (e.g. wanted stars from 2 to 4).

## Failure handling

- Modded HUDs or RP servers (later, once GTA 6 RP exists) change the screen; RP profiles become their own sub-profiles.
- Low confidence events are passed with their confidence; the heatmap weights by it.

## Done when

- [ ] Death, arrest and wanted-level events detected at 90%+ precision on held-out GTA 6 footage.
- [ ] Loading and menu spans are reliably excluded from clips.
- [ ] Event detection adds under 10 seconds of compute per candidate window.

## Open questions

- [ ] The real GTA 6 HUD layout and banner wording, confirmed from launch footage.
