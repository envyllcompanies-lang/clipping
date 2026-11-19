"""Packaging (doc 14): hook text, titles, captions, hashtags and credit per platform, written natively in the
channel's language. One LLM call returns every field when a key is set; otherwise native templates. Limits are
enforced in code (regenerate once, then truncate at a word boundary); recent posts are never repeated."""

from __future__ import annotations

import hashlib
import random
import re
from functools import lru_cache

from clipping.core import config
from clipping.llm import client as llm

PLATFORMS = ["youtube", "tiktok", "instagram", "facebook", "threads", "snapchat"]
PLATFORM_NAME = {"twitch": "Twitch", "kick": "Kick", "youtube": "YouTube"}
SLURS = ["nigger", "nigga", "faggot", "retard", "tranny", "chink", "spic", "kike"]
PII = [
    r"[\w.+-]+@[\w-]+\.[\w.]+",
    r"\+?\d[\d\s().-]{8,}\d",
    r"\b\d{1,5}\s+\w+\s+(street|st|avenue|ave|road|rd)\b",
]


def cfg() -> dict:
    return config.load("packaging.yaml")


def similar(a: str, b: str) -> float:
    """3-gram Jaccard similarity (cheap stand-in for embedding distance)."""

    def grams(s):
        s = re.sub(r"\s+", " ", s.lower())
        return {s[i : i + 3] for i in range(max(1, len(s) - 2))}

    ga, gb = grams(a), grams(b)
    return len(ga & gb) / max(len(ga | gb), 1)


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > limit * 0.6 else cut).rstrip(" ,.;:-|")


def wrap_hook(text: str, max_line: int) -> str:
    """At most two lines of ~max_line characters."""
    if len(text) <= max_line or " " not in text:
        return truncate(text, max_line * 2) if " " in text else text[: max_line * 2]
    words, a = text.split(), ""
    for i, w in enumerate(words):
        if len(a) + len(w) + 1 > max_line and a:
            return a.strip() + "\n" + truncate(" ".join(words[i:]), max_line)
        a += " " + w
    return a.strip()


def safe(text: str) -> bool:
    low = text.lower()
    if any(re.search(rf"\b{s}", low) for s in SLURS):
        return False
    return not any(re.search(p, text, re.I) for p in PII)


@lru_cache(maxsize=4)
def _detector(codes: tuple[str, ...]):
    from lingua import IsoCode639_1, Language, LanguageDetectorBuilder

    langs = [
        Language.from_iso_code_639_1(getattr(IsoCode639_1, c.upper()))
        for c in codes
        if hasattr(IsoCode639_1, c.upper())
    ]
    return LanguageDetectorBuilder.from_languages(*langs).build()


def detect_language(
    text: str, strip: list[str] | None = None, codes: tuple[str, ...] | None = None
) -> str | None:
    """Language of a text among our channel languages (Lingua; accurate on short social copy)."""
    for sname in strip or []:
        text = text.replace(sname, " ")
    text = re.sub(r"[#@]\S+|GTA\s?6|GTAVI|\d+|[\U0001F300-\U0001FAFF]", " ", text)
    codes = codes or tuple(sorted({ch["stream_language"] for ch in config.channels().values()} | {"en"}))
    lang = _detector(codes).detect_language_of(text)
    return lang.iso_code_639_1.name.lower() if lang else None


def _pick(options: list[str], recent: list[str], rng: random.Random) -> str:
    opts = options[:]
    rng.shuffle(opts)
    for o in opts:
        if all(similar(o, r) < 0.8 for r in recent):
            return o
    return opts[0]


def _hashtags(
    language: str,
    core: list[str],
    creator: str,
    event: str,
    n: tuple[int, int],
    rng: random.Random,
    recent_blocks: list[str],
    platform: str | None = None,
) -> list[str]:
    if n[1] == 0:
        return []
    dyn = cfg()["dynamic_tags"].get(language, cfg()["dynamic_tags"]["en"])
    creator_tag = "#" + re.sub(r"\W", "", creator).lower()
    event_tag = "#" + re.sub(r"\s", "", event)
    plat_core = (cfg().get("core_tags") or {}).get(platform)
    for _ in range(12):
        k = rng.randint(n[0], n[1])
        if (
            plat_core
        ):  # research: core platform tags then the creator's name tag, e.g. #fyp #viral #gta #gta6 #lacy
            pool = (
                plat_core[: max(1, k - 1)] + [creator_tag] + rng.sample(dyn, min(2, len(dyn))) + [event_tag]
            )
        else:
            pool = core[:2] + [creator_tag, event_tag] + rng.sample(dyn, min(3, len(dyn)))
        tags = list(dict.fromkeys(pool))[:k]
        block = " ".join(tags)
        if block not in recent_blocks:  # rotate: identical tag blocks don't repeat post after post
            return tags
    return tags


def pick_quote(words: list[dict], plan: dict, language: str, max_chars: int = 32) -> str | None:
    """The creator's own line for a "quote + context" hook: the spoken phrase (2-7 words) with the most emphasis
    words (09 marks punchline/catchphrase), closest to the payoff. None when nothing short and clean was said."""
    s, e = plan.get("start_t", 0.0), plan.get("end_t", 1e9)
    emph = set(plan.get("emphasis_words", []))
    payoff = plan.get("payoff_t", (s + e) / 2)
    body = [w for w in words if s <= w["start"] <= e]
    best, best_sc = None, -1.0
    joiner = "" if language == "ja" else " "
    for i in range(len(body)):
        for n in range(2, 8):
            ph = body[i : i + n]
            if len(ph) < n or any(ph[k + 1]["start"] - ph[k]["end"] > 0.6 for k in range(n - 1)):
                break
            txt = joiner.join(w["word"] for w in ph).strip(" ,.")
            if len(txt) > max_chars or not safe(txt):
                continue
            covers = ph[0]["start"] - 0.3 <= payoff <= ph[-1]["end"] + 0.3
            near = 3.0 if covers else 3 / (1 + min(abs(ph[0]["start"] - payoff), abs(ph[-1]["end"] - payoff)))
            hits = [k for k, w in enumerate(ph) if w["index"] in emph]
            central = -0.5 * abs((n - 1) / 2 - sum(hits) / len(hits)) if hits else 0.0
            sc = 2 * len(hits) + near + central + (0.3 if 3 <= n <= 6 else 0.0)
            if sc > best_sc:
                best, best_sc = txt, sc
    if best:
        best = best[0].upper() + best[1:] if language not in ("ja", "ar") else best
    return best


def reaction_emoji(moment_type: str, rng: random.Random) -> str:
    c = cfg()
    return rng.choice(c["reaction_emojis"][c["type_reaction"].get(moment_type, "laugh")])


def creator_event(language: str, creator: str, moment_type: str, rng: random.Random) -> str:
    c = cfg()
    lang = language if language in c["what"] else "en"
    what = c["what"][lang]
    phrase = rng.choice(what.get(moment_type) or what["peak"])
    return c["creator_event"][lang].format(creator=creator, what=phrase)


def template_package(
    words: list[dict],
    plan: dict,
    *,
    language: str,
    creator: str,
    platform: str,
    channel: dict,
    recent: list[str],
    rng: random.Random,
) -> dict:
    c = cfg()
    lang = language if language in c["hooks"] else "en"
    kind = plan.get("payoff_kind", "peak")
    mtype = plan.get("moment_type") or {
        "death": "death",
        "arrest": "arrest",
        "crash": "crash",
        "wanted": "chase",
    }.get(kind, "peak")
    event = c["events"][lang].get(kind, c["events"][lang]["peak"])
    stars = re.findall(r"\b([2-5])\b", " ".join(w["word"] for w in words))
    n = stars[0] if stars else str(rng.choice([3, 4, 5]))
    quote = pick_quote(words, plan, lang)
    arms = dict(c.get("hook_pattern_arms") or {"reaction": 1.0})
    if not quote:
        arms.pop("quote", None)
    # hook candidates per pattern; the pattern is drawn from its A/B share, then the least-repeated option wins
    cands: dict[str, list[str]] = {
        p: [h.format(creator=creator, n=n, event=event) for h in hs] for p, hs in c["hooks"][lang].items()
    }
    cands["creator_event"] = [
        f"{creator_event(lang, creator, mtype, rng)} {reaction_emoji(mtype, rng)}" for _ in range(6)
    ]
    if quote:
        cands["quote"] = [
            f"{t.format(quote=quote, creator=creator)} {reaction_emoji(mtype, rng)}" for t in c["quote"][lang]
        ]
    from clipping.style import profiles

    pattern = profiles.sample({k: v for k, v in arms.items() if k in cands}, rng)
    titles = [("ce", None)] * 3 + [(i, t) for i, t in enumerate(c["titles"][lang])]
    emojis = ["", " 😳", " 💀", " 🔥", " 😂", " 😭"]
    options = [(h, t, e) for h in cands[pattern] for t in titles for e in emojis]
    rng.shuffle(options)
    ce_title = f"{creator_event(lang, creator, mtype, rng)} {reaction_emoji(mtype, rng)}"
    best, best_sim = None, 2.0
    for h, (ti, t), e in options[:400]:
        # YouTube/others: creator name first + what happened + "GTA 6" + one emoji (research takeaway 7)
        title_ = ce_title if t is None else t.format(creator=creator, event=event, hook=h) + e
        if title_ in recent:
            continue
        sim = max((similar(title_, r) for r in recent[-200:]), default=0.0)
        if sim < best_sim:
            best, best_sim = (h, ti, title_), sim
        if sim < 0.6:
            break
    if best is None:  # every option was used recently: vary the creator-event line
        best = (
            cands[pattern][0],
            "ce",
            f"{creator_event(lang, creator, mtype, rng)} {reaction_emoji(mtype, rng)}",
        )
    hook, title_style, title = best
    hook = wrap_hook(hook, c["limits"]["hook_line"])
    credit = c["credit"][lang].format(creator=creator, platform=PLATFORM_NAME.get(platform, platform))
    cta = rng.choice(c["cta"][lang])
    post_line = (
        rng.choice(c["reaction_lines"][lang])
        if rng.random() < 0.6
        else c["topic"][lang].format(CREATOR=creator.upper() if lang not in ("ja", "ar") else creator)
    )
    return {
        "hook_text": hook,
        "hook_pattern": pattern,
        "title": title,
        "title_style": title_style,
        "credit": credit,
        "cta": cta,
        "event": event,
        "post_line": post_line,
        "moment_type": mtype,
        "source": "templates",
    }


def llm_package(
    words: list[dict],
    plan: dict,
    *,
    language: str,
    creator: str,
    platform: str,
    channel: dict,
    recent: list[str],
    c=None,
) -> dict | None:
    if not llm.available():
        return None
    s, e = plan["start_t"], plan["end_t"]
    excerpt = " ".join(w["word"] for w in words if s <= w["start"] <= e)
    prompt = (
        f"Write packaging for a GTA 6 short clip. Language: {language} (write natively, never translate). "
        f"Voice: {channel.get('voice', 'hype')}. Creator: {creator} on {platform}. Payoff: {plan.get('payoff_kind')}.\n"
        f"Transcript: {excerpt}\nRecent titles to avoid repeating: {recent[-10:]}\n"
        "Hook patterns that work on current GTA 6 clips: creator + what happened + 'in GTA 6' + 1-2 emojis matching the "
        "reaction (laughter 😭🤣, shock 😳😨, hype 🔥), e.g. 'N3on survived a plane crash in GTA 6 😭'; or the creator's own "
        "line in quotes + context. Sentence case, not all caps.\n"
        'Return JSON: {"hook_text": str (<=40 chars per line, max 2 lines), "hook_pattern": one of creator_event|quote|'
        'reaction|question|number|creator_first, "title": str (<=60 chars, creator name first + what happened + GTA 6 + '
        'one emoji), "caption": str (short reaction line, no hashtags), "cta": str}'
    )
    out = llm.call_json(
        prompt,
        "You write short-form social copy for gaming clips. No slurs, no claims beyond what the clip shows.",
        c=c,
    )
    if not out or not all(isinstance(out.get(k), str) for k in ("hook_text", "title")):
        return None
    out["hook_text"] = wrap_hook(out["hook_text"].replace("\n", " "), cfg()["limits"]["hook_line"])
    out["source"] = "llm"
    return out


def package(
    words: list[dict],
    plan: dict,
    *,
    language: str,
    creator: str,
    platform: str,
    channel: dict | None = None,
    recent: list[str] | None = None,
    recent_tag_blocks: list[str] | None = None,
    seed: int | None = None,
    c=None,
) -> dict:
    channel = channel or next(
        (ch for ch in config.channels().values() if ch["stream_language"] == language), {}
    )
    recent = recent or []
    seed = (
        seed
        if seed is not None
        else int(hashlib.sha256(f"{creator}{plan.get('start_t')}{language}".encode()).hexdigest()[:8], 16)
    )
    rng = random.Random(seed)
    base = None
    for _ in range(2):
        base = llm_package(
            words,
            plan,
            language=language,
            creator=creator,
            platform=platform,
            channel=channel,
            recent=recent,
            c=c,
        )
        if base and safe(base["title"] + base["hook_text"]):
            break
        base = None
    tpl = template_package(
        words,
        plan,
        language=language,
        creator=creator,
        platform=platform,
        channel=channel,
        recent=recent,
        rng=rng,
    )
    base = {**tpl, **(base or {})}
    base.setdefault("caption", base["title"])
    lim = cfg()["limits"]
    core = channel.get("hashtags_core", ["#GTA6", "#GTAVI", "#gaming"])
    blocks = recent_tag_blocks or []
    fields = {}
    tags = {
        p: _hashtags(language, core, creator, base["event"], tuple(lim[p]["hashtags"]), rng, blocks, p)
        for p in PLATFORMS
    }
    yt_title = truncate(base["title"], lim["youtube"]["title"])
    fields["youtube"] = {
        "title": yt_title,
        "description": truncate(
            f"{base['credit']}\n{base['cta']}\n\n{' '.join(tags['youtube'])}", lim["youtube"]["description"]
        ),
        "tags": [t.lstrip("#") for t in tags["youtube"]],
    }
    # post caption: short reaction line or ALL-CAPS topic, then the tags (doc 14 rule 3)
    body = base.get("caption") if base.get("source") == "llm" else base["post_line"]
    fields["tiktok"] = {
        "caption": truncate(f"{body} {' '.join(tags['tiktok'])} {base['credit']}", lim["tiktok"]["caption"])
    }
    fields["instagram"] = {
        "caption": truncate(
            f"{body}\n\n{base['credit']}\n{base['cta']}\n\n{' '.join(tags['instagram'])}",
            lim["instagram"]["caption"],
        )
    }
    fields["facebook"] = {
        "description": truncate(
            f"{body} {base['credit']} {' '.join(tags['facebook'])}", lim["facebook"]["description"]
        )
    }
    fields["threads"] = {
        "text": truncate(f"{body} {base['credit']}", lim["threads"]["text"] - 20),
        "topic_tag": (tags["threads"] or [None])[0],
    }
    fields["snapchat"] = {"text": truncate(f"{body} {' '.join(tags['snapchat'])}", lim["snapchat"]["text"])}
    ok = safe(" ".join(str(v) for f in fields.values() for v in f.values()))
    return {
        "hook_text": base["hook_text"],
        "fields": fields,
        "language": language,
        "credit": base["credit"],
        "features": {
            "hook_pattern": base["hook_pattern"],
            "title_style": base.get("title_style"),
            "moment_type": base.get("moment_type"),
            "source": base["source"],
        },
        "safe": ok,
        "tag_blocks": {p: " ".join(t) for p, t in tags.items()},
    }


def within_limits(pk: dict) -> list[str]:
    lim = cfg()["limits"]
    errs = []
    f = pk["fields"]
    checks = [
        ("youtube.title", f["youtube"]["title"], lim["youtube"]["title"]),
        ("youtube.description", f["youtube"]["description"], lim["youtube"]["description"]),
        ("tiktok.caption", f["tiktok"]["caption"], lim["tiktok"]["caption"]),
        ("instagram.caption", f["instagram"]["caption"], lim["instagram"]["caption"]),
        ("facebook.description", f["facebook"]["description"], lim["facebook"]["description"]),
        (
            "threads.text",
            f["threads"]["text"] + " " + (f["threads"]["topic_tag"] or ""),
            lim["threads"]["text"],
        ),
        ("snapchat.text", f["snapchat"]["text"], lim["snapchat"]["text"]),
    ]
    errs += [f"{n} {len(v)}>{m}" for n, v, m in checks if len(v) > m]
    for p in PLATFORMS:
        lo, hi = lim[p]["hashtags"]
        n = len([t for t in pk["tag_blocks"][p].split() if t])
        if not lo <= n <= hi:
            errs.append(f"{p} hashtags {n} not in {lo}-{hi}")
    for line in pk["hook_text"].split("\n"):
        if len(line) > lim["hook_line"]:
            errs.append(f"hook line {len(line)}>{lim['hook_line']}")
    if pk["hook_text"].count("\n") > 1:
        errs.append("hook over 2 lines")
    return errs
