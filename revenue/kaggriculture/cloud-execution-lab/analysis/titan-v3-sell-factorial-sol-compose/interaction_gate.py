#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed 2x2 interaction gate for TITAN SELL-policy candidates.

The four arms are the exact same runtime closure with neither overlay (control),
the own-value objective only, receipt-invariance-certified market pressure only, and both.
This module verifies common official-interpreter provenance, a complete paired
grid, terminal bank identity, and pre-interpreter returned-action custody before
computing singleton, composition, and factorial interaction effects.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable, Mapping

ARM_NAMES = ("control", "own_value", "certified_pressure", "both")
CANDIDATE_ARMS = ARM_NAMES[1:]
PROVENANCE_KEYS = (
    "schema_version",
    "engine_ref",
    "engine_sha256",
    "loader_sha256",
    "evaluator_sha256",
    "seeds",
    "agent_rng_seed",
    "limits",
    "opponents",
)
EXPECTED_EPISODE_STEPS = 720
EXPECTED_ACTION_COUNT = 719
MANIFEST_OPERATION = "titan-v3-sell-factorial-arm-manifest-20260910-01"
PRESSURE_CONTRACT = "TITAN-V3-PRESSURE-PREFIX-UNION-INVARIANCE-CERTIFICATE-20260910-01"
FACTOR_NAMES = ("own_value", "certified_pressure")
EXPECTED_ARM_FACTORS = {
    "control": (),
    "own_value": ("own_value",),
    "certified_pressure": ("certified_pressure",),
    "both": FACTOR_NAMES,
}


class EvidenceError(ValueError):
    """A report is malformed, detached, incomplete, or not truly comparable."""


def strict_load(path: Path, label: str) -> dict[str, Any]:
    """Load strict UTF-8 JSON, rejecting duplicate keys and non-finite values."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise EvidenceError(f"{label} has duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise EvidenceError(f"{label} contains non-finite JSON constant {value}")

    try:
        value = json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot load {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} root must be an object")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EvidenceError(f"{label} must be finite")
    return result


def _true_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise EvidenceError(f"{label} must be an integer >= {minimum}")
    return value


def _hex_digest(value: Any, label: str, *, length: int) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise EvidenceError(f"{label} must be a {length}-character hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise EvidenceError(f"{label} must be a {length}-character hex digest") from exc
    return value.lower()


def _digest(value: Any, label: str) -> str:
    return _hex_digest(value, label, length=64)


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise EvidenceError(
            f"{label} keys differ: missing={sorted(expected-actual)!r}, "
            f"unexpected={sorted(actual-expected)!r}"
        )
    return value


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{label} must be a non-empty string")
    return value


def _fingerprint(report: Mapping[str, Any], label: str) -> dict[str, Any]:
    value = report.get("candidate")
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} candidate fingerprint is missing")
    _digest(value.get("sha256"), f"{label} candidate SHA-256")
    entrypoint = value.get("entrypoint")
    if entrypoint is not None and (not isinstance(entrypoint, str) or not entrypoint):
        raise EvidenceError(f"{label} candidate entrypoint is malformed")
    return dict(value)


def _validate_arm_manifest(
    manifest: Mapping[str, Any],
    reports: Mapping[str, Mapping[str, Any]],
    report_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind arm labels to exact factor bytes and one canonical runtime closure."""
    root = _exact_keys(
        manifest,
        {"schema_version", "operation", "panel_binding", "factors", "arms"},
        "arm manifest",
    )
    if _true_int(root["schema_version"], "arm manifest schema", minimum=1) != 1:
        raise EvidenceError("unsupported arm manifest schema")
    if root["operation"] != MANIFEST_OPERATION:
        raise EvidenceError("arm manifest operation mismatch")

    panel = _exact_keys(
        root["panel_binding"],
        {
            "archive_sha256",
            "source_manifest_sha256",
            "runtime_tree_sha256",
            "engine_sha256",
            "loader_sha256",
            "evaluator_sha256",
        },
        "arm manifest panel_binding",
    )
    normalized_panel = {name: _digest(value, f"panel {name}") for name, value in panel.items()}
    for name in ("engine_sha256", "loader_sha256", "evaluator_sha256"):
        if normalized_panel[name] != report_provenance[name]:
            raise EvidenceError(f"arm manifest panel binding differs from reports: {name}")

    factors = _exact_keys(root["factors"], set(FACTOR_NAMES), "arm manifest factors")
    normalized_factors: dict[str, dict[str, Any]] = {}
    for name in FACTOR_NAMES:
        expected = {"contract", "source_sha256", "source_git_blob_sha1", "receipt_sha256"}
        if name == "certified_pressure":
            expected.update(
                {
                    "inventory_window_mode",
                    "rival_bound_source",
                    "market_order_cap_source",
                    "price_floor_source",
                }
            )
        row = _exact_keys(factors[name], expected, f"factor {name}")
        contract = _nonempty_string(row["contract"], f"factor {name} contract")
        if name == "certified_pressure":
            if contract != PRESSURE_CONTRACT:
                raise EvidenceError("certified-pressure contract identity mismatch")
            expected_pressure_binding = {
                "inventory_window_mode": "parent_candidate_execution_prefix_union",
                "rival_bound_source": "shedCapacity",
                "market_order_cap_source": "maxMarketOrdersPerTurn",
                "price_floor_source": "PRICE_FLOOR",
            }
            for field, expected_value in expected_pressure_binding.items():
                if row[field] != expected_value:
                    raise EvidenceError(
                        f"certified-pressure {field} must be {expected_value}"
                    )
        normalized = {
            "contract": contract,
            "source_sha256": _digest(row["source_sha256"], f"factor {name} source SHA-256"),
            "source_git_blob_sha1": _hex_digest(
                row["source_git_blob_sha1"], f"factor {name} Git blob", length=40
            ),
            "receipt_sha256": _digest(row["receipt_sha256"], f"factor {name} receipt SHA-256"),
        }
        if name == "certified_pressure":
            normalized.update(
                {
                    "inventory_window_mode": "parent_candidate_execution_prefix_union",
                    "rival_bound_source": "shedCapacity",
                    "market_order_cap_source": "maxMarketOrdersPerTurn",
                    "price_floor_source": "PRICE_FLOOR",
                }
            )
        normalized_factors[name] = normalized
    if len({row["source_sha256"] for row in normalized_factors.values()}) != len(FACTOR_NAMES):
        raise EvidenceError("factor source identities must be distinct")

    arms = _exact_keys(root["arms"], set(ARM_NAMES), "arm manifest arms")
    normalized_arms: dict[str, dict[str, Any]] = {}
    for arm in ARM_NAMES:
        row = _exact_keys(
            arms[arm],
            {
                "candidate_sha256",
                "build_receipt_sha256",
                "archive_sha256",
                "source_manifest_sha256",
                "runtime_tree_sha256",
                "factors",
            },
            f"arm manifest {arm}",
        )
        candidate_sha = _digest(row["candidate_sha256"], f"{arm} manifest candidate SHA-256")
        report_sha = _digest(
            reports[arm]["candidate"]["sha256"], f"{arm} report candidate SHA-256"
        )
        if candidate_sha != report_sha:
            raise EvidenceError(f"{arm} manifest candidate differs from executed report")
        for field in ("archive_sha256", "source_manifest_sha256", "runtime_tree_sha256"):
            value = _digest(row[field], f"{arm} {field}")
            if value != normalized_panel[field]:
                raise EvidenceError(f"{arm} canonical closure differs from panel binding: {field}")
        arm_factors = _exact_keys(
            row["factors"], set(EXPECTED_ARM_FACTORS[arm]), f"{arm} factor map"
        )
        normalized_arm_factors: dict[str, str] = {}
        for factor, source_sha in arm_factors.items():
            normalized_sha = _digest(source_sha, f"{arm} factor {factor} source SHA-256")
            if normalized_sha != normalized_factors[factor]["source_sha256"]:
                raise EvidenceError(
                    f"{arm} does not bind the exact singleton source bytes for {factor}"
                )
            normalized_arm_factors[factor] = normalized_sha
        normalized_arms[arm] = {
            "candidate_sha256": candidate_sha,
            "build_receipt_sha256": _digest(
                row["build_receipt_sha256"], f"{arm} build receipt SHA-256"
            ),
            "archive_sha256": normalized_panel["archive_sha256"],
            "source_manifest_sha256": normalized_panel["source_manifest_sha256"],
            "runtime_tree_sha256": normalized_panel["runtime_tree_sha256"],
            "factors": normalized_arm_factors,
        }

    normalized = {
        "schema_version": 1,
        "operation": MANIFEST_OPERATION,
        "panel_binding": normalized_panel,
        "factors": normalized_factors,
        "arms": normalized_arms,
    }
    payload = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return {
        "semantic_sha256": hashlib.sha256(payload).hexdigest(),
        "manifest": normalized,
    }


def _expected_keys(report: Mapping[str, Any]) -> set[tuple[str, int, int]]:
    opponents = report.get("opponents")
    seeds = report.get("seeds")
    if not isinstance(opponents, dict) or not opponents:
        raise EvidenceError("control report has no opponents")
    if not isinstance(seeds, list) or not seeds:
        raise EvidenceError("control report has no seeds")
    normalized_seeds: list[int] = []
    for offset, seed in enumerate(seeds):
        normalized = _true_int(seed, f"seed[{offset}]")
        normalized_seeds.append(normalized)
    if len(set(normalized_seeds)) != len(normalized_seeds):
        raise EvidenceError("control seed ledger contains duplicates")
    names = [str(name) for name in opponents]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise EvidenceError("control opponent ledger is malformed")
    return {
        (opponent, seed, seat)
        for opponent in names
        for seed in normalized_seeds
        for seat in (0, 1)
    }


def _validate_shared_provenance(reports: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if set(reports) != set(ARM_NAMES):
        raise EvidenceError(
            f"arm set mismatch: expected {sorted(ARM_NAMES)!r}, got {sorted(reports)!r}"
        )
    control = reports["control"]
    provenance: dict[str, Any] = {}
    for key in PROVENANCE_KEYS:
        if key not in control:
            raise EvidenceError(f"control report lacks provenance field {key}")
        provenance[key] = control[key]
        for arm in CANDIDATE_ARMS:
            if key not in reports[arm] or reports[arm][key] != control[key]:
                raise EvidenceError(f"{arm} provenance differs from control: {key}")

    _true_int(provenance["schema_version"], "report schema version", minimum=1)
    engine_ref = provenance["engine_ref"]
    if not isinstance(engine_ref, str) or not engine_ref:
        raise EvidenceError("engine_ref must be a non-empty string")
    for key in ("engine_sha256", "loader_sha256", "evaluator_sha256"):
        provenance[key] = _digest(provenance[key], key)
    _true_int(provenance["agent_rng_seed"], "agent_rng_seed")
    if not isinstance(provenance["limits"], dict):
        raise EvidenceError("limits provenance must be an object")

    fingerprints = {arm: _fingerprint(reports[arm], arm) for arm in ARM_NAMES}
    digests = [row["sha256"].lower() for row in fingerprints.values()]
    if len(set(digests)) != len(digests):
        raise EvidenceError("all four arm entrypoint fingerprints must be distinct")
    return {"shared": provenance, "fingerprints": fingerprints}


def _index_report(
    report: Mapping[str, Any],
    label: str,
    expected: set[tuple[str, int, int]],
) -> dict[tuple[str, int, int], dict[str, Any]]:
    progress = report.get("progress")
    games = report.get("games")
    if not isinstance(progress, dict) or progress.get("state") != "complete":
        raise EvidenceError(f"{label} is not a completed final report")
    if not isinstance(games, list):
        raise EvidenceError(f"{label} games must be a list")
    planned = _true_int(progress.get("planned_games"), f"{label} planned games", minimum=1)
    recorded = _true_int(progress.get("recorded_games"), f"{label} recorded games", minimum=1)
    if planned != recorded or recorded != len(games) or recorded != len(expected):
        raise EvidenceError(f"{label} progress/game cardinality mismatch")

    rows: dict[tuple[str, int, int], dict[str, Any]] = {}
    for offset, game in enumerate(games):
        if not isinstance(game, dict):
            raise EvidenceError(f"{label} game {offset} is not an object")
        try:
            opponent = game["opponent"]
            if not isinstance(opponent, str) or not opponent:
                raise EvidenceError(f"{label} game {offset} has malformed opponent")
            key = (
                opponent,
                _true_int(game["seed"], f"{label} seed at game {offset}"),
                _true_int(
                    game["candidate_seat"],
                    f"{label} candidate seat at game {offset}",
                ),
            )
        except KeyError as exc:
            raise EvidenceError(f"{label} game {offset} has malformed identity") from exc
        if key[2] not in (0, 1) or key not in expected:
            raise EvidenceError(f"{label} game has unexpected identity {key}")
        if key in rows:
            raise EvidenceError(f"{label} has duplicate cell {key}")
        if game.get("status") != "complete" or game.get("failure") is not None:
            raise EvidenceError(f"{label} cell {key} is not complete")
        episode_steps = _true_int(
            game.get("episode_steps"), f"{label} episode steps {key}", minimum=2
        )
        steps = _true_int(game.get("steps"), f"{label} action steps {key}", minimum=1)
        actions = _true_int(
            game.get("candidate_action_count"),
            f"{label} candidate action count {key}",
            minimum=1,
        )
        if episode_steps != EXPECTED_EPISODE_STEPS:
            raise EvidenceError(f"{label} cell {key} does not have a 720-state lifecycle")
        if steps != EXPECTED_ACTION_COUNT or actions != steps:
            raise EvidenceError(f"{label} cell {key} does not have 719 captured candidate actions")
        action_sha = _digest(
            game.get("candidate_action_sha256"), f"{label} action SHA-256 {key}"
        )
        trace_sha = _digest(game.get("trace_sha256"), f"{label} trace SHA-256 {key}")
        scores = game.get("scores")
        bank = game.get("bank_snapshot")
        if not isinstance(scores, list) or len(scores) != 2:
            raise EvidenceError(f"{label} cell {key} has malformed terminal scores")
        if not isinstance(bank, list) or len(bank) != 2:
            raise EvidenceError(f"{label} cell {key} has malformed terminal bank")
        score_values = [_finite(value, f"{label} score {key}") for value in scores]
        bank_values = [_finite(value, f"{label} bank {key}") for value in bank]
        if score_values != bank_values:
            raise EvidenceError(f"{label} cell {key} scores differ from terminal bank")
        rows[key] = {
            **game,
            "candidate_action_sha256": action_sha,
            "trace_sha256": trace_sha,
            "scores": score_values,
            "bank_snapshot": bank_values,
        }
    if set(rows) != expected:
        raise EvidenceError(
            f"{label} grid mismatch: expected {len(expected)} cells, got {len(rows)}"
        )
    return rows


def _outcome(own: float, rival: float) -> str:
    if own > rival:
        return "win"
    if own < rival:
        return "loss"
    return "tie"


def _arm_state(game: Mapping[str, Any], seat: int) -> dict[str, Any]:
    own = _finite(game["scores"][seat], "own cash")
    rival = _finite(game["scores"][1 - seat], "rival cash")
    margin = _finite(own - rival, "terminal margin")
    return {
        "own_cash": own,
        "rival_cash": rival,
        "margin": margin,
        "outcome": _outcome(own, rival),
        "candidate_action_sha256": game["candidate_action_sha256"],
        "trace_sha256": game["trace_sha256"],
    }


def _pair_row(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    own_delta = _finite(right["own_cash"] - left["own_cash"], "own-cash delta")
    rival_delta = _finite(right["rival_cash"] - left["rival_cash"], "rival-cash delta")
    margin_delta = _finite(own_delta - rival_delta, "margin delta")
    action_changed = right["candidate_action_sha256"] != left["candidate_action_sha256"]
    trace_changed = right["trace_sha256"] != left["trace_sha256"]
    score_changed = own_delta != 0 or rival_delta != 0
    if (trace_changed or score_changed) and not action_changed:
        raise EvidenceError(
            "trace or terminal score changed while the captured candidate action stream stayed equal"
        )
    return {
        "own_cash_delta": own_delta,
        "rival_cash_delta": rival_delta,
        "margin_delta": margin_delta,
        "candidate_action_changed": action_changed,
        "trace_changed": trace_changed,
        "new_loss": left["outcome"] != "loss" and right["outcome"] == "loss",
        "lost_win": left["outcome"] == "win" and right["outcome"] != "win",
        "outcome_before": left["outcome"],
        "outcome_after": right["outcome"],
    }


def _numeric_summary(values: Iterable[float]) -> dict[str, Any]:
    data = [_finite(value, "aggregate value") for value in values]
    if not data:
        raise EvidenceError("cannot aggregate an empty value set")
    try:
        total = math.fsum(data)
        mean = total / len(data)
        median = statistics.median(data)
    except OverflowError as exc:
        raise EvidenceError("aggregate arithmetic overflowed") from exc
    return {
        "cells": len(data),
        "mean": _finite(mean, "aggregate mean"),
        "median": _finite(median, "aggregate median"),
        "min": min(data),
        "max": max(data),
        "total": _finite(total, "aggregate total"),
        "positive": sum(value > 0 for value in data),
        "zero": sum(value == 0 for value in data),
        "negative": sum(value < 0 for value in data),
    }


def _aggregate_pair(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise EvidenceError("cannot aggregate an empty pairwise stratum")
    return {
        "cells": len(rows),
        "own_cash": _numeric_summary(row["own_cash_delta"] for row in rows),
        "rival_cash": _numeric_summary(row["rival_cash_delta"] for row in rows),
        "margin": _numeric_summary(row["margin_delta"] for row in rows),
        "candidate_action_changed_cells": sum(
            bool(row["candidate_action_changed"]) for row in rows
        ),
        "trace_changed_cells": sum(bool(row["trace_changed"]) for row in rows),
        "new_losses": sum(bool(row["new_loss"]) for row in rows),
        "lost_wins": sum(bool(row["lost_win"]) for row in rows),
    }


def _pair_safe(summary: Mapping[str, Any], *, require_activation: bool) -> bool:
    own = summary["own_cash"]
    margin = summary["margin"]
    return bool(
        (not require_activation or summary["candidate_action_changed_cells"] > 0)
        and own["mean"] >= 0
        and own["median"] >= 0
        and own["positive"] >= own["negative"]
        and margin["mean"] >= 0
        and summary["new_losses"] == 0
        and summary["lost_wins"] == 0
    )


def _strict_advance_safe(summary: Mapping[str, Any]) -> bool:
    """Singleton/control gate: positive own mean plus non-regression conditions."""
    return _pair_safe(summary, require_activation=True) and summary["own_cash"]["mean"] > 0


def _build_cells(
    indexed: Mapping[str, Mapping[tuple[str, int, int], Mapping[str, Any]]],
    expected: set[tuple[str, int, int]],
) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for opponent, seed, seat in sorted(expected):
        states = {arm: _arm_state(indexed[arm][(opponent, seed, seat)], seat) for arm in ARM_NAMES}
        # Equal candidate action streams must imply an identical deterministic game.
        for i, left_name in enumerate(ARM_NAMES):
            for right_name in ARM_NAMES[i + 1 :]:
                left = states[left_name]
                right = states[right_name]
                if left["candidate_action_sha256"] == right["candidate_action_sha256"]:
                    if (
                        left["trace_sha256"] != right["trace_sha256"]
                        or left["own_cash"] != right["own_cash"]
                        or left["rival_cash"] != right["rival_cash"]
                    ):
                        raise EvidenceError(
                            f"cell {(opponent, seed, seat)} has equal candidate action streams "
                            f"but divergent deterministic outcomes for {left_name}/{right_name}"
                        )
        pairwise = {
            "own_value_vs_control": _pair_row(states["control"], states["own_value"]),
            "certified_pressure_vs_control": _pair_row(states["control"], states["certified_pressure"]),
            "both_vs_control": _pair_row(states["control"], states["both"]),
            "both_vs_own_value": _pair_row(states["own_value"], states["both"]),
            "both_vs_certified_pressure": _pair_row(states["certified_pressure"], states["both"]),
        }
        own_effect = _finite(
            (
                (states["own_value"]["own_cash"] - states["control"]["own_cash"])
                + (states["both"]["own_cash"] - states["certified_pressure"]["own_cash"])
            )
            / 2.0,
            "own-value main effect",
        )
        certified_pressure_effect = _finite(
            (
                (states["certified_pressure"]["own_cash"] - states["control"]["own_cash"])
                + (states["both"]["own_cash"] - states["own_value"]["own_cash"])
            )
            / 2.0,
            "certified-pressure main effect",
        )
        interaction = _finite(
            states["both"]["own_cash"]
            - states["own_value"]["own_cash"]
            - states["certified_pressure"]["own_cash"]
            + states["control"]["own_cash"],
            "own-cash interaction",
        )
        margin_interaction = _finite(
            states["both"]["margin"]
            - states["own_value"]["margin"]
            - states["certified_pressure"]["margin"]
            + states["control"]["margin"],
            "margin interaction",
        )
        cells.append(
            {
                "opponent": opponent,
                "seed": seed,
                "candidate_seat": seat,
                "arms": states,
                "pairwise": pairwise,
                "factorial": {
                    "own_value_main_effect": own_effect,
                    "certified_pressure_main_effect": certified_pressure_effect,
                    "own_cash_interaction": interaction,
                    "margin_interaction": margin_interaction,
                },
            }
        )
    return cells


def _pair_rows(cells: list[Mapping[str, Any]], name: str) -> list[Mapping[str, Any]]:
    return [cell["pairwise"][name] for cell in cells]


def _stratum_key(cell: Mapping[str, Any]) -> str:
    return f"{cell['opponent']}|seat{cell['candidate_seat']}"


def _aggregate_all(cells: list[Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    pair_names = (
        "own_value_vs_control",
        "certified_pressure_vs_control",
        "both_vs_control",
        "both_vs_own_value",
        "both_vs_certified_pressure",
    )
    overall = {name: _aggregate_pair(_pair_rows(cells, name)) for name in pair_names}
    strata: dict[str, Any] = {}
    for key in sorted({_stratum_key(cell) for cell in cells}):
        subset = [cell for cell in cells if _stratum_key(cell) == key]
        strata[key] = {
            name: _aggregate_pair(_pair_rows(subset, name)) for name in pair_names
        }
    factorial = {
        "own_value_main_effect": _numeric_summary(
            cell["factorial"]["own_value_main_effect"] for cell in cells
        ),
        "certified_pressure_main_effect": _numeric_summary(
            cell["factorial"]["certified_pressure_main_effect"] for cell in cells
        ),
        "own_cash_interaction": _numeric_summary(
            cell["factorial"]["own_cash_interaction"] for cell in cells
        ),
        "margin_interaction": _numeric_summary(
            cell["factorial"]["margin_interaction"] for cell in cells
        ),
    }
    return {"pairwise": overall, "factorial": factorial}, strata


def _safe_against_control(
    pair_name: str,
    overall: Mapping[str, Any],
    strata: Mapping[str, Any],
) -> bool:
    return _strict_advance_safe(overall[pair_name]) and all(
        _pair_safe(row[pair_name], require_activation=False) for row in strata.values()
    )


def _noninferior_to_singleton(
    pair_name: str,
    overall: Mapping[str, Any],
    strata: Mapping[str, Any],
) -> bool:
    return _pair_safe(overall[pair_name], require_activation=False) and all(
        _pair_safe(row[pair_name], require_activation=False) for row in strata.values()
    )


def _selection(
    overall: Mapping[str, Any],
    strata: Mapping[str, Any],
) -> dict[str, Any]:
    control_pairs = {
        "own_value": "own_value_vs_control",
        "certified_pressure": "certified_pressure_vs_control",
        "both": "both_vs_control",
    }
    eligible = {
        arm: _safe_against_control(pair, overall, strata)
        for arm, pair in control_pairs.items()
    }
    composition_frontier = bool(
        eligible["both"]
        and (
            not eligible["own_value"]
            or _noninferior_to_singleton("both_vs_own_value", overall, strata)
        )
        and (
            not eligible["certified_pressure"]
            or _noninferior_to_singleton("both_vs_certified_pressure", overall, strata)
        )
    )
    if composition_frontier:
        selected = "both"
    else:
        # A composed arm that is not noninferior to every eligible singleton is
        # not allowed back into the ranking through a larger pooled mean.
        candidates = [
            arm for arm in ("own_value", "certified_pressure") if eligible[arm]
        ]
        selected = max(
            candidates,
            key=lambda arm: (
                overall[control_pairs[arm]]["own_cash"]["mean"],
                overall[control_pairs[arm]]["margin"]["mean"],
                -overall[control_pairs[arm]]["own_cash"]["negative"],
                -overall[control_pairs[arm]]["candidate_action_changed_cells"],
            ),
            default=None,
        )
    if selected is None:
        activated = any(
            overall[pair]["candidate_action_changed_cells"] > 0
            for pair in control_pairs.values()
        )
        verdict = "NO_SAFE_ADVANCE" if activated else "INACTIVE"
    else:
        verdict = {
            "own_value": "SELECT_OWN_VALUE",
            "certified_pressure": "SELECT_CERTIFIED_PRESSURE",
            "both": "SELECT_BOTH",
        }[selected]
    return {
        "verdict": verdict,
        "selected_arm": selected,
        "eligible_against_control": eligible,
        "composition_nondominated": composition_frontier,
        "promotion_authorized": False,
        "hosted_leaderboard_claim": False,
    }


def assess(
    reports: Mapping[str, Mapping[str, Any]],
    arm_manifest: Mapping[str, Any],
    *,
    git_head: str | None = None,
) -> dict[str, Any]:
    """Validate four reports plus exact arm construction and return a decision packet."""
    provenance = _validate_shared_provenance(reports)
    manifest_binding = _validate_arm_manifest(
        arm_manifest, reports, provenance["shared"]
    )
    expected = _expected_keys(reports["control"])
    indexed = {
        arm: _index_report(reports[arm], arm, expected)
        for arm in ARM_NAMES
    }
    cells = _build_cells(indexed, expected)
    overall, strata = _aggregate_all(cells)
    selection = _selection(overall["pairwise"], strata)
    return {
        "schema_version": 1,
        "operation": "titan-v3-sell-objective-certified-pressure-factorial-gate-20260910-01",
        "git_head": git_head,
        "arms": list(ARM_NAMES),
        "paired_provenance": provenance,
        "arm_manifest_binding": manifest_binding,
        "grid": {
            "cells_per_arm": len(expected),
            "total_games": len(expected) * len(ARM_NAMES),
            "opponents": sorted({key[0] for key in expected}),
            "seeds": sorted({key[1] for key in expected}),
            "both_seats": True,
        },
        "overall": overall,
        "by_opponent_seat": strata,
        "selection": selection,
        "cells": cells,
    }


def markdown(report: Mapping[str, Any]) -> str:
    selection = report["selection"]
    pairwise = report["overall"]["pairwise"]
    factorial = report["overall"]["factorial"]
    lines = [
        "# TITAN V3 SELL 2×2 interaction gate",
        "",
        f"- Verdict: **{selection['verdict']}**",
        f"- Selected arm: **{selection['selected_arm'] or 'none'}**",
        f"- Cells per arm: **{report['grid']['cells_per_arm']}**",
        f"- Total official-interpreter games: **{report['grid']['total_games']}**",
        f"- Composition nondominated: **{selection['composition_nondominated']}**",
        "",
        "| Comparison | Mean own Δ | Median own Δ | Mean margin Δ | + / 0 / - | Action changes | New losses | Lost wins |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in (
        "own_value_vs_control",
        "certified_pressure_vs_control",
        "both_vs_control",
        "both_vs_own_value",
        "both_vs_certified_pressure",
    ):
        row = pairwise[name]
        own = row["own_cash"]
        lines.append(
            f"| {name} | {own['mean']:.3f} | {own['median']:.3f} | "
            f"{row['margin']['mean']:.3f} | {own['positive']} / {own['zero']} / "
            f"{own['negative']} | {row['candidate_action_changed_cells']} | "
            f"{row['new_losses']} | {row['lost_wins']} |"
        )
    lines.extend(
        [
            "",
            "## Factorial effects on own cash",
            "",
            f"- Own-value main effect: **{factorial['own_value_main_effect']['mean']:.3f}**",
            f"- Certified-pressure main effect: **{factorial['certified_pressure_main_effect']['mean']:.3f}**",
            f"- Interaction: **{factorial['own_cash_interaction']['mean']:.3f}**",
            f"- Margin interaction: **{factorial['margin_interaction']['mean']:.3f}**",
            "",
            "This gate selects only among the measured four arms. It does not authorize "
            "promotion, alter the canonical package, or make a Kaggle leaderboard claim.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--own-value", type=Path, required=True)
    parser.add_argument("--certified-pressure", type=Path, required=True)
    parser.add_argument("--both", type=Path, required=True)
    parser.add_argument("--arm-manifest", type=Path, required=True)
    parser.add_argument("--head")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    reports = {
        "control": strict_load(args.control, "control"),
        "own_value": strict_load(args.own_value, "own-value"),
        "certified_pressure": strict_load(args.certified_pressure, "certified-pressure"),
        "both": strict_load(args.both, "both"),
    }
    arm_manifest = strict_load(args.arm_manifest, "arm manifest")
    report = assess(reports, arm_manifest, git_head=args.head)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "verdict": report["selection"]["verdict"],
                "selected_arm": report["selection"]["selected_arm"],
                "cells_per_arm": report["grid"]["cells_per_arm"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
