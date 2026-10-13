#!/usr/bin/env python3
"""Challenge-agnostic case-level benchmark summary for Orchestrate-style agents."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable

ACTIONS = {"answer", "escalate"}


class BenchmarkError(ValueError):
    pass


def _require_bool(record: dict[str, Any], key: str, *, default: bool | None = None) -> bool:
    if key not in record:
        if default is None:
            raise BenchmarkError(f"missing required boolean field {key!r}")
        return default
    value = record[key]
    if not isinstance(value, bool):
        raise BenchmarkError(f"{key!r} must be boolean")
    return value


def _require_action(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if value not in ACTIONS:
        raise BenchmarkError(f"{key!r} must be one of {sorted(ACTIONS)}")
    return str(value)


def _nonnegative_number(record: dict[str, Any], key: str) -> float:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BenchmarkError(f"{key!r} must be a number")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise BenchmarkError(f"{key!r} must be finite and non-negative")
    return value


def _nonnegative_int(record: dict[str, Any], key: str, default: int = 0) -> int:
    value = record.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BenchmarkError(f"{key!r} must be a non-negative integer")
    return value


def _string_set(record: dict[str, Any], key: str) -> set[str]:
    value = record.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise BenchmarkError(f"{key!r} must be a list of strings")
    return {item for item in value if item}


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise BenchmarkError(f"{path}:{lineno}: invalid JSON: {exc.msg}") from exc
            if not isinstance(record, dict):
                raise BenchmarkError(f"{path}:{lineno}: each line must be a JSON object")

            case_id = record.get("case_id")
            if not isinstance(case_id, str) or not case_id.strip():
                raise BenchmarkError(f"{path}:{lineno}: case_id must be a non-empty string")
            if case_id in seen:
                raise BenchmarkError(f"{path}:{lineno}: duplicate case_id {case_id!r}")
            seen.add(case_id)

            expected = _require_action(record, "expected_action")
            actual = _require_action(record, "actual_action")
            latency_ms = _nonnegative_number(record, "latency_ms")
            retries = _nonnegative_int(record, "retries")

            answer_correct = record.get("answer_correct")
            if answer_correct is not None and not isinstance(answer_correct, bool):
                raise BenchmarkError(f"{path}:{lineno}: 'answer_correct' must be boolean")
            if expected == "answer" and actual == "answer" and answer_correct is None:
                raise BenchmarkError(
                    f"{path}:{lineno}: answer_correct is required for answer->answer cases"
                )

            failure_injected = _require_bool(record, "failure_injected", default=False)
            recovered = _require_bool(record, "recovered", default=False)
            if recovered and not failure_injected:
                raise BenchmarkError(
                    f"{path}:{lineno}: recovered=true requires failure_injected=true"
                )

            injection_case = _require_bool(record, "injection_case", default=False)
            injection_contained = record.get("injection_contained")
            if injection_contained is not None and not isinstance(injection_contained, bool):
                raise BenchmarkError(
                    f"{path}:{lineno}: 'injection_contained' must be boolean"
                )
            if injection_case and injection_contained is None:
                raise BenchmarkError(
                    f"{path}:{lineno}: injection_contained is required for injection cases"
                )

            tokens = record.get("tokens")
            if tokens is not None:
                if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
                    raise BenchmarkError(
                        f"{path}:{lineno}: 'tokens' must be a non-negative integer"
                    )

            gold = _string_set(record, "gold_evidence")
            used = _string_set(record, "used_evidence")

            cases.append(
                {
                    "case_id": case_id,
                    "expected_action": expected,
                    "actual_action": actual,
                    "answer_correct": answer_correct,
                    "latency_ms": latency_ms,
                    "retries": retries,
                    "failure_injected": failure_injected,
                    "recovered": recovered,
                    "injection_case": injection_case,
                    "injection_contained": injection_contained,
                    "tokens": tokens,
                    "gold_evidence": gold,
                    "used_evidence": used,
                }
            )
    if not cases:
        raise BenchmarkError(f"{path}: no benchmark cases")
    return cases


def _quantile(values: Iterable[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise BenchmarkError("cannot compute quantile of empty input")
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return float(ordered[lo])
    weight = position - lo
    return float(ordered[lo] * (1 - weight) + ordered[hi] * weight)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases)
    false_reply = false_escalation = wrong_answer = correct_escalation = 0
    successes = 0

    for case in cases:
        expected = case["expected_action"]
        actual = case["actual_action"]
        if expected == "escalate":
            if actual == "escalate":
                correct_escalation += 1
                successes += 1
            else:
                false_reply += 1
        elif actual == "escalate":
            false_escalation += 1
        elif case["answer_correct"]:
            successes += 1
        else:
            wrong_answer += 1

    retry_cases = sum(case["retries"] > 0 for case in cases)
    total_retries = sum(case["retries"] for case in cases)

    injected = [case for case in cases if case["failure_injected"]]
    recovered = sum(case["recovered"] for case in injected)

    injections = [case for case in cases if case["injection_case"]]
    contained = sum(case["injection_contained"] is True for case in injections)

    gold_total = sum(len(case["gold_evidence"]) for case in cases)
    gold_hits = sum(
        len(case["gold_evidence"] & case["used_evidence"]) for case in cases
    )

    token_cases = [case["tokens"] for case in cases if case["tokens"] is not None]
    latencies = [case["latency_ms"] for case in cases]

    return {
        "schema_version": 1,
        "cases": total,
        "success": {
            "count": successes,
            "rate": _ratio(successes, total),
            "false_reply": false_reply,
            "false_escalation": false_escalation,
            "wrong_answer": wrong_answer,
            "correct_escalation": correct_escalation,
        },
        "latency_ms": {
            "p50": _quantile(latencies, 0.50),
            "p95": _quantile(latencies, 0.95),
            "max": max(latencies),
        },
        "retries": {
            "cases_with_retry": retry_cases,
            "case_rate": _ratio(retry_cases, total),
            "total": total_retries,
        },
        "failure_recovery": {
            "injected_cases": len(injected),
            "recovered": recovered,
            "rate": _ratio(recovered, len(injected)),
        },
        "prompt_injection": {
            "cases": len(injections),
            "contained": contained,
            "containment_rate": _ratio(contained, len(injections)),
        },
        "retrieval": {
            "gold_items": gold_total,
            "hits": gold_hits,
            "micro_recall": _ratio(gold_hits, gold_total),
        },
        "tokens": {
            "reported_cases": len(token_cases),
            "total": sum(token_cases),
            "mean": (sum(token_cases) / len(token_cases)) if token_cases else None,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSONL benchmark cases")
    parser.add_argument("--output", type=Path, help="write pretty JSON to this path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = summarize(load_cases(args.input))
    except (BenchmarkError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
