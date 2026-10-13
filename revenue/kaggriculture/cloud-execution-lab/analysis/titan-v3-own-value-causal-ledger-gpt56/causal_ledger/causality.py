# SPDX-License-Identifier: Apache-2.0
"""Replay identity and first-realized-divergence analysis."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .strict import EvidenceError, _exact_equal, _mapping, _number, _require_exact, digest
from .game_model import GameView, validate_game

def _validate_replay(
    primary_raw: Any,
    replay_raw: Any,
    *,
    expected_actions: int,
    field: str,
    expected_identity: Mapping[str, Any],
    expected_provenance: Mapping[str, str],
) -> str:
    primary = validate_game(
        primary_raw,
        expected_actions=expected_actions,
        field=f"{field}.primary",
        expected_identity=expected_identity,
        expected_provenance=expected_provenance,
    )
    replay = validate_game(
        replay_raw,
        expected_actions=expected_actions,
        field=f"{field}.replay",
        expected_identity=expected_identity,
        expected_provenance=expected_provenance,
    )
    if primary.digest != replay.digest:
        raise EvidenceError(f"{field} replay is not byte-deterministic")
    return replay.digest


def _outcome(scores: Sequence[Any], seat: int) -> str:
    own = _number(scores[seat], "scores[tested_seat]")
    rival = _number(scores[1 - seat], "scores[rival_seat]")
    if own > rival:
        return "W"
    if own < rival:
        return "L"
    return "T"


def _outcome_value(value: str) -> int:
    return {"L": -1, "T": 0, "W": 1}[value]


def _first_divergence(control: GameView, candidate: GameView, seat: int) -> dict[str, Any] | None:
    rival = 1 - seat
    for index, (left, right) in enumerate(zip(control.steps, candidate.steps)):
        tested_same = _exact_equal(left["actions"][seat], right["actions"][seat])
        row_same = _exact_equal(left, right)
        if tested_same:
            if not row_same:
                raise EvidenceError(
                    "arms diverged before the first tested-seat action change "
                    f"at step {index}"
                )
            continue
        _require_exact(
            left["preworld"], right["preworld"],
            f"first divergence step {index} does not share an identical preworld",
        )
        _require_exact(
            left["observations"], right["observations"],
            f"first divergence step {index} does not share identical observations",
        )
        _require_exact(
            left["actions"][rival], right["actions"][rival],
            f"rival action differs at tested-seat first divergence step {index}",
        )
        if _exact_equal(left["postworld"], right["postworld"]):
            raise EvidenceError(
                f"tested-seat action change at step {index} did not change the next world"
            )
        return {
            "step": index,
            "preworld_sha256": digest(left["preworld"]),
            "observations_sha256": digest(left["observations"]),
            "control_tested_action_sha256": digest(left["actions"][seat]),
            "candidate_tested_action_sha256": digest(right["actions"][seat]),
            "rival_action_sha256": digest(left["actions"][rival]),
            "control_postworld_sha256": digest(left["postworld"]),
            "candidate_postworld_sha256": digest(right["postworld"]),
            "realized_next_world_change": True,
        }
    return None


def _arm(
    value: Any,
    *,
    expected_actions: int,
    field: str,
    expected_identity: Mapping[str, Any],
    expected_provenance: Mapping[str, str],
) -> tuple[GameView, Any]:
    arm = _mapping(value, field)
    if set(arm) != {"primary", "replay"}:
        missing = sorted({"primary", "replay"} - set(arm))
        extra = sorted(set(arm) - {"primary", "replay"})
        raise EvidenceError(f"{field} key mismatch; missing={missing}, extra={extra}")
    primary = validate_game(
        arm["primary"],
        expected_actions=expected_actions,
        field=f"{field}.primary",
        expected_identity=expected_identity,
        expected_provenance=expected_provenance,
    )
    return primary, arm["replay"]

