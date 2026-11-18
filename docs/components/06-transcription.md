# Clipper Component 06 — Transcription

Nov 18, 2026

Transcription turns each candidate window's speech into word-level text with exact timestamps, which drives clip boundaries, hooks, captions and the LLM steps. It runs on the M1's GPU and only on candidate windows, never full streams.

## Job and boundaries

- **Does:** transcribe the voice track of each candidate window, produce word timestamps, detect language, and number every word so later steps reference words by index.
- **Doesn't:** caption-style or translate. No translation anywhere in the system; each language page uses native audio.

## Engine choice on the M1

| Option | Strength | Limit |
| --- | --- | --- |
| [whisper.cpp](https://github.com/ggml-org/whisper.cpp) with Metal (+ Core ML encoder) | Fast on Apple Silicon, MIT license, every Whisper language | C++ binary; call it from Python |
| [mlx-whisper](https://github.com/ml-explore/mlx-examples) | Pure Python on Apple's MLX, GPU-accelerated | Pin a version; newer project |
| [parakeet-mlx](https://pypi.org/project/parakeet-mlx/) | Fastest on Apple Silicon in published benchmarks ([benchmark](https://github.com/anvanvan/mac-whisper-speedtest)) | English plus 25 European languages only |
| faster-whisper | Great on NVIDIA | No Metal backend; CPU-only on Mac ([source](https://codersera.com/blog/faster-whisper-vs-whisper-cpp-speech-to-text-2026/amp/)) |

**Decision:** whisper.cpp (Metal) as the default for every language, model `large-v3-turbo` quantized. Optionally Parakeet for English pages if speed becomes the bottleneck. Benchmark both on the actual M1 in week one.

## Throughput budget

- Large-v3 runs at roughly 2–3× real time on an M1 ([PromptQuorum](https://www.promptquorum.com/ko/local-llms/apple-silicon-whisper-metal-benchmark)); turbo is faster.
- A 2-minute window takes well under a minute. At 10 windows per stream hour and 10 recorded streams, that's about 100 windows an hour, which fits if each takes under 30 s. If not, reduce windows per hour or move transcription to a cloud worker.

## Pipeline per window

1. Take the cleaned voice track from Component 07 (music removed). Transcribing the voice stem instead of the full mix sharply reduces errors from radio lyrics and explosions.
2. Resample to 16 kHz mono.
3. Run Whisper with word timestamps on, language auto-detect off when the creator's language is known (forced language is more accurate), and a game-specific initial prompt listing names and slang (GTA 6, Vice City, Leonida, Jason, Lucia, wanted level, plus the creator's name and frequent co-stars from past transcripts).
4. Run voice-activity detection first and skip silent stretches, so long quiet driving segments cost nothing.
5. Output a word list: `{index, word, start, end, confidence, speaker?}`.
6. Store as `transcript` JSON tied to the window.

## Word indices (why they matter)

The LLM never sees or returns timestamps. It sees words prefixed with their index and answers with index ranges ("start at word 112, end at word 187, hook = words 140–151"). Code maps indices to times. This prevents the model from inventing timestamps, an approach used by open-source clippers like autoclip.

## Speakers

- Streams often have the streamer plus friends on voice chat. Speaker diarization (e.g. pyannote) labels who speaks, which helps captions (color per speaker) and hooks.
- Diarization is heavy; run it only on windows that reach the build stage, and make it optional per channel.

## Accuracy safeguards

- Words below a confidence threshold are flagged; captions show them only if neighbors are confident, otherwise the caption step uses a shorter phrase.
- Profanity is kept in the transcript; the caption step decides per platform whether to mask it.
- Custom vocabulary (names, slang) grows automatically from frequent low-confidence corrections across streams.

## Failure handling

- No speech in window: mark as visual-only; the clip builder relies on audio/visual peaks and on-screen text hooks instead of dialogue.
- Wrong language detected: use the creator's known language from the radar.
- GPU busy with another job: queue; the M1 runs one heavy model at a time if it has 8 GB of memory.

## Done when

- [ ] Every candidate window has a word-level transcript within 2 minutes of extraction.
- [ ] Word error rate on a hand-checked sample of 20 GTA clips is acceptable for captions.
- [ ] Indices map to timestamps exactly; no LLM step ever outputs a raw time.

## Open questions

- [ ] M1 memory (8 GB or 16 GB) decides model size and whether diarization runs locally.
