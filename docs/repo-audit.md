# Repo audit (license + activity)

Generated 2026-11-19 by `scripts/repo_audit.py` from [repos.md](repos.md) via GitHub search. Verdicts: **reuse ok** = permissive license, active; **reuse with care** = permissive but archived or no push in 18+ months; **use as dependency** = LGPL (link, don't copy); **separate process/CLI only** = GPL (call the tool, never import or copy its code); **study only** = AGPL or no license (read for ideas, write our own).

| Stage | Repo | License | Last push | Stars | Verdict | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Stream recording & source ingest | [streamlink/streamlink](https://github.com/streamlink/streamlink) | BSD-2-Clause | 2026-11-18 | 11964 | reuse ok |  |
| 1. Stream recording & source ingest | [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense | 2026-11-17 | 209172 | reuse ok |  |
| 1. Stream recording & source ingest | [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg) | LGPL-2.1-or-later | 2026-11-19 | 67632 | use as dependency | checked: license file; we only run the ffmpeg binary (separate process) |
| 1. Stream recording & source ingest | [lay295/TwitchDownloader](https://github.com/lay295/TwitchDownloader) | MIT | 2026-11-15 | 4100 | reuse ok |  |
| 1. Stream recording & source ingest | [ihabunek/twitch-dl](https://github.com/ihabunek/twitch-dl) | GPL-3.0 | 2026-08-23 | 761 | separate process/CLI only |  |
| 1. Stream recording & source ingest | [Teekeks/pyTwitchAPI](https://github.com/Teekeks/pyTwitchAPI) | MIT | 2026-11-16 | 294 | reuse ok |  |
| 1. Stream recording & source ingest | [PythonistaGuild/TwitchIO](https://github.com/PythonistaGuild/TwitchIO) | MIT | 2026-08-04 | - | reuse ok | checked: PyPI twitchio (repo link not indexed) |
| 1. Stream recording & source ingest | [Bukk94/KickLib](https://github.com/Bukk94/KickLib) | MIT | 2026-10-08 | 38 | reuse ok |  |
| 2. Chat capture & chat-spike detection | [PetterKraabol/Twitch-Chat-Downloader](https://github.com/PetterKraabol/Twitch-Chat-Downloader) | MIT | 2022-12-26 | 651 | reuse with care | no push in 47 months |
| 2. Chat capture & chat-spike detection | [xenova/chat-replay-downloader](https://github.com/xenova/chat-replay-downloader) | MIT | 2023-09-03 | - | reuse with care | checked: superseded by xenova/chat-downloader (PyPI chat-downloader), no release in 18+ months |
| 2. Chat capture & chat-spike detection | [xenova/chat-downloader](https://github.com/xenova/chat-downloader) | MIT | 2025-11-05 | 1198 | reuse ok |  |
| 2. Chat capture & chat-spike detection | [josec07/clipper](https://github.com/josec07/clipper) | - | - | - | not found | check manually (renamed, private or not indexed) |
| 2. Chat capture & chat-spike detection | [hamzaskewl/clippy](https://github.com/hamzaskewl/clippy) | MIT | 2026-04-20 | 9 | reuse ok |  |
| 2. Chat capture & chat-spike detection | [nirvagold/stream-clipper](https://github.com/nirvagold/stream-clipper) | MIT | 2025-12-31 | 5 | reuse ok |  |
| 3. Audio: music removal, loudness, sound events | [facebookresearch/demucs](https://github.com/facebookresearch/demucs) | MIT | 2024-04-24 | 10418 | reuse with care | archived, no push in 31 months |
| 3. Audio: music removal, loudness, sound events | [adefossez/demucs](https://github.com/adefossez/demucs) | MIT | 2026-07-11 | - | reuse ok | checked: PyPI demucs 4.1.0 (maintained fork; forks aren't searchable) |
| 3. Audio: music removal, loudness, sound events | [nomadkaraoke/python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator) | MIT | 2026-10-29 | 1502 | reuse ok |  |
| 3. Audio: music removal, loudness, sound events | [Anjok07/ultimatevocalremovergui](https://github.com/Anjok07/ultimatevocalremovergui) | MIT | 2026-10-06 | 27260 | reuse ok |  |
| 3. Audio: music removal, loudness, sound events | [acoustid/chromaprint](https://github.com/acoustid/chromaprint) | LGPL-2.1 | 2026-10-15 | 1428 | use as dependency | checked: license file; fpcalc CLI as a separate process |
| 3. Audio: music removal, loudness, sound events | [worldveil/dejavu](https://github.com/worldveil/dejavu) | MIT | 2024-04-22 | 6789 | reuse with care | no push in 31 months |
| 3. Audio: music removal, loudness, sound events | [csteinmetz1/pyloudnorm](https://github.com/csteinmetz1/pyloudnorm) | MIT | 2026-01-04 | 796 | reuse ok |  |
| 3. Audio: music removal, loudness, sound events | [slhck/ffmpeg-normalize](https://github.com/slhck/ffmpeg-normalize) | MIT | 2026-11-17 | 1545 | reuse ok | checked: PyPI |
| 3. Audio: music removal, loudness, sound events | [qiuqiangkong/audioset_tagging_cnn](https://github.com/qiuqiangkong/audioset_tagging_cnn) | MIT | 2024-07-25 | 1800 | reuse with care | no push in 28 months |
| 3. Audio: music removal, loudness, sound events | [tensorflow/models](https://github.com/tensorflow/models) | Apache-2.0 | 2026-11-16 | 77629 | reuse ok | checked: license file |
| 3. Audio: music removal, loudness, sound events | [snakers4/silero-vad](https://github.com/snakers4/silero-vad) | MIT | 2026-10-22 | 10712 | reuse ok |  |
| 3. Audio: music removal, loudness, sound events | [librosa/librosa](https://github.com/librosa/librosa) | ISC | 2026-11-19 | 9029 | reuse ok |  |
| 4. Transcription & speakers | [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) | MIT | 2026-11-19 | 55338 | reuse ok |  |
| 4. Transcription & speakers | [ml-explore/mlx-examples](https://github.com/ml-explore/mlx-examples) | MIT | 2026-04-06 | 9074 | reuse ok |  |
| 4. Transcription & speakers | [anvanvan/mac-whisper-speedtest](https://github.com/anvanvan/mac-whisper-speedtest) | MIT | 2025-08-04 | 49 | reuse ok |  |
| 4. Transcription & speakers | [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | MIT | 2026-11-12 | 26874 | reuse ok |  |
| 4. Transcription & speakers | [m-bain/whisperX](https://github.com/m-bain/whisperX) | BSD-2-Clause | 2026-11-12 | 25490 | reuse ok |  |
| 4. Transcription & speakers | [pyannote/pyannote-audio](https://github.com/pyannote/pyannote-audio) | MIT | 2026-11-19 | 10814 | reuse ok |  |
| 4. Transcription & speakers | [resemble-ai/Resemblyzer](https://github.com/resemble-ai/Resemblyzer) | Apache-2.0 | 2023-10-12 | 3311 | reuse with care | no push in 37 months |
| 4. Transcription & speakers | [jitsi/jiwer](https://github.com/jitsi/jiwer) | Apache-2.0 | 2026-09-03 | 947 | reuse ok |  |
| 4. Transcription & speakers | [pemistahl/lingua-py](https://github.com/pemistahl/lingua-py) | Apache-2.0 | 2026-07-20 | 1821 | reuse ok |  |
| 5. Vision: scenes, HUD, cutscenes, faces, motion | [Breakthrough/PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | BSD-3-Clause | 2026-11-18 | 5583 | reuse ok |  |
| 5. Vision: scenes, HUD, cutscenes, faces, motion | [bendawg2010/Auto-clipper](https://github.com/bendawg2010/Auto-clipper) | MIT | 2026-04-19 | 13 | reuse ok |  |
| 5. Vision: scenes, HUD, cutscenes, faces, motion | [opencv/opencv](https://github.com/opencv/opencv) | Apache-2.0 | 2026-11-19 | 91642 | reuse ok |  |
| 5. Vision: scenes, HUD, cutscenes, faces, motion | [opencv/opencv_zoo](https://github.com/opencv/opencv_zoo) | Apache-2.0 | 2026-10-20 | 1135 | reuse ok |  |
| 5. Vision: scenes, HUD, cutscenes, faces, motion | [google-ai-edge/mediapipe](https://github.com/google-ai-edge/mediapipe) | Apache-2.0 | 2026-11-19 | 37743 | reuse ok |  |
| 5. Vision: scenes, HUD, cutscenes, faces, motion | [ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) | AGPL-3.0 | 2026-11-19 | 63605 | study only |  |
| 5. Vision: scenes, HUD, cutscenes, faces, motion | [princeton-vl/RAFT](https://github.com/princeton-vl/RAFT) | BSD-3-Clause | 2025-08-24 | 4129 | reuse ok |  |
| 5. Vision: scenes, HUD, cutscenes, faces, motion | [tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract) | Apache-2.0 | 2026-11-19 | 77589 | reuse ok |  |
| 5. Vision: scenes, HUD, cutscenes, faces, motion | [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | Apache-2.0 | 2026-09-16 | 92905 | reuse ok |  |
| 5. Vision: scenes, HUD, cutscenes, faces, motion | [JaidedAI/EasyOCR](https://github.com/JaidedAI/EasyOCR) | Apache-2.0 | 2026-11-13 | 30157 | reuse ok |  |
| 5. Vision: scenes, HUD, cutscenes, faces, motion | [mlfoundations/open_clip](https://github.com/mlfoundations/open_clip) | MIT | 2026-11-17 | 14279 | reuse ok | checked: PyPI open-clip-torch |
| 5. Vision: scenes, HUD, cutscenes, faces, motion | [JohannesBuchner/imagehash](https://github.com/JohannesBuchner/imagehash) | BSD-2-Clause | 2025-02-01 | - | reuse with care | checked: PyPI imagehash (already a dependency), no release in 18+ months |
| 5. Vision: scenes, HUD, cutscenes, faces, motion | [Blaizzy/mlx-vlm](https://github.com/Blaizzy/mlx-vlm) | MIT | 2026-11-16 | - | reuse ok | checked: PyPI mlx-vlm |
| 6. LLM | [ollama/ollama](https://github.com/ollama/ollama) | MIT | 2026-11-18 | 187639 | reuse ok |  |
| 6. LLM | [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | MIT | 2026-11-19 | 135731 | reuse ok |  |
| 6. LLM | [carpedm20/emoji](https://github.com/carpedm20/emoji) | BSD-3-Clause | 2026-09-16 | 2045 | reuse ok | checked: PyPI |
| 7. Editing, captions & render | [libass/libass](https://github.com/libass/libass) | ISC | 2026-11-18 | 1195 | reuse ok |  |
| 7. Editing, captions & render | [kkroening/ffmpeg-python](https://github.com/kkroening/ffmpeg-python) | Apache-2.0 | 2024-08-04 | 11022 | reuse with care | no push in 27 months |
| 7. Editing, captions & render | [PyAV-Org/PyAV](https://github.com/PyAV-Org/PyAV) | BSD-3-Clause | 2026-11-19 | 3337 | reuse ok |  |
| 7. Editing, captions & render | [WyattBlue/auto-editor](https://github.com/WyattBlue/auto-editor) | Unlicense | 2026-11-19 | 6009 | reuse ok |  |
| 7. Editing, captions & render | [Zulko/moviepy](https://github.com/Zulko/moviepy) | MIT | 2026-08-26 | 15173 | reuse ok |  |
| 8. Whole clippers to study | [artbyjazi/autoclip](https://github.com/artbyjazi/autoclip) | MIT | 2026-08-01 | 451 | reuse ok |  |
| 8. Whole clippers to study | [Steezy-code/clipper](https://github.com/Steezy-code/clipper) | MIT | 2026-10-20 | 5 | reuse ok |  |
| 8. Whole clippers to study | [ClipsAI/clipsai](https://github.com/ClipsAI/clipsai) | MIT | 2024-01-17 | 578 | reuse with care | no push in 34 months |
| 8. Whole clippers to study | [sherlock-dev-ai/Clipify-AI-Video-Clipper-FREE](https://github.com/sherlock-dev-ai/Clipify-AI-Video-Clipper-FREE) | NOASSERTION | 2026-11-19 | 81 | study only | no recognised license |
| 8. Whole clippers to study | [Cstrp/vml](https://github.com/Cstrp/vml) | MIT | 2026-04-29 | 1 | reuse ok |  |
| 8. Whole clippers to study | [viddotech/videoalchemy](https://github.com/viddotech/videoalchemy) | MIT | 2025-09-18 | 140 | reuse ok |  |
| 8. Whole clippers to study | [SamurAIGPT/AI-Youtube-Shorts-Generator](https://github.com/SamurAIGPT/AI-Youtube-Shorts-Generator) | - | - | - | not found | check manually (renamed, private or not indexed) |
| 9. Publishing | [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app) | AGPL-3.0 | 2026-11-18 | 41986 | study only |  |
| 9. Publishing | [googleapis/google-api-python-client](https://github.com/googleapis/google-api-python-client) | Apache-2.0 | 2026-11-17 | 8976 | reuse ok |  |
| 9. Publishing | [youtube/api-samples](https://github.com/youtube/api-samples) | Apache-2.0 | 2026-11-18 | 6025 | reuse ok | checked: license file |
| 9. Publishing | [facebook/facebook-python-business-sdk](https://github.com/facebook/facebook-python-business-sdk) | Meta platform license | 2026-11-19 | - | use as dependency | checked: PyPI facebook-business; custom license: use as dependency only |
| 10. Infrastructure, jobs, dashboard | [procrastinate-org/procrastinate](https://github.com/procrastinate-org/procrastinate) | MIT | 2026-11-19 | 1460 | reuse ok |  |
| 10. Infrastructure, jobs, dashboard | [janbjorge/pgqueuer](https://github.com/janbjorge/pgqueuer) | MIT | 2026-11-09 | 1558 | reuse ok |  |
| 10. Infrastructure, jobs, dashboard | [supabase/supabase](https://github.com/supabase/supabase) | Apache-2.0 | 2026-11-19 | 115166 | reuse ok |  |
| 10. Infrastructure, jobs, dashboard | [minio/minio](https://github.com/minio/minio) | AGPL-3.0 | 2026-04-24 | 61253 | study only | archived |
| 10. Infrastructure, jobs, dashboard | [vercel/next.js](https://github.com/vercel/next.js) | MIT | 2026-11-19 | 143588 | reuse ok |  |
| 10. Infrastructure, jobs, dashboard | [shadcn-ui/ui](https://github.com/shadcn-ui/ui) | MIT | 2026-11-19 | 128575 | reuse ok |  |
| 10. Infrastructure, jobs, dashboard | [getsentry/sentry-python](https://github.com/getsentry/sentry-python) | MIT | 2026-11-19 | 2219 | reuse ok |  |
| 11. Learning, analytics & backtesting | [scikit-learn/scikit-learn](https://github.com/scikit-learn/scikit-learn) | BSD-3-Clause | 2026-11-19 | 68251 | reuse ok |  |
| 11. Learning, analytics & backtesting | [microsoft/LightGBM](https://github.com/microsoft/LightGBM) | MIT | 2026-07-18 | - | reuse ok | checked: PyPI lightgbm 4.7.0 |
| 11. Learning, analytics & backtesting | [mlflow/mlflow](https://github.com/mlflow/mlflow) | Apache-2.0 | 2026-11-19 | 28899 | reuse ok |  |
| 12. Accounts tool | [anonaddy/anonaddy](https://github.com/anonaddy/anonaddy) | AGPL-3.0 | 2026-11-17 | 4958 | study only |  |
| 12. Accounts tool | [simple-login/app](https://github.com/simple-login/app) | AGPL-3.0 | 2026-11-13 | 7153 | study only |  |
| 13. Dev tooling | [astral-sh/uv](https://github.com/astral-sh/uv) | Apache-2.0 | 2026-11-19 | 92413 | reuse ok |  |
| 13. Dev tooling | [astral-sh/ruff](https://github.com/astral-sh/ruff) | MIT | 2026-11-19 | 51318 | reuse ok |  |
| 13. Dev tooling | [pytest-dev/pytest](https://github.com/pytest-dev/pytest) | MIT | 2026-11-19 | 14714 | reuse ok |  |
