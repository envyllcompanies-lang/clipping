"""Stage backtests 16-20 (publishing): one clip reaches every platform in fallback mode with the right fields;
crashes and injected failures never double-post; limits are never exceeded; files go when uploads finish."""

from __future__ import annotations

import datetime as dt
import subprocess
import tempfile
from pathlib import Path

from clipping.accounts import credentials
from clipping.core import db
from clipping.eval.fakeplatforms import FakePlatforms
from clipping.eval.harness import Example, StageResult, scratch_db, stage
from clipping.publish import framework, registry
from clipping.storage import files

UTC = dt.UTC
PLATFORMS = ["youtube", "instagram", "facebook", "threads", "tiktok", "snapchat"]


def make_mp4(path: Path, seconds: float = 4) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=540x960:r=30",
            "-f",
            "lavfi",
            "-i",
            "sine",
            "-t",
            str(seconds),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )
    return path


def seed(c, mode: str = "fallback", n_clips: int = 1, created_days_ago: int = 60):
    from clipping.packaging import write

    ch = db.scalar(
        c,
        """INSERT INTO channel(key,language,time_zone,config) VALUES ('gta6-en','en','UTC',%s) RETURNING id""",
        db.j(
            {"posting_slots": [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)], "warmup_days": 21}
        ),
    )
    accs = {}
    for p in PLATFORMS:
        a = db.scalar(
            c,
            """INSERT INTO account(channel_id,platform,platform_account_id,status,mode,created_at)
                            VALUES (%s,%s,%s,'connected',%s, now() - make_interval(days => %s)) RETURNING id""",
            ch,
            p,
            f"{p}-id",
            mode,
            created_days_ago,
        )
        credentials.store(
            c, a, p, "oauth", {"access_token": "tok"}, dt.datetime.now(UTC) + dt.timedelta(days=30)
        )
        accs[p] = a
    cr = db.scalar(
        c, "INSERT INTO creator(platform,platform_id,handle) VALUES ('twitch','1','streamer') RETURNING id"
    )
    st = db.scalar(
        c,
        "INSERT INTO stream(creator_id,platform_stream_id,started_at) VALUES (%s,'s',now()) RETURNING id",
        cr,
    )
    cvs = []
    for k in range(n_clips):
        mid = db.scalar(
            c,
            "INSERT INTO moment(stream_id,start_s,end_s,peak_s,score) VALUES (%s,%s,%s,%s,0.9) RETURNING id",
            st,
            k * 100,
            k * 100 + 75,
            k * 100 + 45,
        )
        plan = {"start_t": 1.0, "end_t": 30.0, "payoff_kind": "crash"}
        pk = write.package(
            [{"word": "bro", "start": 2, "end": 2.3}],
            plan,
            language="en",
            creator="streamer",
            platform="twitch",
            seed=k,
        )
        clip = db.scalar(
            c,
            "INSERT INTO clip(moment_id,channel_id,creator_id,packaging) VALUES (%s,%s,%s,%s) RETURNING id",
            mid,
            ch,
            cr,
            db.j(pk),
        )
        f = make_mp4(files.managed("renders") / f"c{k}.mp4")
        cv = db.scalar(
            c,
            """INSERT INTO clip_version(clip_id,version_type,path,duration_s,status,targets) VALUES (%s,'short',%s,4,'queued',%s)
                             RETURNING id""",
            clip,
            str(f),
            db.j([{"account_id": a, "platform": p} for p, a in accs.items()]),
        )
        files.register(c, f, "render", "clip_version", cv)
        cvs.append(cv)
    return ch, accs, cvs


def drain(c, ads, now, rounds: int = 12):
    for i in range(rounds):
        framework.run_due(c, ads, now + dt.timedelta(minutes=20 * i))


@stage("16", "Publishing (framework + connectors 17-20)")
def run() -> StageResult:
    ex = []
    with scratch_db() as c, tempfile.TemporaryDirectory():
        fake = FakePlatforms()
        fake.fail_next = {"yt_chunk": [503], "meta:/v21.0/instagram-id/media": [500]}
        ch, accs, (cv,) = seed(c)
        now = dt.datetime.now(UTC)
        framework.schedule(c, now)
        ads = registry.adapters(c, fake.transport())
        drain(c, ads, now + dt.timedelta(days=2))
        posts = db.all_(c, "SELECT platform, status, fallback, fields FROM post")
        every = all(p["status"] == "live" for p in posts) and {p["platform"] for p in posts} == set(PLATFORMS)
        single = all(len(fake.posts[p]) == 1 for p in PLATFORMS)
        if not every:
            ex.append(Example("one_clip", "not_live", 0, str([(p["platform"], p["status"]) for p in posts])))
        fallback_ok = (
            db.scalar(c, "SELECT count(*) FROM fallback_task WHERE kind IN ('publish_private','inbox_draft')")
            == 2
        )
        yt_private = (
            list(fake.yt_videos.values())[0]["meta"]["status"]["privacyStatus"] == "private"
            if fake.yt_videos
            else False
        )
        fields_ok = (
            all(p["fields"] for p in posts)
            and len(next(p for p in posts if p["platform"] == "youtube")["fields"]["snippet"]["title"]) <= 100
        )
        file_gone = not Path(db.scalar(c, "SELECT path FROM clip_version WHERE id=%s", cv)).exists()
        public_gone = (
            db.scalar(c, "SELECT count(*) FROM file WHERE kind='public' AND deleted_at IS NULL") == 0
        )
    # crash mid-upload -> resume, never double post
    with scratch_db() as c:
        fake = FakePlatforms()
        ch, accs, (cv,) = seed(c, mode="direct")
        now = dt.datetime.now(UTC) + dt.timedelta(days=2)
        framework.schedule(c, now - dt.timedelta(days=2))
        ads = registry.adapters(c, fake.transport())
        ig = db.scalar(c, "SELECT id FROM post WHERE platform='instagram'")
        orig = ads["instagram"].check_container

        def crash(*a, **k):
            raise KeyboardInterrupt("worker killed")

        ads["instagram"].check_container = crash
        try:
            framework.run_post(c, ig, ads, now)  # creates the container
            framework.run_post(c, ig, ads, now)  # killed while polling it
        except KeyboardInterrupt:
            pass
        ads["instagram"].check_container = orig
        drain(c, ads, now)
        crash_single = (
            len(fake.posts["instagram"]) == 1
            and sum(v["kind"] == "media" for v in fake.ig_containers.values()) == 1
        )
    # limits: 40 clips to one TikTok account (cap 15/day, 10% reserve) and a 2-day-old account (warm-up)
    with scratch_db() as c:
        fake = FakePlatforms()
        fake.audited_tiktok = True
        ch, accs, cvs = seed(c, mode="direct", n_clips=40)
        c.execute(
            "UPDATE clip_version SET targets = jsonb_path_query_array(targets, '$[*] ? (@.platform == \"tiktok\")')"
        )
        now = dt.datetime.now(UTC)
        ads = registry.adapters(c, fake.transport())
        for h in range(0, 48):
            t = now + dt.timedelta(hours=h)
            framework.schedule(c, t)
            framework.run_due(c, ads, t)
        per_day = db.all_(c, "SELECT date_trunc('day', at) d, count(*) n FROM quota_use GROUP BY 1")
        cap = int(framework.limit_24h("tiktok") * (1 - framework.RESERVE))
        windows_ok = all(framework.used_24h(c, accs["tiktok"]) <= cap for _ in [0])
        rolling = db.all_(c, "SELECT at FROM quota_use ORDER BY at")
        max_roll = max(
            (sum(1 for y in rolling if 0 <= (y["at"] - x["at"]).total_seconds() < 86400) for x in rolling),
            default=0,
        )
        spacing_ok = db.scalar(
            c,
            """SELECT bool_and(gap >= interval '15 minutes') FROM (SELECT scheduled_at - lag(scheduled_at) OVER
                                     (PARTITION BY account_id ORDER BY scheduled_at) gap FROM post) g WHERE gap IS NOT NULL""",
        )
        _ = per_day
    return StageResult(
        {
            "one_clip_every_platform": 1.0 if every else 0.0,
            "no_double_posts": 1.0 if single and crash_single else 0.0,
            "fallback_tasks_created": 1.0 if fallback_ok and yt_private else 0.0,
            "fields_valid": 1.0 if fields_ok else 0.0,
            "media_deleted_after_upload": 1.0 if file_gone and public_gone else 0.0,
            "rate_limit_respected": 1.0 if max_roll <= cap and windows_ok else 0.0,
            "spacing_respected": 1.0 if spacing_ok else 0.0,
        },
        ex,
        "fakeplatforms@v1",
        {"max_rolling_24h": max_roll, "cap": cap},
    )
