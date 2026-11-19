"""Backtesting & evaluation harness (doc 30).

Each stage registers a function that replays its dataset and returns metrics plus worst examples. Results are
compared with eval/thresholds.yaml (absolute bars) and eval/baselines/<stage>.json (last accepted run). Any metric
that falls below its bar, or is worse than baseline by more than the tolerance, fails the run.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from clipping.core import config
from clipping.core.settings import ROOT

EVAL = ROOT / "eval"
DATASETS = EVAL / "datasets"
REPORTS = EVAL / "reports"
BASELINES = EVAL / "baselines"
TOLERANCE = 0.02


@dataclass
class Example:
    example_id: str
    metric: str
    value: float
    notes: str = ""


@dataclass
class StageResult:
    metrics: dict[str, float]
    examples: list[Example] = field(default_factory=list)
    dataset_version: str = ""
    info: dict = field(default_factory=dict)


@dataclass
class MetricCheck:
    metric: str
    value: float
    baseline: float | None
    bar: float | None
    direction: str
    passed: bool
    reason: str = ""


@dataclass
class RunReport:
    stage: str
    passed: bool
    checks: list[MetricCheck]
    result: StageResult
    seconds: float
    report_path: Path | None = None


STAGES: dict[str, Callable[[], StageResult]] = {}
STAGE_NAMES: dict[str, str] = {}


def stage(code: str, name: str):
    def deco(fn: Callable[[], StageResult]):
        STAGES[code] = fn
        STAGE_NAMES[code] = name
        return fn

    return deco


def thresholds() -> dict:
    return yaml.safe_load((EVAL / "thresholds.yaml").read_text())


def dataset_dir(name: str, version: str | None = None) -> Path:
    base = DATASETS / name
    if version is None:
        versions = sorted(p.name for p in base.iterdir() if p.is_dir())
        if not versions:
            raise FileNotFoundError(f"no versions for dataset {name}")
        version = versions[-1]
    return base / version


def load_baseline(code: str) -> dict | None:
    p = BASELINES / f"{code}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _worse(value: float, ref: float, direction: str, tol: float) -> bool:
    slack = max(abs(ref) * tol, 1e-9)
    return value < ref - slack if direction == "higher" else value > ref + slack


def evaluate(
    code: str, result: StageResult, baseline: dict | None, tol: float = TOLERANCE
) -> list[MetricCheck]:
    spec = thresholds().get(code, {})
    checks = []
    for metric, value in result.metrics.items():
        s = spec.get(metric, {})
        direction = s.get("direction", "higher")
        bar = s.get("bar")
        base = (baseline or {}).get("metrics", {}).get(metric)
        ok, reasons = True, []
        if bar is not None and (value < bar if direction == "higher" else value > bar):
            if s.get(
                "target_only"
            ):  # doc target not yet reachable on real data: reported, gated by baseline only
                reasons.append(f"below target {bar} (target only)")
            else:
                ok = False
                reasons.append(f"misses bar {bar}")
        if base is not None and _worse(value, base, direction, s.get("tolerance", tol)):
            ok = False
            reasons.append(f"worse than baseline {base:.4f}")
        checks.append(MetricCheck(metric, value, base, bar, direction, ok, "; ".join(reasons)))
    for metric in spec:
        if metric not in result.metrics and spec[metric].get("required", True):
            checks.append(
                MetricCheck(
                    metric, float("nan"), None, spec[metric].get("bar"), "higher", False, "metric missing"
                )
            )
    return checks


def code_version() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT
        ).stdout.strip()
    except OSError:
        return "unknown"


def write_report(rep: RunReport) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    day = dt.date.today().isoformat()
    base = REPORTS / f"{day}-{rep.stage}"
    data = {
        "stage": rep.stage,
        "name": STAGE_NAMES.get(rep.stage),
        "passed": rep.passed,
        "seconds": round(rep.seconds, 2),
        "dataset_version": rep.result.dataset_version,
        "code_version": code_version(),
        "metrics": [c.__dict__ for c in rep.checks],
        "worst_examples": [e.__dict__ for e in rep.result.examples[:25]],
        "info": rep.result.info,
    }
    base.with_suffix(".json").write_text(json.dumps(data, indent=2, default=str))
    lines = [
        f"# Backtest {rep.stage} — {STAGE_NAMES.get(rep.stage)} ({'PASS' if rep.passed else 'FAIL'})",
        "",
        f"Dataset `{rep.result.dataset_version}`, code `{data['code_version']}`, {rep.seconds:.1f}s",
        "",
        "| Metric | Value | Bar | Baseline | Result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c in rep.checks:
        bl = "—" if c.baseline is None else f"{c.baseline:.4f}"
        lines.append(
            f"| {c.metric} | {c.value:.4f} | {c.bar if c.bar is not None else '—'} | {bl} | {'ok' if c.passed else c.reason} |"
        )
    if rep.result.examples:
        lines += ["", "## Worst examples", ""]
        lines += [f"- `{e.example_id}` {e.metric}={e.value:.3f} {e.notes}" for e in rep.result.examples[:10]]
    base.with_suffix(".md").write_text("\n".join(lines) + "\n")
    return base.with_suffix(".json")


def record_db(rep: RunReport, kind: str = "stage") -> None:
    try:
        from clipping.core import db

        with db.conn() as c:
            run_id = db.scalar(
                c,
                """INSERT INTO eval_run(kind,stage,dataset_version,code_version,config_hash,finished_at,passed)
                      VALUES (%s,%s,%s,%s,%s,now(),%s) RETURNING id""",
                kind,
                rep.stage,
                rep.result.dataset_version,
                code_version(),
                config.config_hash(),
                rep.passed,
            )
            for ch in rep.checks:
                c.execute(
                    "INSERT INTO eval_metric VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (
                        run_id,
                        ch.metric,
                        None if ch.value != ch.value else ch.value,
                        ch.baseline,
                        ch.bar,
                        ch.passed,
                    ),
                )
            for e in rep.result.examples[:25]:
                c.execute(
                    "INSERT INTO eval_example(run_id,example_id,metric,value,notes) VALUES (%s,%s,%s,%s,%s)",
                    (run_id, e.example_id, e.metric, e.value, e.notes),
                )
    except Exception:  # noqa: BLE001 - harness must work offline without a database
        pass


def accept(rep: RunReport, note: str = "") -> None:
    """Store a passing run as the new baseline and log it in eval/CHANGELOG.md."""
    if not rep.passed:
        raise ValueError("refusing to accept a failing run as baseline")
    BASELINES.mkdir(parents=True, exist_ok=True)
    old = load_baseline(rep.stage)
    (BASELINES / f"{rep.stage}.json").write_text(
        json.dumps(
            {
                "stage": rep.stage,
                "accepted_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "dataset_version": rep.result.dataset_version,
                "code_version": code_version(),
                "metrics": rep.result.metrics,
            },
            indent=2,
        )
    )
    cl = EVAL / "CHANGELOG.md"
    if not cl.exists():
        cl.write_text("# Eval changelog\n\nAccepted baselines with before/after metrics.\n")
    before = (old or {}).get("metrics", {})
    parts = [
        f"{k} {before.get(k, float('nan')):.3f}→{v:.3f}" if k in before else f"{k} {v:.3f}"
        for k, v in rep.result.metrics.items()
    ]
    with cl.open("a") as f:
        f.write(
            f"\n- {dt.date.today()} stage {rep.stage} ({STAGE_NAMES.get(rep.stage)}): {', '.join(parts)}{' — ' + note if note else ''}\n"
        )


def run_stage(code: str, *, do_accept: bool = False, record: bool = True, note: str = "") -> RunReport:
    import clipping.eval.stages  # noqa: F401 - registers stages

    t0 = time.time()
    result = STAGES[code]()
    checks = evaluate(code, result, load_baseline(code))
    rep = RunReport(code, all(c.passed for c in checks), checks, result, time.time() - t0)
    rep.report_path = write_report(rep)
    if record:
        record_db(rep)
    if do_accept and rep.passed:
        accept(rep, note)
    return rep


def run_all(*, do_accept: bool = False, stages: list[str] | None = None) -> list[RunReport]:
    import clipping.eval.stages  # noqa: F401

    return [run_stage(c, do_accept=do_accept) for c in (stages or sorted(STAGES))]


def dsver(d: Path) -> str:
    return f"{d.parent.name}@{d.name}"


import contextlib  # noqa: E402


@contextlib.contextmanager
def scratch_db(name: str = "clipping_eval"):
    """Fresh schema in a throwaway database so backtests never touch production data."""
    import os
    import tempfile

    import psycopg

    from clipping.core import db

    base = db.url()
    admin = base.rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(admin, autocommit=True) as a:
        if not a.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
            a.execute(f'CREATE DATABASE "{name}"')
    url = base.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(url, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        db.migrate(c)
    old_url, old_dir = db._url_override, os.environ.get("CLIPPING_DATA_DIR")
    old_key = os.environ.get("TOKEN_ENCRYPTION_KEY")
    if not old_key:
        os.environ["TOKEN_ENCRYPTION_KEY"] = "backtest-only-throwaway-key"
    tmp = tempfile.mkdtemp(prefix="clipping-eval-")
    db.set_url(url)
    os.environ["CLIPPING_DATA_DIR"] = tmp
    try:
        with db.conn() as c:
            yield c
    finally:
        db.set_url(old_url)
        if not old_key:
            os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
        if old_dir is None:
            os.environ.pop("CLIPPING_DATA_DIR", None)
        else:
            os.environ["CLIPPING_DATA_DIR"] = old_dir
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
