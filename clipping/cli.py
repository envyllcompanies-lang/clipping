"""`clip` command line."""

from __future__ import annotations

import argparse
import json
import sys


def cmd_db(a):
    from clipping.core import db

    if a.action == "migrate":
        db.migrate()
        print("schema up to date")


def cmd_eval(a):
    from clipping.eval import harness, synthetic

    if a.action == "build-synthetic":
        print("built:", ", ".join(synthetic.build_all(a.names or None)))
        return
    if a.action == "run":
        reps = harness.run_all(do_accept=a.accept) if a.all else [harness.run_stage(s, do_accept=a.accept) for s in a.stage]
        ok = True
        for r in reps:
            ok &= r.passed
            print(f"[{'PASS' if r.passed else 'FAIL'}] {r.stage} {harness.STAGE_NAMES.get(r.stage)}: " + ", ".join(
                f"{c.metric}={c.value:.4f}" + ("" if c.passed else f" ({c.reason})") for c in r.checks))
        sys.exit(0 if ok else 1)


def cmd_hw(a):
    from clipping.core import hardware

    print(json.dumps(hardware.profile().__dict__, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(prog="clip")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("db")
    d.add_argument("action", choices=["migrate"])
    d.set_defaults(fn=cmd_db)
    e = sub.add_parser("eval")
    e.add_argument("action", choices=["build-synthetic", "run"])
    e.add_argument("--stage", action="append", default=[])
    e.add_argument("--all", action="store_true")
    e.add_argument("--accept", action="store_true", help="store passing results as the new baseline")
    e.add_argument("names", nargs="*")
    e.set_defaults(fn=cmd_eval)
    h = sub.add_parser("hardware")
    h.set_defaults(fn=cmd_hw)
    from clipping import cli_ext

    cli_ext.register(sub)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
