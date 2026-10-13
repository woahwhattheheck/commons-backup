#!/usr/bin/env python3
"""Run the frozen ROADEF portfolio serially on set A and compare sprint prefixes."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

FROZEN_COMMIT = "6feb9c0566b8f203c5d1a2ffdfbf1cb6d11be055"
CANDIDATE_SHA256 = "758977095f8f34263bbcd9ed043ac4ab7943f04f65fae530c78ee64787c34f8f"
SPRINT_SHA256 = "b6218e41ac204e73c4688aa9e0e56825c1f5b864440675c4f7ffba27a75f45ca"
OFFICIAL_COMMIT = "d84d319a7fdb8de3b1866830d2eaa2937871e5ae"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, env: dict[str, str] | None = None,
        stdout: Path | None = None, stderr: Path | None = None,
        timeout: float | None = None) -> subprocess.CompletedProcess[bytes]:
    out_handle = stdout.open("wb") if stdout else subprocess.PIPE
    err_handle = stderr.open("wb") if stderr else subprocess.PIPE
    try:
        return subprocess.run(command, env=env, stdout=out_handle, stderr=err_handle,
                              timeout=timeout, check=False)
    finally:
        if stdout:
            out_handle.close()
        if stderr:
            err_handle.close()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_frozen_comparator(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("roadef_frozen_compare_checker", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load frozen comparator from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("load_result", "load_sprint_reference"):
        if not callable(getattr(module, name, None)):
            raise ImportError(f"Frozen comparator has no callable {name}")
    return module


def instance_paths(official: Path, label: str) -> tuple[Path, Path, Path]:
    root = official / "setA"
    return (root / f"{label}-net.json", root / f"{label}-tm.json",
            root / f"{label}-scenario.json")


def validate_inputs(official: Path) -> list[dict[str, Any]]:
    records = []
    for number in range(1, 21):
        label = f"setA-{number:02d}"
        paths = instance_paths(official, label)
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"{label}: missing {missing}")
        records.append({
            "instance": label,
            "network": {"bytes": paths[0].stat().st_size, "sha256": sha256(paths[0])},
            "traffic": {"bytes": paths[1].stat().st_size, "sha256": sha256(paths[1])},
            "scenario": {"bytes": paths[2].stat().st_size, "sha256": sha256(paths[2])},
        })
    return records


def expected_portfolio_timing(seconds: int) -> tuple[float, float]:
    reserve = min(20.0, float(seconds) * 0.12)
    return float(seconds) - reserve, reserve


def validate_portfolio_timing(receipt: dict[str, Any], seconds: int) -> tuple[float, float]:
    expected_search, expected_reserve = expected_portfolio_timing(seconds)
    values: dict[str, float] = {}
    for field in ("search_allowance_seconds", "deadline_seconds"):
        raw = receipt.get(field)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"portfolio receipt has no numeric {field}")
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError(f"portfolio receipt has nonfinite {field}")
        values[field] = value
    if not math.isclose(values["deadline_seconds"], float(seconds), rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("portfolio receipt deadline differs from requested total")
    if not math.isclose(values["search_allowance_seconds"], expected_search,
                        rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("portfolio receipt search allowance differs from frozen formula")
    return expected_search, expected_reserve


def compare_published_prefix(candidate: dict[str, Any], target: dict[str, Any],
                             instance: str) -> dict[str, Any]:
    reference_vector = target["vector"]
    report: dict[str, Any] = {
        "instance": instance,
        "candidate_valid": candidate["valid"],
        "reference_best_team": target["best_team"],
        "reference_csv_line": target["csv_line"],
        "reference_vector_length": len(reference_vector),
        "candidate_checker_path": candidate["path"],
        "candidate_checker_sha256": candidate["sha256"],
        "candidate_total_cost_diagnostic": candidate.get("total_cost"),
        "cost_used_in_ranking": False,
        "first_changed_rank": None,
        "reference_link_time_coordinates_available": False,
        "input_binding": "exact set-A paths from pinned official commit; file hashes recorded by harness",
    }
    if not candidate["valid"]:
        report.update(winner="reference", comparison_status="candidate_invalid",
                      candidate_vector_length=None, compared_prefix_length=0,
                      reference_is_strict_prefix=None)
        return report

    candidate_vector = candidate["vector"]
    candidate_length = len(candidate_vector)
    reference_length = len(reference_vector)
    report.update(candidate_vector_length=candidate_length,
                  compared_prefix_length=min(candidate_length, reference_length),
                  candidate_mlu=str(candidate_vector[0]),
                  reference_mlu=str(reference_vector[0]))
    if candidate_length < reference_length:
        report.update(winner="shape_mismatch",
                      comparison_status="candidate_shorter_than_published_reference",
                      reference_is_strict_prefix=False)
        return report

    prefix = candidate_vector[:reference_length]
    difference = next((index for index, values in enumerate(zip(prefix, reference_vector))
                       if values[0] != values[1]), None)
    strict_prefix = candidate_length > reference_length
    report["reference_is_strict_prefix"] = strict_prefix
    if difference is None:
        if strict_prefix:
            report.update(winner="inconclusive",
                          comparison_status="tied_on_published_prefix")
        else:
            report.update(winner="tie", comparison_status="full_vector_tie")
        return report

    candidate_value = prefix[difference]
    reference_value = reference_vector[difference]
    report.update(
        winner="candidate" if candidate_value < reference_value else "reference",
        comparison_status="compared_on_published_prefix",
        first_changed_rank=difference + 1,
        candidate_at_first_change=str(candidate_value),
        reference_at_first_change=str(reference_value),
    )
    return report


def sprint_prefix_report(output: Path, reference_path: Path, comparator: Any) -> dict[str, Any]:
    reference = comparator.load_sprint_reference(reference_path)
    labels = [f"setA-{number:02d}" for number in range(1, 21)]
    unknown = [label for label in labels if label not in reference["records"]]
    if unknown:
        raise ValueError(f"Instances absent from pinned sprint reference: {unknown}")
    rows = []
    for label in labels:
        checker = output / label / "checker-6.json"
        if not checker.is_file():
            raise FileNotFoundError(checker)
        rows.append(compare_published_prefix(
            comparator.load_result(checker), reference["records"][label], label))
    outcomes = ("candidate", "reference", "tie", "inconclusive", "shape_mismatch")
    return {
        "comparison": (
            "official six-decimal candidate vectors versus published sprint prefixes; "
            "lexicographic first difference only; no cost tiebreak"
        ),
        "competition_rank": "unknown; historical per-instance best teams are not a qualification ranking",
        "resource_budgets_matched": False,
        "equal_strict_prefix_interpretation": "inconclusive, not a full-vector tie",
        "reference": {key: value for key, value in reference.items() if key != "records"},
        "reference_instances_not_compared": sorted(set(reference["records"]) - set(labels)),
        "counts": {outcome: sum(row["winner"] == outcome for row in rows)
                   for outcome in outcomes},
        "invalid_candidate_count": sum(not row["candidate_valid"] for row in rows),
        "instances": rows,
    }


def write_partial(output: Path, records: list[dict[str, Any]]) -> None:
    (output / "RUN-PARTIAL.json").write_text(
        json.dumps({"runs": records}, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-root", type=Path, required=True,
                        help="fleet-candidate directory checked out at the frozen commit")
    parser.add_argument("--context", type=Path, required=True,
                        help="built verified context containing run.sh and bin/checker")
    parser.add_argument("--official-root", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--case-timeout", type=float, default=75.0)
    args = parser.parse_args()
    if args.seconds < 2:
        parser.error("--seconds must be at least 2")
    if not math.isfinite(args.case_timeout) or args.case_timeout <= 0:
        parser.error("--case-timeout must be finite and positive")

    frozen = args.frozen_root.resolve()
    context = args.context.resolve()
    official = args.official_root.resolve()
    reference = args.reference.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    candidate = frozen / "main.cpp"
    comparator_path = frozen / "compare_checker.py"
    if sha256(candidate) != CANDIDATE_SHA256:
        raise ValueError("frozen candidate source hash mismatch")
    if sha256(reference) != SPRINT_SHA256:
        raise ValueError("sprint reference hash mismatch")
    for path in (context / "run.sh", context / "bin" / "checker", comparator_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    comparator = load_frozen_comparator(comparator_path)

    inputs = validate_inputs(official)
    # The workflow uploads this result directory under ``if: always()``.
    # Retain the complete 60-file census before the first expensive case.
    (output / "INPUTS.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "frozen_commit": FROZEN_COMMIT,
                "candidate_source_sha256": CANDIDATE_SHA256,
                "official_commit": OFFICIAL_COMMIT,
                "sprint_reference_sha256": SPRINT_SHA256,
                "input_files": inputs,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    run_records: list[dict[str, Any]] = []
    started = time.time()
    expected_search, expected_reserve = expected_portfolio_timing(args.seconds)
    for number in range(1, 21):
        label = f"setA-{number:02d}"
        network, traffic, scenario = instance_paths(official, label)
        case = output / label
        case.mkdir(parents=True, exist_ok=True)
        solution = case / "solution.json"
        receipt = case / "portfolio.json"
        artifacts = case / "artifacts"
        artifacts.mkdir(exist_ok=True)
        env = os.environ.copy()
        env.update({
            "PORTFOLIO_SECONDS": str(args.seconds),
            "PORTFOLIO_ARTIFACTS": str(artifacts),
            "PORTFOLIO_RECEIPT": str(receipt),
            "FLEET_DIRECTED": "1",
            "FLEET_JOINT": "1",
            "FLEET_WAYPOINT_LIMIT": "0",
            "OMP_NUM_THREADS": "1",
        })
        for key in ("SEDGE_MAX_ROUNDS", "SEDGE_STATS", "CLOUD_INITIAL_SOLUTION"):
            env.pop(key, None)
        portfolio_started = time.monotonic()
        try:
            result = run([str(context / "run.sh"), str(network), str(traffic),
                          str(scenario), str(solution)], env=env,
                         stdout=case / "portfolio.stdout", stderr=case / "portfolio.stderr",
                         timeout=args.case_timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            result = None
            timed_out = True
        portfolio_elapsed = time.monotonic() - portfolio_started
        if timed_out or result is None or result.returncode != 0 or not solution.is_file():
            record = {"instance": label, "portfolio_elapsed_seconds": portfolio_elapsed,
                      "timeout": timed_out,
                      "returncode": None if result is None else result.returncode,
                      "solution_exists": solution.is_file(),
                      "receipt_exists": receipt.is_file()}
            run_records.append(record)
            write_partial(output, run_records)
            raise RuntimeError(f"{label}: portfolio failed: {record}")

        checker = case / "checker-6.json"
        checker_started = time.monotonic()
        check = run([str(context / "bin" / "checker"), "--net", str(network),
                     "--tm", str(traffic), "--scenario", str(scenario),
                     "--srpaths", str(solution), "--max-decimal-places", "6"],
                    stdout=checker, stderr=case / "checker.stderr", timeout=30)
        checker_elapsed = time.monotonic() - checker_started
        checker_doc = None
        checker_parse_error = None
        if checker.is_file():
            try:
                checker_doc = read_json(checker)
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                checker_parse_error = type(error).__name__
        if check.returncode != 0 or not isinstance(checker_doc, dict) or checker_doc.get("valid") is not True:
            record = {"instance": label,
                      "portfolio_elapsed_seconds": round(portfolio_elapsed, 6),
                      "checker_elapsed_seconds": round(checker_elapsed, 6),
                      "portfolio_returncode": result.returncode,
                      "solution_exists": solution.is_file(),
                      "solution_sha256": sha256(solution) if solution.is_file() else None,
                      "receipt_exists": receipt.is_file(),
                      "receipt_sha256": sha256(receipt) if receipt.is_file() else None,
                      "checker_returncode": check.returncode,
                      "checker_exists": checker.is_file(),
                      "checker_sha256": sha256(checker) if checker.is_file() else None,
                      "checker_parse_error": checker_parse_error,
                      "checker_valid": (checker_doc.get("valid")
                                        if isinstance(checker_doc, dict) else None)}
            run_records.append(record)
            write_partial(output, run_records)
            raise RuntimeError(f"{label}: official checker failed: {record}")

        receipt_doc = read_json(receipt)
        actual_search, actual_reserve = validate_portfolio_timing(receipt_doc, args.seconds)
        candidate_result = comparator.load_result(checker)
        record = {
            "instance": label,
            "portfolio_elapsed_seconds": round(portfolio_elapsed, 6),
            "checker_elapsed_seconds": round(checker_elapsed, 6),
            "independent_checker_outside_portfolio_envelope": True,
            "portfolio_returncode": result.returncode,
            "checker_returncode": check.returncode,
            "solution_sha256": sha256(solution),
            "checker_sha256": sha256(checker),
            "load_count": len(candidate_result["vector"]),
            "mlu": str(candidate_result["vector"][0]),
            "total_cost_diagnostic": checker_doc.get("total_cost"),
            "portfolio_status": receipt_doc.get("status"),
            "selected_lane": receipt_doc.get("selected_lane"),
            "receipt_sha256": sha256(receipt),
            "portfolio_deadline_seconds": float(receipt_doc["deadline_seconds"]),
            "portfolio_search_allowance_seconds": actual_search,
            "portfolio_selection_and_checker_reserve_seconds": actual_reserve,
        }
        run_records.append(record)
        write_partial(output, run_records)
        print(f"{label}: valid {record['mlu']} portfolio={portfolio_elapsed:.2f}s "
              f"checker={checker_elapsed:.2f}s", flush=True)

    comparison = output / "A-vs-sprint.json"
    comparison_doc = sprint_prefix_report(output, reference, comparator)
    comparison_text = json.dumps(comparison_doc, indent=2, default=str) + "\n"
    comparison.write_text(comparison_text, encoding="utf-8")
    (output / "compare.stdout").write_text(comparison_text, encoding="utf-8")
    (output / "compare.stderr").write_text("", encoding="utf-8")

    metadata = {
        "schema_version": 2,
        "purpose": "historical set-A prefix calibration only; resource budgets are unequal",
        "submission_performed": False,
        "frozen_commit": FROZEN_COMMIT,
        "candidate_source_sha256": CANDIDATE_SHA256,
        "official_commit": OFFICIAL_COMMIT,
        "sprint_reference_sha256": SPRINT_SHA256,
        "serial": True,
        "portfolio_timing": {
            "requested_total_seconds_per_case": args.seconds,
            "internal_search_allowance_seconds": expected_search,
            "internal_selection_and_checker_reserve_seconds": expected_reserve,
            "independent_final_checker_outside_portfolio_envelope": True,
            "case_timeout_seconds": args.case_timeout,
        },
        "started_unix": started,
        "finished_unix": time.time(),
        "input_files": inputs,
        "context": {
            "candidate_binary_sha256": sha256(context / "bin" / "candidate"),
            "sedge_binary_sha256": sha256(context / "bin" / "sedge"),
            "flora_binary_sha256": sha256(context / "bin" / "flora"),
            "checker_binary_sha256": sha256(context / "bin" / "checker"),
        },
        "runs": run_records,
        "comparison_counts": comparison_doc.get("counts"),
        "invalid_candidate_count": comparison_doc.get("invalid_candidate_count"),
    }
    (output / "RUN.json").write_text(
        json.dumps(metadata, indent=2, default=str) + "\n", encoding="utf-8")

    lines = [
        "# ROADEF set-A sprint-reference calibration",
        "",
        "This is a historical reference calibration, not a qualification ranking. The",
        "current serial portfolio and published sprint best-team rows used unequal resource",
        "budgets and may have run on different hardware. Each current case gives the portfolio",
        f"{expected_search:g} seconds of internal search plus a {expected_reserve:g}-second",
        "selection/checking reserve; the independent final official checker runs afterward,",
        "outside that portfolio envelope. No submission or tuning occurred.",
        "",
        "Published sprint rows may be strict prefixes of the candidate vector. A first",
        "difference inside the published prefix determines the reported reference gap. An",
        "equal strict prefix is INCONCLUSIVE, not a full-vector tie or a rank statement.",
        "",
        f"- Frozen source: `{FROZEN_COMMIT}` / `{CANDIDATE_SHA256}`",
        f"- Official data: `{OFFICIAL_COMMIT}`",
        f"- Reference CSV: `{SPRINT_SHA256}`",
        f"- Valid runs: {len(run_records)}/20",
        f"- Comparison counts: `{json.dumps(comparison_doc.get('counts'), sort_keys=True)}`",
        "",
        "| Instance | Prefix result | Status | First rank | Candidate | Reference | Lengths C/R | MLU | Lane |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    by_instance = {row["instance"]: row for row in comparison_doc["instances"]}
    for record in run_records:
        row = by_instance[record["instance"]]
        lengths = f"{row.get('candidate_vector_length', '-')}/{row.get('reference_vector_length', '-')}"
        lines.append(
            f"| {record['instance']} | {row['winner']} | {row['comparison_status']} | "
            f"{row.get('first_changed_rank') or '-'} | "
            f"{row.get('candidate_at_first_change', '-')} | "
            f"{row.get('reference_at_first_change', '-')} | {lengths} | "
            f"{row.get('candidate_mlu', record['mlu'])} | {record.get('selected_lane') or '-'} |"
        )
    (output / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.copy2(reference, output / "REFERENCE.csv")

    shape_mismatches = [row["instance"] for row in comparison_doc["instances"]
                        if row["winner"] == "shape_mismatch"]
    if shape_mismatches:
        raise RuntimeError(f"Candidate vectors shorter than published references: {shape_mismatches}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
