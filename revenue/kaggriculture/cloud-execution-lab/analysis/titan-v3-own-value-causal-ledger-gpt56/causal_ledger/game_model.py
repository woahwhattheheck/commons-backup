# SPDX-License-Identifier: Apache-2.0
"""Strict transition-ledger model and game-level provenance validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .strict import (
    GAME_SCHEMA,
    EvidenceError,
    _exact_equal,
    _integer,
    _mapping,
    _require_exact,
    _sequence,
    _sha256,
    canonical_bytes,
    digest,
)

@dataclass(frozen=True)
class GameView:
    identity: Mapping[str, Any]
    provenance: Mapping[str, str]
    steps: tuple[Mapping[str, Any], ...]
    terminal_bank: tuple[Any, Any]
    scores: tuple[Any, Any]
    digest: str


_REQUIRED_PROVENANCE = (
    "engine_sha256",
    "loader_sha256",
    "evaluator_sha256",
    "runtime_tree_sha256",
    "entry_sha256",
    "opponent_tree_sha256",
)
_SHARED_PROVENANCE = (
    "engine_sha256",
    "loader_sha256",
    "evaluator_sha256",
    "opponent_tree_sha256",
)
_PANEL_PROVENANCE = (
    "engine_sha256",
    "loader_sha256",
    "evaluator_sha256",
    "control_runtime_tree_sha256",
    "control_entry_sha256",
    "candidate_runtime_tree_sha256",
    "candidate_entry_sha256",
    "opponent_tree_sha256",
)
_IDENTITY_FIELDS = ("opponent", "seed", "candidate_seat", "arm")


def _validate_identity(value: Any, field: str) -> dict[str, Any]:
    identity = _mapping(value, field)
    if set(identity) != set(_IDENTITY_FIELDS):
        missing = sorted(set(_IDENTITY_FIELDS) - set(identity))
        extra = sorted(set(identity) - set(_IDENTITY_FIELDS))
        raise EvidenceError(f"{field} key mismatch; missing={missing}, extra={extra}")
    opponent = identity["opponent"]
    if not isinstance(opponent, str) or not opponent.strip():
        raise EvidenceError(f"{field}.opponent must be a nonempty string")
    seed = _integer(identity["seed"], f"{field}.seed", minimum=0)
    seat = _integer(identity["candidate_seat"], f"{field}.candidate_seat", minimum=0)
    if seat not in (0, 1):
        raise EvidenceError(f"{field}.candidate_seat must be 0 or 1")
    arm = identity["arm"]
    if arm not in ("control", "candidate"):
        raise EvidenceError(f"{field}.arm must be 'control' or 'candidate'")
    return {"opponent": opponent, "seed": seed, "candidate_seat": seat, "arm": arm}


def validate_game(
    value: Any,
    *,
    expected_actions: int,
    field: str,
    expected_identity: Mapping[str, Any] | None = None,
    expected_provenance: Mapping[str, str] | None = None,
) -> GameView:
    game = _mapping(value, field)
    if game.get("schema") != GAME_SCHEMA:
        raise EvidenceError(f"{field}.schema must be {GAME_SCHEMA!r}")
    if game.get("complete") is not True:
        raise EvidenceError(f"{field}.complete must be the boolean true")

    identity = _validate_identity(game.get("identity"), f"{field}.identity")
    if expected_identity is not None:
        _require_exact(identity, dict(expected_identity), f"{field}.identity is detached from its cell")

    provenance = _mapping(game.get("provenance"), f"{field}.provenance")
    normalized_provenance: dict[str, str] = {}
    if set(provenance) != set(_REQUIRED_PROVENANCE):
        missing = sorted(set(_REQUIRED_PROVENANCE) - set(provenance))
        extra = sorted(set(provenance) - set(_REQUIRED_PROVENANCE))
        raise EvidenceError(
            f"{field}.provenance key mismatch; missing={missing}, extra={extra}"
        )
    for key in _REQUIRED_PROVENANCE:
        normalized_provenance[key] = _sha256(
            provenance[key], f"{field}.provenance.{key}"
        )
    if expected_provenance is not None:
        _require_exact(
            normalized_provenance,
            dict(expected_provenance),
            f"{field}.provenance is detached from the panel closure",
        )

    steps = _sequence(game.get("steps"), f"{field}.steps", length=expected_actions)
    normalized_steps: list[Mapping[str, Any]] = []
    prior_postworld: Any = None
    for index, raw_step in enumerate(steps):
        step = _mapping(raw_step, f"{field}.steps[{index}]")
        required = {"step", "preworld", "observations", "actions", "postworld", "bank"}
        if set(step) != required:
            missing = sorted(required - set(step))
            extra = sorted(set(step) - required)
            raise EvidenceError(
                f"{field}.steps[{index}] key mismatch; missing={missing}, extra={extra}"
            )
        if _integer(step["step"], f"{field}.steps[{index}].step", minimum=0) != index:
            raise EvidenceError(f"{field}.steps[{index}].step must equal {index}")
        observations = _sequence(
            step["observations"], f"{field}.steps[{index}].observations", length=2
        )
        actions = _sequence(step["actions"], f"{field}.steps[{index}].actions", length=2)
        bank = _sequence(step["bank"], f"{field}.steps[{index}].bank", length=2)
        _integer(bank[0], f"{field}.steps[{index}].bank[0]")
        _integer(bank[1], f"{field}.steps[{index}].bank[1]")
        canonical_bytes(step["preworld"])
        canonical_bytes(observations)
        canonical_bytes(actions)
        canonical_bytes(step["postworld"])
        if index and not _exact_equal(prior_postworld, step["preworld"]):
            raise EvidenceError(
                f"{field}.steps[{index}] preworld does not equal prior postworld"
            )
        prior_postworld = step["postworld"]
        normalized_steps.append(step)

    terminal_bank = _sequence(game.get("terminal_bank"), f"{field}.terminal_bank", length=2)
    scores = _sequence(game.get("scores"), f"{field}.scores", length=2)
    for seat in (0, 1):
        _integer(terminal_bank[seat], f"{field}.terminal_bank[{seat}]")
        _integer(scores[seat], f"{field}.scores[{seat}]")
    _require_exact(
        normalized_steps[-1]["bank"],
        terminal_bank,
        f"{field}.terminal_bank must equal the final interpreted bank",
    )
    _require_exact(
        scores,
        terminal_bank,
        f"{field}.scores must be byte-exact terminal-bank values",
    )
    allowed = {
        "schema",
        "complete",
        "identity",
        "provenance",
        "steps",
        "terminal_bank",
        "scores",
    }
    if set(game) != allowed:
        missing = sorted(allowed - set(game))
        extra = sorted(set(game) - allowed)
        raise EvidenceError(f"{field} key mismatch; missing={missing}, extra={extra}")
    return GameView(
        identity=identity,
        provenance=normalized_provenance,
        steps=tuple(normalized_steps),
        terminal_bank=(terminal_bank[0], terminal_bank[1]),
        scores=(scores[0], scores[1]),
        digest=digest(game),
    )
