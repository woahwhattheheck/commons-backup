# SPDX-License-Identifier: Apache-2.0
"""Run the same full authenticated suite against explicit behavioral mutants."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MUTATIONS = {
    "downstream-fill-theft": (
        'if any(final["outcomes"].get(i, {}).get("completed", 0) < old["completed"]',
        'if False and any(final["outcomes"].get(i, {}).get("completed", 0) < old["completed"]'),
    "unowned-stock": (
        'if any(q > private["shed"].get(item, 0) for item, q in totals.items()):',
        'if False and any(q > private["shed"].get(item, 0) for item, q in totals.items()):'),
    "budget-ignored": ('if visited >= budget:', 'if False:'),
    "source-pin-disabled": (
        'if hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest() != NATIVE_SHA256:',
        'if False:'),
    "suffix-admitted": ('prefix = orders[:cap]', 'prefix = orders'),
    "sale-not-debited": ('after = prefix[source][2] - moved', 'after = prefix[source][2]'),
    "default-on": ('enabled: bool = False', 'enabled: bool = True'),
    "maximum-movement": ('for total in range(2, sum(capacities) + 1):',
                         'for total in range(sum(capacities), 1, -1):'),
    "single-source-only": ('if candidate is None or len(moves) < 2:',
                           'if candidate is None or len(moves) != 1:'),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    source = (root / "funding_basket.py").read_text()
    # A red baseline is never mutation sensitivity evidence.
    for optimized in (False, True):
        cmd = [sys.executable] + (["-O"] if optimized else []) + [
            str(root / "test_funding_basket.py"), "--package", str(Path(args.package).resolve())]
        control = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        report = json.loads(control.stdout.strip().splitlines()[-1])
        if control.returncode or report["failures"] or report["errors"] or report["tests"] != 26:
            raise RuntimeError("unmodified control is not green; mutation experiment invalid")
    records = []
    for name, (before, after) in MUTATIONS.items():
        if source.count(before) != 1:
            raise ValueError("nonunique mutation anchor: " + name)
        for optimized in (False, True):
            with tempfile.TemporaryDirectory(prefix="titan-funding-mutant-") as tmp:
                target = Path(tmp)
                (target / "funding_basket.py").write_text(source.replace(before, after))
                shutil.copy2(root / "test_funding_basket.py", target)
                cmd = [sys.executable] + (["-O"] if optimized else []) + [
                    str(target / "test_funding_basket.py"), "--package", str(Path(args.package).resolve())]
                done = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                try:
                    report = json.loads(done.stdout.strip().splitlines()[-1])
                except (IndexError, json.JSONDecodeError) as exc:
                    raise RuntimeError("mutant failed to execute suite: " + name) from exc
                killed = done.returncode == 1 and report["failures"] > 0 and report["tests"] == 26
                records.append({"mutant": name, "optimized": optimized, "killed": killed,
                                "exit_code": done.returncode, "failures": report["failures"],
                                "errors": report["errors"], "tests": report["tests"],
                                "failing_tests": [line for line in done.stderr.splitlines()
                                                  if line.startswith(("FAIL:", "ERROR:"))]})
    Path(args.output).write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps({"runs": len(records), "killed": sum(r["killed"] for r in records)}))
    return 0 if all(r["killed"] for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
