# SPDX-License-Identifier: Apache-2.0
"""Cell-level causal custody for paired TITAN policy games."""
from __future__ import annotations

from typing import Any, Mapping

from .strict import EvidenceError, _exact_equal, _integer, _mapping, _number
from .game import (
    _SHARED_PROVENANCE,
    _arm,
    _first_divergence,
    _outcome,
    _outcome_value,
    _validate_replay,
)

def analyze_cell(
    value: Any,
    *,
    expected_actions: int,
    panel_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    cell = _mapping(value, "cell")
    required = {"opponent", "seed", "candidate_seat", "control", "candidate"}
    if set(cell) != required:
        missing = sorted(required - set(cell))
        extra = sorted(set(cell) - required)
        raise EvidenceError(f"cell key mismatch; missing={missing}, extra={extra}")
    opponent = cell["opponent"]
    if not isinstance(opponent, str) or not opponent.strip():
        raise EvidenceError("cell.opponent must be a nonempty string")
    seed = _integer(cell["seed"], "cell.seed", minimum=0)
    seat = _integer(cell["candidate_seat"], "cell.candidate_seat", minimum=0)
    if seat not in (0, 1):
        raise EvidenceError("cell.candidate_seat must be 0 or 1")

    opponent_trees = panel_provenance["opponent_tree_sha256"]
    expected_identities = {
        arm: {
            "opponent": opponent,
            "seed": seed,
            "candidate_seat": seat,
            "arm": arm,
        }
        for arm in ("control", "candidate")
    }
    shared = {
        "engine_sha256": panel_provenance["engine_sha256"],
        "loader_sha256": panel_provenance["loader_sha256"],
        "evaluator_sha256": panel_provenance["evaluator_sha256"],
        "opponent_tree_sha256": opponent_trees[opponent],
    }
    expected_provenance = {
        "control": {
            **shared,
            "runtime_tree_sha256": panel_provenance["control_runtime_tree_sha256"],
            "entry_sha256": panel_provenance["control_entry_sha256"],
        },
        "candidate": {
            **shared,
            "runtime_tree_sha256": panel_provenance["candidate_runtime_tree_sha256"],
            "entry_sha256": panel_provenance["candidate_entry_sha256"],
        },
    }
    control, control_replay = _arm(
        cell["control"],
        expected_actions=expected_actions,
        field="cell.control",
        expected_identity=expected_identities["control"],
        expected_provenance=expected_provenance["control"],
    )
    candidate, candidate_replay = _arm(
        cell["candidate"],
        expected_actions=expected_actions,
        field="cell.candidate",
        expected_identity=expected_identities["candidate"],
        expected_provenance=expected_provenance["candidate"],
    )
    for key in _SHARED_PROVENANCE:
        if control.provenance[key] != candidate.provenance[key]:
            raise EvidenceError(f"control/candidate provenance differs at {key}")
    if control.provenance["runtime_tree_sha256"] == candidate.provenance["runtime_tree_sha256"]:
        raise EvidenceError("control and candidate runtime-tree digests must differ")

    divergence = _first_divergence(control, candidate, seat)
    score_changed = not _exact_equal(list(control.scores), list(candidate.scores))
    action_changed = divergence is not None
    if score_changed and not action_changed:
        raise EvidenceError("terminal score changed without a causal tested-seat action divergence")
    active = score_changed or action_changed
    replay_digests: dict[str, str] | None = None
    if active:
        if control_replay is None or candidate_replay is None:
            raise EvidenceError("every action- or score-active cell requires both deterministic replays")
        replay_digests = {
            "control": _validate_replay(
                cell["control"]["primary"], control_replay,
                expected_actions=expected_actions,
                field="cell.control",
                expected_identity=expected_identities["control"],
                expected_provenance=expected_provenance["control"],
            ),
            "candidate": _validate_replay(
                cell["candidate"]["primary"], candidate_replay,
                expected_actions=expected_actions,
                field="cell.candidate",
                expected_identity=expected_identities["candidate"],
                expected_provenance=expected_provenance["candidate"],
            ),
        }
    else:
        if control_replay is not None:
            _validate_replay(
                cell["control"]["primary"],
                control_replay,
                expected_actions=expected_actions,
                field="cell.control",
                expected_identity=expected_identities["control"],
                expected_provenance=expected_provenance["control"],
            )
        if candidate_replay is not None:
            _validate_replay(
                cell["candidate"]["primary"],
                candidate_replay,
                expected_actions=expected_actions,
                field="cell.candidate",
                expected_identity=expected_identities["candidate"],
                expected_provenance=expected_provenance["candidate"],
            )

    control_own = _number(control.scores[seat], "control own score")
    control_rival = _number(control.scores[1 - seat], "control rival score")
    candidate_own = _number(candidate.scores[seat], "candidate own score")
    candidate_rival = _number(candidate.scores[1 - seat], "candidate rival score")
    own_delta = candidate_own - control_own
    rival_delta = candidate_rival - control_rival
    margin_delta = own_delta - rival_delta
    control_outcome = _outcome(control.scores, seat)
    candidate_outcome = _outcome(candidate.scores, seat)
    return {
        "opponent": opponent,
        "seed": seed,
        "candidate_seat": seat,
        "control_game_sha256": control.digest,
        "candidate_game_sha256": candidate.digest,
        "control_runtime_tree_sha256": control.provenance["runtime_tree_sha256"],
        "candidate_runtime_tree_sha256": candidate.provenance["runtime_tree_sha256"],
        "action_active": action_changed,
        "score_active": score_changed,
        "first_divergence": divergence,
        "replay_sha256": replay_digests,
        "control_own": control_own,
        "candidate_own": candidate_own,
        "control_rival": control_rival,
        "candidate_rival": candidate_rival,
        "own_delta": own_delta,
        "rival_delta": rival_delta,
        "margin_delta": margin_delta,
        "control_outcome": control_outcome,
        "candidate_outcome": candidate_outcome,
        "outcome_delta": _outcome_value(candidate_outcome) - _outcome_value(control_outcome),
        "lost_win": control_outcome == "W" and candidate_outcome != "W",
        "new_loss": control_outcome != "L" and candidate_outcome == "L",
    }
