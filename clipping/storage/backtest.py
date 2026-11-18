"""Stage backtest 21: a simulated week of renders/uploads; files vanish when refcount hits zero; disk stays flat."""

from __future__ import annotations

import datetime as dt

import numpy as np

from clipping.core import db
from clipping.eval.harness import Example, StageResult, scratch_db, stage
from clipping.storage import files, refcount

UTC = dt.UTC


@stage("21", "Storage Lifecycle")
def run() -> StageResult:
    rng = np.random.default_rng(21)
    ex = []
    with scratch_db() as c:
        cr = db.scalar(
            c, "INSERT INTO creator(platform,platform_id,handle) VALUES ('twitch','1','s') RETURNING id"
        )
        st = db.scalar(
            c,
            "INSERT INTO stream(creator_id,platform_stream_id,started_at) VALUES (%s,'x',now()) RETURNING id",
            cr,
        )
        usage, prompt, total_released = [], 0, 0
        live: list[tuple[int, int]] = []  # (clip_version_id, remaining posts)
        for _hour in range(24 * 7):
            for _ in range(rng.poisson(3)):  # new renders per hour
                mid = db.scalar(
                    c,
                    "INSERT INTO moment(stream_id,start_s,end_s,peak_s,score) VALUES (%s,0,1,0,1) RETURNING id",
                    st,
                )
                clip = db.scalar(c, "INSERT INTO clip(moment_id) VALUES (%s) RETURNING id", mid)
                p = files.managed("renders") / f"r{clip}.mp4"
                p.write_bytes(b"\0" * 2000)
                cv = db.scalar(
                    c,
                    "INSERT INTO clip_version(clip_id,version_type,path,status) VALUES (%s,'short',%s,'queued') RETURNING id",
                    clip,
                    str(p),
                )
                files.register(c, p, "render", "clip_version", cv)
                n = int(rng.integers(3, 7))
                refcount.set_pending(c, cv, n)
                live.append((cv, n))
            nxt = []
            for cv, n in live:  # uploads finishing this hour
                done = int(rng.binomial(n, 0.5))
                for _ in range(done):
                    left = refcount.post_finished(c, cv)
                    if left == 0:
                        total_released += 1
                        path = db.scalar(c, "SELECT path FROM clip_version WHERE id=%s", cv)
                        import os

                        if os.path.exists(path):
                            ex.append(
                                Example(
                                    f"cv{cv}", "deleted_promptly", 0, "file still present after last upload"
                                )
                            )
                        else:
                            prompt += 1
                if n - done > 0:
                    nxt.append((cv, n - done))
            live = nxt
            files.sweep(c)
            usage.append(sum(p.stat().st_size for p in files.managed("renders").glob("*")))
        stray = files.managed("work") / "stray.bin"
        stray.write_bytes(b"x")
        rec = files.reconcile(c)
    day2 = np.mean(usage[24:48])
    day7 = np.mean(usage[-24:])
    return StageResult(
        {
            "deleted_promptly": prompt / max(total_released, 1),
            "disk_growth_ratio": float(day7 / max(day2, 1)),
            "orphans_left": 0.0 if rec["removed_unknown"] == 1 else 1.0,
        },
        ex,
        "synthetic@v1",
        {"released": total_released},
    )
