"""Stage backtest 15: seeded duplicates caught (>= 99%) with no false duplicates among distinct clips; every
decision has a stored reason; a repeat to the same account is rejected; blocklisting pulls clips everywhere."""

from __future__ import annotations

import itertools
import shlex
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from clipping.core import db
from clipping.eval import reframefx
from clipping.eval.harness import Example, StageResult, scratch_db, stage
from clipping.gate import checks, takedown
from clipping.render.engine import perceptual_hash

VARIANTS = [
    "-c:v libx264 -crf 35",  # heavy re-encode
    "-vf scale=iw*0.75:-2 -c:v libx264",  # lower resolution
    "-vf eq=brightness=0.06:contrast=1.1 -c:v libx264",  # color tweak
    "-vf crop=iw*0.94:ih*0.94,scale=640:360 -c:v libx264",  # light crop
    "-vf drawtext=fontfile=assets/fonts/Montserrat-ExtraBold.ttf:text='WAIT FOR IT':fontsize=28:fontcolor=yellow:x=(w-tw)/2:y=h*0.4 -c:v libx264",
]


def _clip(path: Path, seed: int) -> None:
    s = reframefx.stream(seed, seconds=6, fps=10, cam=seed % 2 == 0)
    fr = s["frames"]
    p = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            "640x360",
            "-r",
            "10",
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        stdin=subprocess.PIPE,
    )
    p.stdin.write(fr.tobytes())
    p.stdin.close()
    p.wait()


@stage("15", "Auto-Gate")
def run() -> StageResult:
    ex = []
    with tempfile.TemporaryDirectory() as d:
        base = []
        for k in range(16):
            p = Path(d) / f"b{k}.mp4"
            _clip(p, 1500 + k)
            base.append(perceptual_hash(p))
        caught = []
        for k, h in enumerate(base[:12]):
            for j, v in enumerate(VARIANTS):
                q = Path(d) / f"v{k}_{j}.mp4"
                subprocess.run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        str(Path(d) / f"b{k}.mp4"),
                        *shlex.split(v),
                        str(q),
                    ],
                    check=True,
                )
                hit = checks.is_duplicate(h, perceptual_hash(q))
                caught.append(hit)
                if not hit:
                    ex.append(
                        Example(
                            f"b{k}:variant{j}", "missed_dup", checks.phash_distance(h, perceptual_hash(q)), v
                        )
                    )
        false = []
        for a, b in itertools.combinations(range(16), 2):
            fp = checks.is_duplicate(base[a], base[b])
            false.append(fp)
            if fp:
                ex.append(Example(f"b{a}~b{b}", "false_dup", checks.phash_distance(base[a], base[b]), ""))
    # DB-level behaviour
    with scratch_db() as c:
        ch = db.scalar(
            c,
            "INSERT INTO channel(key,language,time_zone,score_floor) VALUES ('gta6-en','en','UTC',0.3) RETURNING id",
        )
        acc = db.scalar(
            c,
            "INSERT INTO account(channel_id,platform,status) VALUES (%s,'youtube','connected') RETURNING id",
            ch,
        )
        snap = db.scalar(
            c,
            "INSERT INTO account(channel_id,platform,status) VALUES (%s,'snapchat','connected') RETURNING id",
            ch,
        )
        cr = db.scalar(
            c, "INSERT INTO creator(platform,platform_id,handle) VALUES ('twitch','1','x') RETURNING id"
        )
        st = db.scalar(
            c,
            "INSERT INTO stream(creator_id,platform_stream_id,started_at) VALUES (%s,'s',now()) RETURNING id",
            cr,
        )
        plan = {
            "transformations": ["hook_text", "captions", "credit", "zooms"],
            "segments": [{"start": 0, "end": 30, "role": "body"}],
        }

        def make_cv(start_s, phash):
            mid = db.scalar(
                c,
                "INSERT INTO moment(stream_id,start_s,end_s,peak_s,score) VALUES (%s,%s,%s,%s,0.8) RETURNING id",
                st,
                start_s,
                start_s + 75,
                start_s + 45,
            )
            clip = db.scalar(
                c,
                "INSERT INTO clip(moment_id,channel_id,creator_id,edit_plan,packaging) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                mid,
                ch,
                cr,
                db.j({"versions": {"short": plan}}),
                db.j({"safe": True, "hook_text": "x"}),
            )
            return db.scalar(
                c,
                """INSERT INTO clip_version(clip_id,version_type,phash,duration_s,validation,status)
                                   VALUES (%s,'short',%s,30,%s,'rendered') RETURNING id""",
                clip,
                phash,
                db.j({"passed": True}),
            )

        cv1 = make_cv(100, base[0])
        d1 = checks.gate(c, cv1)
        for t in d1.targets:
            c.execute(
                "INSERT INTO post(clip_version_id,account_id,platform,status,scheduled_at) VALUES (%s,%s,%s,'live',now())",
                (cv1, t["account_id"], t["platform"]),
            )
        cv2 = make_cv(102, base[0])  # same moment, same video -> must not go to the same account
        d2 = checks.gate(c, cv2)
        reasons_ok = db.scalar(c, "SELECT bool_and(reason IS NOT NULL AND reason <> '') FROM gate_result")
        res = takedown.blocklist_creator(c, cr)
        pulled = db.scalar(c, "SELECT count(*) FROM post WHERE status IN ('scheduled','retry_wait')") == 0
        jobs_ok = (
            db.scalar(c, "SELECT count(*) FROM job WHERE type='post_delete'") == res["delete_jobs"]
            and res["manual_deletes"] == 1
        )
        _ = (acc, snap)
    return StageResult(
        {
            "duplicates_caught": float(np.mean(caught)),
            "false_duplicates": float(np.mean(false)),
            "repeat_to_same_account_blocked": 1.0 if d2.status == "rejected" else 0.0,
            "first_post_allowed": 1.0 if d1.status == "queued" and len(d1.targets) == 2 else 0.0,
            "decisions_have_reasons": 1.0 if reasons_ok else 0.0,
            "blocklist_pulls_everywhere": 1.0 if pulled and jobs_ok else 0.0,
        },
        ex,
        "seeded@v1",
    )
