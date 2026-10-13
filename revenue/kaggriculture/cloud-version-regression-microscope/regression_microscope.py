#!/usr/bin/env python3
"""Three-way, tested-seat regression attribution for TITAN.

This is a diagnostic consumer of a separate causal-admission receipt. It never
runs games, changes policy/configuration, or emits a promotion decision. Given
exact V1, V2 and V3 cells, it identifies V1->V2 harm, V2->V3 recovery, V1->V3
net regressions, and repeated first returned-action divergence signatures.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA = "titan-three-way-regression-microscope/v1"
DEFAULT_EXPECTED_ACTION_COUNT = 719
OUTCOME_RANK = {"L": 0, "T": 1, "W": 2}


class MicroscopeError(ValueError):
    """The supplied evidence cannot support an exact three-way comparison."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MicroscopeError(f"{where} must be an object")
    return value


def _sequence(value: Any, where: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise MicroscopeError(f"{where} must be an array")
    return value


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MicroscopeError(f"{where} must be a non-empty string")
    return value


def _sha(value: Any, where: str) -> str:
    value = _text(value, where)
    if value != value.lower() or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise MicroscopeError(f"{where} must be a lowercase 64-hex SHA-256")
    return value


def _integer(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MicroscopeError(f"{where} must be an integer")
    return value


def _number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise MicroscopeError(f"{where} must be a finite number")
    return float(value)


def _one_of(obj: Mapping[str, Any], names: Iterable[str], where: str) -> Any:
    for name in names:
        if name in obj:
            return obj[name]
    raise MicroscopeError(f"{where} is missing one of: {', '.join(names)}")


def _unwrap(action: Any) -> Any:
    if isinstance(action, Mapping) and "action" in action and set(action) <= {
        "step", "action", "tested_seat", "candidate_seat"
    }:
        return copy.deepcopy(action["action"])
    return copy.deepcopy(action)


def action_sequence_digest(actions: Sequence[Any]) -> str:
    return sha256_json([_unwrap(action) for action in actions])


def _outcome(own: float, rival: float) -> str:
    return "W" if own > rival else "L" if own < rival else "T"


def _first_divergence(left: Sequence[Any], right: Sequence[Any]) -> int | None:
    if len(left) != len(right):
        raise MicroscopeError("cannot compare action sequences of different lengths")
    for index, (a, b) in enumerate(zip(left, right)):
        if canonical_json(_unwrap(a)) != canonical_json(_unwrap(b)):
            return index
    return None


def _action_tokens(action: Any) -> list[str]:
    tokens: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            fields: list[str] = []
            for key in ("type", "action", "command", "kind", "name"):
                if isinstance(node.get(key), str) and node[key]:
                    fields.append(node[key].upper())
                    break
            for key in ("product", "crop", "animal", "item", "resource"):
                if isinstance(node.get(key), (str, int, float)) and not isinstance(node[key], bool):
                    fields.append(str(node[key]).upper())
                    break
            for key in ("quantity", "amount", "count", "number", "n"):
                if isinstance(node.get(key), (int, float)) and not isinstance(node[key], bool):
                    value = float(node[key])
                    fields.append(str(int(value)) if value.is_integer() else str(value))
                    break
            if fields:
                tokens.append(":".join(fields))
            else:
                for key in sorted(node):
                    walk(node[key])
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
            for item in node:
                walk(item)
        elif isinstance(node, str) and node.strip():
            tokens.append(node.strip().upper())

    walk(_unwrap(action))
    return tokens or [f"sha256:{sha256_json(_unwrap(action))[:16]}"]


def divergence_signature(step: int, before: Any, after: Any) -> str:
    return f"step={step}|{'+'.join(_action_tokens(before))}->{'+'.join(_action_tokens(after))}"


@dataclass(frozen=True, order=True)
class CellKey:
    opponent: str
    seed: int
    seat: int

    def display(self) -> str:
        return f"{self.opponent}|seed={self.seed}|seat={self.seat}"


@dataclass(frozen=True)
class Terminal:
    own_cash: float
    rival_cash: float
    own_score: float
    rival_score: float
    world_sha256: str
    trace_sha256: str

    @property
    def outcome(self) -> str:
        return _outcome(self.own_score, self.rival_score)


@dataclass(frozen=True)
class Cell:
    key: CellKey
    engine_sha256: str
    opponent_sha256: str
    actions: tuple[Any, ...]
    action_sha256: str
    terminal: Terminal


@dataclass(frozen=True)
class Version:
    label: str
    identity: Mapping[str, str]
    cells: Mapping[CellKey, Cell]


def _parse_gate(root: Mapping[str, Any]) -> Mapping[str, str]:
    gate = _mapping(root.get("upstream_causal_gate"), "upstream_causal_gate")
    status = _text(gate.get("status"), "upstream_causal_gate.status")
    if status != "PASS":
        raise MicroscopeError("upstream_causal_gate.status must be PASS")
    return {
        "tool": _text(gate.get("tool"), "upstream_causal_gate.tool"),
        "schema": _text(gate.get("schema"), "upstream_causal_gate.schema"),
        "status": status,
        "receipt_sha256": _sha(gate.get("receipt_sha256"), "upstream_causal_gate.receipt_sha256"),
    }


def _parse_expected_cells(root: Mapping[str, Any]) -> frozenset[CellKey]:
    raw = _sequence(root.get("expected_cells"), "expected_cells")
    keys: set[CellKey] = set()
    seats_by_pair: dict[tuple[str, int], set[int]] = defaultdict(set)
    for index, item in enumerate(raw):
        where = f"expected_cells[{index}]"
        obj = _mapping(item, where)
        key = CellKey(
            _text(obj.get("opponent"), f"{where}.opponent"),
            _integer(obj.get("seed"), f"{where}.seed"),
            _integer(obj.get("seat"), f"{where}.seat"),
        )
        if key.seat not in (0, 1):
            raise MicroscopeError(f"{where}.seat must be 0 or 1")
        if key in keys:
            raise MicroscopeError(f"expected_cells contains duplicate cell {key.display()}")
        keys.add(key)
        seats_by_pair[(key.opponent, key.seed)].add(key.seat)
    if not keys:
        raise MicroscopeError("expected_cells cannot be empty")
    incomplete = [
        f"{opponent}|seed={seed}"
        for (opponent, seed), seats in sorted(seats_by_pair.items())
        if seats != {0, 1}
    ]
    if incomplete:
        raise MicroscopeError("expected_cells must contain both seats for every opponent/seed: " + ", ".join(incomplete))
    return frozenset(keys)


def _parse_actions(raw: Any, where: str, action_count: int, seat: int) -> tuple[Any, ...]:
    records = _sequence(raw, where)
    if len(records) != action_count:
        raise MicroscopeError(f"{where} must contain exactly {action_count} returned actions")
    actions: list[Any] = []
    wrapper_keys = {"step", "action", "tested_seat", "candidate_seat"}
    for index, record in enumerate(records):
        if isinstance(record, Mapping) and "action" in record and set(record) <= wrapper_keys:
            if "step" not in record:
                raise MicroscopeError(f"{where}[{index}] wrapper is missing step")
            if _integer(record["step"], f"{where}[{index}].step") != index:
                raise MicroscopeError(f"{where}[{index}].step must equal {index}")
            seat_fields = [field for field in ("tested_seat", "candidate_seat") if field in record]
            if not seat_fields:
                raise MicroscopeError(f"{where}[{index}] wrapper is missing tested-seat identity")
            for field in seat_fields:
                if _integer(record[field], f"{where}[{index}].{field}") != seat:
                    raise MicroscopeError(f"{where}[{index}].{field} must equal cell seat {seat}")
            actions.append(copy.deepcopy(record["action"]))
        else:
            actions.append(copy.deepcopy(record))
    return tuple(actions)


def _parse_cell(raw: Any, where: str, action_count: int) -> Cell:
    obj = _mapping(raw, where)
    state = _text(obj.get("state"), f"{where}.state").lower()
    phase = _text(obj.get("phase"), f"{where}.phase").lower()
    if state != "complete" or phase != "finalize":
        raise MicroscopeError(f"{where} must be complete/finalize")
    seat = _integer(_one_of(obj, ("seat", "candidate_seat", "tested_seat"), f"{where}.seat"), f"{where}.seat")
    if seat not in (0, 1):
        raise MicroscopeError(f"{where}.seat must be 0 or 1")
    actions = _parse_actions(
        _one_of(obj, ("tested_seat_actions", "candidate_actions", "actions"), f"{where}.actions"),
        f"{where}.actions",
        action_count,
        seat,
    )
    digest = action_sequence_digest(actions)
    declared = _sha(
        _one_of(obj, ("tested_action_sha256", "candidate_action_sha256"), f"{where}.tested_action_sha256"),
        f"{where}.tested_action_sha256",
    )
    if declared != digest:
        raise MicroscopeError(f"{where}.tested_action_sha256 does not match returned actions")
    terminal = _mapping(obj.get("terminal"), f"{where}.terminal")
    own_cash = _number(_one_of(terminal, ("own_cash", "candidate_cash", "tested_cash"), f"{where}.terminal.own_cash"), f"{where}.terminal.own_cash")
    rival_cash = _number(_one_of(terminal, ("rival_cash", "opponent_cash"), f"{where}.terminal.rival_cash"), f"{where}.terminal.rival_cash")
    parsed_terminal = Terminal(
        own_cash=own_cash,
        rival_cash=rival_cash,
        own_score=_number(terminal.get("own_score", terminal.get("candidate_score", own_cash)), f"{where}.terminal.own_score"),
        rival_score=_number(terminal.get("rival_score", terminal.get("opponent_score", rival_cash)), f"{where}.terminal.rival_score"),
        world_sha256=_sha(_one_of(terminal, ("terminal_world_sha256", "world_sha256", "state_sha256"), f"{where}.terminal.world"), f"{where}.terminal.world"),
        trace_sha256=_sha(_one_of(terminal, ("full_trace_sha256", "trace_sha256"), f"{where}.terminal.trace"), f"{where}.terminal.trace"),
    )
    return Cell(
        key=CellKey(_text(obj.get("opponent"), f"{where}.opponent"), _integer(obj.get("seed"), f"{where}.seed"), seat),
        engine_sha256=_sha(obj.get("engine_sha256"), f"{where}.engine_sha256"),
        opponent_sha256=_sha(obj.get("opponent_sha256"), f"{where}.opponent_sha256"),
        actions=actions,
        action_sha256=digest,
        terminal=parsed_terminal,
    )


def _parse_dataset(raw: Any) -> tuple[int, Mapping[str, str], tuple[str, str, str], Mapping[str, Version]]:
    root = _mapping(raw, "dataset")
    if root.get("schema") != SCHEMA:
        raise MicroscopeError(f"dataset.schema must be {SCHEMA!r}")
    action_count = _integer(root.get("expected_action_count", DEFAULT_EXPECTED_ACTION_COUNT), "expected_action_count")
    if action_count != DEFAULT_EXPECTED_ACTION_COUNT:
        raise MicroscopeError(f"expected_action_count must equal {DEFAULT_EXPECTED_ACTION_COUNT}")
    expected_cells = _parse_expected_cells(root)
    gate = _parse_gate(root)
    labels_raw = _sequence(root.get("three_way"), "three_way")
    if len(labels_raw) != 3:
        raise MicroscopeError("three_way must contain exactly three labels")
    labels = tuple(_text(value, f"three_way[{index}]") for index, value in enumerate(labels_raw))
    if len(set(labels)) != 3:
        raise MicroscopeError("three_way labels must be unique")
    versions_raw = _mapping(root.get("versions"), "versions")
    if set(versions_raw) != set(labels):
        raise MicroscopeError("versions must equal the three_way labels")
    versions: dict[str, Version] = {}
    for label in labels:
        obj = _mapping(versions_raw[label], f"versions[{label!r}]")
        identity = _mapping(obj.get("identity"), f"versions[{label!r}].identity")
        parsed_identity = {
            field: _sha(identity.get(field), f"versions[{label!r}].identity.{field}")
            for field in ("source_sha256", "archive_sha256", "config_sha256")
        }
        cells: dict[CellKey, Cell] = {}
        for index, raw_cell in enumerate(_sequence(obj.get("cells"), f"versions[{label!r}].cells")):
            cell = _parse_cell(raw_cell, f"versions[{label!r}].cells[{index}]", action_count)
            if cell.key in cells:
                raise MicroscopeError(f"versions[{label!r}] contains duplicate cell {cell.key.display()}")
            cells[cell.key] = cell
        if set(cells) != set(expected_cells):
            missing = sorted(key.display() for key in expected_cells - set(cells))
            extra = sorted(key.display() for key in set(cells) - expected_cells)
            raise MicroscopeError(f"grid mismatch for {label}: missing={missing}, extra={extra}")
        versions[label] = Version(label, parsed_identity, cells)
    return action_count, gate, labels, versions  # type: ignore[return-value]


def _compare_cell(base: Cell, candidate: Cell) -> Mapping[str, Any]:
    step = _first_divergence(base.actions, candidate.actions)
    changed = step is not None
    a, b = base.terminal, candidate.terminal
    own_delta = b.own_cash - a.own_cash
    rival_delta = b.rival_cash - a.rival_cash
    margin_delta = (b.own_score - b.rival_score) - (a.own_score - a.rival_score)
    outcome_delta = OUTCOME_RANK[b.outcome] - OUTCOME_RANK[a.outcome]
    issues: list[str] = []
    if base.engine_sha256 != candidate.engine_sha256:
        issues.append("engine_sha256_mismatch")
    if base.opponent_sha256 != candidate.opponent_sha256:
        issues.append("opponent_sha256_mismatch")
    if not changed:
        pairs = (
            (a.world_sha256, b.world_sha256, "action_identical_terminal_world_drift"),
            (a.trace_sha256, b.trace_sha256, "action_identical_full_trace_drift"),
            (a.own_cash, b.own_cash, "action_identical_own_cash_drift"),
            (a.rival_cash, b.rival_cash, "action_identical_rival_cash_drift"),
            (a.own_score, b.own_score, "action_identical_own_score_drift"),
            (a.rival_score, b.rival_score, "action_identical_rival_score_drift"),
        )
        issues.extend(name for left, right, name in pairs if left != right)
    elif a.trace_sha256 == b.trace_sha256:
        issues.append("action_changed_but_full_trace_identical")
    if issues:
        classification = "invalid_confounded"
    elif not changed:
        classification = "inert"
    elif own_delta < 0 and (margin_delta > 0 or outcome_delta > 0):
        classification = "objective_conflict"
    elif own_delta < 0 or outcome_delta < 0:
        classification = "candidate_harm"
    elif own_delta > 0 and margin_delta >= 0 and outcome_delta >= 0:
        classification = "candidate_benefit"
    elif own_delta == rival_delta == margin_delta == outcome_delta == 0:
        classification = "realized_neutral"
    else:
        classification = "objective_conflict"
    before = base.actions[step] if step is not None else None
    after = candidate.actions[step] if step is not None else None
    return {
        "cell": {"key": base.key.display(), "opponent": base.key.opponent, "seed": base.key.seed, "seat": base.key.seat},
        "classification": classification,
        "defense_in_depth_issues": issues,
        "action_changed": changed,
        "base_action_sha256": base.action_sha256,
        "candidate_action_sha256": candidate.action_sha256,
        "first_divergence_step": step,
        "first_divergence_signature": divergence_signature(step, before, after) if step is not None else None,
        "first_divergence_base_action": before,
        "first_divergence_candidate_action": after,
        "base": {"own_cash": a.own_cash, "rival_cash": a.rival_cash, "margin": a.own_score - a.rival_score, "outcome": a.outcome},
        "candidate": {"own_cash": b.own_cash, "rival_cash": b.rival_cash, "margin": b.own_score - b.rival_score, "outcome": b.outcome},
        "delta": {"own_cash": own_delta, "rival_cash": rival_delta, "margin": margin_delta, "outcome_rank": outcome_delta},
    }


def _is_regression(row: Mapping[str, Any]) -> bool:
    return row["classification"] in {"candidate_harm", "objective_conflict"} and (
        row["delta"]["own_cash"] < 0 or row["delta"]["outcome_rank"] < 0
    )


def _summary(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    own = [float(row["delta"]["own_cash"]) for row in rows]
    margin = [float(row["delta"]["margin"]) for row in rows]
    classes = Counter(row["classification"] for row in rows)
    invalid = classes["invalid_confounded"]
    regressions = sum(_is_regression(row) for row in rows)
    status = "INVALID_EVIDENCE" if invalid else "REGRESSION_PRESENT" if regressions else "NO_REGRESSION_DETECTED"
    return {
        "diagnostic_status": status,
        "diagnostic_reasons": [f"{invalid} defense-in-depth violations"] if invalid else [f"{regressions} regression cells"] if regressions else ["zero regression cells"],
        "cell_count": len(rows),
        "action_changed_cells": sum(row["action_changed"] for row in rows),
        "classifications": dict(sorted(classes.items())),
        "own_cash_delta_sum": sum(own),
        "own_cash_delta_mean": statistics.fmean(own),
        "own_cash_delta_median": statistics.median(own),
        "own_cash_delta_min": min(own),
        "margin_delta_sum": sum(margin),
        "margin_delta_mean": statistics.fmean(margin),
        "new_losses": sum(row["base"]["outcome"] != "L" and row["candidate"]["outcome"] == "L" for row in rows),
        "lost_wins": sum(row["base"]["outcome"] == "W" and row["candidate"]["outcome"] != "W" for row in rows),
        "gained_wins": sum(row["base"]["outcome"] != "W" and row["candidate"]["outcome"] == "W" for row in rows),
    }


def _compare_versions(base: Version, candidate: Version) -> Mapping[str, Any]:
    if set(base.cells) != set(candidate.cells):
        missing = sorted(key.display() for key in set(base.cells) - set(candidate.cells))
        extra = sorted(key.display() for key in set(candidate.cells) - set(base.cells))
        raise MicroscopeError(f"grid mismatch {base.label}->{candidate.label}: missing={missing}, extra={extra}")
    rows = [_compare_cell(base.cells[key], candidate.cells[key]) for key in sorted(base.cells)]
    return {
        "base": base.label,
        "candidate": candidate.label,
        "base_identity": dict(base.identity),
        "candidate_identity": dict(candidate.identity),
        "cells": rows,
        "summary": _summary(rows),
    }


def _rows(comparison: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    return {row["cell"]["key"]: row for row in comparison["cells"]}


def _clusters(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["first_divergence_signature"]:
            groups[row["first_divergence_signature"]].append(row)
    result = []
    for signature, group in groups.items():
        result.append({
            "signature": signature,
            "count": len(group),
            "cells": [row["cell"]["key"] for row in group],
            "own_cash_delta_sum": sum(row["delta"]["own_cash"] for row in group),
            "own_cash_delta_min": min(row["delta"]["own_cash"] for row in group),
            "margin_delta_sum": sum(row["delta"]["margin"] for row in group),
            "outcome_regressions": sum(row["delta"]["outcome_rank"] < 0 for row in group),
        })
    return sorted(result, key=lambda item: (item["own_cash_delta_sum"], -item["count"], item["signature"]))


def build_report(raw: Any) -> Mapping[str, Any]:
    action_count, gate, labels, versions = _parse_dataset(raw)
    v1, v2, v3 = labels
    c12 = _compare_versions(versions[v1], versions[v2])
    c23 = _compare_versions(versions[v2], versions[v3])
    c13 = _compare_versions(versions[v1], versions[v3])
    r12, r23, r13 = _rows(c12), _rows(c23), _rows(c13)
    regressions = sorted(key for key, row in r12.items() if _is_regression(row))
    repairs = sorted(
        key
        for key in regressions
        if r23[key]["classification"] == "candidate_benefit"
        and r23[key]["action_changed"]
        and not r23[key]["defense_in_depth_issues"]
        and not r13[key]["defense_in_depth_issues"]
        and r13[key]["delta"]["own_cash"] >= 0
        and r13[key]["delta"]["outcome_rank"] >= 0
    )
    unrepaired = sorted(set(regressions) - set(repairs))
    new_v3 = sorted(key for key, row in r13.items() if _is_regression(row) and key not in regressions)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "input_sha256": sha256_json(raw),
        "expected_action_count": action_count,
        "expected_cell_count": len(versions[v1].cells),
        "upstream_causal_gate": dict(gate),
        "labels": {"v1": v1, "v2": v2, "v3": v3},
        "comparisons": {f"{v1}->{v2}": c12, f"{v2}->{v3}": c23, f"{v1}->{v3}": c13},
        "attribution": {
            "v2_regression_cells": regressions,
            "v3_repaired_to_v1_cells": repairs,
            "v3_unrepaired_v2_regressions": unrepaired,
            "v3_new_regression_cells": new_v3,
            "v2_harmful_first_divergence_clusters": _clusters([r12[key] for key in regressions]),
            "v1_to_v3_net_diagnostic_status": c13["summary"]["diagnostic_status"],
        },
    }
    report["report_sha256"] = sha256_json(report)
    return report


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.6f}".rstrip("0").rstrip(".")


def render_markdown(report: Mapping[str, Any]) -> str:
    gate, attribution = report["upstream_causal_gate"], report["attribution"]
    lines = [
        "# TITAN three-way regression delta microscope", "",
        f"Input SHA-256: `{report['input_sha256']}`  ",
        f"Report SHA-256: `{report['report_sha256']}`  ",
        f"Upstream causal receipt: `{gate['receipt_sha256']}` — **{gate['status']}**", "",
        "> Diagnostic only. This consumer never emits a promote, feature keep/drop, or release decision.", "",
        "## Three-way attribution", "",
        f"- V2 regression cells: {len(attribution['v2_regression_cells'])}",
        f"- V3 repairs to at least V1: {len(attribution['v3_repaired_to_v1_cells'])}",
        f"- Unrepaired V2 regressions: {len(attribution['v3_unrepaired_v2_regressions'])}",
        f"- New V3 regressions: {len(attribution['v3_new_regression_cells'])}",
        f"- V1→V3 net diagnostic: **{attribution['v1_to_v3_net_diagnostic_status']}**", "",
    ]
    clusters = attribution["v2_harmful_first_divergence_clusters"]
    if clusters:
        lines += ["### Repeated harmful first-divergence signatures", "", "| Signature | Cells | Own Δ sum | Own Δ min | Margin Δ sum |", "|---|---:|---:|---:|---:|"]
        for item in clusters:
            lines.append(f"| `{item['signature'].replace('|', '\\|')}` | {item['count']} | {_fmt(item['own_cash_delta_sum'])} | {_fmt(item['own_cash_delta_min'])} | {_fmt(item['margin_delta_sum'])} |")
        lines.append("")
    for name, comparison in report["comparisons"].items():
        summary = comparison["summary"]
        lines += [f"## {name}", "", f"- Diagnostic: **{summary['diagnostic_status']}**", f"- Cells/action changes: {summary['cell_count']}/{summary['action_changed_cells']}", f"- Own cash Δ sum/mean/median/min: {_fmt(summary['own_cash_delta_sum'])} / {_fmt(summary['own_cash_delta_mean'])} / {_fmt(summary['own_cash_delta_median'])} / {_fmt(summary['own_cash_delta_min'])}", f"- New losses/lost wins/gained wins: {summary['new_losses']}/{summary['lost_wins']}/{summary['gained_wins']}", "", "| Cell | Class | First divergence | Own Δ | Margin Δ | Outcome |", "|---|---|---:|---:|---:|---|"]
        for row in comparison["cells"]:
            step = "—" if row["first_divergence_step"] is None else row["first_divergence_step"]
            lines.append(f"| {row['cell']['key']} | {row['classification']} | {step} | {_fmt(row['delta']['own_cash'])} | {_fmt(row['delta']['margin'])} | {row['base']['outcome']}→{row['candidate']['outcome']} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Map exact V1→V2 regressions and V2→V3 repairs")
    parser.add_argument("input", type=Path)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        report = build_report(raw)
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.markdown_out.write_text(render_markdown(report), encoding="utf-8")
    except (OSError, json.JSONDecodeError, MicroscopeError) as exc:
        print(f"three-way regression microscope: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
