"""DB-backed clip production for one window (M1 `build` job): plan -> reframe -> captions -> render -> package -> gate.
The offline `clip run` (clipping.run) uses the same components without the database."""

from __future__ import annotations

import datetime as dt
import random

import numpy as np
import psycopg

from clipping.builder import plan as bp
from clipping.captions import ass
from clipping.core import config, db, media
from clipping.gate import checks
from clipping.packaging import write
from clipping.reframe import layout as rl
from clipping.render import engine
from clipping.storage import files
from clipping.style import profiles

UTC = dt.UTC


def sync_channels(c: psycopg.Connection) -> dict[str, int]:
    """config/channels/*.yaml -> channel rows (and one account row per platform, disconnected until the owner connects)."""
    out = {}
    for ch in config.channels().values():
        cid = db.scalar(
            c,
            """INSERT INTO channel(key,language,time_zone,style_profile,score_floor,config) VALUES (%s,%s,%s,%s,%s,%s)
                              ON CONFLICT (key) DO UPDATE SET language=EXCLUDED.language, time_zone=EXCLUDED.time_zone,
                              style_profile=EXCLUDED.style_profile, config=EXCLUDED.config RETURNING id""",
            ch["key"],
            ch["stream_language"],
            ch["time_zone"],
            ch.get("style_profile", "house"),
            ch.get("score_floor", 0.0),
            db.j(ch),
        )
        for p in ch.get("platforms", []):
            c.execute(
                "INSERT INTO account(channel_id,platform) VALUES (%s,%s) ON CONFLICT DO NOTHING", (cid, p)
            )
        out[ch["stream_language"]] = cid
    return out


def stream_layout(c: psycopg.Connection, stream_id: int, window_path: str) -> rl.StreamLayout:
    st = db.one(c, "SELECT layout FROM stream WHERE id=%s", stream_id)
    lay = st["layout"] or {}
    if "reframe" in lay:
        r = lay["reframe"]
        return rl.StreamLayout(
            r["width"],
            r["height"],
            tuple(r["facecam"]) if r["facecam"] else None,
            tuple(r["face"]) if r["face"] else None,
            tuple(r["game"]),
        )
    segs = db.all_(
        c, "SELECT path FROM segment WHERE stream_id=%s AND NOT deleted ORDER BY start_utc", stream_id
    )
    if len(segs) >= 5:
        picks = [segs[int(k)]["path"] for k in np.linspace(0, len(segs) - 1, min(30, len(segs)))]
        frames = np.concatenate([media.decode_frames(p, fps=1, width=640, dur=1.0)[:1] for p in picks])
    else:
        frames = media.decode_frames(window_path, fps=0.5, width=640)
    det = rl.detect_layout(frames)
    info = [s for s in media.probe(window_path)["streams"] if s["codec_type"] == "video"][0]
    k = int(info["width"]) / frames.shape[2]
    res = rl.StreamLayout(
        int(info["width"]),
        int(info["height"]),
        tuple(int(v * k) for v in det.facecam) if det.facecam else None,
        tuple(int(v * k) for v in det.face) if det.face else None,
        tuple(int(v * k) for v in det.game),
    )
    lay["reframe"] = res.to_json()
    c.execute("UPDATE stream SET layout=%s WHERE id=%s", (db.j(lay), stream_id))
    return res


def produce(c: psycopg.Connection, window_id: int, rng_seed: int | None = None) -> dict:
    w = db.one(
        c,
        """SELECT w.*, m.id moment_id, m.stream_id, m.peak_s, m.score, s.started_at, s.creator_id, cr.handle, cr.platform,
                            cr.language, t.words, t.language tlang FROM "window" w JOIN moment m ON m.id=w.moment_id
                     JOIN stream s ON s.id=m.stream_id JOIN creator cr ON cr.id=s.creator_id
                     LEFT JOIN transcript t ON t.window_id=w.id WHERE w.id=%s""",
        window_id,
    )
    chans = sync_channels(c)
    language = w["language"] or w["tlang"] or "en"
    channel_id = chans.get(language)
    if channel_id is None:
        c.execute(
            "UPDATE moment SET status='discarded', reason='no channel for language' WHERE id=%s",
            (w["moment_id"],),
        )
        return {"discarded": f"no channel for {language}"}
    ch_cfg = db.scalar(c, "SELECT config FROM channel WHERE id=%s", channel_id)
    style_name = ch_cfg.get("style_profile", "house")
    style = profiles.load(style_name)
    offset = (w["start_utc"] - w["started_at"]).total_seconds()
    dur = media.duration(w["path"])
    words = w["words"] or []
    evs = [
        {"t": r["t_s"] - offset, "type": r["type"], "confidence": r["confidence"]}
        for r in db.all_(c, "SELECT * FROM game_event WHERE window_id=%s", window_id)
        if not (r["details"] or {}).get("negative")
    ]
    neg = [
        ((r["t_s"] - offset), (r["details"]["end"] - 0))
        for r in db.all_(c, "SELECT * FROM game_event WHERE window_id=%s", window_id)
        if (r["details"] or {}).get("negative")
    ]
    inp = bp.Inputs(dur, words, evs, w["peak_s"] - offset, [], None, neg, language, w["handle"])
    plans = bp.build(inp, style_name, c)
    if not plans["versions"]:
        c.execute(
            "UPDATE moment SET status='discarded', reason=%s WHERE id=%s",
            (plans["discarded"], w["moment_id"]),
        )
        return {"discarded": plans["discarded"]}
    clip_id = db.scalar(
        c,
        """INSERT INTO clip(moment_id,channel_id,creator_id,edit_plan,style_profile,status) VALUES (%s,%s,%s,%s,%s,'planned')
                              ON CONFLICT (moment_id,channel_id) DO UPDATE SET edit_plan=EXCLUDED.edit_plan RETURNING id""",
        w["moment_id"],
        channel_id,
        w["creator_id"],
        db.j(plans),
        style_name,
    )
    recent = [
        r["t"]
        for r in db.all_(
            c,
            """SELECT cl.packaging->'fields'->'youtube'->>'title' t FROM clip cl WHERE cl.channel_id=%s
                                           AND cl.packaging IS NOT NULL ORDER BY cl.id DESC LIMIT 200""",
            channel_id,
        )
        if r["t"]
    ]
    pk = write.package(
        words,
        plans["versions"]["short"],
        language=language,
        creator=w["handle"],
        platform=w["platform"],
        channel=ch_cfg,
        recent=recent,
        c=c,
    )
    c.execute("UPDATE clip SET packaging=%s WHERE id=%s", (db.j(pk), clip_id))
    lay = stream_layout(c, w["stream_id"], w["path"])
    full = media.decode_frames(w["path"], fps=5, width=640)
    rng = random.Random(rng_seed if rng_seed is not None else clip_id)
    layout = rl.choose_layout(lay, _layout_arms(c, channel_id, style), rng)
    audio = w["audio"] or {}
    clean = audio.get("clean_mix")
    out = {}
    for vname, p in plans["versions"].items():
        cp = rl.plan(
            full,
            5,
            lay,
            layout,
            emphasis_t=p["emphasis_t"],
            zoom_amount=style["pacing"]["zoom_amount"],
            cam_ratio=style["layout"]["stacked"]["cam_ratio"],
            caption_size_pct=style["captions"]["size_pct"],
        )
        profanity = (ch_cfg.get("profanity") or {}).get("youtube", "mask")
        doc, _ = ass.build_ass(
            p,
            cp,
            words,
            style,
            language=language,
            hook_text=pk["hook_text"],
            credit=ass.credit_line(
                w["handle"],
                w["platform"],
                style.get("credit", {}).get("template", "@{creator} on {platform}"),
            ),
            profanity=profanity,
            emphasis_words=set(p.get("emphasis_words", [])),
        )
        wd = files.work_dir(c, f"r{clip_id}_{vname}")
        (wd / "captions.ass").write_text(doc, encoding="utf-8")
        target = files.managed("renders") / f"clip{clip_id}_{vname}.mp4"
        key = engine.input_hash(w["path"], clean, p, cp, doc)
        prev = db.one(c, "SELECT * FROM clip_version WHERE clip_id=%s AND version_type=%s", clip_id, vname)
        if prev and prev["input_hash"] == key and prev["path"] and target.exists():
            out[vname] = {"cached": True, "clip_version_id": prev["id"]}
            continue
        r = engine.render(
            w["path"], clean, p, cp, str(wd / "captions.ass"), str(target), fonts_dir=str(ass.FONTS_DIR)
        )
        files.register(c, target, "render", "clip_version", None)
        cv = db.scalar(
            c,
            """INSERT INTO clip_version(clip_id,version_type,path,input_hash,phash,duration_s,validation,thumbnail,status)
                             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'rendered')
                             ON CONFLICT (clip_id,version_type) DO UPDATE SET path=EXCLUDED.path, input_hash=EXCLUDED.input_hash,
                               phash=EXCLUDED.phash, duration_s=EXCLUDED.duration_s, validation=EXCLUDED.validation,
                               thumbnail=EXCLUDED.thumbnail, status='rendered' RETURNING id""",
            clip_id,
            vname,
            str(target),
            key,
            r.phash,
            r.duration,
            db.j(r.validation),
            r.thumbnail_jpg,
        )
        c.execute("UPDATE file SET owner_id=%s WHERE path=%s", (cv, str(target)))
        c.execute("UPDATE clip SET crop_plan=%s WHERE id=%s", (db.j({"layout": layout, vname: cp}), clip_id))
        files.delete_path(c, wd)
        d = checks.gate(c, cv)
        out[vname] = {
            "clip_version_id": cv,
            "gate": d.status,
            "targets": len(d.targets),
            "validation": r.validation["passed"],
        }
    c.execute("UPDATE clip SET status='built' WHERE id=%s", (clip_id,))
    c.execute("UPDATE moment SET status='built' WHERE id=%s", (w["moment_id"],))
    c.execute("""UPDATE "window" SET status='rendered' WHERE id=%s""", (window_id,))
    if w["path"]:
        files.delete_path(c, w["path"])  # windows are deleted once every version is rendered (doc 21)
    return {"clip_id": clip_id, "layout": layout, "versions": out}


def _layout_arms(c: psycopg.Connection, channel_id: int, style: dict) -> dict[str, float]:
    """Bandit-adjusted layout shares from analytics (22) when present, else the style profile's starting mix."""
    r = db.one(
        c,
        """SELECT "values" FROM weights WHERE component=%s AND active ORDER BY version DESC LIMIT 1""",
        f"layout:{channel_id}",
    )
    return r["values"] if r else profiles.layout_arms(style)
