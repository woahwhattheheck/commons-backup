#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile and validate the critical-rank-band component on supplied pinned inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

CORE_STATS = ("resumed", "attempted", "joint_attempted", "joint_accepted",
              "ranked_candidates", "accepted", "initial_mlu", "final_mlu",
              "budget_used", "loads")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], *, env: dict[str, str] | None = None,
        timeout: int = 120) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stderr}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--vendor", required=True, type=Path)
    parser.add_argument("--fixtures", required=True, type=Path,
                        help="Directory containing joint-net/joint-tm/joint-scenario fixtures")
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="roadef-critical-ranks-") as temporary:
        temp = Path(temporary)
        candidate = temp / "candidate.cpp"
        run([str(here / "build_candidate.py"), "--source", str(args.source), "--output", str(candidate)])
        shutil.copy2(here / "test_rank_schedule.cpp", temp / "test_rank_schedule.cpp")
        compilers = [name for name in ("g++", "clang++") if shutil.which(name)]
        if not compilers:
            raise RuntimeError("no C++ compiler available")
        binaries: dict[str, dict[str, Path]] = {}
        schedule = []
        for compiler in compilers:
            tag = Path(compiler).name.replace("+", "p")
            original = temp / f"original-{tag}"
            built = temp / f"candidate-{tag}"
            harness = temp / f"schedule-{tag}"
            common = [compiler, "-std=c++20", "-O3", "-DNDEBUG", "-I", str(args.vendor)]
            run(common + [str(args.source), "-o", str(original)])
            run(common + [str(candidate), "-o", str(built)])
            run(common + ["-I", str(temp), str(temp / "test_rank_schedule.cpp"), "-o", str(harness)])
            message = run([str(harness)]).stdout.strip()
            schedule.append({"compiler": compiler, "message": message})
            binaries[compiler] = {"original": original, "candidate": built}

        cases = []
        for family, tm, scenario in (("joint", "joint-tm.json", "joint-scenario.json"),
                                     ("joint-budget", "joint-budget-tm.json", "joint-budget-scenario.json")):
            for rounds in (0, 3, 12, 64):
                for joint in (0, 1):
                    outputs: dict[str, tuple[bytes, dict]] = {}
                    for compiler in compilers:
                        for arm in ("original", "candidate"):
                            label = f"{compiler}-{arm}"
                            solution = temp / f"{family}-{rounds}-{joint}-{label}.json"
                            stats = temp / f"{family}-{rounds}-{joint}-{label}-stats.json"
                            env = os.environ.copy()
                            env.update(SEDGE_SECONDS="1000", SEDGE_MAX_ROUNDS=str(rounds),
                                       FLEET_JOINT=str(joint), FLEET_DIRECTED="1", SEDGE_STATS=str(stats))
                            run([str(binaries[compiler][arm]), str(args.fixtures / "joint-net.json"),
                                 str(args.fixtures / tm), str(args.fixtures / scenario), str(solution)],
                                env=env, timeout=60)
                            outputs[label] = (solution.read_bytes(), json.loads(stats.read_text()))
                    reference = outputs[f"{compilers[0]}-original"]
                    for compiler in compilers:
                        candidate_result = outputs[f"{compiler}-candidate"]
                        if candidate_result[0] != reference[0]:
                            raise AssertionError("default candidate solution differs from original")
                        for key in CORE_STATS:
                            if candidate_result[1][key] != reference[1][key]:
                                raise AssertionError(f"default candidate differs in {key}")
                        if candidate_result[1]["critical_rank_limit"] != 32:
                            raise AssertionError("default rank limit changed")
                        if candidate_result[1]["critical_stall_limit"] != 64:
                            raise AssertionError("default stall limit changed")
                    cases.append({"family": family, "rounds": rounds, "joint": joint,
                                  "solution_sha256": hashlib.sha256(reference[0]).hexdigest(),
                                  "attempted": reference[1]["attempted"],
                                  "accepted": reference[1]["accepted"]})
        report = {"schema": "roadef-critical-rank-component-validation-v1", "status": "PASS",
                  "source_sha256": digest(args.source), "candidate_sha256": digest(candidate),
                  "compilers": compilers, "schedule": schedule,
                  "default_parity_cases": len(cases),
                  "default_parity_compiler_comparisons": len(cases) * len(compilers),
                  "cases": cases,
                  "limits": ["No public-instance search is run by this focused component command.",
                             "The separate RESULTS.json records the saved B12 continuation experiment.",
                             "Default rank/stall settings preserve the original search order and stop."]}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"status": "PASS", "report": str(args.report),
                          "default_parity_cases": len(cases), "compilers": compilers}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
