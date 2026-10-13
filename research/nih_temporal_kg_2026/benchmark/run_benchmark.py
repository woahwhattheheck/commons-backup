from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from temporal_evidence import EvidenceEvent, Fact, TemporalEvidenceError, TemporalEvidenceGraph, canonical_json, digest_json

SCHEMA = "temporal-kg-benchmark/v1"
RESULT_SCHEMA = "temporal-kg-benchmark-result/v1"
DEFAULT_CASES = HERE / "cases.json"


class BenchmarkError(ValueError):
    pass


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json_strict(path: Path) -> Any:
    from temporal_evidence import strict_json_loads
    return strict_json_loads(path.read_text(encoding="utf-8"))


def _validate_fact_record(record: Mapping[str, Any]) -> None:
    required = {"name", "subject", "predicate", "object", "valid_from", "valid_to", "observed_at", "source_id", "source_sha256", "confidence"}
    if set(record) != required:
        raise BenchmarkError(f"fact fields mismatch: expected {sorted(required)}, got {sorted(record)}")
    if not isinstance(record["name"], str) or not record["name"].strip():
        raise BenchmarkError("fact name must be a non-empty string")
    Fact.create(**{k: record[k] for k in required if k != "name"})


def _validate_event_record(record: Mapping[str, Any], fact_names: set[str]) -> None:
    required = {"action", "target", "observed_at", "source_id", "source_sha256"}
    optional = {"replacement"}
    if not required <= set(record) or set(record) - (required | optional):
        raise BenchmarkError(f"event fields mismatch: {sorted(record)}")
    if record["target"] not in fact_names:
        raise BenchmarkError(f"event target {record['target']!r} is not a fact name")
    if record["action"] == "supersede":
        if record.get("replacement") not in fact_names:
            raise BenchmarkError("supersede replacement must name an existing fact")
    elif record["action"] == "retract":
        if "replacement" in record:
            raise BenchmarkError("retract event must not have replacement")
    else:
        raise BenchmarkError("event action must be retract or supersede")


def validate_dataset(dataset: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(dataset, Mapping) or dataset.get("schema") != SCHEMA:
        raise BenchmarkError(f"dataset schema must be {SCHEMA}")
    if set(dataset) != {"schema", "description", "cases"}:
        raise BenchmarkError("dataset top-level fields are fixed")
    if not isinstance(dataset["description"], str) or not dataset["description"].strip():
        raise BenchmarkError("dataset description is required")
    cases = dataset["cases"]
    if not isinstance(cases, list) or len(cases) < 12:
        raise BenchmarkError("benchmark requires at least 12 cases")
    ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for raw in cases:
        if not isinstance(raw, Mapping):
            raise BenchmarkError("each case must be an object")
        required = {"id", "family", "error_class", "mode", "facts", "events", "query", "expected"}
        if set(raw) != required:
            raise BenchmarkError(f"case fields mismatch for {raw.get('id')!r}")
        case_id = raw["id"]
        if not isinstance(case_id, str) or not case_id.strip() or case_id in ids:
            raise BenchmarkError(f"case id must be unique and non-empty: {case_id!r}")
        ids.add(case_id)
        if raw["mode"] not in {"snapshot", "path"}:
            raise BenchmarkError(f"unsupported mode in {case_id}")
        if not isinstance(raw["family"], str) or not raw["family"].strip():
            raise BenchmarkError(f"family missing in {case_id}")
        if not isinstance(raw["error_class"], str) or not raw["error_class"].strip():
            raise BenchmarkError(f"error_class missing in {case_id}")
        if not isinstance(raw["facts"], list) or not raw["facts"]:
            raise BenchmarkError(f"facts missing in {case_id}")
        names: set[str] = set()
        for fact in raw["facts"]:
            if not isinstance(fact, Mapping):
                raise BenchmarkError(f"fact must be an object in {case_id}")
            _validate_fact_record(fact)
            if fact["name"] in names:
                raise BenchmarkError(f"duplicate fact name {fact['name']!r} in {case_id}")
            names.add(fact["name"])
        if not isinstance(raw["events"], list):
            raise BenchmarkError(f"events must be a list in {case_id}")
        for event in raw["events"]:
            if not isinstance(event, Mapping):
                raise BenchmarkError(f"event must be an object in {case_id}")
            _validate_event_record(event, names)
        if not isinstance(raw["query"], Mapping) or not isinstance(raw["expected"], Mapping):
            raise BenchmarkError(f"query/expected must be objects in {case_id}")
        if raw["mode"] == "snapshot":
            required_query = {"valid_at", "known_at", "subject", "predicate"}
            if set(raw["query"]) != required_query or set(raw["expected"]) != {"objects"}:
                raise BenchmarkError(f"snapshot query/expected shape mismatch in {case_id}")
            objects = raw["expected"]["objects"]
            if not isinstance(objects, list) or objects != sorted(set(objects)) or not all(isinstance(x, str) for x in objects):
                raise BenchmarkError(f"snapshot expected objects must be sorted unique strings in {case_id}")
        else:
            required_query = {"start", "goal", "earliest", "latest", "known_at", "predicates", "max_hops"}
            if set(raw["query"]) != required_query or set(raw["expected"]) != {"path_exists"}:
                raise BenchmarkError(f"path query/expected shape mismatch in {case_id}")
            if not isinstance(raw["expected"]["path_exists"], bool):
                raise BenchmarkError(f"path_exists must be boolean in {case_id}")
            predicates = raw["query"]["predicates"]
            if not isinstance(predicates, list) or predicates != sorted(set(predicates)):
                raise BenchmarkError(f"path predicates must be sorted unique strings in {case_id}")
        normalized.append(dict(raw))
    normalized.sort(key=lambda item: item["id"])
    return {"schema": SCHEMA, "description": dataset["description"], "cases": normalized}


def load_dataset(path: Path | str = DEFAULT_CASES) -> dict[str, Any]:
    return validate_dataset(_load_json_strict(Path(path)))


def _build_facts(case: Mapping[str, Any]) -> tuple[dict[str, Fact], list[Fact]]:
    by_name: dict[str, Fact] = {}
    facts: list[Fact] = []
    for raw in case["facts"]:
        kwargs = {k: raw[k] for k in raw if k != "name"}
        fact = Fact.create(**kwargs)
        by_name[raw["name"]] = fact
        facts.append(fact)
    return by_name, facts


def _all_events(case: Mapping[str, Any], by_name: Mapping[str, Fact]) -> list[EvidenceEvent]:
    events: list[EvidenceEvent] = []
    for raw in case["events"]:
        kwargs = dict(
            action=raw["action"],
            target_fact_id=by_name[raw["target"]].fact_id,
            observed_at=raw["observed_at"],
            source_id=raw["source_id"],
            source_sha256=raw["source_sha256"],
        )
        if raw["action"] == "supersede":
            kwargs["replacement_fact_id"] = by_name[raw["replacement"]].fact_id
        events.append(EvidenceEvent.create(**kwargs))
    return events


def _static_final_facts(case: Mapping[str, Any]) -> list[Fact]:
    by_name, facts = _build_facts(case)
    inactive = {event.target_fact_id for event in _all_events(case, by_name)}
    return [fact for fact in facts if fact.fact_id not in inactive]


def static_answer(case: Mapping[str, Any]) -> dict[str, Any]:
    facts = _static_final_facts(case)
    query = case["query"]
    if case["mode"] == "snapshot":
        matching = [fact for fact in facts if fact.subject == query["subject"] and fact.predicate == query["predicate"]]
        if not matching:
            return {"objects": []}
        latest = max(fact.observed_at for fact in matching)
        objects = sorted({fact.object for fact in matching if fact.observed_at == latest})
        return {"objects": objects}

    allowed = set(query["predicates"])
    outgoing: dict[str, list[str]] = {}
    for fact in facts:
        if fact.predicate in allowed:
            outgoing.setdefault(fact.subject, []).append(fact.object)
    for values in outgoing.values():
        values.sort()
    start, goal = query["start"], query["goal"]
    if start == goal:
        return {"path_exists": True}
    queue = deque([(start, 0)])
    seen = {start}
    while queue:
        node, hops = queue.popleft()
        if hops >= query["max_hops"]:
            continue
        for nxt in outgoing.get(node, []):
            if nxt == goal:
                return {"path_exists": True}
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, hops + 1))
    return {"path_exists": False}


def temporal_answer(case: Mapping[str, Any]) -> dict[str, Any]:
    by_name, facts = _build_facts(case)
    graph = TemporalEvidenceGraph()
    for fact in facts:
        graph.add_fact(fact)
    for event in sorted(_all_events(case, by_name), key=lambda item: (item.observed_at, item.event_id)):
        graph.add_event(event)
    query = case["query"]
    if case["mode"] == "snapshot":
        active = graph.active_facts(
            valid_at=query["valid_at"],
            known_at=query["known_at"],
            subject=query["subject"],
            predicate=query["predicate"],
        )
        return {"objects": sorted({fact.object for fact in active})}
    path = graph.time_respecting_path(
        query["start"],
        query["goal"],
        earliest=query["earliest"],
        latest=query["latest"],
        known_at=query["known_at"],
        predicates=query["predicates"],
        max_hops=query["max_hops"],
    )
    return {"path_exists": path is not None}


def _system_metrics(rows: list[dict[str, Any]], system: str) -> dict[str, Any]:
    total = len(rows)
    correct = sum(1 for row in rows if row[system]["correct"])
    classes = sorted({row["error_class"] for row in rows})
    errors_by_class = {name: sum(1 for row in rows if row["error_class"] == name and not row[system]["correct"]) for name in classes}
    totals_by_class = {name: sum(1 for row in rows if row["error_class"] == name) for name in classes}
    correct_by_class = {name: totals_by_class[name] - errors_by_class[name] for name in classes}
    control_total = totals_by_class.get("control", 0)
    control_correct = correct_by_class.get("control", 0)
    abstention_rows = [row for row in rows if row["expected"] in ({"objects": []}, {"path_exists": False})]
    abstention_correct = sum(1 for row in abstention_rows if row[system]["correct"])
    return {
        "total": total,
        "correct": correct,
        "errors": total - correct,
        "exact_accuracy": correct / total,
        "totals_by_class": totals_by_class,
        "correct_by_class": correct_by_class,
        "errors_by_class": errors_by_class,
        "control_accuracy": (control_correct / control_total) if control_total else None,
        "abstention_total": len(abstention_rows),
        "abstention_correct": abstention_correct,
    }


def _file_digest(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def run_benchmark(dataset_path: Path | str = DEFAULT_CASES) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    dataset_digest = digest_json(dataset)
    rows: list[dict[str, Any]] = []
    static_ns = 0
    temporal_ns = 0
    for case in dataset["cases"]:
        start = time.perf_counter_ns()
        static = static_answer(case)
        static_ns += time.perf_counter_ns() - start
        start = time.perf_counter_ns()
        temporal = temporal_answer(case)
        temporal_ns += time.perf_counter_ns() - start
        expected = case["expected"]
        rows.append({
            "id": case["id"],
            "family": case["family"],
            "error_class": case["error_class"],
            "mode": case["mode"],
            "expected": expected,
            "static": {"answer": static, "correct": static == expected},
            "temporal": {"answer": temporal, "correct": temporal == expected},
        })
    static_metrics = _system_metrics(rows, "static")
    temporal_metrics = _system_metrics(rows, "temporal")
    adversarial_classes = [name for name in temporal_metrics["totals_by_class"] if name != "control"]
    static_adv_errors = sum(static_metrics["errors_by_class"][name] for name in adversarial_classes)
    temporal_adv_errors = sum(temporal_metrics["errors_by_class"][name] for name in adversarial_classes)
    no_control_regression = temporal_metrics["control_accuracy"] is not None and temporal_metrics["control_accuracy"] >= static_metrics["control_accuracy"]
    promotion_passed = temporal_adv_errors < static_adv_errors and no_control_regression
    semantic = {
        "schema": RESULT_SCHEMA,
        "dataset_sha256": dataset_digest,
        "implementations": {
            "benchmark_sha256": _file_digest(Path(__file__)),
            "temporal_evidence_sha256": _file_digest(ROOT / "temporal_evidence.py"),
        },
        "cases": rows,
        "metrics": {"static": static_metrics, "temporal": temporal_metrics},
        "promotion": {
            "passed": promotion_passed,
            "falsifier_triggered": not promotion_passed,
            "static_adversarial_errors": static_adv_errors,
            "temporal_adversarial_errors": temporal_adv_errors,
            "control_regression": not no_control_regression,
            "rule": "promote only if temporal reduces adversarial temporal errors without lowering control accuracy",
        },
    }
    receipt_sha256 = digest_json(semantic)
    return {
        **semantic,
        "runtime_ns": {"static": static_ns, "temporal": temporal_ns},
        "receipt_sha256": receipt_sha256,
    }


def verify_result(result: Mapping[str, Any]) -> bool:
    expected = {"schema", "dataset_sha256", "implementations", "cases", "metrics", "promotion", "runtime_ns", "receipt_sha256"}
    if not isinstance(result, Mapping) or set(result) != expected or result.get("schema") != RESULT_SCHEMA:
        return False
    try:
        if not isinstance(result["runtime_ns"], Mapping) or set(result["runtime_ns"]) != {"static", "temporal"}:
            return False
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in result["runtime_ns"].values()):
            return False
        semantic = {key: result[key] for key in result if key not in {"runtime_ns", "receipt_sha256"}}
        return digest_json(semantic) == result["receipt_sha256"]
    except (TemporalEvidenceError, TypeError, KeyError):
        return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the synthetic static-vs-bitemporal benchmark")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    result = run_benchmark(args.cases)
    rendered = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
