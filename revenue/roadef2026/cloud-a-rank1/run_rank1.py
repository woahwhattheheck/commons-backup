#!/usr/bin/env python3
"""Continue the frozen ROADEF candidate only on the three rank-one set-A gaps.

This is an execution harness, not a new solver.  It starts from the exact selected
30-second calibration incumbents, runs the same frozen candidate longer, checks
every result independently at 6 and 12 decimals, and records the first changed
rank plus the named peak-coordinate movement.  It never submits a competition
entry and never touches any instance outside A04/A14/A16.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

CANDIDATE_SHA256 = "758977095f8f34263bbcd9ed043ac4ab7943f04f65fae530c78ee64787c34f8f"
CALIBRATION_RUN = 34197720573
CALIBRATION_ARTIFACT = 10044831235
OFFICIAL_COMMIT = "d84d319a7fdb8de3b1866830d2eaa2937871e5ae"
CASES: dict[str, dict[str, Any]] = {
    "setA-04": {
        "target": {"t": 1, "from": 43, "to": 12},
        "candidate": "0.587276",
        "reference": "0.581237",
        "network": {"bytes": 30995, "sha256": "fbab36e356e73d8660f2a1a1aa3c110a3037938d834583d46707722b767c1559"},
        "traffic": {"bytes": 20766, "sha256": "eae88eb99c495a5a4fa6f42717867169f2dbd12babb51520a0a26aa40be4be84"},
        "scenario": {"bytes": 191, "sha256": "2a1b2744591d2707b2fb0ed7844a07ec2f5a61f6790df3ae0b60e392c950ad7e"},
    },
    "setA-14": {
        "target": {"t": 1, "from": 215, "to": 122},
        "candidate": "0.533147",
        "reference": "0.517621",
        "network": {"bytes": 149533, "sha256": "779364ffbae366e1943dcf913f61ce8cc0928fcd52c158660b4eb7c68b1446cb"},
        "traffic": {"bytes": 62427, "sha256": "244b41ce8d5a1cf19e7a42c1b86a0ef4de18a173ccfa24a61a602c3200032d28"},
        "scenario": {"bytes": 191, "sha256": "e891294997f9580cd976b164faaeb1e182f76338d727a5eb7dbb5f0aba32505a"},
    },
    "setA-16": {
        "target": {"t": 1, "from": 131, "to": 228},
        "candidate": "0.079918",
        "reference": "0.044262",
        "network": {"bytes": 187335, "sha256": "341c874ba43a464f1140944fbde8b0b22afc70557acb9a1ed37c13116c748268"},
        "traffic": {"bytes": 507495, "sha256": "db98d522634230e15337dc81ddca15a9922e1f505056f8c696db9b6cd6e00d3f"},
        "scenario": {"bytes": 191, "sha256": "a992e5ddc30bdcdc33a2f64737abfd0f20231f272419a038e76582b49db7b7f0"},
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(command: list[str], *, env: dict[str, str] | None = None,
        stdout: Path | None = None, stderr: Path | None = None,
        timeout: float | None = None) -> subprocess.CompletedProcess[bytes]:
    out = stdout.open("wb") if stdout else subprocess.PIPE
    err = stderr.open("wb") if stderr else subprocess.PIPE
    try:
        return subprocess.run(command, env=env, stdout=out, stderr=err,
                              timeout=timeout, check=False)
    finally:
        if stdout:
            out.close()
        if stderr:
            err.close()


def vector(checker: dict[str, Any]) -> tuple[int, ...]:
    rows = checker.get("saturations")
    if checker.get("valid") is not True or not isinstance(rows, list) or not rows:
        raise ValueError("checker result is not a complete valid saturation vector")
    result = []
    for row in rows:
        value = row.get("sat")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("checker saturation is not finite")
        # The 6-decimal checker is the ranking source.  Convert exactly as emitted.
        result.append(int(round(float(value) * 1_000_000)))
    return tuple(result)


def first_difference(before: tuple[int, ...], after: tuple[int, ...]) -> dict[str, Any] | None:
    if len(before) != len(after):
        return {"shape_mismatch": [len(before), len(after)]}
    for index, (old, new) in enumerate(zip(before, after)):
        if old != new:
            return {"rank": index + 1, "before": f"{old / 1_000_000:.6f}",
                    "after": f"{new / 1_000_000:.6f}",
                    "winner": "continued" if new < old else "incumbent"}
    return None


def coordinate(checker: dict[str, Any], target: dict[str, int]) -> str | None:
    for row in checker.get("saturations", []):
        if all(int(row[key]) == int(target[key]) for key in ("t", "from", "to")):
            return f"{float(row['sat']):.6f}"
    return None


def verify_file(path: Path, expected: dict[str, Any], label: str) -> dict[str, Any]:
    actual = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    if actual != expected:
        raise ValueError(f"{label} identity differs: {actual}")
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--official-root", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--candidate-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--case-timeout", type=float, default=240.0)
    args = parser.parse_args()

    if not 30 <= args.seconds <= 600:
        parser.error("--seconds must be in 30..600")
    if not math.isfinite(args.case_timeout) or args.case_timeout <= args.seconds:
        parser.error("--case-timeout must be finite and exceed --seconds")

    context = args.context.resolve()
    official = args.official_root.resolve()
    calibration = args.calibration.resolve()
    source = args.candidate_source.resolve()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("--output must be fresh")
    output.mkdir(parents=True, exist_ok=True)

    if sha256(source) != CANDIDATE_SHA256:
        raise ValueError("candidate source hash differs")
    candidate = context / "bin" / "candidate"
    checker = context / "bin" / "checker"
    for path in (candidate, checker):
        if not path.is_file():
            raise FileNotFoundError(path)

    records: list[dict[str, Any]] = []
    started = time.time()
    for label, contract in CASES.items():
        case = output / label
        case.mkdir()
        official_case = official / "setA"
        network = official_case / f"{label}-net.json"
        traffic = official_case / f"{label}-tm.json"
        scenario = official_case / f"{label}-scenario.json"
        input_identity = {
            "network": verify_file(network, contract["network"], f"{label} network"),
            "traffic": verify_file(traffic, contract["traffic"], f"{label} traffic"),
            "scenario": verify_file(scenario, contract["scenario"], f"{label} scenario"),
        }

        incumbent = calibration / label / "solution.json"
        incumbent_check6 = calibration / label / "checker-6.json"
        if not incumbent.is_file() or not incumbent_check6.is_file():
            raise FileNotFoundError(f"{label}: selected calibration incumbent is absent")
        incumbent_doc = read_json(incumbent_check6)
        incumbent_vector = vector(incumbent_doc)
        target_before = coordinate(incumbent_doc, contract["target"])
        if target_before != contract["candidate"]:
            raise ValueError(f"{label}: authoritative target changed: {target_before}")

        shutil.copy2(incumbent, case / "incumbent.json")
        shutil.copy2(incumbent_check6, case / "incumbent-checker-6.json")
        solution = case / "solution.json"
        stats = case / "stats.json"
        env = os.environ.copy()
        env.update({
            "CLOUD_INITIAL_SOLUTION": str(case / "incumbent.json"),
            "SEDGE_SECONDS": str(args.seconds),
            "SEDGE_STATS": str(stats),
            "FLEET_DIRECTED": "1",
            "FLEET_JOINT": "1",
            "FLEET_WAYPOINT_LIMIT": "0",
            "OMP_NUM_THREADS": "1",
        })
        rank1_report = case / "rank1-report.json"
        if float(env.get("FLEET_RANK1", "0")) != 0:
            env["FLEET_RANK1_REPORT"] = str(rank1_report)
        env.pop("SEDGE_MAX_ROUNDS", None)
        run_started = time.monotonic()
        try:
            process = run([str(candidate), str(network), str(traffic), str(scenario), str(solution)],
                          env=env, stdout=case / "candidate.stdout",
                          stderr=case / "candidate.stderr", timeout=args.case_timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            process = None
            timed_out = True
        elapsed = time.monotonic() - run_started
        if timed_out or process is None or process.returncode != 0 or not solution.is_file():
            record = {"instance": label, "complete": False, "timed_out": timed_out,
                      "returncode": None if process is None else process.returncode,
                      "wall_seconds": round(elapsed, 6), "solution_exists": solution.is_file()}
            records.append(record)
            write_json(output / "RUN-PARTIAL.json", {"runs": records})
            raise RuntimeError(f"{label}: continuation failed: {record}")

        checker_docs: dict[str, dict[str, Any]] = {}
        checker_ids: dict[str, dict[str, Any]] = {}
        for precision in (6, 12):
            result_path = case / f"checker-{precision}.json"
            checked = run([str(checker), "--net", str(network), "--tm", str(traffic),
                           "--scenario", str(scenario), "--srpaths", str(solution),
                           "--max-decimal-places", str(precision)],
                          stdout=result_path, stderr=case / f"checker-{precision}.stderr",
                          timeout=60)
            doc = read_json(result_path)
            if checked.returncode != 0 or doc.get("valid") is not True:
                raise RuntimeError(f"{label}: checker-{precision} rejected continuation")
            checker_docs[str(precision)] = doc
            checker_ids[str(precision)] = {
                "bytes": result_path.stat().st_size, "sha256": sha256(result_path)}
        continued_vector = vector(checker_docs["6"])
        difference = first_difference(incumbent_vector, continued_vector)
        if continued_vector > incumbent_vector:
            raise ValueError(f"{label}: continuation worsened the official six-decimal vector")
        target_after = coordinate(checker_docs["6"], contract["target"])
        stats_doc = read_json(stats) if stats.is_file() else None
        rank1_doc = read_json(rank1_report) if rank1_report.is_file() else None
        record = {
            "instance": label,
            "complete": True,
            "wall_seconds": round(elapsed, 6),
            "allowance_seconds": args.seconds,
            "input_identity": input_identity,
            "incumbent": {
                "solution_sha256": sha256(incumbent),
                "checker_6_sha256": sha256(incumbent_check6),
                "target": {**contract["target"], "sat": target_before},
                "reference_target": contract["reference"],
                "vector_length": len(incumbent_vector),
            },
            "continued": {
                "solution_sha256": sha256(solution),
                "checker": checker_ids,
                "target": {**contract["target"], "sat": target_after},
                "vector_length": len(continued_vector),
                "first_difference": difference,
                "changed": difference is not None,
                "strictly_better": continued_vector < incumbent_vector,
                "total_cost_diagnostic": checker_docs["6"].get("total_cost"),
                "srpaths": checker_docs["6"].get("total_srpaths"),
                "segments": checker_docs["6"].get("total_segments"),
            },
            "candidate_stats": stats_doc,
            "rank1_report": rank1_doc,
        }
        records.append(record)
        write_json(output / "RUN-PARTIAL.json", {"runs": records})
        print(f"{label}: target {target_before}->{target_after}; "
              f"first={difference}; wall={elapsed:.2f}s", flush=True)

    summary = {
        "schema": "roadef.a-rank1-diversion-result.v1",
        "complete": True,
        "submission_performed": False,
        "calibration": {"run_id": CALIBRATION_RUN, "artifact_id": CALIBRATION_ARTIFACT},
        "official_commit": OFFICIAL_COMMIT,
        "candidate_source_sha256": CANDIDATE_SHA256,
        "seconds_per_case": args.seconds,
        "started_unix": started,
        "finished_unix": time.time(),
        "counts": {
            "cases": len(records),
            "strictly_better": sum(r["continued"]["strictly_better"] for r in records),
            "unchanged": sum(not r["continued"]["changed"] for r in records),
        },
        "runs": records,
    }
    write_json(output / "RESULTS.json", summary)
    lines = [
        "# ROADEF A-RANK1 continuation result",
        "",
        f"Frozen candidate `{CANDIDATE_SHA256}` resumed from the exact selected "
        f"30-second calibration incumbents for {args.seconds} seconds per case.",
        "",
        "| Instance | Target | Incumbent | Continued | First changed rank | Result |",
        "|---|---|---:|---:|---:|---|",
    ]
    for record in records:
        target = record["incumbent"]["target"]
        diff = record["continued"]["first_difference"]
        lines.append(
            f"| {record['instance']} | t{target['t']} {target['from']}→{target['to']} | "
            f"{target['sat']} | {record['continued']['target']['sat']} | "
            f"{diff['rank'] if diff and 'rank' in diff else '—'} | "
            f"{'strictly better' if record['continued']['strictly_better'] else 'unchanged'} |")
    lines += [
        "",
        "All outputs were independently accepted by the pinned official checker at "
        "6 and 12 decimals. This is a bounded three-case continuation, not a "
        "qualification submission or a set-wide score claim.",
    ]
    (output / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
