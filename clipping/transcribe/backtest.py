"""Stage backtest 06: WER per launch language (CER for Japanese) and utterance timing error.

Speech is TTS (flite for English, Piper neural voices for the rest; voices in var/models/piper), placed at known times with gaps. TTS is harder than
real speech for some languages (robotic prosody), so this is a conservative proxy until the platform-caption
transcript set can be built (needs keys)."""

from __future__ import annotations

import re
import unicodedata

import numpy as np

from clipping.core.settings import ROOT
from clipping.eval import audiofx
from clipping.eval.harness import Example, StageResult, stage
from clipping.transcribe import engine

SR = 16000
LINES = {
    "en": [
        "the cops are right behind us go left now",
        "he just flew off the bridge in a sports car",
        "we have five stars and one tire left",
    ],
    "es": [
        "la policía está justo detrás de nosotros",
        "acaba de volar por encima del puente",
        "tenemos cinco estrellas y una sola rueda",
    ],
    "pt": [
        "a polícia está bem atrás da gente",
        "ele voou da ponte com o carro esportivo",
        "temos cinco estrelas e só um pneu",
    ],
    "fr": [
        "la police est juste derrière nous",
        "il vient de sauter du pont en voiture",
        "on a cinq étoiles et un seul pneu",
    ],
    "de": [
        "die polizei ist direkt hinter uns",
        "er ist gerade von der brücke geflogen",
        "wir haben fünf sterne und nur einen reifen",
    ],
    "ru": [
        "полиция прямо за нами",
        "он только что слетел с моста на машине",
        "у нас пять звёзд и одно колесо",
    ],
    "tr": ["polis tam arkamızda", "köprüden arabayla uçtu", "beş yıldızımız ve tek lastiğimiz var"],
    "vi": [
        "cảnh sát đang ở ngay phía sau chúng ta",
        "anh ấy vừa bay khỏi cây cầu",
        "chúng ta có năm sao và một bánh xe",
    ],
    "ar": ["الشرطة خلفنا مباشرة", "لقد طار من فوق الجسر بالسيارة", "لدينا خمس نجوم وإطار واحد"],
    "ja": ["警察がすぐ後ろにいる", "彼は車で橋から飛んだ", "星が五つでタイヤが一つしかない"],
}
PIPER = {
    "es": "es_ES-davefx-medium",
    "pt": "pt_BR-faber-medium",
    "fr": "fr_FR-siwis-medium",
    "de": "de_DE-kerstin-medium",
    "ru": "ru_RU-irina-medium",
    "tr": "tr_TR-dfki-medium",
    "vi": "vi_VN-vais1000-medium",
    "ar": "ar_JO-kareem-medium",
    "ja": "ja_JP-hi_fi_captain-medium",
}
PIPER_DIR = ROOT / "var" / "models" / "piper"
NUMBERS = {
    "en": ["one", "two", "three", "four", "five"],
    "es": ["uno", "dos", "tres", "cuatro", "cinco"],
    "pt": ["um", "dois", "três", "quatro", "cinco"],
    "fr": ["un", "deux", "trois", "quatre", "cinq"],
    "de": ["eins", "zwei", "drei", "vier", "fünf"],
    "ru": ["один", "два", "три", "четыре", "пять"],
    "tr": ["bir", "iki", "üç", "dört", "beş"],
    "vi": ["một", "hai", "ba", "bốn", "năm"],
    "ar": ["واحد", "اثنان", "ثلاث", "أربع", "خمس"],
    "ja": ["一", "二", "三", "四", "五"],
}


def piper_tts(text: str, lang: str) -> np.ndarray:
    from scipy.signal import resample_poly

    v = _voice(lang)
    from piper import SynthesisConfig

    cfg = SynthesisConfig(
        noise_scale=0.0, noise_w_scale=0.0
    )  # VITS samples noise: zero it for reproducible audio
    x = np.concatenate([ch.audio_float_array for ch in v.synthesize(text, syn_config=cfg)])
    sr = v.config.sample_rate
    g = np.gcd(sr, SR)
    return resample_poly(x, SR // g, sr // g).astype(np.float32)


_VOICES: dict = {}


PIPER_PATHS = {
    "es": "es/es_ES/davefx",
    "pt": "pt/pt_BR/faber",
    "fr": "fr/fr_FR/siwis",
    "de": "de/de_DE/kerstin",
    "ru": "ru/ru_RU/irina",
    "tr": "tr/tr_TR/dfki",
    "vi": "vi/vi_VN/vais1000",
    "ar": "ar/ar_JO/kareem",
    "ja": "ja/ja_JP/hi_fi_captain",
}


def ensure_voice(lang: str) -> None:
    """Download the Piper voice (MIT code, per-voice dataset licenses) from Hugging Face on first use."""
    import httpx

    PIPER_DIR.mkdir(parents=True, exist_ok=True)
    for ext in (".onnx", ".onnx.json"):
        dst = PIPER_DIR / f"{PIPER[lang]}{ext}"
        if not dst.exists():
            url = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{PIPER_PATHS[lang]}/medium/{PIPER[lang]}{ext}"
            with httpx.stream("GET", url, follow_redirects=True, timeout=300) as r:
                r.raise_for_status()
                with open(dst.with_suffix(dst.suffix + ".part"), "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
            dst.with_suffix(dst.suffix + ".part").rename(dst)


def _voice(lang: str):
    from piper import PiperVoice

    if lang not in _VOICES:
        ensure_voice(lang)
        _VOICES[lang] = PiperVoice.load(str(PIPER_DIR / f"{PIPER[lang]}.onnx"))
    return _VOICES[lang]


def norm(s: str, lang: str = "en") -> str:
    s = unicodedata.normalize("NFKC", s.lower())
    if lang == "ar":
        s = re.sub("[\u064b-\u0652\u0640]", "", s)  # diacritics, tatweel
        s = re.sub("[إأآ]", "ا", s).replace("ة", "ه").replace("ى", "ي")
    if lang == "ja":
        import pykakasi

        for k, kanji in enumerate(NUMBERS["ja"], 1):
            s = s.replace(kanji, str(k))
        s = "".join(i["hira"] for i in pykakasi.kakasi().convert(s))
    s = re.sub(r"[^\w\s]", " ", s)
    words = s.split()
    nums = NUMBERS.get(lang, [])
    words = [str(nums.index(w) + 1) if w in nums else w for w in words]
    return " ".join(words)


def edit_distance(a: list, b: list) -> int:
    d = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(b) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] != b[j - 1]))
            prev = cur
    return d[-1]


def error_rate(ref: str, hyp: str, chars: bool, lang: str = "en") -> float:
    r, h = norm(ref, lang), norm(hyp, lang)
    a, b = (list(r.replace(" ", "")), list(h.replace(" ", ""))) if chars else (r.split(), h.split())
    return edit_distance(a, b) / max(len(a), 1)


def onset_offset(x: np.ndarray) -> tuple[float, float]:
    hop = 160
    e = np.sqrt(np.convolve(x**2, np.ones(hop) / hop, mode="same"))
    on = np.nonzero(e > 0.1 * e.max())[0]
    return on[0] / SR, on[-1] / SR


@stage("06", "Transcription")
def run() -> StageResult:
    metrics, ex, timing = {}, [], []
    for lang, lines in LINES.items():
        parts, truth, pos = [], [], 0.5
        audio = np.zeros(int(0.5 * SR), np.float32)
        for k, line in enumerate(lines):
            seg = audiofx.tts(line, audiofx.VOICES[k % 4]) if lang == "en" else piper_tts(line, lang)
            on, off = onset_offset(seg)
            truth.append((pos + on, pos + off))
            audio = np.r_[audio, seg, np.zeros(int(0.8 * SR), np.float32)]
            pos = len(audio) / SR
            parts.append(line)
        t = engine.transcribe(audio, SR, language=lang, prompt="")
        hyp = " ".join(w["word"] for w in t.words)
        er = error_rate(" ".join(parts), hyp, chars=(lang == "ja"), lang=lang)
        metrics[f"wer_{lang}"] = er
        if er > 0.1:
            ex.append(Example(lang, "wer", er, f"hyp='{hyp[:120]}'"))
        for on, off in truth:
            ws = [w for w in t.words if on - 0.6 <= (w["start"] + w["end"]) / 2 <= off + 0.6]
            if ws:
                timing += [abs(ws[0]["start"] - on), abs(ws[-1]["end"] - off)]
    others = [v for k, v in metrics.items() if k != "wer_en"]
    metrics["wer_others_max"] = max(others)
    metrics["wer_others_mean"] = float(np.mean(others))
    metrics["timing_median_s"] = float(np.median(timing))
    ex.sort(key=lambda e: -e.value)
    return StageResult(metrics, ex, "tts@v1", {"engine": t.engine})
