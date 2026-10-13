# SPDX-License-Identifier: Apache-2.0
"""Run and compare exact-current baseline/LAND paired panels."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ci_prepare import opponent_paths
from ci_support import invoke_python, run, sha256


def run_panel(
    repo: Path, lane: Path, lab: Path, work: Path, python: Path,
    engine: Path, pin: dict[str, Any], arm: str,
) -> dict[str, Any]:
    holdout = pin["holdout"]
    package = work / f"current/{'baseline' if arm == 'baseline' else 'land'}"
    opponents = opponent_paths(repo, lab, work)
    seeds = ",".join(
        str(holdout["seed_start"] + index)
        for index in range(holdout["seed_count"])
    )
    command = [
        str(python), "-B", str(repo / "results/v25/s24/runner.py"),
        "--python", str(python),
        "--evaluator", str(work / "current/baseline/checks/reference/evaluator/evaluate.py"),
        "--engine-dir", str(engine),
        "--loader", str(repo / "revenue/kaggriculture/20260907-offline-agent/evaluate.py"),
        "--seeds", seeds,
        "--workers", str(holdout["workers"]),
        "--action-timeout", str(holdout["action_timeout_seconds"]),
        "--startup-timeout", "60", "--game-timeout", "1800",
    ]
    for name in holdout["opponents"]:
        command += ["--opponent", f"{name}={opponents[name]}::agent"]
    command += [
        "--candidate", str(package / "main.py"),
        "--output-dir", str(work / f"{arm}-panel"),
    ]
    started = time.monotonic()
    result = run(
        command, cwd=repo, stdout=work / f"{arm}.stdout.txt",
        stderr=work / f"{arm}.stderr.txt", check=False,
    )
    receipt = {
        "arm": arm,
        "returncode": result.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "candidate_sha256": sha256(package / "main.py"),
    }
    (work / f"{arm}.RUN.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def compare_current(
    repo: Path, lane: Path, work: Path, python: Path, pin: dict[str, Any]
) -> Path:
    holdout = pin["holdout"]
    output = work / "CURRENT-DELTA.json"
    invoke_python(
        python, lane / "panel_delta.py",
        [
            "--baseline", work / "baseline-panel/GAMES.jsonl",
            "--candidate", work / "land-panel/GAMES.jsonl",
            "--opponents", ",".join(holdout["opponents"]),
            "--seed-start", holdout["seed_start"],
            "--seed-count", holdout["seed_count"],
            "--json-out", output,
            "--markdown-out", work / "CURRENT-DELTA.md",
        ], cwd=repo,
    )
    return output


def write_summary(work: Path) -> None:
    sections = [
        "# TITAN V3: current LAND admission", "",
        "## Historical L01 reproduction", "",
    ]
    historical = work / "historical-l01/DELTA.md"
    sections.append(
        historical.read_text(encoding="utf-8")
        if historical.exists() else "Historical check did not complete.\n"
    )
    sections += ["", "## Current disjoint holdout", ""]
    current = work / "CURRENT-DELTA.md"
    sections.append(
        current.read_text(encoding="utf-8")
        if current.exists() else "Current paired panel did not complete.\n"
    )
    sections += ["", "## Exact route intervention", ""]
    route = work / "ROUTE-DIFF.json"
    if route.exists():
        row = json.loads(route.read_text(encoding="utf-8"))
        sections += [
            f"- changed route rows: {row['changed_rows']}",
            f"- transform exact: {row['exact_transform_match']}",
        ]
        first = row.get("first_divergence")
        if first:
            sections.append(
                f"- first divergence: route `{first['route']}`, step `{first['step']}`"
            )
    else:
        sections.append("Route probe did not complete.")
    (work / "SUMMARY.md").write_text(
        "\n".join(sections) + "\n", encoding="utf-8"
    )
