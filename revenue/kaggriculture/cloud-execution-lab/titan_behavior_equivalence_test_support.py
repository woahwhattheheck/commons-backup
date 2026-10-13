# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

import titan_behavior_equivalence_gate as gate

def digest(character: str) -> str:
    return character * 64


ENGINE = digest("1")
EVALUATOR = digest("2")
OPPONENT_A = digest("3")
OPPONENT_B = digest("4")
ACTION_CHARS = "5678"
WORLD_CHARS = "9abc"
TERMINAL_CHARS = "def0"


def common_keys() -> list[gate.CellKey]:
    return [
        gate.CellKey(101, OPPONENT_A, 0),
        gate.CellKey(101, OPPONENT_A, 1),
        gate.CellKey(202, OPPONENT_B, 0),
        gate.CellKey(202, OPPONENT_B, 1),
    ]


def closure_record(member_sha256: str) -> dict:
    return {
        "schema": gate.CLOSURE_SCHEMA,
        "complete": True,
        "members": [
            {"path": "main.py", "sha256": member_sha256, "bytes": 1234},
        ],
    }


def candidate_record(candidate_id: str, archive: str, closure_member_sha: str) -> dict:
    closure = closure_record(closure_member_sha)
    return {
        "candidate_id": candidate_id,
        "archive_sha256": archive,
        "executable_closure_sha256": gate.sha256_json(closure),
        "invocation_sha256": digest("8"),
        "entrypoint": "main.py::agent",
        "executable_closure": closure,
    }


def family_raw(
    *,
    closures: tuple[str, str] = (digest("a"), digest("b")),
    archives: tuple[str, str] = (digest("c"), digest("d")),
) -> dict:
    return {
        "schema": gate.FAMILY_SCHEMA,
        "family_id": "screen-20260910",
        "declared_before_results": True,
        "engine_sha256": ENGINE,
        "evaluator_sha256": EVALUATOR,
        "schedule_sha256": gate.schedule_sha256(common_keys()),
        "candidates": [
            candidate_record("alpha", archives[0], closures[0]),
            candidate_record("beta", archives[1], closures[1]),
        ],
    }


def cell_row(spec: gate.CandidateSpec, key: gate.CellKey, ordinal: int) -> dict:
    own = 1000.0 + ordinal
    rival = 900.0
    return {
        "status": "COMPLETE",
        "candidate_archive_sha256": spec.archive_sha256,
        "candidate_executable_closure_sha256": spec.executable_closure_sha256,
        "candidate_invocation_sha256": spec.invocation_sha256,
        "engine_sha256": ENGINE,
        "evaluator_sha256": EVALUATOR,
        "environment_seed": key.environment_seed,
        "opponent_sha256": key.opponent_sha256,
        "seat": key.seat,
        "action_tape_sha256": digest(ACTION_CHARS[ordinal]),
        "world_tape_sha256": digest(WORLD_CHARS[ordinal]),
        "terminal_state_sha256": digest(TERMINAL_CHARS[ordinal]),
        "own_cash": own,
        "rival_cash": rival,
        "margin": own - rival,
        "outcome": "WIN",
    }


def observations_raw(family: dict) -> dict:
    parsed = gate.validate_family(family)
    candidates = []
    for spec in parsed.candidates:
        cells = [cell_row(spec, key, index) for index, key in enumerate(common_keys())]
        candidates.append(
            {
                **spec.as_dict(),
                "games": len(cells),
                "cells": cells,
            }
        )
    return {
        "schema": gate.OBSERVATIONS_SCHEMA,
        "family_sha256": parsed.family_sha256,
        "engine_sha256": parsed.engine_sha256,
        "evaluator_sha256": parsed.evaluator_sha256,
        "schedule_sha256": parsed.schedule_sha256,
        "candidates": candidates,
    }

