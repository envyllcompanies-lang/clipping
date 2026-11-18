# Clipper Component 10 — Reframe & Layout

Nov 18, 2026

Reframe & Layout converts 16:9 stream footage into a 9:16 vertical frame: it finds the game area and the facecam, picks a layout, and plans a smooth crop path that follows the action. The output is a per-frame crop plan the render engine applies.

## Job and boundaries

- **Does:** detect stream layout (game rectangle, facecam box, overlays), choose a vertical layout per clip, compute crop/scale paths, and plan punch-in zooms on emphasis words.
- **Doesn't:** encode video (12) or draw captions (11), though it reserves caption-safe space.

## Step 1 — Detect the stream layout (once per stream, refreshed hourly)

1. Sample 30 frames across the stream.
2. **Facecam:** run a face detector (e.g. OpenCV YuNet, used in open-source clippers) on each frame. A face that appears in the same small rectangle in most frames is the facecam; record its box. Pixel stability around it (a static border) refines the box edges.
3. **Game area:** the remaining large region with high motion; usually the full frame minus overlays.
4. **Overlays:** regions static across frames but not HUD (alerts, chat boxes, logos) form a mask so crops avoid centering on them.
5. Store `stream_layout`: facecam box (or none), game rect, overlay mask.

## Step 2 — Choose a vertical layout

| Layout | When | Composition (1080×1920) |
| --- | --- | --- |
| **Stacked (house layout, default)** | Facecam exists (almost every stream) | Creator facecam top ~40% (0–768 px), caption band centered on the seam, gameplay bottom ~60% (768–1920 px). See [reference](../assets/layout-reference.png) |
| Full gameplay | No facecam, or the moment is purely visual | Gameplay crop fills the frame, tracking the action |
| Gameplay + small cam | Facecam exists but action needs most of the frame | Gameplay fills; facecam in a corner bubble clear of caption zone |
| Split speakers | Two creators' POVs of the same moment (from two recordings) | Top/bottom halves |

**House layout (owner decision):** creator on top, captions in the middle on the seam, gameplay at the bottom, as in the [reference screenshot](../assets/layout-reference.png). Every clip with a detectable facecam uses it. The other layouts are fallbacks only: full gameplay when there's no facecam or it's hidden, gameplay + small cam never by default. Style profiles (13) may fine-tune the split (35–45% top) and caption styling within this layout, but can't switch the default to another layout.

Facecam panel: crop the facecam box with ~10% padding, scale to fill the 1080-wide top panel (crop sides, never letterbox), keep the face in the upper-middle of the panel. Gameplay panel: center crop of the game rect following the action (Step 3). No border between panels; the caption band covers the seam.

## Step 3 — Gameplay crop path

- **Target point per frame:** weighted center of motion (optical-flow magnitude) inside the game rect, plus pulls toward detected objects of interest (player character center, explosions, the vehicle) when Component 08 detects them.
- **Smoothing:** the crop center follows the target with a critically-damped spring (or a Kalman filter) so the camera never jitters; maximum pan speed is capped (e.g. 25% of frame width per second).
- **Shot changes:** at scene cuts, the crop jumps instantly rather than panning.
- **Crop width:** for stacked layout the gameplay panel is 1080 wide from a 1920-wide source scaled so the panel shows roughly the center 60–70% of the game; never upscale beyond 1.5× to avoid blur.

## Step 4 — Punch-in zooms

- At emphasis words and payoff moments (from Component 09), apply a 110–120% zoom over 150–250 ms, hold, and ease out, at the rate the style profile measured (e.g. one per 3–5 s).
- Zoom toward the action point, not the frame center.
- No zooms during fast pans (motion is already high).

## Step 5 — Safe zones

Keep key action, faces and captions in the middle band; leave about the bottom 20% clear for platform captions and the right 15% clear for engagement buttons. The crop plan exports these zones so captions (11) and hook text never collide with platform UI.

## Output

`crop_plan.json`: layout type, panel rectangles, and per-frame (or per-keyframe with interpolation) crop boxes and zoom factors for each panel.

## Failure handling

- Facecam detection flips between frames: require stability over 10+ frames before using it.
- Creator switches layout mid-stream (BRB screens, full-cam segments): re-detect on scene changes; skip windows dominated by non-game screens (Component 08 negatives).
- Very low source resolution: use full-gameplay layout to avoid magnifying blur.

## Done when

- [ ] Facecam correctly found on 95%+ of streams that have one.
- [ ] No visible jitter in crop motion on a 30-clip sample.
- [ ] Captions never overlap faces or platform UI zones.

## Open questions

- [x] Default layout: stacked, creator top ~40% / captions on seam / gameplay bottom ~60% (owner decision; reference in docs/assets/layout-reference.png).
