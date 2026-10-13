# SPDX-License-Identifier: Apache-2.0
"""Evaluator adapter for engine-owned pre/action/post transition bytes."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .strict import (
    GAME_SCHEMA,
    EvidenceError,
    _deep_copy,
    _exact_equal,
    _integer,
    _recorder_pair,
    _require_exact,
    _sha256,
    canonical_bytes,
)
from .game_model import _REQUIRED_PROVENANCE, _validate_identity, validate_game

class GameRecorder:
    """Small evaluator adapter that records engine-owned transition bytes.

    Call ``append`` after both actions are returned and after the official
    interpreter produces ``postworld`` and ``bank``.  The recorder does not
    simulate or infer any field.
    """

    def __init__(
        self,
        identity: Mapping[str, Any],
        provenance: Mapping[str, Any],
        expected_actions: int,
    ):
        self.expected_actions = _integer(expected_actions, "expected_actions", minimum=1)
        self.identity = _validate_identity(identity, "identity")
        if set(provenance) != set(_REQUIRED_PROVENANCE):
            raise EvidenceError("recorder provenance does not match the required closure")
        self.provenance = {
            key: _sha256(provenance[key], f"provenance.{key}")
            for key in _REQUIRED_PROVENANCE
        }
        self.steps: list[dict[str, Any]] = []

    def append(
        self,
        *,
        step: int,
        preworld: Any,
        observations: Sequence[Any],
        actions: Sequence[Any],
        postworld: Any,
        bank: Sequence[Any],
    ) -> None:
        index = _integer(step, "step", minimum=0)
        if index != len(self.steps):
            raise EvidenceError(f"recorder expected step {len(self.steps)}, got {index}")
        observation_pair = _recorder_pair(observations, "observations")
        action_pair = _recorder_pair(actions, "actions")
        bank_pair = _recorder_pair(bank, "bank")
        _integer(bank_pair[0], "bank[0]")
        _integer(bank_pair[1], "bank[1]")
        if self.steps and not _exact_equal(self.steps[-1]["postworld"], preworld):
            raise EvidenceError("recorder preworld does not equal prior postworld")
        row = {
            "step": index,
            "preworld": _deep_copy(preworld),
            "observations": _deep_copy(observation_pair),
            "actions": _deep_copy(action_pair),
            "postworld": _deep_copy(postworld),
            "bank": _deep_copy(bank_pair),
        }
        canonical_bytes(row)
        self.steps.append(row)

    def finalize(self, *, scores: Sequence[Any], complete: bool = True) -> dict[str, Any]:
        if complete is not True:
            raise EvidenceError("recorder only finalizes complete games")
        if len(self.steps) != self.expected_actions:
            raise EvidenceError(
                f"recorder expected {self.expected_actions} actions, got {len(self.steps)}"
            )
        terminal_bank = self.steps[-1]["bank"]
        score_pair = _recorder_pair(scores, "scores")
        _require_exact(score_pair, terminal_bank, "recorder scores must equal terminal bank")
        game = {
            "schema": GAME_SCHEMA,
            "complete": True,
            "identity": dict(self.identity),
            "provenance": dict(self.provenance),
            "steps": _deep_copy(self.steps),
            "terminal_bank": _deep_copy(terminal_bank),
            "scores": _deep_copy(score_pair),
        }
        validate_game(
            game,
            expected_actions=self.expected_actions,
            field="recorded_game",
            expected_identity=self.identity,
            expected_provenance=self.provenance,
        )
        return game
