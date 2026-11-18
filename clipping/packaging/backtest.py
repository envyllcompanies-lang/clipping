"""Stage backtest 14: every field within platform limits, detected language = channel language, no repeated
titles/captions within a channel's recent posts, patterns tracked as features, safety filter holds."""

from __future__ import annotations

import numpy as np

from clipping.builder import backtest as bb
from clipping.builder import plan as bp
from clipping.core import config
from clipping.eval.harness import Example, StageResult, stage
from clipping.packaging import write

TRANSCRIPTS = {
    "en": "bro the cops are right behind us go left go left",
    "es": "hermano la policía está detrás vamos a la izquierda",
    "pt": "mano a polícia está atrás da gente vai pra esquerda",
    "fr": "frère la police est juste derrière nous va à gauche",
    "de": "bruder die polizei ist direkt hinter uns fahr links",
    "ru": "брат полиция прямо за нами давай налево",
    "tr": "kardeşim polis tam arkamızda sola dön",
    "vi": "anh ơi cảnh sát ở ngay phía sau rẽ trái đi",
    "ar": "يا أخي الشرطة خلفنا مباشرة لف يسار",
    "ja": "警察がすぐ後ろにいる左に曲がって",
}


@stage("14", "Packaging")
def run() -> StageResult:
    in_limits, lang_ok, dup_free, tracked, ex = [], [], [], [], []
    for ch in config.channels().values():
        lang = ch["stream_language"]
        recent_titles, recent_blocks, seen = [], [], []
        for k in range(60):  # 60 posts per channel
            inp, _ = bb.synth_window(1400 + k)
            plan = bp.build(inp)["versions"]["short"]
            plan["payoff_kind"] = ["death", "crash", "wanted", "peak"][k % 4]
            words = [{"word": w, "start": i, "end": i + 0.5} for i, w in enumerate(TRANSCRIPTS[lang].split())]
            pk = write.package(
                words,
                plan,
                language=lang,
                creator=f"creator{k % 7}",
                platform="twitch",
                channel=ch,
                recent=recent_titles[-200:],
                recent_tag_blocks=recent_blocks[-5:],
                seed=k,
            )
            errs = write.within_limits(pk)
            in_limits.append(not errs)
            if errs:
                ex.append(Example(f"{lang}:{k}", "limits", len(errs), "; ".join(errs)))
            title = pk["fields"]["youtube"]["title"]
            seen.append(title)
            recent_titles.append(title)
            recent_blocks.append(pk["tag_blocks"]["instagram"])
            tracked.append(bool(pk["features"]["hook_pattern"]) and pk["features"]["title_style"] is not None)
            if k % 10 == 0:
                body = pk["fields"]["instagram"]["caption"]
                det = write.detect_language(body, strip=[f"creator{k % 7}", "Twitch"])
                ok = det == lang or (lang == "pt" and det == "pt")
                lang_ok.append(ok)
                if not ok:
                    ex.append(Example(f"{lang}:{k}", "language", 0, f"detected {det}: {body[:80]}"))
        dup_free.append(len(set(seen)) == len(seen))
        if len(set(seen)) != len(seen):
            ex.append(Example(lang, "duplicates", len(seen) - len(set(seen)), ""))
    unsafe = write.package(
        [{"word": "x", "start": 0, "end": 1}],
        plan,
        language="en",
        creator="call me 555 123 4567",
        platform="twitch",
    )
    return StageResult(
        {
            "within_limits": float(np.mean(in_limits)),
            "language_match": float(np.mean(lang_ok)),
            "no_duplicate_titles": float(np.mean(dup_free)),
            "patterns_tracked": float(np.mean(tracked)),
            "safety_blocks_pii": 0.0 if unsafe["safe"] else 1.0,
        },
        ex,
        "synthetic@v1",
    )
