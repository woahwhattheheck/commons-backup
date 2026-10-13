# SPDX-License-Identifier: Apache-2.0
"""Run six wrong implementations through behavioral tests, never hash tests."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from compose_hire_cost import DECLARATION, TABLE, compose_source


def mutants(source: str) -> dict[str, str]:
    wrong = (0,) + TABLE[1:]
    table = "_TITAN_HIRE_FIB64 = " + repr(wrong) + "\n\n"
    return {
        "wrong_first_hire": source.replace(DECLARATION, table, 1),
        "shifted_lookup": source.replace("return _TITAN_HIRE_FIB64[n]", "return _TITAN_HIRE_FIB64[(n + 1) % 64]", 1),
        "negative_lookup": source.replace("0 <= n < 64", "-63 <= n < 64", 1),
        "float_coercion": source.replace("type(n) is int", "type(n) in (int, float)", 1).replace("return _TITAN_HIRE_FIB64[n]", "return _TITAN_HIRE_FIB64[int(n)]", 1),
        "large_clamped": source.replace("    a, b = 1, 1\n", "    if type(n) is int and n >= 64:\n        return _TITAN_HIRE_FIB64[63]\n    a, b = 1, 1\n", 1),
        "floating_receipt": source.replace("return _TITAN_HIRE_FIB64[n]", "return float(_TITAN_HIRE_FIB64[n])", 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = compose_source((args.runtime / "mechanics.py").read_text())
    tests = Path(__file__).with_name("test_hire_cost.py")
    result = []
    with tempfile.TemporaryDirectory(prefix="titan-hire-mutants-") as tmp:
        for mode in ("normal", "optimized"):
            command = [sys.executable] + (["-O"] if mode == "optimized" else []) + [str(tests), "BehaviorTests", "InterpreterTests"]
            env = dict(os.environ, TITAN_RUNTIME=str(args.runtime.resolve()))
            env.pop("HIRE_COST_MUTANT_FILE", None)
            control = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
            args.output.joinpath(mode + "-control.log").write_text(control.stdout + control.stderr)
            if control.returncode or not re.search(r"Ran 9 tests", control.stderr) or not re.search(r"\nOK\s*$", control.stderr):
                raise RuntimeError("behavioral control did not execute all nine tests cleanly")
            for name, text in mutants(source).items():
                if text == source:
                    raise RuntimeError("inactive mutant: " + name)
                path = Path(tmp) / (name + ".py")
                path.write_text(text)
                run = subprocess.run(command, env=dict(env, HIRE_COST_MUTANT_FILE=str(path)), capture_output=True, text=True, timeout=30)
                args.output.joinpath(mode + "-" + name + ".log").write_text(run.stdout + run.stderr)
                match = re.search(r"FAILED \(failures=(\d+)\)", run.stderr)
                killed = run.returncode != 0 and bool(match) and bool(re.search(r"Ran 9 tests", run.stderr))
                record = {"mode": mode, "mutant": name, "killed_by_assertions": killed,
                          "failed_assertions_or_subcases": int(match[1]) if match else None,
                          "returncode": run.returncode, "errors": 0 if match else "inspect-log"}
                result.append(record)
                if not killed:
                    raise RuntimeError("mutant did not fail exclusively by assertions: " + str(record))
    args.output.joinpath("RESULT.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"normal": 6, "optimized": 6, "behavioral_mutants_rejected": len(result)}))


if __name__ == "__main__":
    main()
