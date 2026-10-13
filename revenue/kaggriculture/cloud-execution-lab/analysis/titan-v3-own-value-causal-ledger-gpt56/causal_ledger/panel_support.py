# SPDX-License-Identifier: Apache-2.0
"""Panel topology, exact-tail statistics, and provenance closure helpers."""
from __future__ import annotations

import math
import statistics
from typing import Any, Iterable, Mapping, Sequence

from .strict import (
    EvidenceError,
    _git_sha,
    _integer,
    _mapping,
    _number,
    _sha256,
    digest,
)
from .game import _PANEL_PROVENANCE

def _mean(values: Iterable[float]) -> float:
    data = list(values)
    return math.fsum(data) / len(data) if data else 0.0


def _positive_tail_p(values: Iterable[float]) -> float | None:
    data = [value for value in values if value != 0]
    if not data:
        return None
    positives = sum(value > 0 for value in data)
    n = len(data)
    numerator = sum(math.comb(n, k) for k in range(positives, n + 1))
    return numerator / (2 ** n)


def _aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    own = [float(row["own_delta"]) for row in rows]
    rival = [float(row["rival_delta"]) for row in rows]
    margin = [float(row["margin_delta"]) for row in rows]
    return {
        "cells": len(rows),
        "action_active_cells": sum(bool(row["action_active"]) for row in rows),
        "score_active_cells": sum(bool(row["score_active"]) for row in rows),
        "own_total": math.fsum(own),
        "own_mean": _mean(own),
        "own_median": statistics.median(own) if own else 0.0,
        "rival_total": math.fsum(rival),
        "rival_mean": _mean(rival),
        "margin_total": math.fsum(margin),
        "margin_mean": _mean(margin),
        "own_positive": sum(value > 0 for value in own),
        "own_negative": sum(value < 0 for value in own),
        "own_zero": sum(value == 0 for value in own),
        "margin_positive": sum(value > 0 for value in margin),
        "margin_negative": sum(value < 0 for value in margin),
        "margin_zero": sum(value == 0 for value in margin),
        "lost_wins": sum(bool(row["lost_win"]) for row in rows),
        "new_losses": sum(bool(row["new_loss"]) for row in rows),
        "outcome_balance": sum(int(row["outcome_delta"]) for row in rows),
    }


def _group(rows: Sequence[Mapping[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for row in rows:
        key = tuple(row[name] for name in keys)
        groups.setdefault(key, []).append(row)
    result = []
    for key in sorted(groups, key=lambda item: tuple(str(part) for part in item)):
        report = {name: value for name, value in zip(keys, key)}
        report.update(_aggregate(groups[key]))
        result.append(report)
    return result


def _gate_config(value: Any) -> dict[str, float]:
    defaults = {
        "min_seed_own_mean": 0.0,
        "min_seed_margin_mean": 0.0,
        "max_seed_own_positive_tail_p": 0.05,
        "max_seed_margin_positive_tail_p": 0.05,
    }
    if value is None:
        return defaults
    raw = _mapping(value, "gate")
    if set(raw) - set(defaults):
        raise EvidenceError(f"unknown gate fields: {sorted(set(raw) - set(defaults))}")
    result = dict(defaults)
    for key, item in raw.items():
        number = _number(item, f"gate.{key}")
        if key.startswith("max_") and not 0 <= number <= 1:
            raise EvidenceError(f"gate.{key} must be within [0, 1]")
        result[key] = number
    return result



def seed_bank_sha256(
    *,
    label: str,
    opponents: Sequence[str],
    seeds: Sequence[int],
    candidate_seats: Sequence[int],
) -> str:
    """Content-address the exact precommitted panel topology."""
    if not isinstance(label, str) or not label.strip():
        raise EvidenceError("seed bank label must be a nonempty string")
    return digest({
        "label": label,
        "opponents": list(opponents),
        "seeds": list(seeds),
        "candidate_seats": list(candidate_seats),
    })


def _experiment_config(
    value: Any,
    *,
    opponents: Sequence[str],
    seeds: Sequence[int],
    seats: Sequence[int],
) -> dict[str, Any]:
    raw = _mapping(value, "experiment")
    fields = {
        "id",
        "hypothesis_sha256",
        "seed_bank_label",
        "seed_bank_sha256",
        "git_head",
        "parent_head",
        "run_id",
        "run_attempt",
    }
    if set(raw) != fields:
        missing = sorted(fields - set(raw))
        extra = sorted(set(raw) - fields)
        raise EvidenceError(f"experiment key mismatch; missing={missing}, extra={extra}")
    experiment_id = raw["id"]
    label = raw["seed_bank_label"]
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise EvidenceError("experiment.id must be a nonempty string")
    if not isinstance(label, str) or not label.strip():
        raise EvidenceError("experiment.seed_bank_label must be a nonempty string")
    hypothesis = _sha256(raw["hypothesis_sha256"], "experiment.hypothesis_sha256")
    declared_bank = _sha256(raw["seed_bank_sha256"], "experiment.seed_bank_sha256")
    expected_bank = seed_bank_sha256(
        label=label, opponents=opponents, seeds=seeds, candidate_seats=seats
    )
    if declared_bank != expected_bank:
        raise EvidenceError("experiment.seed_bank_sha256 does not bind the exact panel grid")
    head = _git_sha(raw["git_head"], "experiment.git_head")
    parent = _git_sha(raw["parent_head"], "experiment.parent_head")
    if head == parent:
        raise EvidenceError("experiment.git_head must differ from parent_head")
    run_id = _integer(raw["run_id"], "experiment.run_id", minimum=1)
    run_attempt = _integer(raw["run_attempt"], "experiment.run_attempt", minimum=1)
    if run_attempt != 1:
        raise EvidenceError("the precommitted seed bank may be spent only on run_attempt 1")
    return {
        "id": experiment_id,
        "hypothesis_sha256": hypothesis,
        "seed_bank_label": label,
        "seed_bank_sha256": declared_bank,
        "git_head": head,
        "parent_head": parent,
        "run_id": run_id,
        "run_attempt": run_attempt,
    }


def _panel_provenance(value: Any, opponents: Sequence[str]) -> dict[str, Any]:
    raw = _mapping(value, "provenance")
    if set(raw) != set(_PANEL_PROVENANCE):
        missing = sorted(set(_PANEL_PROVENANCE) - set(raw))
        extra = sorted(set(raw) - set(_PANEL_PROVENANCE))
        raise EvidenceError(f"provenance key mismatch; missing={missing}, extra={extra}")
    result = {
        key: _sha256(raw[key], f"provenance.{key}")
        for key in _PANEL_PROVENANCE
        if key != "opponent_tree_sha256"
    }
    if result["control_runtime_tree_sha256"] == result["candidate_runtime_tree_sha256"]:
        raise EvidenceError("control and candidate runtime-tree digests must differ")
    opponent_trees = _mapping(raw["opponent_tree_sha256"], "provenance.opponent_tree_sha256")
    if set(opponent_trees) != set(opponents):
        missing = sorted(set(opponents) - set(opponent_trees))
        extra = sorted(set(opponent_trees) - set(opponents))
        raise EvidenceError(
            "provenance.opponent_tree_sha256 key mismatch; "
            f"missing={missing}, extra={extra}"
        )
    result["opponent_tree_sha256"] = {
        name: _sha256(opponent_trees[name], f"provenance.opponent_tree_sha256.{name}")
        for name in opponents
    }
    return result
