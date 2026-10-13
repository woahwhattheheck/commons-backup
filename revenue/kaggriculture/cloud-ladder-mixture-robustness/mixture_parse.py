"""Strict parser for the TITAN ladder-mixture evidence contract."""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from typing import Any

from mixture_common import (
    SCHEMA, Cell, MixFamily, ParsedInput, _bool, _digest, _exact_keys,
    _family_name, _fraction, _integer, _list, _mapping, _ratio_text,
    _require, _seed_id, _text,
)

def _parse_document(document: Any) -> ParsedInput:
    root = _mapping(document, "root")
    _exact_keys(root, "root", {"schema", "release_pair", "panel", "calibration", "mixture", "gate"})
    _require(root.get("schema") == SCHEMA, "SCHEMA", f"schema must be {SCHEMA}", observed=root.get("schema"))

    release = _mapping(root.get("release_pair"), "release_pair")
    _exact_keys(release, "release_pair", {"incumbent_id", "candidate_id", "incumbent_archive_sha256", "candidate_archive_sha256", "incumbent_source_commit", "candidate_source_commit"})
    incumbent_id = _text(release.get("incumbent_id"), "release_pair.incumbent_id")
    candidate_id = _text(release.get("candidate_id"), "release_pair.candidate_id")
    _require(incumbent_id != candidate_id, "RELEASE_ALIAS", "incumbent and candidate IDs must differ")
    release_normalized = {
        "incumbent_id": incumbent_id,
        "candidate_id": candidate_id,
        "incumbent_archive_sha256": _digest(release.get("incumbent_archive_sha256"), "release_pair.incumbent_archive_sha256"),
        "candidate_archive_sha256": _digest(release.get("candidate_archive_sha256"), "release_pair.candidate_archive_sha256"),
        "incumbent_source_commit": _digest(release.get("incumbent_source_commit"), "release_pair.incumbent_source_commit", bits=160),
        "candidate_source_commit": _digest(release.get("candidate_source_commit"), "release_pair.candidate_source_commit", bits=160),
    }
    _require(
        release_normalized["incumbent_archive_sha256"] != release_normalized["candidate_archive_sha256"],
        "ARCHIVE_ALIAS",
        "incumbent and candidate archive hashes must differ",
    )

    panel = _mapping(root.get("panel"), "panel")
    _exact_keys(panel, "panel", {"panel_receipt_sha256", "engine_sha256", "evaluator_sha256", "loader_sha256", "causality_status", "causality_receipt_sha256", "expected_seats", "cells"})
    expected_seats_raw = _list(panel.get("expected_seats"), "panel.expected_seats")
    expected_seats = tuple(_integer(value, f"panel.expected_seats[{index}]", minimum=0) for index, value in enumerate(expected_seats_raw))
    _require(expected_seats == tuple(sorted(set(expected_seats))), "SEATS", "expected seats must be sorted and unique", seats=expected_seats)
    _require(expected_seats == (0, 1), "SEATS", "TITAN two-player evidence must cover exactly seats 0 and 1", seats=expected_seats)
    causality_status = _text(panel.get("causality_status"), "panel.causality_status")
    panel_normalized = {
        "panel_receipt_sha256": _digest(panel.get("panel_receipt_sha256"), "panel.panel_receipt_sha256"),
        "engine_sha256": _digest(panel.get("engine_sha256"), "panel.engine_sha256"),
        "evaluator_sha256": _digest(panel.get("evaluator_sha256"), "panel.evaluator_sha256"),
        "loader_sha256": _digest(panel.get("loader_sha256"), "panel.loader_sha256"),
        "causality_status": causality_status,
        "causality_receipt_sha256": _digest(panel.get("causality_receipt_sha256"), "panel.causality_receipt_sha256"),
        "expected_seats": list(expected_seats),
    }

    calibration = _mapping(root.get("calibration"), "calibration")
    _exact_keys(calibration, "calibration", {"registry_receipt_sha256", "families"})
    calibration_rows = _list(calibration.get("families"), "calibration.families")
    calibration_status: dict[str, str] = {}
    calibration_normalized_rows: list[dict[str, Any]] = []
    for index, raw in enumerate(calibration_rows):
        row = _mapping(raw, f"calibration.families[{index}]")
        _exact_keys(row, f"calibration.families[{index}]", {"opponent_family", "status", "receipt_sha256"})
        name = _family_name(row.get("opponent_family"), f"calibration.families[{index}].opponent_family")
        _require(name not in calibration_status, "DUPLICATE_FAMILY", "duplicate calibration family", family=name)
        status = _text(row.get("status"), f"calibration.families[{index}].status")
        calibration_status[name] = status
        calibration_normalized_rows.append(
            {
                "opponent_family": name,
                "status": status,
                "receipt_sha256": _digest(row.get("receipt_sha256"), f"calibration.families[{index}].receipt_sha256"),
            }
        )
    _require(bool(calibration_status), "CALIBRATION_EMPTY", "calibration.families must not be empty")
    calibration_normalized_rows.sort(key=lambda row: row["opponent_family"])
    calibration_normalized = {
        "registry_receipt_sha256": _digest(calibration.get("registry_receipt_sha256"), "calibration.registry_receipt_sha256"),
        "families": calibration_normalized_rows,
    }

    mixture = _mapping(root.get("mixture"), "mixture")
    _exact_keys(mixture, "mixture", {"snapshot_id", "snapshot_sha256", "total_variation_radius", "families"})
    radius = _fraction(mixture.get("total_variation_radius"), "mixture.total_variation_radius")
    _require(Fraction(0) <= radius <= Fraction(1), "RADIUS", "total variation radius must be in [0,1]", radius=_ratio_text(radius))
    mix_rows = _list(mixture.get("families"), "mixture.families")
    preliminary: list[tuple[str, int, Fraction, Fraction]] = []
    seen_mix: set[str] = set()
    for index, raw in enumerate(mix_rows):
        row = _mapping(raw, f"mixture.families[{index}]")
        _exact_keys(row, f"mixture.families[{index}]", {"opponent_family", "hosted_count", "min_weight", "max_weight"})
        name = _family_name(row.get("opponent_family"), f"mixture.families[{index}].opponent_family")
        _require(name not in seen_mix, "DUPLICATE_FAMILY", "duplicate mixture family", family=name)
        seen_mix.add(name)
        count = _integer(row.get("hosted_count"), f"mixture.families[{index}].hosted_count", minimum=0)
        lower = _fraction(row.get("min_weight"), f"mixture.families[{index}].min_weight")
        upper = _fraction(row.get("max_weight"), f"mixture.families[{index}].max_weight")
        _require(Fraction(0) <= lower <= upper <= Fraction(1), "WEIGHT_BOUND", "weight bounds must satisfy 0 <= min <= max <= 1", family=name, lower=_ratio_text(lower), upper=_ratio_text(upper))
        preliminary.append((name, count, lower, upper))
    _require(bool(preliminary), "MIXTURE_EMPTY", "mixture.families must not be empty")
    total_count = sum(row[1] for row in preliminary)
    _require(total_count > 0, "HOSTED_COUNT", "sum of hosted_count must be positive")
    families: list[MixFamily] = []
    mix_normalized_rows: list[dict[str, Any]] = []
    for name, count, lower, upper in preliminary:
        nominal = Fraction(count, total_count)
        _require(lower <= nominal <= upper, "NOMINAL_BOUND", "nominal hosted weight lies outside declared bounds", family=name, nominal=_ratio_text(nominal), lower=_ratio_text(lower), upper=_ratio_text(upper))
        families.append(MixFamily(name, count, nominal, lower, upper))
        mix_normalized_rows.append(
            {
                "opponent_family": name,
                "hosted_count": count,
                "nominal_weight": _ratio_text(nominal),
                "min_weight": _ratio_text(lower),
                "max_weight": _ratio_text(upper),
            }
        )
    _require(sum(f.lower for f in families) <= 1 <= sum(f.upper for f in families), "INFEASIBLE_BOUNDS", "family weight bounds cannot form a probability distribution")
    families.sort(key=lambda family: family.name)
    mix_normalized_rows.sort(key=lambda row: row["opponent_family"])
    mixture_normalized = {
        "snapshot_id": _text(mixture.get("snapshot_id"), "mixture.snapshot_id"),
        "snapshot_sha256": _digest(mixture.get("snapshot_sha256"), "mixture.snapshot_sha256"),
        "total_variation_radius": _ratio_text(radius),
        "families": mix_normalized_rows,
    }

    gate = _mapping(root.get("gate"), "gate")
    _exact_keys(
        gate,
        "gate",
        {
            "minimum_seed_clusters",
            "minimum_seed_own_delta",
            "minimum_seed_margin_delta",
            "minimum_family_seat_own_delta",
            "minimum_family_seat_margin_delta",
            "require_strict_worst_case",
            "require_uniform_family_reference",
            "require_leave_one_family_out",
        },
    )
    minimum_seed_clusters = _integer(gate.get("minimum_seed_clusters"), "gate.minimum_seed_clusters", minimum=2)
    minimum_seed_own_delta = _fraction(gate.get("minimum_seed_own_delta"), "gate.minimum_seed_own_delta")
    minimum_seed_margin_delta = _fraction(gate.get("minimum_seed_margin_delta"), "gate.minimum_seed_margin_delta")
    minimum_family_seat_own_delta = _fraction(
        gate.get("minimum_family_seat_own_delta"),
        "gate.minimum_family_seat_own_delta",
    )
    minimum_family_seat_margin_delta = _fraction(
        gate.get("minimum_family_seat_margin_delta"),
        "gate.minimum_family_seat_margin_delta",
    )
    strict_worst_case = _bool(gate.get("require_strict_worst_case"), "gate.require_strict_worst_case")
    require_uniform_family_reference = _bool(
        gate.get("require_uniform_family_reference"),
        "gate.require_uniform_family_reference",
    )
    require_leave_one_family_out = _bool(
        gate.get("require_leave_one_family_out"),
        "gate.require_leave_one_family_out",
    )
    gate_normalized = {
        "minimum_seed_clusters": minimum_seed_clusters,
        "minimum_seed_own_delta": _ratio_text(minimum_seed_own_delta),
        "minimum_seed_margin_delta": _ratio_text(minimum_seed_margin_delta),
        "minimum_family_seat_own_delta": _ratio_text(minimum_family_seat_own_delta),
        "minimum_family_seat_margin_delta": _ratio_text(minimum_family_seat_margin_delta),
        "require_strict_worst_case": strict_worst_case,
        "require_uniform_family_reference": require_uniform_family_reference,
        "require_leave_one_family_out": require_leave_one_family_out,
    }

    cells_raw = _list(panel.get("cells"), "panel.cells")
    _require(bool(cells_raw), "CELLS_EMPTY", "panel.cells must not be empty")
    cells: list[Cell] = []
    normalized_cells: list[dict[str, Any]] = []
    seen_cells: set[tuple[str, str, int]] = set()
    for index, raw in enumerate(cells_raw):
        row = _mapping(raw, f"panel.cells[{index}]")
        _exact_keys(row, f"panel.cells[{index}]", {"status", "opponent_family", "seed", "candidate_seat", "incumbent_steps", "candidate_steps", "incumbent_own", "incumbent_rival", "candidate_own", "candidate_rival", "action_changed", "trace_changed"})
        prefix = f"panel.cells[{index}]"
        _require(row.get("status") == "complete", "CELL_STATUS", "every cell must be complete", index=index, status=row.get("status"))
        family = _family_name(row.get("opponent_family"), f"{prefix}.opponent_family")
        seed = _seed_id(row.get("seed"), f"{prefix}.seed")
        seat = _integer(row.get("candidate_seat"), f"{prefix}.candidate_seat", minimum=0)
        _require(seat in expected_seats, "CELL_SEAT", "cell seat is outside expected seats", family=family, seed=seed, seat=seat)
        key = (family, seed, seat)
        _require(key not in seen_cells, "DUPLICATE_CELL", "duplicate opponent×seed×seat cell", family=family, seed=seed, seat=seat)
        seen_cells.add(key)
        incumbent_steps = _integer(row.get("incumbent_steps"), f"{prefix}.incumbent_steps", minimum=0)
        candidate_steps = _integer(row.get("candidate_steps"), f"{prefix}.candidate_steps", minimum=0)
        _require(incumbent_steps == 719 and candidate_steps == 719, "LIFECYCLE", "every arm must contain the exact 719-action lifecycle", family=family, seed=seed, seat=seat, incumbent_steps=incumbent_steps, candidate_steps=candidate_steps)
        cell = Cell(
            family=family,
            seed=seed,
            seat=seat,
            incumbent_own=_fraction(row.get("incumbent_own"), f"{prefix}.incumbent_own"),
            incumbent_rival=_fraction(row.get("incumbent_rival"), f"{prefix}.incumbent_rival"),
            candidate_own=_fraction(row.get("candidate_own"), f"{prefix}.candidate_own"),
            candidate_rival=_fraction(row.get("candidate_rival"), f"{prefix}.candidate_rival"),
            action_changed=_bool(row.get("action_changed"), f"{prefix}.action_changed"),
            trace_changed=_bool(row.get("trace_changed"), f"{prefix}.trace_changed"),
        )
        cells.append(cell)
        normalized_cells.append(
            {
                "status": "complete",
                "opponent_family": family,
                "seed": seed,
                "candidate_seat": seat,
                "incumbent_steps": incumbent_steps,
                "candidate_steps": candidate_steps,
                "incumbent_own": _ratio_text(cell.incumbent_own),
                "incumbent_rival": _ratio_text(cell.incumbent_rival),
                "candidate_own": _ratio_text(cell.candidate_own),
                "candidate_rival": _ratio_text(cell.candidate_rival),
                "action_changed": cell.action_changed,
                "trace_changed": cell.trace_changed,
            }
        )

    mix_names = {family.name for family in families}
    cell_names = {cell.family for cell in cells}
    calibration_names = set(calibration_status)
    _require(mix_names == cell_names == calibration_names, "FAMILY_CLOSURE", "mixture, panel, and calibration family sets must match exactly", mixture=sorted(mix_names), panel=sorted(cell_names), calibration=sorted(calibration_names))

    grouped_seats: dict[tuple[str, str], set[int]] = defaultdict(set)
    for cell in cells:
        grouped_seats[(cell.family, cell.seed)].add(cell.seat)
    for (family, seed), observed in sorted(grouped_seats.items()):
        _require(tuple(sorted(observed)) == expected_seats, "MISSING_SEAT", "every opponent×seed cluster must contain both candidate seats", family=family, seed=seed, observed=sorted(observed), expected=list(expected_seats))

    cells.sort(key=lambda cell: (cell.family, cell.seed, cell.seat))
    normalized_cells.sort(key=lambda row: (row["opponent_family"], row["seed"], row["candidate_seat"]))
    panel_normalized["cells"] = normalized_cells
    normalized = {
        "schema": SCHEMA,
        "release_pair": release_normalized,
        "panel": panel_normalized,
        "calibration": calibration_normalized,
        "mixture": mixture_normalized,
        "gate": gate_normalized,
    }
    return ParsedInput(
        normalized=normalized,
        families=tuple(families),
        cells=tuple(cells),
        expected_seats=expected_seats,
        calibration_status=calibration_status,
        minimum_seed_clusters=minimum_seed_clusters,
        minimum_seed_own_delta=minimum_seed_own_delta,
        minimum_seed_margin_delta=minimum_seed_margin_delta,
        minimum_family_seat_own_delta=minimum_family_seat_own_delta,
        minimum_family_seat_margin_delta=minimum_family_seat_margin_delta,
        total_variation_radius=radius,
        strict_worst_case=strict_worst_case,
        require_uniform_family_reference=require_uniform_family_reference,
        require_leave_one_family_out=require_leave_one_family_out,
    )
