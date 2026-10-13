# SPDX-License-Identifier: Apache-2.0
"""Confirm that the same existing checker rejects three broken experiments."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
MUTATIONS = {
    "skip_actual_harvest": ('action("HARVEST" if step == 92 else "PASS", market=orders)',
                            'action("PASS", market=orders)'),
    "omit_pre_eod_unwind": ('orders = [["SELL", "WHEAT", quantity]]', 'orders = []'),
    "erase_cash_threshold": ('world = fixture(engine, seat, cash=cash, shops=1)',
                              'world = fixture(engine, seat, cash=27, shops=1)'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    text = (HERE / "opportunity_cost.py").read_text()
    checker = (HERE / "check_opportunity_cost.py").read_bytes()
    results = []
    for name, (before, after) in MUTATIONS.items():
        if text.count(before) != 1:
            parser.exit(2, "mutation anchor drift: " + name + "\n")
        with tempfile.TemporaryDirectory(prefix="fwd-mutation-") as tmp:
            root = Path(tmp)
            (root / "opportunity_cost.py").write_text(text.replace(before, after, 1))
            (root / "check_opportunity_cost.py").write_bytes(checker)
            for mode in ([], ["-O"]):
                process = subprocess.run([sys.executable, *mode,
                    str(root / "check_opportunity_cost.py"), "--engine-dir", str(args.engine_dir.resolve())],
                    capture_output=True, text=True, timeout=30)
                try:
                    counts = json.loads(process.stdout.strip().splitlines()[-1])
                except (IndexError, json.JSONDecodeError):
                    parser.exit(2, "missing completed checker summary: " + name + "\n")
                if process.returncode != 1 or counts["failures"] < 1 or counts["errors"] != 0:
                    parser.exit(1, "mutation did not fail by assertion: " + name + repr(counts) + "\n")
                results.append({"mutation": name, "mode": "optimized" if mode else "normal", **counts})
    args.output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    print(json.dumps(results, sort_keys=True))


if __name__ == "__main__":
    main()
