# SPDX-License-Identifier: Apache-2.0
"""Complete-grid action, world, terminal, and economic evidence validation."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from .core import (
    BehaviorGateError,
    CandidateSpec,
    COMPLETE_STATUSES,
    EXPECTED_SEATS,
    FamilySpec,
    OBSERVATIONS_SCHEMA,
    _finite_number,
    _mapping,
    _nonempty_string,
    _nonnegative_int,
    _sequence,
    _sha256,
    sha256_json,
)

@dataclass(frozen=True, order=True)
class CellKey:
    environment_seed: int
    opponent_sha256: str
    seat: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "environment_seed": self.environment_seed,
            "opponent_sha256": self.opponent_sha256,
            "seat": self.seat,
        }


@dataclass(frozen=True)
class CellEvidence:
    key: CellKey
    action_tape_sha256: str
    world_tape_sha256: str
    terminal_state_sha256: str
    own_cash: float
    rival_cash: float
    margin: float
    outcome: str

    def action_dict(self) -> dict[str, Any]:
        return {**self.key.as_dict(), "action_tape_sha256": self.action_tape_sha256}

    def effect_dict(self) -> dict[str, Any]:
        return {
            **self.key.as_dict(),
            "action_tape_sha256": self.action_tape_sha256,
            "world_tape_sha256": self.world_tape_sha256,
            "terminal_state_sha256": self.terminal_state_sha256,
            "own_cash": self.own_cash,
            "rival_cash": self.rival_cash,
            "margin": self.margin,
            "outcome": self.outcome,
        }

    def score_dict(self) -> dict[str, Any]:
        return {
            **self.key.as_dict(),
            "own_cash": self.own_cash,
            "rival_cash": self.rival_cash,
            "margin": self.margin,
            "outcome": self.outcome,
        }


@dataclass(frozen=True)
class CandidateObservation:
    spec: CandidateSpec
    cells: Mapping[CellKey, CellEvidence]

    @property
    def action_signature_sha256(self) -> str:
        return sha256_json([self.cells[key].action_dict() for key in sorted(self.cells)])

    @property
    def behavior_signature_sha256(self) -> str:
        return sha256_json([self.cells[key].effect_dict() for key in sorted(self.cells)])

    @property
    def score_signature_sha256(self) -> str:
        return sha256_json([self.cells[key].score_dict() for key in sorted(self.cells)])


def canonical_schedule(keys: Iterable[CellKey]) -> list[dict[str, Any]]:
    return [key.as_dict() for key in sorted(keys)]


def schedule_sha256(keys: Iterable[CellKey]) -> str:
    return sha256_json(canonical_schedule(keys))


def _validate_pairs(keys: Iterable[CellKey], where: str) -> int:
    seats: dict[tuple[int, str], set[int]] = defaultdict(set)
    for key in keys:
        seats[(key.environment_seed, key.opponent_sha256)].add(key.seat)
    broken = [
        {
            "environment_seed": seed,
            "opponent_sha256": opponent,
            "seats": sorted(actual),
        }
        for (seed, opponent), actual in sorted(seats.items())
        if actual != EXPECTED_SEATS
    ]
    if broken:
        raise BehaviorGateError(
            f"{where} has incomplete paired-seat matchups: "
            + json.dumps(broken, sort_keys=True, separators=(",", ":"))
        )
    return len(seats)


def _parse_cell(
    raw: Mapping[str, Any],
    where: str,
    *,
    family: FamilySpec,
    candidate: CandidateSpec,
) -> CellEvidence:
    row = _mapping(raw, where)
    status = str(row.get("status", "")).upper()
    if status not in COMPLETE_STATUSES:
        raise BehaviorGateError(f"{where}.status is not complete: {status or '<missing>'}")
    for field in ("error", "timeout", "timed_out"):
        if row.get(field):
            raise BehaviorGateError(f"{where} reports {field}")

    if _sha256(row.get("candidate_archive_sha256"), f"{where}.candidate_archive_sha256") != candidate.archive_sha256:
        raise BehaviorGateError(f"{where} is bound to the wrong candidate archive")
    if (
        _sha256(
            row.get("candidate_executable_closure_sha256"),
            f"{where}.candidate_executable_closure_sha256",
        )
        != candidate.executable_closure_sha256
    ):
        raise BehaviorGateError(f"{where} is bound to the wrong executable closure")
    if (
        _sha256(
            row.get("candidate_invocation_sha256"),
            f"{where}.candidate_invocation_sha256",
        )
        != candidate.invocation_sha256
    ):
        raise BehaviorGateError(f"{where} is bound to the wrong invocation contract")

    row_engine = _sha256(row.get("engine_sha256"), f"{where}.engine_sha256")
    if row_engine != family.engine_sha256:
        raise BehaviorGateError(f"{where}.engine_sha256 does not match family")
    row_evaluator = _sha256(row.get("evaluator_sha256"), f"{where}.evaluator_sha256")
    if row_evaluator != family.evaluator_sha256:
        raise BehaviorGateError(f"{where}.evaluator_sha256 does not match family")

    seed = _nonnegative_int(
        row.get("environment_seed", row.get("seed")),
        f"{where}.environment_seed",
    )
    opponent = _sha256(row.get("opponent_sha256"), f"{where}.opponent_sha256")
    seat = row.get("seat", row.get("candidate_seat"))
    if isinstance(seat, bool) or not isinstance(seat, int) or seat not in EXPECTED_SEATS:
        raise BehaviorGateError(f"{where}.seat must be exactly 0 or 1")

    own_cash = _finite_number(row.get("own_cash"), f"{where}.own_cash")
    rival_cash = _finite_number(row.get("rival_cash"), f"{where}.rival_cash")
    reported_margin = _finite_number(row.get("margin"), f"{where}.margin")
    derived_margin = own_cash - rival_cash
    if not math.isclose(reported_margin, derived_margin, rel_tol=0.0, abs_tol=1e-9):
        raise BehaviorGateError(
            f"{where}.margin contradicts own_cash-rival_cash: {reported_margin} != {derived_margin}"
        )
    margin = 0.0 if derived_margin == 0.0 else derived_margin

    outcome = _nonempty_string(row.get("outcome"), f"{where}.outcome").upper()
    expected_outcome = "WIN" if margin > 0 else "LOSS" if margin < 0 else "TIE"
    if outcome != expected_outcome:
        raise BehaviorGateError(
            f"{where}.outcome={outcome!r} contradicts cash-derived margin ({expected_outcome})"
        )

    return CellEvidence(
        key=CellKey(seed, opponent, seat),
        action_tape_sha256=_sha256(
            row.get("action_tape_sha256"), f"{where}.action_tape_sha256"
        ),
        world_tape_sha256=_sha256(
            row.get("world_tape_sha256"), f"{where}.world_tape_sha256"
        ),
        terminal_state_sha256=_sha256(
            row.get("terminal_state_sha256"), f"{where}.terminal_state_sha256"
        ),
        own_cash=own_cash,
        rival_cash=rival_cash,
        margin=margin,
        outcome=outcome,
    )


def validate_observations(
    raw: Mapping[str, Any], family: FamilySpec
) -> tuple[tuple[CandidateObservation, ...], str]:
    raw = _mapping(raw, "observations")
    if raw.get("schema") != OBSERVATIONS_SCHEMA:
        raise BehaviorGateError(
            f"observations.schema must equal {OBSERVATIONS_SCHEMA!r}"
        )
    if _sha256(raw.get("family_sha256"), "observations.family_sha256") != family.family_sha256:
        raise BehaviorGateError("observations.family_sha256 does not match family")
    for field, expected in (
        ("engine_sha256", family.engine_sha256),
        ("evaluator_sha256", family.evaluator_sha256),
        ("schedule_sha256", family.schedule_sha256),
    ):
        if _sha256(raw.get(field), f"observations.{field}") != expected:
            raise BehaviorGateError(f"observations.{field} does not match family")

    values = _sequence(raw.get("candidates"), "observations.candidates")
    expected_candidates = family.candidates_by_id
    parsed: dict[str, CandidateObservation] = {}
    reference_keys: set[CellKey] | None = None

    for candidate_index, value in enumerate(values):
        where = f"observations.candidates[{candidate_index}]"
        row = _mapping(value, where)
        candidate_id = _nonempty_string(row.get("candidate_id"), f"{where}.candidate_id")
        if candidate_id in parsed:
            raise BehaviorGateError(f"duplicate observation candidate_id: {candidate_id!r}")
        try:
            spec = expected_candidates[candidate_id]
        except KeyError as exc:
            raise BehaviorGateError(
                f"observations includes undeclared candidate {candidate_id!r}"
            ) from exc
        if _sha256(row.get("archive_sha256"), f"{where}.archive_sha256") != spec.archive_sha256:
            raise BehaviorGateError(f"{where}.archive_sha256 does not match family")
        if (
            _sha256(
                row.get("executable_closure_sha256"),
                f"{where}.executable_closure_sha256",
            )
            != spec.executable_closure_sha256
        ):
            raise BehaviorGateError(
                f"{where}.executable_closure_sha256 does not match family"
            )
        if _nonempty_string(row.get("entrypoint"), f"{where}.entrypoint") != spec.entrypoint:
            raise BehaviorGateError(f"{where}.entrypoint does not match family")
        if (
            _sha256(row.get("invocation_sha256"), f"{where}.invocation_sha256")
            != spec.invocation_sha256
        ):
            raise BehaviorGateError(f"{where}.invocation_sha256 does not match family")

        cells_raw = _sequence(row.get("cells"), f"{where}.cells")
        if not cells_raw:
            raise BehaviorGateError(f"{where}.cells must be nonempty")
        games = _nonnegative_int(row.get("games"), f"{where}.games")
        if games != len(cells_raw):
            raise BehaviorGateError(
                f"{where}.games={games} does not equal cells={len(cells_raw)}"
            )

        cells: dict[CellKey, CellEvidence] = {}
        for cell_index, cell_raw in enumerate(cells_raw):
            cell = _parse_cell(
                _mapping(cell_raw, f"{where}.cells[{cell_index}]"),
                f"{where}.cells[{cell_index}]",
                family=family,
                candidate=spec,
            )
            if cell.key in cells:
                raise BehaviorGateError(
                    f"{where} has duplicate cell "
                    + json.dumps(cell.key.as_dict(), sort_keys=True, separators=(",", ":"))
                )
            cells[cell.key] = cell

        _validate_pairs(cells, where)
        actual_schedule = schedule_sha256(cells)
        if actual_schedule != family.schedule_sha256:
            raise BehaviorGateError(
                f"{where} schedule mismatch: expected={family.schedule_sha256} actual={actual_schedule}"
            )
        keys = set(cells)
        if reference_keys is None:
            reference_keys = keys
        elif keys != reference_keys:
            raise BehaviorGateError(
                f"{where} does not contain the exact common candidate grid"
            )
        parsed[candidate_id] = CandidateObservation(spec=spec, cells=cells)

    missing = sorted(set(expected_candidates) - set(parsed))
    if missing:
        raise BehaviorGateError(f"observations omits declared candidates: {missing}")
    if len(parsed) != len(expected_candidates):
        raise BehaviorGateError("observations candidate cardinality mismatch")

    normalized = {
        "schema": OBSERVATIONS_SCHEMA,
        "family_sha256": family.family_sha256,
        "engine_sha256": family.engine_sha256,
        "evaluator_sha256": family.evaluator_sha256,
        "schedule_sha256": family.schedule_sha256,
        "candidates": [
            {
                **observation.spec.as_dict(),
                "games": len(observation.cells),
                "cells": [
                    {
                        "status": "COMPLETE",
                        "candidate_archive_sha256": observation.spec.archive_sha256,
                        "candidate_executable_closure_sha256": observation.spec.executable_closure_sha256,
                        "candidate_invocation_sha256": observation.spec.invocation_sha256,
                        "engine_sha256": family.engine_sha256,
                        "evaluator_sha256": family.evaluator_sha256,
                        **observation.cells[key].effect_dict(),
                    }
                    for key in sorted(observation.cells)
                ],
            }
            for observation in sorted(parsed.values(), key=lambda item: item.spec.candidate_id)
        ],
    }
    digest = sha256_json(normalized)
    declared = raw.get("observations_sha256")
    if declared is not None:
        declared = _sha256(declared, "observations.observations_sha256")
        if declared != digest:
            raise BehaviorGateError(
                f"observations.observations_sha256 mismatch: declared={declared} actual={digest}"
            )
    return tuple(sorted(parsed.values(), key=lambda item: item.spec.candidate_id)), digest


def _group_by(
    observations: Sequence[CandidateObservation], attribute: str
) -> Mapping[str, list[CandidateObservation]]:
    grouped: dict[str, list[CandidateObservation]] = defaultdict(list)
    for observation in observations:
        grouped[str(getattr(observation, attribute))].append(observation)
    return grouped
