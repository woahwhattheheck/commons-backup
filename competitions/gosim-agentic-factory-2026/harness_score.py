from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

SCHEMA = "gosim-agentic-factory-readiness/v1"
POLICY_SCHEMA = "gosim-agentic-factory-score-policy/v1"
REPORT_SCHEMA = "gosim-agentic-factory-readiness-report/v1"
RUN_KEYS = {
    "schema", "task_id", "trial_id", "harness_revision", "model_label",
    "started_at", "finished_at", "input_tokens", "output_tokens", "cache_tokens",
    "wall_clock_ms", "tests_total", "tests_passed", "tests_failed",
    "task_spec_sha256", "artifact_manifest_sha256", "trace_sha256",
}
POLICY_KEYS = {
    "schema", "correctness_floor_micros", "correctness_weight_micros",
    "token_weight_micros", "time_weight_micros", "token_reference",
    "time_reference_ms", "max_correctness_drop_micros",
    "max_token_regression_bps", "max_time_regression_bps",
}
MAX_INT = (1 << 63) - 1
ONE = 1_000_000


class ContractError(ValueError):
    pass


def _no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_bytes(data: bytes) -> Any:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ContractError("JSON must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_no_dupes,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ContractError(f"non-finite JSON number: {value}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise ContractError("invalid JSON") from exc


def load_json(path: str | Path) -> Any:
    with open(path, "rb") as handle:
        return load_json_bytes(handle.read())


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("value is not canonical JSON") from exc


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _strict_int(value: Any, field: str, *, minimum: int = 0, maximum: int = MAX_INT) -> int:
    if type(value) is not int:
        raise ContractError(f"{field} must be an integer")
    if value < minimum or value > maximum:
        raise ContractError(f"{field} out of range")
    return value


def _safe_text(value: Any, field: str, *, maximum_bytes: int = 256) -> str:
    if type(value) is not str or not value:
        raise ContractError(f"{field} must be a non-empty string")
    encoded = value.encode("utf-8")
    if len(encoded) > maximum_bytes:
        raise ContractError(f"{field} is too large")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ContractError(f"{field} contains control characters")
    return value


def _hex64(value: Any, field: str) -> str:
    if type(value) is not str or len(value) != 64:
        raise ContractError(f"{field} must be 64 lowercase hex characters")
    if value != value.lower() or any(ch not in "0123456789abcdef" for ch in value):
        raise ContractError(f"{field} must be 64 lowercase hex characters")
    return value


def _utc_millis(value: Any, field: str) -> tuple[str, int]:
    if type(value) is not str or not value.endswith("Z"):
        raise ContractError(f"{field} must be RFC3339 UTC ending in Z")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{field} must be RFC3339 UTC") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise ContractError(f"{field} must be UTC")
    if dt.microsecond % 1000:
        raise ContractError(f"{field} must use millisecond precision")
    canonical = dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if value != canonical:
        raise ContractError(f"{field} must use canonical millisecond UTC")
    epoch_ms = int(dt.timestamp()) * 1000 + dt.microsecond // 1000
    return value, epoch_ms


def validate_run(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict or set(raw) != RUN_KEYS:
        raise ContractError("run keys mismatch")
    if raw["schema"] != SCHEMA:
        raise ContractError("unsupported run schema")
    run = dict(raw)
    run["task_id"] = _safe_text(raw["task_id"], "task_id")
    run["trial_id"] = _safe_text(raw["trial_id"], "trial_id")
    run["harness_revision"] = _safe_text(raw["harness_revision"], "harness_revision", maximum_bytes=128)
    run["model_label"] = _safe_text(raw["model_label"], "model_label", maximum_bytes=128)
    started, started_ms = _utc_millis(raw["started_at"], "started_at")
    finished, finished_ms = _utc_millis(raw["finished_at"], "finished_at")
    if finished_ms < started_ms:
        raise ContractError("finished_at precedes started_at")
    run["started_at"], run["finished_at"] = started, finished
    for name in (
        "input_tokens", "output_tokens", "cache_tokens", "wall_clock_ms",
        "tests_total", "tests_passed", "tests_failed",
    ):
        minimum = 1 if name in ("wall_clock_ms", "tests_total") else 0
        run[name] = _strict_int(raw[name], name, minimum=minimum)
    if finished_ms - started_ms != run["wall_clock_ms"]:
        raise ContractError("wall_clock_ms must exactly equal finished_at - started_at")
    if run["tests_passed"] + run["tests_failed"] != run["tests_total"]:
        raise ContractError("tests_passed + tests_failed must equal tests_total")
    for name in ("task_spec_sha256", "artifact_manifest_sha256", "trace_sha256"):
        run[name] = _hex64(raw[name], name)
    return run


def validate_policy(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict or set(raw) != POLICY_KEYS:
        raise ContractError("policy keys mismatch")
    if raw["schema"] != POLICY_SCHEMA:
        raise ContractError("unsupported policy schema")
    policy = dict(raw)
    for name in POLICY_KEYS - {"schema"}:
        minimum = 1 if name in ("token_reference", "time_reference_ms") else 0
        maximum = ONE if name in {
            "correctness_floor_micros", "correctness_weight_micros",
            "token_weight_micros", "time_weight_micros", "max_correctness_drop_micros",
        } else MAX_INT
        policy[name] = _strict_int(raw[name], name, minimum=minimum, maximum=maximum)
    if sum(policy[name] for name in (
        "correctness_weight_micros", "token_weight_micros", "time_weight_micros"
    )) != ONE:
        raise ContractError("score weights must sum to 1000000")
    if policy["max_token_regression_bps"] > 1_000_000 or policy["max_time_regression_bps"] > 1_000_000:
        raise ContractError("regression basis points are unreasonably large")
    return policy


def _ratio_micros(run: dict[str, Any]) -> int:
    return run["tests_passed"] * ONE // run["tests_total"]


def _total_tokens(run: dict[str, Any]) -> int:
    total = run["input_tokens"] + run["output_tokens"] + run["cache_tokens"]
    if total > MAX_INT:
        raise ContractError("combined token count out of range")
    return total


def _efficiency_micros(reference: int, observed: int) -> int:
    if observed <= 0:
        return ONE
    return min(ONE, reference * ONE // observed)


def metrics_for_run(run: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    correctness = _ratio_micros(run)
    tokens = _total_tokens(run)
    token_eff = _efficiency_micros(policy["token_reference"], tokens)
    time_eff = _efficiency_micros(policy["time_reference_ms"], run["wall_clock_ms"])
    efficiency_enabled = correctness >= policy["correctness_floor_micros"]
    readiness = correctness * policy["correctness_weight_micros"] // ONE
    if efficiency_enabled:
        readiness += token_eff * policy["token_weight_micros"] // ONE
        readiness += time_eff * policy["time_weight_micros"] // ONE
    return {
        "correctness_micros": correctness,
        "total_tokens": tokens,
        "wall_clock_ms": run["wall_clock_ms"],
        "token_efficiency_micros": token_eff,
        "time_efficiency_micros": time_eff,
        "efficiency_enabled": efficiency_enabled,
        "internal_readiness_micros": readiness,
    }


def _dominates(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ma, mb = a["metrics"], b["metrics"]
    no_worse = (
        ma["correctness_micros"] >= mb["correctness_micros"]
        and ma["total_tokens"] <= mb["total_tokens"]
        and ma["wall_clock_ms"] <= mb["wall_clock_ms"]
    )
    strict = (
        ma["correctness_micros"] > mb["correctness_micros"]
        or ma["total_tokens"] < mb["total_tokens"]
        or ma["wall_clock_ms"] < mb["wall_clock_ms"]
    )
    return no_worse and strict


def _median_int(values: list[int]) -> int:
    if not values:
        raise ContractError("median requires data")
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) // 2


def _normalize_runs(raw: Any) -> list[dict[str, Any]]:
    if type(raw) is not list:
        raise ContractError("runs must be a JSON array")
    if not raw:
        raise ContractError("run set must not be empty")
    runs = [validate_run(item) for item in raw]
    seen: dict[tuple[str, str], bytes] = {}
    for run in runs:
        identity = (run["task_id"], run["trial_id"])
        body = canonical_bytes(run)
        if identity in seen:
            if seen[identity] != body:
                raise ContractError("trial identity reused with changed bytes")
            raise ContractError("duplicate trial identity")
        seen[identity] = body
    return sorted(runs, key=lambda r: (r["task_id"], r["trial_id"]))


def _reject_cross_set_identity_reuse(candidate: list[dict[str, Any]], baseline: list[dict[str, Any]]) -> None:
    candidate_by_id = {(run["task_id"], run["trial_id"]): canonical_bytes(run) for run in candidate}
    for run in baseline:
        identity = (run["task_id"], run["trial_id"])
        if identity not in candidate_by_id:
            continue
        if candidate_by_id[identity] != canonical_bytes(run):
            raise ContractError("trial identity reused with changed bytes across candidate and baseline")


def _task_generations(entries: list[dict[str, Any]]) -> dict[str, tuple[str, int]]:
    generations: dict[str, tuple[str, int]] = {}
    for entry in entries:
        run = entry["run"]
        task_id = run["task_id"]
        generation = (run["task_spec_sha256"], run["tests_total"])
        prior = generations.get(task_id)
        if prior is not None and prior != generation:
            raise ContractError("task_id spans multiple task generations")
        generations[task_id] = generation
    return generations


def _configuration_groups(entries: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entry in entries:
        run = entry["run"]
        key = (run["harness_revision"], run["model_label"])
        groups.setdefault(key, []).append(entry)
    return groups


def _configuration_ref(key: tuple[str, str]) -> dict[str, str]:
    return {"harness_revision": key[0], "model_label": key[1]}


def _single_configuration(
    entries: list[dict[str, Any]], label: str
) -> tuple[tuple[str, str], list[dict[str, Any]]]:
    groups = _configuration_groups(entries)
    if len(groups) != 1:
        raise ContractError(f"{label} must contain exactly one harness/model configuration")
    return next(iter(groups.items()))


def _best_by_task(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        task = entry["run"]["task_id"]
        key = (
            -entry["metrics"]["correctness_micros"],
            entry["metrics"]["total_tokens"],
            entry["metrics"]["wall_clock_ms"],
            entry["run"]["trial_id"],
        )
        current = result.get(task)
        if current is None:
            result[task] = entry
            continue
        current_key = (
            -current["metrics"]["correctness_micros"],
            current["metrics"]["total_tokens"],
            current["metrics"]["wall_clock_ms"],
            current["run"]["trial_id"],
        )
        if key < current_key:
            result[task] = entry
    return result


def _regression_gate_for_configuration(
    candidate_entries: list[dict[str, Any]],
    baseline_entries: list[dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    candidate_generations = _task_generations(candidate_entries)
    baseline_generations = _task_generations(baseline_entries)
    cand, base = _best_by_task(candidate_entries), _best_by_task(baseline_entries)
    failures: list[dict[str, Any]] = []
    for task_id in sorted(base):
        if task_id not in cand:
            failures.append({"task_id": task_id, "reason": "MISSING_CANDIDATE_TASK"})
            continue
        if candidate_generations[task_id] != baseline_generations[task_id]:
            failures.append({"task_id": task_id, "reason": "TASK_GENERATION_MISMATCH"})
            continue
        cm, bm = cand[task_id]["metrics"], base[task_id]["metrics"]
        if cm["correctness_micros"] + policy["max_correctness_drop_micros"] < bm["correctness_micros"]:
            failures.append({"task_id": task_id, "reason": "CORRECTNESS_REGRESSION"})
            continue
        if cm["correctness_micros"] == bm["correctness_micros"]:
            if cm["total_tokens"] * 10_000 > bm["total_tokens"] * (10_000 + policy["max_token_regression_bps"]):
                failures.append({"task_id": task_id, "reason": "TOKEN_REGRESSION_AT_EQUAL_CORRECTNESS"})
            if cm["wall_clock_ms"] * 10_000 > bm["wall_clock_ms"] * (10_000 + policy["max_time_regression_bps"]):
                failures.append({"task_id": task_id, "reason": "TIME_REGRESSION_AT_EQUAL_CORRECTNESS"})
    return {"passed": not failures, "failures": failures}


def regression_gate(
    candidate_entries: list[dict[str, Any]],
    baseline_entries: list[dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    baseline_key, baseline_group = _single_configuration(baseline_entries, "baseline")
    candidate_groups = _configuration_groups(candidate_entries)
    configuration_results: list[dict[str, Any]] = []
    passing_configurations: list[dict[str, str]] = []
    for key in sorted(candidate_groups):
        result = _regression_gate_for_configuration(candidate_groups[key], baseline_group, policy)
        configuration_results.append({
            **_configuration_ref(key),
            "passed": result["passed"],
            "failures": result["failures"],
        })
        if result["passed"]:
            passing_configurations.append(_configuration_ref(key))

    passed = bool(passing_configurations)
    if passed:
        failures: list[dict[str, Any]] = []
    elif len(configuration_results) == 1:
        failures = configuration_results[0]["failures"]
    else:
        failures = [{"task_id": "*", "reason": "NO_CANDIDATE_CONFIGURATION_PASSED"}]

    return {
        "passed": passed,
        "failures": failures,
        "baseline_configuration": _configuration_ref(baseline_key),
        "configuration_results": configuration_results,
        "passing_configurations": passing_configurations,
    }


def compile_report(runs_raw: Any, policy_raw: Any, baseline_raw: Any | None = None) -> dict[str, Any]:
    runs = _normalize_runs(runs_raw)
    policy = validate_policy(policy_raw)
    entries = [{"run": run, "metrics": metrics_for_run(run, policy)} for run in runs]
    _task_generations(entries)

    by_task: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        by_task.setdefault(entry["run"]["task_id"], []).append(entry)
    for task_entries in by_task.values():
        for entry in task_entries:
            entry["pareto"] = not any(
                other is not entry and _dominates(other, entry) for other in task_entries
            )

    entries.sort(key=lambda e: (
        e["run"]["task_id"], -e["metrics"]["correctness_micros"],
        e["metrics"]["total_tokens"], e["metrics"]["wall_clock_ms"], e["run"]["trial_id"],
    ))

    configs = _configuration_groups(entries)
    summaries = []
    for harness_revision, model_label in sorted(configs):
        group = configs[(harness_revision, model_label)]
        c = [e["metrics"]["correctness_micros"] for e in group]
        t = [e["metrics"]["total_tokens"] for e in group]
        w = [e["metrics"]["wall_clock_ms"] for e in group]
        summaries.append({
            "harness_revision": harness_revision,
            "model_label": model_label,
            "trials": len(group),
            "median_correctness_micros": _median_int(c),
            "worst_correctness_micros": min(c),
            "median_total_tokens": _median_int(t),
            "worst_total_tokens": max(t),
            "median_wall_clock_ms": _median_int(w),
            "worst_wall_clock_ms": max(w),
        })

    baseline_runs = None
    gate = None
    if baseline_raw is not None:
        baseline_runs = _normalize_runs(baseline_raw)
        _reject_cross_set_identity_reuse(runs, baseline_runs)
        baseline_entries = [{"run": run, "metrics": metrics_for_run(run, policy)} for run in baseline_runs]
        gate = regression_gate(entries, baseline_entries, policy)

    report_core = {
        "schema": REPORT_SCHEMA,
        "disclaimer": "Internal readiness score only; not an official GOSIM score and not a prediction of organizer ranking.",
        "policy": policy,
        "entries": entries,
        "configuration_summaries": summaries,
        "regression_gate": gate,
    }
    receipt_payload = {
        "policy": policy, "runs": runs, "baseline_runs": baseline_runs, "report_core": report_core,
    }
    return {**report_core, "receipt_sha256": sha256_json(receipt_payload)}


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GOSIM Agentic Factory — Internal Readiness Report",
        "",
        f"> {report['disclaimer']}",
        "",
        f"Receipt: `{report['receipt_sha256']}`",
        "",
        "## Trials",
        "",
        "| Task | Trial | Model | Correctness | Tokens | Time ms | Pareto | Internal score |",
        "|---|---|---|---:|---:|---:|:---:|---:|",
    ]
    for entry in report["entries"]:
        run, metrics = entry["run"], entry["metrics"]
        lines.append(
            f"| {run['task_id']} | {run['trial_id']} | {run['model_label']} | "
            f"{metrics['correctness_micros']}/1000000 | {metrics['total_tokens']} | "
            f"{metrics['wall_clock_ms']} | {'yes' if entry['pareto'] else 'no'} | "
            f"{metrics['internal_readiness_micros']} |"
        )
    lines += ["", "## Configuration summaries", ""]
    for summary in report["configuration_summaries"]:
        lines.append(
            f"- harness `{summary['harness_revision']}` / model `{summary['model_label']}`: {summary['trials']} trial(s); "
            f"median correctness {summary['median_correctness_micros']}/1000000; "
            f"worst correctness {summary['worst_correctness_micros']}/1000000; "
            f"median tokens {summary['median_total_tokens']}; worst tokens {summary['worst_total_tokens']}; "
            f"median time {summary['median_wall_clock_ms']} ms; worst time {summary['worst_wall_clock_ms']} ms."
        )
    if report["regression_gate"] is not None:
        lines += ["", "## Regression gate", ""]
        gate = report["regression_gate"]
        base = gate["baseline_configuration"]
        lines.append(
            f"- Baseline: harness `{base['harness_revision']}` / model `{base['model_label']}`"
        )
        lines.append(f"- Result: **{'PASS' if gate['passed'] else 'FAIL'}**")
        for result in gate["configuration_results"]:
            lines.append(
                f"- Candidate harness `{result['harness_revision']}` / model `{result['model_label']}`: "
                f"**{'PASS' if result['passed'] else 'FAIL'}**"
            )
            for failure in result["failures"]:
                lines.append(f"  - `{failure['task_id']}`: `{failure['reason']}`")
    return "\n".join(lines) + "\n"


def verify_report(runs_raw: Any, policy_raw: Any, report_raw: Any, baseline_raw: Any | None = None) -> bool:
    return canonical_bytes(compile_report(runs_raw, policy_raw, baseline_raw)) == canonical_bytes(report_raw)


def _write_new(path: str | Path, data: bytes) -> None:
    with open(path, "xb") as handle:
        handle.write(data)


def _command_compile(args: argparse.Namespace) -> int:
    runs = load_json(args.runs)
    policy = load_json(args.policy)
    baseline = load_json(args.baseline) if args.baseline else None
    report = compile_report(runs, policy, baseline)
    if report["regression_gate"] is not None and not report["regression_gate"]["passed"]:
        return 2
    _write_new(args.output_json, canonical_bytes(report) + b"\n")
    _write_new(args.output_md, render_markdown(report).encode("utf-8"))
    return 0


def _command_verify(args: argparse.Namespace) -> int:
    runs = load_json(args.runs)
    policy = load_json(args.policy)
    baseline = load_json(args.baseline) if args.baseline else None
    report = load_json(args.report)
    if not verify_report(runs, policy, report, baseline):
        raise ContractError("report verification failed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline GOSIM Agentic Factory readiness scorer")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("--runs", required=True)
    compile_cmd.add_argument("--policy", required=True)
    compile_cmd.add_argument("--baseline")
    compile_cmd.add_argument("--output-json", required=True)
    compile_cmd.add_argument("--output-md", required=True)
    compile_cmd.set_defaults(func=_command_compile)
    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("--runs", required=True)
    verify_cmd.add_argument("--policy", required=True)
    verify_cmd.add_argument("--baseline")
    verify_cmd.add_argument("--report", required=True)
    verify_cmd.set_defaults(func=_command_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ContractError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
