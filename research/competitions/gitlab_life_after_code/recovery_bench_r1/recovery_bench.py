#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, statistics
from pathlib import Path
from typing import Any, Iterable

VALID_DECISIONS = {"promote", "block"}

def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise SystemExit(f"{path}:{line_no}: each row must be an object")
            rows.append(row)
    return rows

def index_unique(rows: Iterable[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    out = {}
    for row in rows:
        case_id = row.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise SystemExit(f"{label}: every row needs non-empty string id")
        if case_id in out:
            raise SystemExit(f"{label}: duplicate id {case_id!r}")
        out[case_id] = row
    return out

def percentile_nearest_rank(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(p * len(ordered)))
    return ordered[rank - 1]

def validate_prediction(case: dict[str, Any], pred: dict[str, Any]) -> list[str]:
    errors = []
    decision = pred.get("decision")
    if decision not in VALID_DECISIONS:
        errors.append("decision must be promote|block")
    expected = case["expected_decision"]
    if decision != expected:
        errors.append(f"decision mismatch: expected {expected}, got {decision}")

    recovered = pred.get("recovered")
    if not isinstance(recovered, bool):
        errors.append("recovered must be boolean")
    expected_stage = case.get("expected_recovery_stage")
    if expected_stage is None:
        if recovered is True:
            errors.append("unexpected recovery on non-recovery case")
    else:
        if recovered is not True:
            errors.append(f"expected recovery of stage {expected_stage}")
        if pred.get("recovery_stage") != expected_stage:
            errors.append(
                f"recovery_stage mismatch: expected {expected_stage}, "
                f"got {pred.get('recovery_stage')}"
            )

    stage_count = pred.get("stage_count")
    if not isinstance(stage_count, int) or isinstance(stage_count, bool) or stage_count < 0:
        errors.append("stage_count must be a non-negative integer")

    wall_ms = pred.get("wall_ms")
    if not isinstance(wall_ms, (int, float)) or isinstance(wall_ms, bool) or wall_ms < 0:
        errors.append("wall_ms must be a non-negative number")

    evidence = pred.get("evidence_urls", [])
    if not isinstance(evidence, list) or any(not isinstance(x, str) for x in evidence):
        errors.append("evidence_urls must be a list of strings")
    else:
        if len(evidence) != len(set(evidence)):
            errors.append("evidence_urls must be unique within the case")
        if any(not x.startswith("https://") for x in evidence):
            errors.append("evidence_urls must be https://")

    if case.get("hazard") in {"security_failure", "reused_evidence"} and decision == "promote":
        errors.append(f"unsafe promotion on hazard={case['hazard']}")
    return errors

def score(cases_path: Path, preds_path: Path) -> dict[str, Any]:
    cases = index_unique(read_jsonl(cases_path), "cases")
    preds = index_unique(read_jsonl(preds_path), "predictions")
    missing = sorted(set(cases) - set(preds))
    extra = sorted(set(preds) - set(cases))
    if missing or extra:
        raise SystemExit(f"case-set mismatch: missing={missing}, extra={extra}")

    results, latencies, stage_counts = [], [], []
    recovery_total = recovery_ok = unsafe_promotions = 0

    for case_id in sorted(cases):
        case, pred = cases[case_id], preds[case_id]
        errors = validate_prediction(case, pred)
        ok = not errors
        if case.get("expected_recovery_stage") is not None:
            recovery_total += 1
            if ok:
                recovery_ok += 1
        if case.get("hazard") in {"security_failure", "reused_evidence"} and pred.get("decision") == "promote":
            unsafe_promotions += 1
        if isinstance(pred.get("wall_ms"), (int, float)) and not isinstance(pred.get("wall_ms"), bool):
            latencies.append(float(pred["wall_ms"]))
        if isinstance(pred.get("stage_count"), int) and not isinstance(pred.get("stage_count"), bool):
            stage_counts.append(pred["stage_count"])
        results.append({"id": case_id, "ok": ok, "errors": errors})

    passed = sum(1 for x in results if x["ok"])
    total = len(results)
    return {
        "cases": total,
        "passed": passed,
        "task_success_rate": passed / total if total else 0.0,
        "unsafe_promotions": unsafe_promotions,
        "recovery_success_rate": recovery_ok / recovery_total if recovery_total else None,
        "wall_ms": {
            "median": statistics.median(latencies) if latencies else 0.0,
            "p95_nearest_rank": percentile_nearest_rank(latencies, 0.95),
        },
        "stage_count": {
            "median": statistics.median(stage_counts) if stage_counts else 0.0,
            "p95_nearest_rank": percentile_nearest_rank([float(x) for x in stage_counts], 0.95),
        },
        "case_results": results,
    }

def compare(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_success_rate_delta": candidate["task_success_rate"] - baseline["task_success_rate"],
        "recovery_success_rate_delta": candidate["recovery_success_rate"] - baseline["recovery_success_rate"],
        "unsafe_promotion_delta": candidate["unsafe_promotions"] - baseline["unsafe_promotions"],
        "median_wall_ms_delta": candidate["wall_ms"]["median"] - baseline["wall_ms"]["median"],
        "p95_wall_ms_delta": candidate["wall_ms"]["p95_nearest_rank"] - baseline["wall_ms"]["p95_nearest_rank"],
        "median_stage_count_delta": candidate["stage_count"]["median"] - baseline["stage_count"]["median"],
    }

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", type=Path)
    ap.add_argument("candidate", type=Path)
    ap.add_argument("--baseline", type=Path)
    args = ap.parse_args()
    candidate = score(args.cases, args.candidate)
    output = {"candidate": candidate}
    if args.baseline:
        baseline = score(args.cases, args.baseline)
        output["baseline"] = baseline
        output["delta_candidate_minus_baseline"] = compare(candidate, baseline)
    print(json.dumps(output, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
