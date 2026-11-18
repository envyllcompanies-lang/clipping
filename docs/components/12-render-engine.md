# Clipper Component 12 — Render Engine

Nov 18, 2026

The Render Engine executes an edit plan into final MP4 files: it cuts and reorders segments, applies the crop and zoom plan, composites panels, burns captions and text, mixes audio and encodes platform-ready files. It runs on the M1 with Apple's hardware encoder so renders are fast and cool.

## Job and boundaries

- **Inputs:** window video, `clean_mix.wav` (07), `edit_plan` (09), `crop_plan` (10), ASS captions and overlays (11), style assets (13).
- **Outputs:** one MP4 per version per channel (short, long, loop variants), plus a thumbnail frame and a perceptual hash for the duplicate check.
- **Doesn't:** decide anything creative; it follows the plans exactly and deterministically (same inputs, same file).

## Render graph (one FFmpeg filter_complex per version)

1. **Trim and order:** `trim`/`atrim` each planned segment, then `concat` in plan order (hook first for cold opens). Audio comes from `clean_mix.wav`, not the original track.
2. **Crop/zoom per panel:** `crop` with per-frame expressions (or `sendcmd` keyframes) from the crop plan, then `scale` to panel size with a high-quality scaler (lanczos).
3. **Composite layout:** `vstack`/`overlay` the facecam and gameplay panels onto a 1080×1920 canvas; facecam bubble with rounded mask if the style uses it.
4. **Text and captions:** burn ASS via `subtitles`/`ass` filter (libass); overlay PNG assets (logo, emoji, credit label) with `overlay`.
5. **Transitions and SFX:** whoosh/pop sound effects mixed at style-set levels on cuts and zooms (licensed SFX library only).
6. **Audio finish:** `loudnorm` two-pass to about −14 LUFS, true peak −1 dBTP; AAC 192 kbps, 48 kHz stereo.
7. **Encode:** H.264 High profile via `h264_videotoolbox` (Apple hardware), 1080×1920, 30 or 60 fps matching source, constant-quality target (or ~10–12 Mbps), `+faststart` so platforms can start processing quickly.

## Platform output specs

| Platform | Container/codec | Resolution | Length limits used | Notes |
| --- | --- | --- | --- | --- |
| YouTube Shorts | MP4 H.264/AAC | 1080×1920 | Up to 3 min allowed; we use the short version | Vertical or square counts as Short |
| Instagram Reels | MP4 H.264/AAC | 1080×1920 | Short version | Pulled from a public URL |
| Facebook Reels | MP4 H.264/AAC | 1080×1920 (min 540×960) | 3–90 s via API ([Meta docs](https://developers.facebook.com/documentation/video-api/guides/reels-publishing)) | |
| Threads | MP4 H.264/AAC | 1080×1920 | Up to 5 min | |
| TikTok | MP4 H.264/AAC | 1080×1920 | Long version (61–90 s) for monetization, short for reach | Max duration set per creator; query before posting |
| Snapchat Spotlight | MP4 H.264/AAC | 1080×1920 | Up to 60 s | Media encrypted before upload (Component 20) |
| Bluesky | MP4 H.264/AAC | 1080×1920 | Up to 3 min | |
| Pinterest | MP4 H.264/AAC | 1080×1920 | Short version | |

One master render per version; platform variants only differ when limits demand it (e.g. a 55 s cut for Snapchat if the short version is over 60 s).

## Performance

- VideoToolbox encoding on Apple Silicon is much faster than software x264 at similar quality for this use; libass and crop expressions run on CPU.
- Target: a 40 s clip renders in under 30 s on the M1. Measure in week one.
- Render jobs run one or two at a time, never alongside separation or transcription on an 8 GB machine.

## Determinism and caching

- Each render is keyed by a hash of all inputs and plan JSON; re-running an unchanged plan reuses the file.
- Intermediate files (scaled panels, temp audio) live in a per-job temp folder deleted at job end (Component 21).

## Validation after render

- `ffprobe` checks: duration within ±0.1 s of plan, resolution, codecs, audio loudness within ±1 LU of target, no black frames over 0.5 s, no silence over 1 s.
- Perceptual hash of sampled frames stored for duplicate detection (15).
- Thumbnail frame chosen at the payoff (used as cover where platforms allow).

## Failure handling

- Encoder failure: retry once with software encoder (libx264, preset veryfast).
- Validation failure: mark render failed with reason; the plan is rebuilt once, then discarded.

## Done when

- [ ] Every version passes validation automatically.
- [ ] Render time per 40 s clip is measured and within budget on the M1.
- [ ] Output files meet every platform's spec in the table above.

## Open questions

- [ ] 30 vs 60 fps output (60 looks smoother for gameplay; doubles some processing).
- [ ] SFX library choice and license.
