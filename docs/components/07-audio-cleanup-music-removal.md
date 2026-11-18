# Clipper Component 07 — Audio Cleanup & Music Removal

Nov 18, 2026

Audio Cleanup strips licensed music (above all GTA 6 radio) out of each window while keeping the streamer's voice and the game's sound effects, then levels the audio for short-form playback. Without it, in-game radio songs trigger automatic copyright claims that divert or block revenue.

## Why this is required

A song playing in GTA 6 is not a license to publish it; Rockstar's guidance gives creators no blanket soundtrack license, and platforms apply their own music-rights checks ([iTechGuides](https://www.itechguides.com/gta-vi-music-what-creators-can-safely-use-in-videos-and-streams)). Content ID claims on in-game radio have hit gaming channels for years ([Kotaku](https://kotaku.com/heres-what-youtube-has-to-say-to-angry-youtubers-1485168478)). Streamers' radio and any background music they play end up in the source audio.

## Job and boundaries

- **Does:** separate audio into voice, game sound and music; drop or heavily duck the music; produce a clean voice stem for transcription; normalize loudness for the final mix.
- **Doesn't:** add music. Any added music must come from a properly licensed library (decided in Component 12).

## Pipeline per window

1. **Music detection (cheap):** a lightweight classifier labels each second as speech, music, music+speech or other. Windows with no music skip separation entirely (saves M1 time).
2. **Source separation (only where music was found):**
   - Primary: a dialogue/effects/music model, which outputs speech, effects and music separately. Tools built for exactly this: [ELUATE](https://pypi.org/project/eluate/) and [husher](https://pypi.org/project/husher/) (video in, video out, music removed, dialogue and SFX kept).
   - Fallback: [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator) or [Demucs](https://github.com/facebookresearch/demucs) with a vocals/other split, then recombine vocals with "other" minus the bass/drums stems that carry most of the song.
3. **Remix:** voice at full level, game effects at about −6 dB under voice, music dropped (or kept below −30 dB only where removal leaves audible artifacts).
4. **Residual check:** run the music detector on the cleaned mix; if music is still clearly present, mark the window `music_risk` so the auto-gate (Component 15) can drop or mute that span.
5. **Loudness:** normalize to about −14 LUFS integrated with a true-peak ceiling of −1 dBTP (FFmpeg `loudnorm`, two-pass), with light compression so shouts and whispers sit evenly.
6. **Outputs:** `voice.wav` (for transcription), `clean_mix.wav` (for render), per-second music probability (for the heatmap and gate).

## Performance on the M1

- Separation models are the heaviest audio step. Run them only on windows that will be built, never on whole streams.
- Use the PyTorch MPS (Metal) backend where the tool supports it; otherwise CPU. Benchmark minutes of processing per minute of audio in week one.
- On an 8 GB M1, never run separation and transcription at the same time.

## Special cases

- **Streamer plays their own music on stream (not game radio):** same treatment; it's still licensed music.
- **Music is the subject** (creator reacting to a real artist's song on the in-game radio, singing along, "Drake is on the radio in GTA 6"): removing the music ruins the clip, and these can perform very well (50K-view example in `docs/research/gta6-clip-examples.md`). Keep the music for these clips (`music_subject=true`, set by doc 31), and route them by platform: post where the platform recognizes and tags licensed music (Snapchat, TikTok, Instagram/Facebook generally attribute it), and on YouTube accept that the clip may be claimed, muted or blocked. Analytics (22) tracks claims and outcomes per platform for these clips, and the scheduler stops sending them to any platform where they keep getting blocked.
- **Game score/cinematic music:** treated like any other music; removed or ducked.
- **Voice chat with music bleeding through friends' mics:** separation handles it; residual check catches the rest.

## Quality checks

- Hand-check 20 windows with radio: voice intelligible, explosions and car sounds intact, no audible song.
- Upload private test clips to YouTube and check whether Content ID still matches; this is the real test.

## Done when

- [ ] Private test uploads of radio-heavy clips come back with no music claims.
- [ ] Voice stays clear after separation on a 20-clip sample.
- [ ] Windows without music skip separation automatically.

## Open questions

- [ ] Which separation tool gives the best voice/SFX quality on GTA footage (test ELUATE, husher and Demucs side by side).
- [ ] Whether to add licensed background music at all, and from which library.
