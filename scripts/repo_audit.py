"""License + activity audit of docs/repos.md (CLAUDE.md: check license and activity before reusing code).

Reads every GitHub link in docs/repos.md, looks each repo up through GitHub search (`gh api search/repositories`,
batched), and writes docs/repo-audit.md: license, last push, archived, stars and a reuse verdict.

  python scripts/repo_audit.py            # refresh docs/repo-audit.md
"""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "repos.md"
OUT = ROOT / "docs" / "repo-audit.md"

PERMISSIVE = {
    "mit",
    "bsd-2-clause",
    "bsd-3-clause",
    "apache-2.0",
    "isc",
    "0bsd",
    "unlicense",
    "zlib",
    "bsl-1.0",
    "cc0-1.0",
    "mpl-2.0",
    "python-2.0",
}
WEAK_COPYLEFT = {"lgpl-2.1", "lgpl-3.0"}
STRONG_COPYLEFT = {"gpl-2.0", "gpl-3.0"}
NETWORK_COPYLEFT = {"agpl-3.0"}
STALE_DAYS = 548  # ~18 months without a push

# GitHub search can't classify some license files (NOASSERTION), doesn't index forks, and misses renamed repos.
# These were checked by hand (PyPI metadata or the repo's license file); spdx, latest activity, source of the check.
OVERRIDES = {
    "ffmpeg/ffmpeg": (
        "LGPL-2.1-or-later",
        None,
        "license file; we only run the ffmpeg binary (separate process)",
    ),
    "acoustid/chromaprint": ("LGPL-2.1", None, "license file; fpcalc CLI as a separate process"),
    "slhck/ffmpeg-normalize": ("MIT", "2026-11-17", "PyPI"),
    "carpedm20/emoji": ("BSD-3-Clause", "2026-09-16", "PyPI"),
    "mlfoundations/open_clip": ("MIT", "2026-11-10", "PyPI open-clip-torch"),
    "tensorflow/models": ("Apache-2.0", None, "license file"),
    "youtube/api-samples": ("Apache-2.0", None, "license file"),
    "pythonistaguild/twitchio": ("MIT", "2026-08-04", "PyPI twitchio (repo link not indexed)"),
    "xenova/chat-replay-downloader": (
        "MIT",
        "2023-09-03",
        "superseded by xenova/chat-downloader (PyPI chat-downloader)",
    ),
    "adefossez/demucs": ("MIT", "2026-07-11", "PyPI demucs 4.1.0 (maintained fork; forks aren't searchable)"),
    "johannesbuchner/imagehash": ("BSD-2-Clause", "2025-02-01", "PyPI imagehash (already a dependency)"),
    "blaizzy/mlx-vlm": ("MIT", "2026-11-16", "PyPI mlx-vlm"),
    "facebook/facebook-python-business-sdk": (
        "Meta platform license",
        "2026-11-19",
        "PyPI facebook-business; custom license: use as dependency only",
    ),
    "microsoft/lightgbm": ("MIT", "2026-07-18", "PyPI lightgbm 4.7.0"),
}


def repos() -> list[tuple[str, str]]:
    """(owner/name, section) for every GitHub repo link, in document order, deduplicated."""
    out, section, seen = [], "", set()
    for line in SRC.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        for m in re.finditer(r"github\.com/([\w.-]+/[\w.-]+)", line):
            name = m.group(1).rstrip(".")
            if name.lower() not in seen:
                seen.add(name.lower())
                out.append((name, section))
    return out


def lookup(names: list[str]) -> dict[str, dict]:
    q = " ".join(f"repo:{n}" for n in names)
    for attempt in range(5):
        r = subprocess.run(
            ["gh", "api", "-X", "GET", "search/repositories", "-f", f"q={q}", "-f", "per_page=100"],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            items = json.loads(r.stdout).get("items", [])
            return {i["full_name"].lower(): i for i in items}
        if "rate limit" in (r.stderr + r.stdout).lower() or "403" in r.stderr:
            time.sleep(20 * (attempt + 1))
            continue
        sys.stderr.write(r.stderr)
        time.sleep(5)
    return {}


def verdict(item: dict | None, now: dt.datetime, name: str = "") -> tuple[str, str]:
    ov = OVERRIDES.get(name.lower())
    if ov:
        lic, last, src = ov
        sp = lic.lower().replace("-or-later", "").replace("-only", "")
        v = (
            "reuse ok"
            if sp in PERMISSIVE
            else "use as dependency"
            if sp in WEAK_COPYLEFT or "meta" in sp
            else "separate process/CLI only"
            if sp in STRONG_COPYLEFT
            else "study only"
        )
        notes = [f"checked: {src}"]
        if last and (now - dt.datetime.fromisoformat(last + "T00:00:00+00:00")).days > STALE_DAYS:
            notes.append("no release in 18+ months")
            v = "reuse with care" if v == "reuse ok" else v
        return v, ", ".join(notes)
    if item is None:
        return "not found", "check manually (renamed, private or not indexed)"
    lic = ((item.get("license") or {}).get("spdx_id") or "NOASSERTION").lower()
    pushed = dt.datetime.fromisoformat(item["pushed_at"].replace("Z", "+00:00"))
    stale = (now - pushed).days > STALE_DAYS
    notes = []
    if item.get("archived"):
        notes.append("archived")
    if stale:
        notes.append(f"no push in {(now - pushed).days // 30} months")
    if lic in PERMISSIVE:
        v = "reuse ok"
    elif lic in WEAK_COPYLEFT:
        v = "use as dependency"
    elif lic in STRONG_COPYLEFT:
        v = "separate process/CLI only"
    elif lic in NETWORK_COPYLEFT:
        v = "study only"
    else:
        v = "study only"
        notes.append("no recognised license")
    if (item.get("archived") or stale) and v == "reuse ok":
        v = "reuse with care"
    return v, ", ".join(notes)


def main() -> None:
    rs = repos()
    names = [n for n, _ in rs]
    found: dict[str, dict] = {}
    for i in range(0, len(names), 8):  # search allows a handful of qualifiers per query; ~10 queries/min
        found |= lookup(names[i : i + 8])
        time.sleep(7)
    now = dt.datetime.now(dt.UTC)
    rows = []
    for name, section in rs:
        it = found.get(name.lower())
        v, notes = verdict(it, now, name)
        ov = OVERRIDES.get(name.lower())
        lic = ov[0] if ov else ((it or {}).get("license") or {}).get("spdx_id") or ("?" if it else "-")
        pushed = (it or {}).get("pushed_at", "")[:10] or (ov[1] if ov and ov[1] else "-")
        stars = (it or {}).get("stargazers_count", "-")
        rows.append(
            f"| {section.split(' (')[0]} | [{name}](https://github.com/{name}) | {lic} | {pushed} | {stars} | {v} | {notes} |"
        )
    OUT.write_text(
        "# Repo audit (license + activity)\n\n"
        f"Generated {now.date()} by `scripts/repo_audit.py` from [repos.md](repos.md) via GitHub search. "
        "Verdicts: **reuse ok** = permissive license, active; **reuse with care** = permissive but archived or no push in "
        "18+ months; **use as dependency** = LGPL (link, don't copy); **separate process/CLI only** = GPL (call the tool, "
        "never import or copy its code); **study only** = AGPL or no license (read for ideas, write our own).\n\n"
        "| Stage | Repo | License | Last push | Stars | Verdict | Notes |\n| --- | --- | --- | --- | --- | --- | --- |\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {OUT.relative_to(ROOT)}: {len(rows)} repos, {sum(1 for n, _ in rs if n.lower() in found)} found"
    )


if __name__ == "__main__":
    main()
