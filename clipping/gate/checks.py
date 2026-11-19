"""Auto-Gate (doc 15): replaces human approval. Every rendered version passes nine checks in order; each decision
is stored with its reason. Duplicates are judged per target account, so one clip can still go to accounts where it
isn't a repeat."""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg

from clipping.core import config, db
from clipping.render.engine import PLATFORM_SPECS

DUP_PHASH_BITS = 14  # mean per-frame dHash distance: seeded dups <= 9, distinct clips >= 19.6
LOOKBACK_DAYS = 90
MUTE_MAX_S = 2.0
ACTIVE_POST = ("scheduled", "uploading", "processing", "live", "retry_wait")


@dataclass
class Decision:
    status: str  # queued | rejected | rebuild | rerender
    targets: list[dict] = field(default_factory=list)
    results: list[tuple[str, bool, str]] = field(default_factory=list)
    mute_spans: list[tuple[float, float]] = field(default_factory=list)


def phash_distance(a: str, b: str) -> float:
    """Mean hamming distance between per-frame 64-bit dHashes (16 hex chars each)."""
    if not a or not b:
        return 64.0
    fa = [int(a[i : i + 16], 16) for i in range(0, len(a) - 15, 16)]
    fb = [int(b[i : i + 16], 16) for i in range(0, len(b) - 15, 16)]
    n = min(len(fa), len(fb))
    if n == 0:
        return 64.0
    return sum(bin(fa[i] ^ fb[i]).count("1") for i in range(n)) / n


def is_duplicate(phash_a: str, phash_b: str) -> bool:
    return phash_distance(phash_a, phash_b) <= DUP_PHASH_BITS


def overlap_s(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def _record(d: Decision, name: str, ok: bool, reason: str) -> bool:
    d.results.append((name, ok, reason))
    return ok


def evaluate(c: psycopg.Connection, clip_version_id: int, candidates: list[dict]) -> Decision:
    """candidates: [{account_id, platform, channel_id}] the scheduler would target. Returns the decision; the caller
    persists it with `persist()`."""
    cv = db.one(
        c,
        """SELECT cv.*, cl.moment_id, cl.channel_id, cl.creator_id, cl.edit_plan, cl.packaging, m.score, m.stream_id,
                             m.start_s, m.end_s, cr.blocklisted, cr.paused AS creator_paused, ch.score_floor, w.music_risk, w.audio, cl.music_subject
                      FROM clip_version cv JOIN clip cl ON cl.id=cv.clip_id JOIN moment m ON m.id=cl.moment_id
                      LEFT JOIN creator cr ON cr.id=cl.creator_id LEFT JOIN channel ch ON ch.id=cl.channel_id
                      LEFT JOIN "window" w ON w.moment_id=m.id WHERE cv.id=%s LIMIT 1""",
        clip_version_id,
    )
    d = Decision("queued", [dict(x) for x in candidates])
    val = cv["validation"] or {}
    plan = (cv["edit_plan"] or {}).get("versions", {}).get(cv["version_type"]) or (cv["edit_plan"] or {})
    # 1 technical
    if not _record(
        d,
        "technical",
        bool(val.get("passed")),
        "render validation "
        + (
            "passed" if val.get("passed") else "failed: " + ", ".join(k for k, v in val.items() if v is False)
        ),
    ):
        d.status = "rerender" if cv["rerenders"] < 1 else "rejected"
        return d
    # 2 minimum score (raised for unhealthy accounts below)
    floor = float(cv["score_floor"] or 0)
    if not _record(d, "min_score", cv["score"] >= floor, f"score {cv['score']:.3f} vs floor {floor:.3f}"):
        d.status = "rejected"
        return d
    # 8 blocklist / paused source (checked early: cheap and absolute)
    if not _record(
        d,
        "blocklist",
        not cv["blocklisted"] and not cv["creator_paused"],
        "creator blocklisted"
        if cv["blocklisted"]
        else "source paused"
        if cv["creator_paused"]
        else "creator clear",
    ):
        d.status = "rejected"
        return d
    # 3 internal duplicates + 4 cross-brand duplicates, per target account
    kept = []
    for t in d.targets:
        acc = db.one(c, "SELECT * FROM account WHERE id=%s", t["account_id"])
        health = acc["health"] or {}
        if health.get("restricted") or health.get("claims_7d", 0) >= 2:
            if cv["score"] < floor + 0.15:
                _record(
                    d,
                    "account_health",
                    False,
                    f"account {acc['id']} unhealthy: needs score >= {floor + 0.15:.2f}",
                )
                continue
        prior = db.all_(
            c,
            f"""SELECT p.account_id, cv2.phash, m2.stream_id, m2.start_s, m2.end_s, cl2.channel_id, cl2.packaging,
                                     cv2.duration_s, cv2.id cvid
                              FROM post p JOIN clip_version cv2 ON cv2.id=p.clip_version_id JOIN clip cl2 ON cl2.id=cv2.clip_id
                              JOIN moment m2 ON m2.id=cl2.moment_id
                              WHERE p.platform=%s AND p.status = ANY(%s) AND p.created_at > now() - interval '{LOOKBACK_DAYS} days'
                                AND cv2.id <> %s""",
            t["platform"],
            list(ACTIVE_POST),
            clip_version_id,
        )
        dup_reason = None
        for pr in prior:
            same_moment = (
                pr["stream_id"] == cv["stream_id"]
                and overlap_s((pr["start_s"], pr["end_s"]), (cv["start_s"], cv["end_s"])) > 5
            )
            same_video = is_duplicate(pr["phash"], cv["phash"])
            if pr["account_id"] == t["account_id"] and (same_moment or same_video):
                dup_reason = f"already posted to account {t['account_id']} (clip_version {pr['cvid']})"
                break
            if pr["account_id"] != t["account_id"] and pr["channel_id"] != cv["channel_id"] and same_video:
                dup_reason = f"same video already on {t['platform']} for another brand"
                break
            if pr["account_id"] != t["account_id"] and pr["channel_id"] != cv["channel_id"] and same_moment:
                hook_a = (pr["packaging"] or {}).get("hook_text") or ""
                hook_b = (cv["packaging"] or {}).get("hook_text") or ""
                distinct = hook_a != hook_b and abs((pr["duration_s"] or 0) - (cv["duration_s"] or 0)) > 2
                if not distinct:
                    dup_reason = "same moment on another brand without a distinct edit"
                    break
        if dup_reason:
            _record(d, "duplicate", False, dup_reason)
            continue
        kept.append(t)
    d.targets = kept
    _record(d, "duplicate_summary", bool(kept), f"{len(kept)} target accounts remain after duplicate checks")
    if not kept:
        d.status = "rejected"
        return d
    # 5 originality layer
    tr = set(plan.get("transformations", []))
    base = {"hook_text", "captions", "credit"}
    extra = tr - base
    if not _record(d, "originality", base <= tr and bool(extra), f"transformations: {sorted(tr)}"):
        d.status = "rebuild"
        return d
    # 6 music risk: mute <= 2 s of flagged spans, else reject. Exception (doc 07): the song is the subject
    if cv.get("music_subject"):
        allowed = music_subject_platforms(c)
        d.targets = [t for t in d.targets if t["platform"] in allowed]
        _record(
            d,
            "music_risk",
            bool(d.targets),
            f"music is the subject: song kept; routed to {sorted({t['platform'] for t in d.targets})}",
        )
        if not d.targets:
            d.status = "rejected"
            return d
        risk_spans = []
    else:
        risk_spans = None
    if risk_spans is None:
        risk_spans = [tuple(s) for s in ((cv["audio"] or {}).get("risk_spans") or [])]
    in_clip = []
    for a, b in risk_spans:
        for seg in plan.get("segments", []):
            o = overlap_s((a, b), (seg["start"], seg["end"]))
            if o > 0:
                in_clip.append((max(a, seg["start"]), min(b, seg["end"])))
    total = sum(b - a for a, b in in_clip)
    if total > MUTE_MAX_S:
        _record(d, "music_risk", False, f"{total:.1f}s of residual music in clip")
        d.status = "rejected"
        return d
    if not cv.get("music_subject"):
        _record(d, "music_risk", True, f"{total:.1f}s residual music" + (" (muted)" if total else ""))
    d.mute_spans = in_clip
    # 7 platform fit: drop platforms whose limits this version misses
    fit = []
    for t in d.targets:
        spec = PLATFORM_SPECS[t["platform"]]
        if spec["min_s"] <= (cv["duration_s"] or 0) <= spec["max_s"]:
            fit.append(t)
        else:
            _record(
                d,
                "platform_fit",
                False,
                f"{t['platform']}: {cv['duration_s']:.1f}s outside {spec['min_s']}-{spec['max_s']}s",
            )
    d.targets = fit
    if not _record(d, "platform_fit_summary", bool(fit), f"{len(fit)} targets fit platform limits"):
        d.status = "rejected"
        return d
    # 9 safety
    pk = cv["packaging"] or {}
    if not _record(
        d, "safety", pk.get("safe", True), "text fields clean" if pk.get("safe", True) else "unsafe text"
    ):
        d.status = "rejected"
        return d
    return d


MUSIC_SUBJECT_PLATFORMS = ["snapchat", "tiktok", "instagram", "facebook", "youtube"]
BLOCK_KINDS = ("blocked", "muted", "copyright", "claim", "removed")


def music_subject_platforms(c: psycopg.Connection, window: int = 5, max_blocked: int = 3) -> set[str]:
    """Platforms that take music-subject clips (doc 07): those that tag licensed music, plus YouTube where a claim is
    accepted; a platform drops out once >= 3 of its last 5 music-subject posts were blocked, muted or claimed."""
    out = set()
    for p in MUSIC_SUBJECT_PLATFORMS:
        rows = db.all_(
            c,
            """SELECT EXISTS (SELECT 1 FROM claim k WHERE k.post_id=po.id AND k.kind = ANY(%s)) blocked
               FROM post po JOIN clip_version cv ON cv.id=po.clip_version_id JOIN clip cl ON cl.id=cv.clip_id
               WHERE cl.music_subject AND po.platform=%s AND po.status IN ('live','posted','removed','blocked')
               ORDER BY po.id DESC LIMIT %s""",
            list(BLOCK_KINDS),
            p,
            window,
        )
        if sum(r["blocked"] for r in rows) < max_blocked:
            out.add(p)
    return out


def persist(c: psycopg.Connection, clip_version_id: int, d: Decision) -> None:
    for name, ok, reason in d.results:
        c.execute(
            "INSERT INTO gate_result(clip_version_id,check_name,passed,reason) VALUES (%s,%s,%s,%s)",
            (clip_version_id, name, ok, reason),
        )
    status = {
        "queued": "queued",
        "rejected": "rejected",
        "rebuild": "needs_rebuild",
        "rerender": "needs_rerender",
    }[d.status]
    c.execute(
        "UPDATE clip_version SET status=%s, targets=%s WHERE id=%s",
        (status, db.j(d.targets), clip_version_id),
    )
    if d.status == "rerender":
        c.execute("UPDATE clip_version SET rerenders=rerenders+1 WHERE id=%s", (clip_version_id,))


def candidates_for(c: psycopg.Connection, clip_version_id: int) -> list[dict]:
    """Accounts of the clip's channel, active and connected, for platforms this version is meant for."""
    cv = db.one(
        c,
        "SELECT cv.version_type, cl.channel_id FROM clip_version cv JOIN clip cl ON cl.id=cv.clip_id WHERE cv.id=%s",
        clip_version_id,
    )
    plats = {
        "short": ["youtube", "instagram", "facebook", "threads", "snapchat", "tiktok"],
        "long": ["tiktok"],
    }.get(cv["version_type"], [])
    rows = db.all_(
        c,
        """SELECT a.id account_id, a.platform, a.channel_id FROM account a JOIN channel ch ON ch.id=a.channel_id
                         WHERE a.channel_id=%s AND a.platform = ANY(%s) AND a.status IN ('connected','verified') AND NOT ch.paused
                         AND (a.paused_until IS NULL OR a.paused_until < now())""",
        cv["channel_id"],
        plats,
    )
    return [dict(r) for r in rows]


def gate(c: psycopg.Connection, clip_version_id: int) -> Decision:
    d = evaluate(c, clip_version_id, candidates_for(c, clip_version_id))
    persist(c, clip_version_id, d)
    return d


_ = config
