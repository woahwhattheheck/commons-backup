#!/usr/bin/env python3
"""Replay the fixed fictional examples without modifying any input or report."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

if __package__:
    from . import checker
else:
    import checker

ROOT = Path(__file__).resolve().parent
CASES = (("parallel", "native", 0), ("inconsistent", "native", 1),
         ("unassigned", "native", 1), ("roadmap085", "roadmap085", 0))


def main() -> int:
    checked = 0
    for name, mode, expected in CASES:
        path = ROOT / "examples" / (name + ".json")
        raw = path.read_bytes()
        report = (checker.analyze(checker.loads(raw)) if mode == "native"
                  else checker.analyze_roadmap085(checker._decode(raw, allow_integers=True)))
        renderings = (("json", "json", json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"),
                      ("markdown", "md", checker.markdown(report)),
                      ("dot", "dot", checker.dot(report)))
        for fmt, extension, rendered in renderings:
            retained = ROOT / "sample_output" / (name + "." + extension)
            if retained.read_bytes() != rendered.encode("utf-8"):
                print(f"FAIL: retained output drift: {retained.relative_to(ROOT)}", file=sys.stderr)
                return 1
            flags = ["-O"] if sys.flags.optimize else []
            run = subprocess.run([sys.executable, *flags, str(ROOT / "checker.py"), str(path),
                                  "--input-format", mode, "--format", fmt],
                                 capture_output=True, text=True, timeout=15)
            if run.returncode != expected or run.stdout != rendered or run.stderr:
                print(f"FAIL: CLI {name}/{fmt}: expected exit {expected}, actual {run.returncode}", file=sys.stderr)
                print(run.stderr, file=sys.stderr)
                return 1
            checked += 1
        print(f"{name}: {report['dependency_check_status']}, exit {expected}, three exact report matches")
    print(f"PASS: {checked} retained report comparisons and {checked} actual CLI runs")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (checker.InputError, OSError, subprocess.TimeoutExpired) as error:
        print(f"example replay failed: {error}", file=sys.stderr)
        raise SystemExit(2)
