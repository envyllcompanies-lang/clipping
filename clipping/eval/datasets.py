"""Dataset manifests (doc 30): eval/datasets/<name>/<version>/manifest.json + data files with checksums."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from clipping.eval.harness import DATASETS


def write(name: str, version: str, files: dict[str, object], meta: dict) -> Path:
    d = DATASETS / name / version
    d.mkdir(parents=True, exist_ok=True)
    sums = {}
    for fname, obj in files.items():
        p = d / fname
        data = obj if isinstance(obj, bytes) else json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode()
        p.write_bytes(data)
        sums[fname] = hashlib.sha256(data).hexdigest()
    manifest = dict(meta, name=name, version=version, built_at=dt.date.today().isoformat(), files=sums)
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return d


def read(d: Path, fname: str) -> object:
    p = d / fname
    m = json.loads((d / "manifest.json").read_text())
    if hashlib.sha256(p.read_bytes()).hexdigest() != m["files"][fname]:
        raise ValueError(f"checksum mismatch for {p}")
    return json.loads(p.read_text())


def manifest(d: Path) -> dict:
    return json.loads((d / "manifest.json").read_text())
