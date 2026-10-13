#!/usr/bin/env python3
"""ChipTrace benchmark and evidence-bound triage layer.

This module evaluates the existing deterministic ChipTrace QC core on a frozen,
lawful synthetic defect corpus and wraps its output in an inspectable triage
record. It is research quality-control support only, not clinical or biological
validation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("chiptrace_core", HERE / "chiptrace.py")
ct = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["chiptrace_core"] = ct
SPEC.loader.exec_module(ct)

SCHEMA = "chiptrace.benchmark.v1"
TRIAGE_SCHEMA = "chiptrace.triage.v1"


@dataclass(frozen=True)
class Scenario:
    name: str
    expected_state: str
    description: str


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("clean", "SUPPORTED", "baseline-like run with no injected QC defect"),
    Scenario("level_shift", "REVIEW", "barrier channel receives a large robust level shift"),
    Scenario("cadence_gap", "REVIEW", "oxygen channel drops two expected samples per replicate"),
    Scenario("replicate_divergence", "REVIEW", "one flow replicate diverges from its peers"),
    Scenario("sparse", "INSUFFICIENT_EVIDENCE", "too few observations for a supported decision"),
)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _clone_observation(o: Any, *, run_id: str, value: float | None = None) -> Any:
    return ct.Observation(
        run_id=run_id,
        replicate_id=o.replicate_id,
        time_s=o.time_s,
        channel=o.channel,
        value=o.value if value is None else value,
        unit=o.unit,
        source="synthetic_benchmark_fixture",
        modality=o.modality,
    )


def build_frozen_corpus(directory: Path) -> dict[str, tuple[Path, Path]]:
    """Create deterministic benchmark cases from the existing ChipTrace fixture."""
    seed_dir = directory / "_seed"
    baseline_path, _ = ct.generate_demo(seed_dir)
    baseline_rows = ct.load_csv(baseline_path)
    models = ct.build_baselines(baseline_rows)

    out: dict[str, tuple[Path, Path]] = {}
    for scenario in SCENARIOS:
        case_dir = directory / scenario.name
        case_dir.mkdir(parents=True, exist_ok=True)
        case_baseline = case_dir / "baseline.csv"
        case_run = case_dir / "candidate.csv"
        ct.write_csv(case_baseline, baseline_rows)

        rows: list[Any]
        if scenario.name == "clean":
            rows = [_clone_observation(o, run_id="clean") for o in baseline_rows]
        elif scenario.name == "level_shift":
            shift = models["barrier_index"].scale * 6.0
            rows = [
                _clone_observation(
                    o,
                    run_id="level_shift",
                    value=o.value + shift if o.channel == "barrier_index" else o.value,
                )
                for o in baseline_rows
            ]
        elif scenario.name == "cadence_gap":
            rows = [
                _clone_observation(o, run_id="cadence_gap")
                for o in baseline_rows
                if not (o.channel == "oxygen_index" and o.time_s in {3000.0, 4800.0})
            ]
        elif scenario.name == "replicate_divergence":
            shift = models["flow_index"].scale * 5.0
            rows = [
                _clone_observation(
                    o,
                    run_id="replicate_divergence",
                    value=o.value + shift
                    if o.channel == "flow_index" and o.replicate_id == "b3"
                    else o.value,
                )
                for o in baseline_rows
            ]
        elif scenario.name == "sparse":
            selected = [o for o in baseline_rows if o.channel == "barrier_index"][:3]
            rows = [_clone_observation(o, run_id="sparse") for o in selected]
        else:
            raise AssertionError(f"unhandled benchmark scenario {scenario.name}")

        ct.write_csv(case_run, rows)
        out[scenario.name] = (case_baseline, case_run)
    return out


def _pointer_get(document: Mapping[str, Any], pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must start with '/'")
    current: Any = document
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(token)]
        elif isinstance(current, Mapping):
            current = current[token]
        else:
            raise KeyError(pointer)
    return current


def _citation(report: Mapping[str, Any], pointer: str) -> dict[str, Any]:
    return {"pointer": pointer, "value": _pointer_get(report, pointer)}


def triage_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a ChipTrace report into evidence-bound, abstention-aware triage."""
    overall = str(report["overall_state"])
    citations: list[dict[str, Any]] = [_citation(report, "/overall_state")]

    if overall == "INSUFFICIENT_EVIDENCE":
        decision = "ABSTAIN"
        summary = "Evidence is insufficient for a supported QC decision; collect more observations."
    elif overall == "REVIEW":
        decision = "REVIEW"
        review_rows = [
            (idx, row)
            for idx, row in enumerate(report["channel_assessments"])
            if row["state"] == "REVIEW"
        ]
        review_rows.sort(key=lambda item: (-float(item[1]["quality_risk_score"]), str(item[1]["channel"])))
        for idx, _ in review_rows[:2]:
            citations.append(_citation(report, f"/channel_assessments/{idx}/quality_risk_score"))
            citations.append(_citation(report, f"/channel_assessments/{idx}/reasons"))
        summary = "One or more deterministic QC signals exceed the configured review boundary."
    else:
        decision = "SUPPORTED_QC"
        citations.append(_citation(report, "/max_quality_risk_score"))
        summary = "No configured QC review threshold was exceeded."

    return {
        "schema": TRIAGE_SCHEMA,
        "decision": decision,
        "summary": summary,
        "citations": citations,
        "authority_boundary": (
            "Research QC only; this output does not establish biological efficacy, "
            "clinical safety, diagnosis, or treatment suitability."
        ),
    }


def validate_citations(report: Mapping[str, Any], triage: Mapping[str, Any]) -> dict[str, Any]:
    total = 0
    valid = 0
    failures: list[str] = []
    for citation in triage.get("citations", []):
        total += 1
        pointer = str(citation.get("pointer", ""))
        try:
            actual = _pointer_get(report, pointer)
        except (KeyError, IndexError, ValueError, TypeError):
            failures.append(pointer)
            continue
        if actual == citation.get("value"):
            valid += 1
        else:
            failures.append(pointer)
    return {
        "valid": valid,
        "total": total,
        "validity": (valid / total) if total else 0.0,
        "failures": failures,
    }


def _classification_metrics(rows: Iterable[Mapping[str, Any]], prediction_key: str) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    considered = 0
    for row in rows:
        expected = str(row["expected_state"])
        if expected == "INSUFFICIENT_EVIDENCE":
            continue
        considered += 1
        positive = expected == "REVIEW"
        predicted = str(row[prediction_key]) == "REVIEW"
        if positive and predicted:
            tp += 1
        elif positive and not predicted:
            fn += 1
        elif not positive and predicted:
            fp += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    false_flag_rate = fp / (fp + tn) if fp + tn else 0.0
    return {
        "considered": considered,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "false_flag_rate": round(false_flag_rate, 6),
    }


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.999999)))
    return ordered[index]


def run_benchmark(directory: Path, *, repeats: int = 3) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    corpus = build_frozen_corpus(directory)
    records: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    citation_valid = 0
    citation_total = 0

    for scenario in SCENARIOS:
        baseline, candidate = corpus[scenario.name]
        for repeat in range(repeats):
            started = time.perf_counter_ns()
            report = ct.analyze(baseline, candidate)
            triage = triage_report(report)
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
            latencies_ms.append(elapsed_ms)

            citation_check = validate_citations(report, triage)
            citation_valid += int(citation_check["valid"])
            citation_total += int(citation_check["total"])

            records.append(
                {
                    "scenario": scenario.name,
                    "repeat": repeat + 1,
                    "expected_state": scenario.expected_state,
                    "qc_state": report["overall_state"],
                    "triage_state": "REVIEW"
                    if triage["decision"] == "REVIEW"
                    else "INSUFFICIENT_EVIDENCE"
                    if triage["decision"] == "ABSTAIN"
                    else "SUPPORTED",
                    "triage_decision": triage["decision"],
                    "report_receipt": report["receipt_sha256"],
                    "citation_check": citation_check,
                }
            )

    qc_metrics = _classification_metrics(records, "qc_state")
    triage_metrics = _classification_metrics(records, "triage_state")
    sparse = [r for r in records if r["expected_state"] == "INSUFFICIENT_EVIDENCE"]
    abstention_accuracy = (
        sum(r["triage_decision"] == "ABSTAIN" for r in sparse) / len(sparse) if sparse else 0.0
    )

    decisions_by_scenario: dict[str, set[str]] = {}
    for record in records:
        decisions_by_scenario.setdefault(str(record["scenario"]), set()).add(str(record["triage_decision"]))
    churn_cases = sum(len(decisions) > 1 for decisions in decisions_by_scenario.values())

    deterministic_evidence = {
        "schema": SCHEMA,
        "repeats": repeats,
        "scenarios": [
            {
                "name": scenario.name,
                "expected_state": scenario.expected_state,
                "description": scenario.description,
                "decisions": sorted(decisions_by_scenario[scenario.name]),
                "report_receipts": sorted(
                    {
                        str(r["report_receipt"])
                        for r in records
                        if r["scenario"] == scenario.name
                    }
                ),
            }
            for scenario in SCENARIOS
        ],
        "qc_only": qc_metrics,
        "evidence_bound_triage": {
            **triage_metrics,
            "abstention_accuracy": round(abstention_accuracy, 6),
            "citation_validity": round(citation_valid / citation_total, 6)
            if citation_total
            else 0.0,
            "decision_churn_rate": round(churn_cases / len(SCENARIOS), 6),
        },
    }

    return {
        **deterministic_evidence,
        "latency_ms": {
            "samples": len(latencies_ms),
            "median": round(float(statistics.median(latencies_ms)), 6),
            "p95": round(_percentile(latencies_ms, 0.95), 6),
            "max": round(max(latencies_ms), 6) if latencies_ms else 0.0,
        },
        "deterministic_receipt_sha256": sha256_json(deterministic_evidence),
        "authority_boundary": (
            "Synthetic benchmark floor for research QC software. It is not clinical validation, "
            "wet-lab validation, or evidence of competition rank, acceptance, or prize."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default=None, help="benchmark working directory")
    parser.add_argument("--out", required=True, help="JSON benchmark receipt path")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)

    if args.directory:
        root = Path(args.directory)
        root.mkdir(parents=True, exist_ok=True)
        result = run_benchmark(root, repeats=args.repeats)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_benchmark(Path(tmp), repeats=args.repeats)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt": result["deterministic_receipt_sha256"],
                "qc_f1": result["qc_only"]["f1"],
                "triage_f1": result["evidence_bound_triage"]["f1"],
                "citation_validity": result["evidence_bound_triage"]["citation_validity"],
                "median_ms": result["latency_ms"]["median"],
                "p95_ms": result["latency_ms"]["p95"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
