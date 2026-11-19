# Master list of useful GitHub repos

Every open-source repo that could help the build, grouped by pipeline stage, with the component docs it serves. ★ = already cited in the docs; the rest were added from a sweep across all 32 component docs. **Check each repo's license before copying code** (reading for ideas is always fine), and prefer installing as a dependency over vendoring. AGPL code (e.g. Postiz) is study-only unless we're willing to publish our changes.

## 1. Stream recording & source ingest (docs 01, 02, 04)

| Repo | Use |
| --- | --- |
| ★ [streamlink/streamlink](https://github.com/streamlink/streamlink) | Record Twitch/Kick/YouTube live streams without re-encoding |
| [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) | Download VODs, YouTube replays and style-study reference Shorts |
| [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg) | Segmenting, cutting, encoding (VideoToolbox), loudness, overlays |
| ★ [lay295/TwitchDownloader](https://github.com/lay295/TwitchDownloader) | Twitch VOD + chat download (CLI) |
| [ihabunek/twitch-dl](https://github.com/ihabunek/twitch-dl) | Lightweight Twitch VOD/clip downloader (Python) |
| [Teekeks/pyTwitchAPI](https://github.com/Teekeks/pyTwitchAPI) | Typed Python client for Helix + EventSub (radar, clips, streams) |
| [PythonistaGuild/TwitchIO](https://github.com/PythonistaGuild/TwitchIO) | Async Twitch client (chat + API) |
| ★ [Bukk94/KickLib](https://github.com/Bukk94/KickLib) | Kick API + chat reference implementation (C#) |

## 2. Chat capture & chat-spike detection (docs 03, 05)

| Repo | Use |
| --- | --- |
| ★ [PetterKraabol/Twitch-Chat-Downloader](https://github.com/PetterKraabol/Twitch-Chat-Downloader) | Twitch VOD chat replay with timestamps |
| ★ [xenova/chat-replay-downloader](https://github.com/xenova/chat-replay-downloader) (also maintained as [xenova/chat-downloader](https://github.com/xenova/chat-downloader)) | YouTube live/replay chat |
| ★ [josec07/clipper](https://github.com/josec07/clipper) | Statistical chat-burst detection (CTIC) |
| ★ [hamzaskewl/clippy](https://github.com/hamzaskewl/clippy) | Chat spikes + AI clip ranking |
| ★ [nirvagold/stream-clipper](https://github.com/nirvagold/stream-clipper) | Chat-driven stream clipping |

## 3. Audio: music removal, loudness, sound events (docs 07, 31, 32)

| Repo | Use |
| --- | --- |
| ★ [facebookresearch/demucs](https://github.com/facebookresearch/demucs) (maintained fork: [adefossez/demucs](https://github.com/adefossez/demucs)) | Source separation: voice / music / game SFX stems |
| ★ [nomadkaraoke/python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator) | Easy wrapper for UVR/MDX/Demucs separation models |
| [Anjok07/ultimatevocalremovergui](https://github.com/Anjok07/ultimatevocalremovergui) | Model zoo + reference for best separation models |
| [acoustid/chromaprint](https://github.com/acoustid/chromaprint) | Audio fingerprints: check our output no longer matches songs |
| [worldveil/dejavu](https://github.com/worldveil/dejavu) | Fingerprint matching (self-check before upload; duplicate detection) |
| [csteinmetz1/pyloudnorm](https://github.com/csteinmetz1/pyloudnorm) | LUFS measurement/normalization (−14 LUFS target) |
| [slhck/ffmpeg-normalize](https://github.com/slhck/ffmpeg-normalize) | Batch loudness normalization via FFmpeg |
| [qiuqiangkong/audioset_tagging_cnn](https://github.com/qiuqiangkong/audioset_tagging_cnn) | PANNs: sirens, gunfire, explosions, laughter, music detection |
| [tensorflow/models](https://github.com/tensorflow/models/tree/master/research/audioset/yamnet) (YAMNet) | Lighter AudioSet event classifier |
| [snakers4/silero-vad](https://github.com/snakers4/silero-vad) | Voice activity detection (speech vs silence, dead-air trim) |
| [librosa/librosa](https://github.com/librosa/librosa) | Pitch, onsets, spectral features for reaction/impact signals |

## 4. Transcription & speakers (docs 06, 32)

| Repo | Use |
| --- | --- |
| ★ [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) | Fast Whisper on M1 (Metal/Core ML) |
| ★ [ml-explore/mlx-examples](https://github.com/ml-explore/mlx-examples) | mlx-whisper on Apple Silicon |
| ★ [anvanvan/mac-whisper-speedtest](https://github.com/anvanvan/mac-whisper-speedtest) | Benchmarks to pick the fastest Whisper backend on the M1 |
| [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | CTranslate2 Whisper for the Linux server/cloud; word timestamps |
| [m-bain/whisperX](https://github.com/m-bain/whisperX) | Forced alignment for accurate word timestamps + diarization |
| [pyannote/pyannote-audio](https://github.com/pyannote/pyannote-audio) | Speaker diarization (creator vs collab voices vs NPC dialogue) |
| [resemble-ai/Resemblyzer](https://github.com/resemble-ai/Resemblyzer) | Speaker embeddings (recognize a creator's voice in collabs) |
| [jitsi/jiwer](https://github.com/jitsi/jiwer) | Word error rate for transcription backtests (doc 30) |
| [pemistahl/lingua-py](https://github.com/pemistahl/lingua-py) | Language detection for creator language/dialect checks |

## 5. Vision: scenes, HUD, cutscenes, faces, motion (docs 08, 10, 13, 31, 32)

| Repo | Use |
| --- | --- |
| ★ [Breakthrough/PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | Shot-cut detection (cutscene beats, pacing in the style study) |
| ★ [bendawg2010/Auto-clipper](https://github.com/bendawg2010/Auto-clipper) | Per-game event profiles (YOLO + pixel rules) to model the GTA 6 profile on |
| [opencv/opencv](https://github.com/opencv/opencv) | Template matching (HUD), optical flow (motion/speed), image stats |
| [opencv/opencv_zoo](https://github.com/opencv/opencv_zoo) | YuNet face detector and other small models |
| [google-ai-edge/mediapipe](https://github.com/google-ai-edge/mediapipe) | Face/pose landmarks on the facecam (reaction score, face-safe crops) |
| [ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) | YOLO for police cars, helicopters, explosions; facecam box detection |
| [princeton-vl/RAFT](https://github.com/princeton-vl/RAFT) | High-quality optical flow if OpenCV flow isn't enough |
| [tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract) | OCR for banners and reference-channel captions |
| [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | Stronger multilingual OCR (Arabic, Japanese, Vietnamese captions) |
| [JaidedAI/EasyOCR](https://github.com/JaidedAI/EasyOCR) | Simple multilingual OCR alternative |
| [mlfoundations/open_clip](https://github.com/mlfoundations/open_clip) | Image embeddings: visual novelty, frame clustering for calibration |
| [JohannesBuchner/imagehash](https://github.com/JohannesBuchner/imagehash) | Perceptual hashes (story-beat IDs, duplicate clips) |
| [Blaizzy/mlx-vlm](https://github.com/Blaizzy/mlx-vlm) | Run vision-language models locally on the M1 for moment verification |

## 6. LLM (moment picking, hooks, titles) (docs 09, 14, 31)

| Repo | Use |
| --- | --- |
| [ollama/ollama](https://github.com/ollama/ollama) | Run local LLMs/VLMs simply (fallback or cost saver) |
| [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | Local LLM inference on Apple Silicon |
| [carpedm20/emoji](https://github.com/carpedm20/emoji) | Emoji handling/validation in hooks and captions |

## 7. Editing, captions & render (docs 09–12)

| Repo | Use |
| --- | --- |
| [libass/libass](https://github.com/libass/libass) | ASS subtitle rendering (burned captions, white-box and outline styles) |
| [kkroening/ffmpeg-python](https://github.com/kkroening/ffmpeg-python) | Build FFmpeg filter graphs from Python |
| [PyAV-Org/PyAV](https://github.com/PyAV-Org/PyAV) | Frame-level decode/encode from Python |
| [WyattBlue/auto-editor](https://github.com/WyattBlue/auto-editor) | Silence/dead-air cutting logic to study |
| [Zulko/moviepy](https://github.com/Zulko/moviepy) | Quick compositing prototypes (production render stays FFmpeg) |

## 8. Whole clippers to study (all stages)

| Repo | What to learn |
| --- | --- |
| ★ [artbyjazi/autoclip](https://github.com/artbyjazi/autoclip) | WhisperX + Pyannote, LLM word-index highlights, shot-aware reframing, libass captions |
| ★ [Steezy-code/clipper](https://github.com/Steezy-code/clipper) | faster-whisper, local scoring, YuNet face tracking |
| ★ [ClipsAI/clipsai](https://github.com/ClipsAI/clipsai) | Segmentation and 16:9 → 9:16 resizing library |
| ★ [sherlock-dev-ai/Clipify-AI-Video-Clipper-FREE](https://github.com/sherlock-dev-ai/Clipify-AI-Video-Clipper-FREE) | Live-stream monitoring, face crop, animated captions |
| ★ [Cstrp/vml](https://github.com/Cstrp/vml) | whisper.cpp + FFmpeg behind a REST API |
| ★ [viddotech/videoalchemy](https://github.com/viddotech/videoalchemy) | YAML-defined Whisper → FFmpeg workflows |
| [SamurAIGPT/AI-Youtube-Shorts-Generator](https://github.com/SamurAIGPT/AI-Youtube-Shorts-Generator) | GPT highlight picking + face-centered vertical crops |

## 9. Publishing (docs 16–20)

| Repo | Use |
| --- | --- |
| ★ [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app) | Working Instagram/YouTube/TikTok/Facebook/Threads integrations to study (AGPL) |
| [googleapis/google-api-python-client](https://github.com/googleapis/google-api-python-client) | YouTube Data/Analytics API + Gmail API (accounts tool) |
| [youtube/api-samples](https://github.com/youtube/api-samples) | Official resumable-upload and analytics examples |
| [facebook/facebook-python-business-sdk](https://github.com/facebook/facebook-python-business-sdk) | Graph API client (Instagram, Pages; Threads via raw Graph calls) |

TikTok and Snapchat have no official Python SDKs; their connectors call the REST APIs directly per docs 19 and 20.

## 10. Infrastructure, jobs, dashboard (docs 21, 23, 25, 29)

| Repo | Use |
| --- | --- |
| [procrastinate-org/procrastinate](https://github.com/procrastinate-org/procrastinate) | Postgres-backed task queue (uses `SKIP LOCKED`), fits doc 25 |
| [janbjorge/pgqueuer](https://github.com/janbjorge/pgqueuer) | Minimal Postgres job queue alternative |
| [supabase/supabase](https://github.com/supabase/supabase) | Hosted Postgres + storage option |
| [minio/minio](https://github.com/minio/minio) | S3-compatible bucket for local dev |
| [vercel/next.js](https://github.com/vercel/next.js) | Dashboard + public policy pages |
| [shadcn-ui/ui](https://github.com/shadcn-ui/ui) | Mobile-friendly dashboard components |
| [getsentry/sentry-python](https://github.com/getsentry/sentry-python) | Error tracking for workers |

## 11. Learning, analytics & backtesting (docs 22, 28, 30)

| Repo | Use |
| --- | --- |
| [scikit-learn/scikit-learn](https://github.com/scikit-learn/scikit-learn) | Regression, percentiles, model evaluation |
| [microsoft/LightGBM](https://github.com/microsoft/LightGBM) | Gradient-boosted moment-type classifiers (doc 31) |
| [mlflow/mlflow](https://github.com/mlflow/mlflow) | Track backtest runs, metrics and accepted baselines |

Thompson-sampling bandits (layout, text mode, hooks) are a few dozen lines with NumPy; no library needed.

## 12. Accounts tool (doc 27)

| Repo | Use |
| --- | --- |
| [anonaddy/anonaddy](https://github.com/anonaddy/anonaddy) | addy.io source; API reference for alias creation |
| [simple-login/app](https://github.com/simple-login/app) | SimpleLogin source; fallback alias provider API |

## 13. Dev tooling (all)

| Repo | Use |
| --- | --- |
| [astral-sh/uv](https://github.com/astral-sh/uv) | Fast Python env/dependency management |
| [astral-sh/ruff](https://github.com/astral-sh/ruff) | Lint/format (per CLAUDE.md) |
| [pytest-dev/pytest](https://github.com/pytest-dev/pytest) | Tests |
