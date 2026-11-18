"""Transcription (doc 06): word-level timestamps, forced language when known, game-vocabulary prompt, VAD.

Engines: whisper.cpp with Metal on the M1 (default there), mlx-whisper as the Mac fallback, faster-whisper on
Linux (CPU). Model size comes from detected RAM (core.hardware). Output: numbered words
{index, word, start, end, conf, speaker}; later steps reference words by index only.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from clipping.core import config, hardware

LOW_CONF = 0.5


@dataclass
class Transcript:
    language: str
    words: list[dict]
    engine: str

    @property
    def visual_only(self) -> bool:
        return not self.words


def number(words: list[dict]) -> list[dict]:
    return [dict(w, index=i) for i, w in enumerate(words)]


def prompt_for(creator: str | None = None, extra: list[str] | None = None, game: str = "gta6") -> str:
    p = config.game(game).get("initial_prompt", "")
    names = [n for n in [creator, *(extra or [])] if n]
    return (p + (" " + ", ".join(names) + "." if names else "")).strip()


def choose_engine() -> str:
    forced = os.environ.get("CLIPPING_ASR_ENGINE")
    if forced:
        return forced
    prof = hardware.profile()
    if prof.is_mac:
        return "whispercpp" if shutil.which("whisper-cli") else "mlx"
    return "faster-whisper"


@lru_cache(maxsize=2)
def _fw_model(size: str):
    from faster_whisper import WhisperModel

    return WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)


def _faster_whisper(
    audio: np.ndarray, language: str | None, prompt: str, size: str
) -> tuple[str, list[dict]]:
    m = _fw_model(size)
    segs, info = m.transcribe(
        audio.astype(np.float32),
        language=language,
        initial_prompt=prompt or None,
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
        condition_on_previous_text=False,
        temperature=0.0,
    )  # deterministic: no random sampling fallback
    words = []
    for s in segs:
        for w in s.words or []:
            words.append(
                {
                    "word": w.word.strip(),
                    "start": round(float(w.start), 3),
                    "end": round(float(w.end), 3),
                    "conf": round(float(w.probability), 3),
                    "speaker": None,
                }
            )
    return info.language, words


def _mlx(audio: np.ndarray, language: str | None, prompt: str, size: str) -> tuple[str, list[dict]]:
    import mlx_whisper  # Mac only

    repo = {
        "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
        "large-v3": "mlx-community/whisper-large-v3-mlx",
        "small": "mlx-community/whisper-small-mlx",
    }[size]
    r = mlx_whisper.transcribe(
        audio.astype(np.float32),
        path_or_hf_repo=repo,
        language=language,
        initial_prompt=prompt or None,
        word_timestamps=True,
    )
    words = [
        {
            "word": w["word"].strip(),
            "start": round(w["start"], 3),
            "end": round(w["end"], 3),
            "conf": round(w.get("probability", 1), 3),
            "speaker": None,
        }
        for s in r["segments"]
        for w in s.get("words", [])
    ]
    return r.get("language", language or ""), words


def _whispercpp(audio: np.ndarray, language: str | None, prompt: str, size: str) -> tuple[str, list[dict]]:
    """whisper.cpp CLI (Metal). Model file: $WHISPER_CPP_MODELS/ggml-<size>-q5_0.bin."""
    from clipping.eval.audiofx import write_wav

    models = Path(os.environ.get("WHISPER_CPP_MODELS", "~/whisper.cpp/models")).expanduser()
    model = next(iter(sorted(models.glob(f"ggml-{size}*.bin"))), None)
    if model is None:
        raise FileNotFoundError(f"no whisper.cpp model for {size} in {models}")
    with tempfile.TemporaryDirectory() as d:
        wav = write_wav(Path(d) / "a.wav", audio, 16000)
        cmd = [
            "whisper-cli",
            "-m",
            str(model),
            "-f",
            str(wav),
            "-ojf",
            "-of",
            str(Path(d) / "out"),
            "-ml",
            "1",
            "-sow",
        ]
        if language:
            cmd += ["-l", language]
        if prompt:
            cmd += ["--prompt", prompt]
        subprocess.run(cmd, capture_output=True, check=True, timeout=1800)
        data = json.loads((Path(d) / "out.json").read_text())
    words = []
    for seg in data.get("transcription", []):
        txt = seg["text"].strip()
        if not txt:
            continue
        toks = [t for t in seg.get("tokens", []) if not t["text"].startswith("[")]
        conf = float(np.mean([t.get("p", 1) for t in toks])) if toks else 1.0
        words.append(
            {
                "word": txt,
                "start": seg["offsets"]["from"] / 1000,
                "end": seg["offsets"]["to"] / 1000,
                "conf": round(conf, 3),
                "speaker": None,
            }
        )
    return data.get("result", {}).get("language", language or ""), words


ENGINES = {"faster-whisper": _faster_whisper, "mlx": _mlx, "whispercpp": _whispercpp}


def transcribe(
    audio: np.ndarray,
    sr: int = 16000,
    language: str | None = None,
    prompt: str = "",
    engine: str | None = None,
    size: str | None = None,
) -> Transcript:
    if sr != 16000:
        from scipy.signal import resample_poly

        g = np.gcd(sr, 16000)
        audio = resample_poly(audio, 16000 // g, sr // g)
    engine = engine or choose_engine()
    size = size or os.environ.get("CLIPPING_ASR_MODEL") or hardware.profile().whisper_model
    lang, words = ENGINES[engine](audio, language, prompt, size)
    words = [w for w in words if w["word"] and w["end"] >= w["start"]]
    words = refine_timing(words, audio, 16000)
    return Transcript(language or lang, number(words), f"{engine}:{size}")


def refine_timing(words: list[dict], audio: np.ndarray, sr: int, pause_s: float = 0.15) -> list[dict]:
    """Whisper tends to start the first word after a pause too early (it absorbs the silence). Move such starts,
    and ends before a pause, to where speech energy actually begins/ends inside the word's span."""
    if not words or len(audio) < sr // 10:
        return words
    hop = sr // 100  # 10 ms
    n = len(audio) // hop
    rms = np.sqrt((audio[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    thresh = 0.05 * float(np.percentile(rms, 99))
    out = [dict(w) for w in words]
    for i, w in enumerate(out):
        a, b = int(w["start"] * 100), min(n, int(w["end"] * 100) + 1)
        if b - a < 3:
            continue
        seg = rms[a:b] > thresh
        if not seg.any():
            continue
        after_pause = i == 0 or w["start"] - out[i - 1]["end"] > pause_s or out[i - 1]["end"] <= w["start"]
        before_pause = i == len(out) - 1 or out[i + 1]["start"] - w["end"] > pause_s
        if after_pause:
            w["start"] = round(max(w["start"], (a + int(np.argmax(seg))) / 100), 3)
        if before_pause:
            last = a + len(seg) - 1 - int(np.argmax(seg[::-1]))
            w["end"] = round(max(w["start"] + 0.05, min(w["end"], (last + 1) / 100)), 3)
    return out


def time_of(words: list[dict], start_word: int, end_word: int) -> tuple[float, float]:
    """Index -> time mapping. The only place word indices become timestamps."""
    if not (0 <= start_word <= end_word < len(words)):
        raise IndexError(f"word range {start_word}-{end_word} outside 0-{len(words) - 1}")
    return words[start_word]["start"], words[end_word]["end"]


def low_confidence(words: list[dict], thresh: float = LOW_CONF) -> list[int]:
    return [w["index"] for w in words if w["conf"] < thresh]


def store(c, window_id: int, t: Transcript) -> None:
    from clipping.core import db

    c.execute(
        """INSERT INTO transcript(window_id,language,words,engine,visual_only) VALUES (%s,%s,%s,%s,%s)
                 ON CONFLICT (window_id) DO UPDATE SET language=EXCLUDED.language, words=EXCLUDED.words, engine=EXCLUDED.engine,
                 visual_only=EXCLUDED.visual_only""",
        (window_id, t.language, db.j(t.words), t.engine, t.visual_only),
    )


def process_window(c, window_id: int) -> dict:
    """Job handler: transcribe the cleaned voice stem with the creator's known language forced."""
    import soundfile as sf

    from clipping.core import db, media

    w = db.one(
        c,
        """SELECT w.*, cr.language, cr.handle FROM "window" w JOIN moment m ON m.id=w.moment_id
                     JOIN stream s ON s.id=m.stream_id JOIN creator cr ON cr.id=s.creator_id WHERE w.id=%s""",
        window_id,
    )
    voice = (w["audio"] or {}).get("voice")
    if voice and os.path.exists(voice):
        audio, sr = sf.read(voice, dtype="float32")
    else:
        audio, sr = media.decode_audio(w["path"], 16000), 16000
    t = transcribe(audio, sr, language=w["language"], prompt=prompt_for(w["handle"]))
    store(c, window_id, t)
    return {"words": len(t.words), "language": t.language, "visual_only": t.visual_only}
