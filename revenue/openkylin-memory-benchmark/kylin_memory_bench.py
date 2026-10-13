#!/usr/bin/env python3
"""Deterministic long-term-memory benchmark for agent evidence bundles.

The scorer intentionally requires no model/API access.  A dataset declares small,
explainable assertions over four evidence channels (dialogue, memory, actions,
files).  Agent adapters can export those channels as JSON and receive comparable
scores with a reason for every assertion.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

DIMENSIONS = (
    "long_term_retention",
    "memory_recall",
    "dynamic_update",
    "similar_item_discrimination",
    "boundary_recognition",
    "task_reuse",
)
CHANNELS = ("dialogue", "memory", "actions", "files")
ASSERTION_TYPES = ("contains", "not_contains", "latest_equals", "ordered_contains")


def _read_json_with_sha(path: Path) -> tuple[Any, str]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc
    return payload, hashlib.sha256(raw).hexdigest()


def _read_json(path: Path) -> Any:
    return _read_json_with_sha(path)[0]


def _read_dataset_with_sha(path: Path) -> tuple[list[dict[str, Any]], str]:
    scenarios: list[dict[str, Any]] = []
    try:
        file_bytes = path.read_bytes()
        lines = file_bytes.decode("utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read dataset {path}: {exc}") from exc
    for line_no, raw in enumerate(lines, 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"dataset line {line_no}: invalid JSON: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"dataset line {line_no}: scenario must be an object")
        scenarios.append(row)
    validate_dataset(scenarios)
    return scenarios, hashlib.sha256(file_bytes).hexdigest()


def _read_dataset(path: Path) -> list[dict[str, Any]]:
    return _read_dataset_with_sha(path)[0]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _nonblank(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonblank string")
    return value


def _weight(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("assertion weight must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError("assertion weight must be finite and > 0")
    return result


def validate_dataset(scenarios: list[dict[str, Any]]) -> None:
    if not scenarios:
        raise ValueError("dataset must contain at least one scenario")
    seen: set[str] = set()
    dims: set[str] = set()
    for idx, row in enumerate(scenarios):
        sid = _nonblank(row.get("id"), f"scenario[{idx}].id")
        if sid in seen:
            raise ValueError(f"duplicate scenario id: {sid}")
        seen.add(sid)
        dimension = row.get("dimension")
        if dimension not in DIMENSIONS:
            raise ValueError(f"scenario {sid}: unsupported dimension {dimension!r}")
        dims.add(dimension)
        assertions = row.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            raise ValueError(f"scenario {sid}: assertions must be a non-empty list")
        for aidx, assertion in enumerate(assertions):
            if not isinstance(assertion, dict):
                raise ValueError(f"scenario {sid} assertion[{aidx}] must be an object")
            atype = assertion.get("type")
            if atype not in ASSERTION_TYPES:
                raise ValueError(f"scenario {sid}: unsupported assertion type {atype!r}")
            channel = assertion.get("channel")
            if channel not in CHANNELS:
                raise ValueError(f"scenario {sid}: unsupported channel {channel!r}")
            if atype == "ordered_contains":
                values = assertion.get("values")
                if not isinstance(values, list) or not values:
                    raise ValueError(f"scenario {sid}: ordered_contains needs non-empty values")
                for value in values:
                    _nonblank(value, f"scenario {sid} ordered value")
            else:
                _nonblank(assertion.get("value"), f"scenario {sid} assertion value")
            _weight(assertion.get("weight", 1.0))
    missing = sorted(set(DIMENSIONS) - dims)
    if missing:
        raise ValueError("dataset is missing required dimensions: " + ", ".join(missing))


def validate_evidence(payload: dict[str, Any], scenario_ids: set[str]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("evidence root must be an object")
    _nonblank(payload.get("agent"), "agent")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    seen: set[str] = set()
    for idx, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"record[{idx}] must be an object")
        sid = _nonblank(record.get("scenario_id"), f"record[{idx}].scenario_id")
        if sid not in scenario_ids:
            raise ValueError(f"record[{idx}] references unknown scenario: {sid}")
        if sid in seen:
            raise ValueError(f"duplicate evidence record for scenario: {sid}")
        seen.add(sid)
        channels = record.get("channels")
        if not isinstance(channels, dict):
            raise ValueError(f"record {sid}: channels must be an object")
        unknown = sorted(set(channels) - set(CHANNELS))
        if unknown:
            raise ValueError(f"record {sid}: unknown channels: {', '.join(unknown)}")
        for channel, items in channels.items():
            if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
                raise ValueError(f"record {sid}: channel {channel} must be a string list")


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains(items: Iterable[str], needle: str) -> bool:
    n = _norm(needle)
    return any(n in _norm(item) for item in items)


def _assertion_result(assertion: dict[str, Any], items: list[str]) -> tuple[bool, str]:
    atype = assertion["type"]
    if atype == "contains":
        value = assertion["value"]
        ok = _contains(items, value)
        return ok, ("found" if ok else "missing") + f" literal {value!r}"
    if atype == "not_contains":
        value = assertion["value"]
        ok = not _contains(items, value)
        return ok, ("excluded" if ok else "unexpectedly found") + f" literal {value!r}"
    if atype == "latest_equals":
        value = _norm(assertion["value"])
        latest = _norm(items[-1]) if items else ""
        ok = latest == value
        shown = items[-1] if items else "<empty>"
        return ok, f"latest={shown!r}, expected={assertion['value']!r}"
    if atype == "ordered_contains":
        values = assertion["values"]
        cursor = 0
        matched = 0
        for item in items:
            if cursor < len(values) and _norm(values[cursor]) in _norm(item):
                cursor += 1
                matched += 1
        ok = cursor == len(values)
        return ok, f"matched {matched}/{len(values)} ordered literals"
    raise AssertionError(atype)


def score(scenarios: list[dict[str, Any]], evidence: dict[str, Any]) -> dict[str, Any]:
    scenario_ids = {row["id"] for row in scenarios}
    validate_evidence(evidence, scenario_ids)
    record_map = {row["scenario_id"]: row for row in evidence["records"]}
    dim_earned: dict[str, float] = defaultdict(float)
    dim_total: dict[str, float] = defaultdict(float)
    scenario_results: list[dict[str, Any]] = []

    for scenario in scenarios:
        sid = scenario["id"]
        record = record_map.get(sid, {"channels": {}})
        results = []
        earned = total = 0.0
        for assertion in scenario["assertions"]:
            weight = _weight(assertion.get("weight", 1.0))
            items = record.get("channels", {}).get(assertion["channel"], [])
            ok, reason = _assertion_result(assertion, items)
            total += weight
            if ok:
                earned += weight
            results.append({
                "type": assertion["type"],
                "channel": assertion["channel"],
                "weight": weight,
                "passed": ok,
                "reason": reason,
            })
        dimension = scenario["dimension"]
        dim_earned[dimension] += earned
        dim_total[dimension] += total
        scenario_results.append({
            "id": sid,
            "dimension": dimension,
            "score": round(100.0 * earned / total, 2),
            "assertions": results,
        })

    dimensions = {
        dim: round(100.0 * dim_earned[dim] / dim_total[dim], 2)
        for dim in DIMENSIONS
    }
    total_earned = sum(dim_earned.values())
    total_weight = sum(dim_total.values())
    return {
        "agent": evidence["agent"],
        "overall": round(100.0 * total_earned / total_weight, 2),
        "dimensions": dimensions,
        "scenarios": scenario_results,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# KylinMemBench report — {report['agent']}",
        "",
        f"**Overall:** {report['overall']:.2f}/100",
        "",
        "| Dimension | Score |",
        "|---|---:|",
    ]
    for dim in DIMENSIONS:
        lines.append(f"| `{dim}` | {report['dimensions'][dim]:.2f} |")
    lines.extend(["", "## Assertion evidence", ""])
    for scenario in report["scenarios"]:
        lines.append(f"### `{scenario['id']}` — {scenario['score']:.2f}")
        for item in scenario["assertions"]:
            mark = "PASS" if item["passed"] else "FAIL"
            lines.append(f"- **{mark}** `{item['channel']}/{item['type']}` — {item['reason']}")
        lines.append("")
    return "\n".join(lines)


def _radar_svg(reports: list[dict[str, Any]]) -> str:
    width = height = 640
    cx = cy = 320.0
    radius = 220.0
    count = len(DIMENSIONS)
    palette = ("#2563eb", "#dc2626", "#059669", "#7c3aed")

    def point(index: int, fraction: float) -> tuple[float, float]:
        angle = -math.pi / 2 + 2 * math.pi * index / count
        return cx + radius * fraction * math.cos(angle), cy + radius * fraction * math.sin(angle)

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="640" viewBox="0 0 640 640">',
        '<rect width="640" height="640" fill="white"/>',
        '<style>text{font-family:sans-serif;font-size:12px}.label{font-size:11px}</style>',
    ]
    for ring in (0.25, 0.5, 0.75, 1.0):
        coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in (point(i, ring) for i in range(count)))
        parts.append(f'<polygon points="{coords}" fill="none" stroke="#d1d5db"/>')
    for i, dim in enumerate(DIMENSIONS):
        x, y = point(i, 1.0)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#d1d5db"/>')
        lx, ly = point(i, 1.12)
        anchor = "middle" if abs(lx - cx) < 25 else ("start" if lx > cx else "end")
        parts.append(f'<text class="label" x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}">{html.escape(dim)}</text>')
    for ridx, report in enumerate(reports):
        color = palette[ridx % len(palette)]
        coords = " ".join(
            f"{x:.1f},{y:.1f}"
            for x, y in (
                point(i, report["dimensions"][dim] / 100.0)
                for i, dim in enumerate(DIMENSIONS)
            )
        )
        parts.append(f'<polygon points="{coords}" fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<text x="20" y="{28 + 20*ridx}" fill="{color}">{html.escape(report["agent"])} — {report["overall"]:.2f}</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _report_slug(agent: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", agent).strip("-") or "agent"


_REPORT_SUFFIXES = (".report.json", ".report.md")
_MAX_REPORT_COMPONENT_BYTES = 255
_MAX_REPORT_SLUG_BYTES = _MAX_REPORT_COMPONENT_BYTES - max(
    len(suffix.encode("ascii")) for suffix in _REPORT_SUFFIXES
)
_WINDOWS_RESERVED_REPORT_BASENAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


def _validated_report_slug(agent: str) -> str:
    slug = _report_slug(agent)
    if len(slug.encode("ascii")) > _MAX_REPORT_SLUG_BYTES:
        raise ValueError(
            "agent report name exceeds "
            f"{_MAX_REPORT_SLUG_BYTES} ASCII bytes after sanitization"
        )
    device_base = slug.split(".", 1)[0].rstrip(" .").upper()
    if device_base in _WINDOWS_RESERVED_REPORT_BASENAMES:
        raise ValueError(f"agent report name is reserved on Windows: {slug!r}")
    return slug


def _write_report(out_dir: Path, report: dict[str, Any]) -> None:
    slug = _validated_report_slug(report["agent"])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{slug}.report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / f"{slug}.report.md").write_text(_markdown(report), encoding="utf-8")


def _load_evidence_with_sha(path: Path, scenario_ids: set[str]) -> tuple[dict[str, Any], str]:
    payload, digest = _read_json_with_sha(path)
    validate_evidence(payload, scenario_ids)
    return payload, digest


def _load_evidence(path: Path, scenario_ids: set[str]) -> dict[str, Any]:
    return _load_evidence_with_sha(path, scenario_ids)[0]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kylin-memory-bench")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="validate dataset and one or more evidence bundles")
    validate.add_argument("--dataset", type=Path, required=True)
    validate.add_argument("--evidence", type=Path, action="append", default=[])
    score_cmd = sub.add_parser("score", help="score one evidence bundle")
    score_cmd.add_argument("--dataset", type=Path, required=True)
    score_cmd.add_argument("--evidence", type=Path, required=True)
    score_cmd.add_argument("--out-dir", type=Path, required=True)
    compare = sub.add_parser("compare", help="score and compare two or more evidence bundles")
    compare.add_argument("--dataset", type=Path, required=True)
    compare.add_argument("--evidence", type=Path, action="append", required=True)
    compare.add_argument("--out-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        scenarios, dataset_sha256 = _read_dataset_with_sha(args.dataset)
        ids = {row["id"] for row in scenarios}
        if args.command == "validate":
            for path in args.evidence:
                _load_evidence(path, ids)
            print(f"VALID dataset={len(scenarios)} scenarios evidence={len(args.evidence)}")
            return 0
        if args.command == "score":
            evidence, evidence_sha256 = _load_evidence_with_sha(args.evidence, ids)
            report = score(scenarios, evidence)
            report["provenance"] = {
                "dataset_sha256": dataset_sha256,
                "evidence_sha256": evidence_sha256,
            }
            _write_report(args.out_dir, report)
            (args.out_dir / "radar.svg").write_text(_radar_svg([report]), encoding="utf-8")
            print(json.dumps({"agent": report["agent"], "overall": report["overall"]}))
            return 0
        if len(args.evidence) < 2:
            raise ValueError("compare requires at least two evidence bundles")
        loaded = [(path, *_load_evidence_with_sha(path, ids)) for path in args.evidence]
        names = [evidence["agent"] for _, evidence, _ in loaded]
        if len(set(names)) != len(names):
            raise ValueError("compare agent names must be unique")
        report_slugs = [_validated_report_slug(name) for name in names]
        slug_keys = [slug.casefold() for slug in report_slugs]
        if len(set(slug_keys)) != len(slug_keys):
            raise ValueError("compare agent output names collide after sanitization")
        reports = []
        for path, evidence, evidence_sha256 in loaded:
            report = score(scenarios, evidence)
            report["provenance"] = {
                "dataset_sha256": dataset_sha256,
                "evidence_sha256": evidence_sha256,
            }
            reports.append(report)
        for report in reports:
            _write_report(args.out_dir, report)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "comparison.json").write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
        (args.out_dir / "radar.svg").write_text(_radar_svg(reports), encoding="utf-8")
        print(json.dumps({report["agent"]: report["overall"] for report in reports}, sort_keys=True))
        return 0
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
