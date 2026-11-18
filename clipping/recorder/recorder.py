"""Stream Recorder (doc 02): streamlink -> ffmpeg 60 s MPEG-TS segments (-c copy), rolling buffer, window extraction."""

from __future__ import annotations

import datetime as dt
import os
import shlex
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import psycopg

from clipping.core import config, db, media, settings
from clipping.storage import files

UTC = dt.UTC


def stream_url(platform: str, login: str) -> str:
    return {
        "twitch": f"https://www.twitch.tv/{login}",
        "kick": f"https://kick.com/{login}",
        "youtube": f"https://www.youtube.com/@{login}/live",
    }[platform]


def segment_dir(creator: str, stream_id: int) -> Path:
    return files.managed("recordings") / creator / str(stream_id)


def record_command(url: str, out_dir: Path, segment_s: int = 60, quality: str = "1080p60,1080p,best") -> str:
    """Shell pipeline. Segment names are the epoch second the segment opened ({creator}/{stream_id}/{epoch}.ts)."""
    ff = (
        f"ffmpeg -hide_banner -loglevel error -probesize 1M -analyzeduration 1000000 -i - -map 0 -c copy -f segment -segment_time {segment_s} "
        f"-segment_format mpegts -reset_timestamps 1 -strftime 1 {shlex.quote(str(out_dir))}/%s.ts"
    )
    sl = f"streamlink --stdout --retry-open 3 --hls-live-restart {shlex.quote(url)} {shlex.quote(quality)}"
    return f"{sl} | {ff}"


def acquire_lock(
    c: psycopg.Connection, creator_id: int, worker: str, stream_id: int | None, lease_s: int = 120
) -> bool:
    """One active worker per creator (lock row with lease)."""
    r = db.one(
        c,
        """INSERT INTO recorder_lock(creator_id,worker,stream_id,locked_until) VALUES (%s,%s,%s,now()+make_interval(secs=>%s))
                     ON CONFLICT (creator_id) DO UPDATE SET worker=EXCLUDED.worker, stream_id=EXCLUDED.stream_id,
                       locked_until=EXCLUDED.locked_until
                     WHERE recorder_lock.locked_until < now() OR recorder_lock.worker=EXCLUDED.worker RETURNING worker""",
        creator_id,
        worker,
        stream_id,
        lease_s,
    )
    return r is not None


def release_lock(c: psycopg.Connection, creator_id: int, worker: str) -> None:
    c.execute("DELETE FROM recorder_lock WHERE creator_id=%s AND worker=%s", (creator_id, worker))


def free_slots(c: psycopg.Connection) -> int:
    used = db.scalar(c, "SELECT count(*) FROM recorder_lock WHERE locked_until > now()")
    return max(0, config.settings()["recorder"]["slots"] - used)


def start_stream(
    c: psycopg.Connection,
    creator_id: int,
    platform_stream_id: str,
    started_at: dt.datetime | None = None,
    language: str | None = None,
) -> int:
    return db.scalar(
        c,
        """INSERT INTO stream(creator_id,platform_stream_id,started_at,language) VALUES (%s,%s,%s,%s)
                           ON CONFLICT (creator_id,platform_stream_id) DO UPDATE SET status=CASE WHEN stream.status='ended'
                             THEN stream.status ELSE 'recording' END RETURNING id""",
        creator_id,
        platform_stream_id,
        started_at or dt.datetime.now(UTC),
        language,
    )


def register_segments(
    c: psycopg.Connection, stream_id: int, seg_dir: Path, include_last: bool = False
) -> int:
    """Record finished segments (all but the one still being written) in `segment` and `file`."""
    known = {r["path"] for r in db.all_(c, "SELECT path FROM segment WHERE stream_id=%s", stream_id)}
    segs = sorted(seg_dir.glob("*.ts"), key=lambda p: int(p.stem))
    if not include_last:
        segs = segs[:-1]
    n = 0
    buf_h = config.settings()["recorder"]["buffer_hours"]
    for p in segs:
        if str(p) in known:
            continue
        try:
            dur = media.duration(p)
        except Exception:  # noqa: BLE001 - truncated segment from a crash: still usable, probe later
            continue
        start = dt.datetime.fromtimestamp(int(p.stem), UTC)
        end = start + dt.timedelta(seconds=dur)
        size = p.stat().st_size
        c.execute(
            "INSERT INTO segment(stream_id,path,start_utc,end_utc,size) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (stream_id, str(p), start, end, size),
        )
        files.register(c, p, "segment", "stream", stream_id, expires_at=end + dt.timedelta(hours=buf_h))
        n += 1
    return n


def covering_segments(
    c: psycopg.Connection, stream_id: int, start: dt.datetime, end: dt.datetime
) -> list[dict]:
    return db.all_(
        c,
        """SELECT * FROM segment WHERE stream_id=%s AND NOT deleted AND end_utc > %s AND start_utc < %s
                         ORDER BY start_utc""",
        stream_id,
        start,
        end,
    )


def extract_window(c: psycopg.Connection, window_id: int) -> dict:
    """Concatenate covering segments (+padding) into one window file, -c copy, no re-encode.

    Window start_utc/end_utc are set to the exact UTC span of the copied segments, so timestamps inside the window
    map exactly to stream time.
    """
    w = db.one(
        c,
        """SELECT w.*, m.stream_id, s.started_at FROM "window" w JOIN moment m ON m.id=w.moment_id
                     JOIN stream s ON s.id=m.stream_id WHERE w.id=%s""",
        window_id,
    )
    m = db.one(c, "SELECT * FROM moment WHERE id=%s", w["moment_id"])
    pad = config.settings()["recorder"]["window_pad_s"]
    want_start = w["start_utc"] or (w["started_at"] + dt.timedelta(seconds=m["start_s"]))
    want_end = w["end_utc"] or (w["started_at"] + dt.timedelta(seconds=m["end_s"]))
    segs = covering_segments(
        c, w["stream_id"], want_start - dt.timedelta(seconds=pad), want_end + dt.timedelta(seconds=pad)
    )
    if not segs:
        c.execute("""UPDATE "window" SET status='unrecoverable' WHERE id=%s""", (window_id,))
        return {"status": "unrecoverable"}
    out = files.managed("windows") / f"w{window_id}.ts"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as lst:
        for s in segs:
            lst.write(f"file '{s['path']}'\n")
    tmp = out.with_suffix(".part.ts")
    media.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            lst.name,
            "-map",
            "0",
            "-c",
            "copy",
            "-f",
            "mpegts",
            str(tmp),
        ]
    )
    os.unlink(lst.name)
    os.replace(tmp, out)
    start, end = segs[0]["start_utc"], segs[-1]["end_utc"]
    c.execute(
        """UPDATE "window" SET path=%s, start_utc=%s, end_utc=%s, status='extracted' WHERE id=%s""",
        (str(out), start, end, window_id),
    )
    files.register(
        c, out, "window", "window", window_id, expires_at=dt.datetime.now(UTC) + dt.timedelta(hours=48)
    )
    return {
        "status": "extracted",
        "path": str(out),
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
    }


def prune(c: psycopg.Connection, now: dt.datetime | None = None) -> int:
    """Delete segments past the buffer age that no pending window touches; ended streams after the grace period."""
    cfg = config.settings()["recorder"]
    now = now or dt.datetime.now(UTC)
    cutoff = now - dt.timedelta(hours=cfg["buffer_hours"])
    grace = now - dt.timedelta(hours=cfg["end_grace_h"])
    rows = db.all_(
        c,
        """
        SELECT sg.id, sg.path FROM segment sg JOIN stream st ON st.id=sg.stream_id
        WHERE NOT sg.deleted AND (sg.end_utc < %s OR (st.status='ended' AND st.ended_at < %s))
          AND NOT EXISTS (
            SELECT 1 FROM "window" w JOIN moment m ON m.id=w.moment_id
            WHERE m.stream_id=sg.stream_id AND w.status='requested'
              AND sg.end_utc > COALESCE(w.start_utc, st.started_at + make_interval(secs => m.start_s)) - interval '30 seconds'
              AND sg.start_utc < COALESCE(w.end_utc, st.started_at + make_interval(secs => m.end_s)) + interval '30 seconds')""",
        cutoff,
        grace,
    )
    for r in rows:
        files.delete_path(c, r["path"])
        c.execute("UPDATE segment SET deleted=true WHERE id=%s", (r["id"],))
    return len(rows)


def end_stream(c: psycopg.Connection, stream_id: int, at: dt.datetime | None = None) -> None:
    c.execute(
        "UPDATE stream SET status='ended', ended_at=%s WHERE id=%s AND status<>'ended'",
        (at or dt.datetime.now(UTC), stream_id),
    )


class Worker:
    """Runs one stream's recording; restarts the pipeline within 10 s on drops and logs gaps."""

    def __init__(self, c: psycopg.Connection, creator: dict, stream_id: int, command: str | None = None):
        self.c, self.creator, self.stream_id = c, creator, stream_id
        self.worker = f"{socket.gethostname()}:{os.getpid()}:{creator['id']}"
        self.dir = segment_dir(creator["handle"], stream_id)
        self.dir.mkdir(parents=True, exist_ok=True)
        cfg = config.settings()["recorder"]
        self.command = command or record_command(
            stream_url(creator["platform"], creator["handle"]), self.dir, cfg["segment_s"], cfg["quality"]
        )
        self.proc: subprocess.Popen | None = None
        self.stop_requested = False

    def _spawn(self) -> None:
        self.proc = subprocess.Popen(
            self.command,
            shell=True,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    def stop(self) -> None:
        self.stop_requested = True
        if self.proc and self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGINT)
            try:
                self.proc.wait(15)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)

    def run(self, is_live=lambda: True, poll_s: float = 5.0, max_seconds: float | None = None) -> None:
        if not acquire_lock(self.c, self.creator["id"], self.worker, self.stream_id):
            return  # another worker already records this creator
        t0 = time.time()
        gap_id = None
        restart_delay = config.settings()["recorder"]["restart_delay_s"]
        try:
            self._spawn()
            while not self.stop_requested:
                time.sleep(poll_s)
                acquire_lock(self.c, self.creator["id"], self.worker, self.stream_id)
                register_segments(self.c, self.stream_id, self.dir)
                if max_seconds and time.time() - t0 > max_seconds:
                    break
                if self.proc.poll() is not None:
                    if not is_live():
                        break
                    if gap_id is None:
                        gap_id = db.scalar(
                            self.c,
                            "INSERT INTO stream_gap(stream_id,gap_start) VALUES (%s,now()) RETURNING id",
                            self.stream_id,
                        )
                    time.sleep(min(restart_delay, poll_s))
                    self._spawn()
                elif gap_id is not None:
                    self.c.execute("UPDATE stream_gap SET gap_end=now() WHERE id=%s", (gap_id,))
                    gap_id = None
        finally:
            self.stop()
            register_segments(self.c, self.stream_id, self.dir, include_last=True)
            end_stream(self.c, self.stream_id)
            release_lock(self.c, self.creator["id"], self.worker)


def recover_on_restart(c: psycopg.Connection) -> list[int]:
    """After a crash: re-register segments on disk for streams still marked recording; return those stream ids."""
    out = []
    for r in db.all_(
        c,
        """SELECT s.id, cr.handle FROM stream s JOIN creator cr ON cr.id=s.creator_id WHERE s.status='recording'""",
    ):
        d = segment_dir(r["handle"], r["id"])
        if d.exists():
            register_segments(c, r["id"], d, include_last=True)
        out.append(r["id"])
    return out


def disk_ok_to_record() -> bool:
    from clipping.storage import guard

    return guard.level(guard.disk_status(settings.data_dir()), role="server") in ("normal", "low")
