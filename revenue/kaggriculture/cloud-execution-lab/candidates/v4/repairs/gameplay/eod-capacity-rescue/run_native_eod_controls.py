# SPDX-License-Identifier: Apache-2.0
"""Run this packet's behavioral negative controls in isolated Python processes."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

MUTANTS = ("disabled", "stale-queue", "fallback-on", "after-receipts", "partial-budget", "legacy-import")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--h3c", type=Path, required=True)
    args = parser.parse_args()
    command = [sys.executable] + ([] if __debug__ else ["-O"])
    command += [str(Path(__file__).with_name("test_native_eod.py")),
                "--package", str(args.package), "--donor", str(args.donor), "--h3c", str(args.h3c)]
    controls = []
    for name in (None, *MUTANTS):
        cmd = command + ([] if name is None else ["--mutant", name])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        # Setup failure cannot masquerade as a killed mutant. Each variant
        # must finish all tests and trip its designated behavioral assertion;
        # the legacy-import control explicitly expects a runtime import error.
        try:
            summary = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            summary = {}
        complete = summary.get("tests") == 20
        passed = complete and result.returncode == 0 and summary.get("ok") is True
        witnesses = {"disabled": "FAIL: test_06_", "stale-queue": "FAIL: test_10_",
                     "fallback-on": "FAIL: test_09_", "after-receipts": "FAIL: test_11_",
                     "partial-budget": "FAIL: test_07_", "legacy-import": "ERROR: test_06_"}
        detecting = witnesses.get(name)
        killed = (complete and result.returncode == 1 and summary.get("ok") is False
                  and detecting is not None and detecting in result.stderr)
        valid = passed if name is None else killed
        controls.append({"name": name or "unmodified", "valid": valid,
                         "returncode": result.returncode, "tests": summary.get("tests"),
                         "required_witness": detecting,
                         "assertion_or_error_report": [line for line in result.stderr.splitlines()
                          if line.startswith(("FAIL:", "ERROR:"))]})
    receipt = {"optimized": not __debug__, "ok": all(x["valid"] for x in controls),
               "controls": controls}
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
