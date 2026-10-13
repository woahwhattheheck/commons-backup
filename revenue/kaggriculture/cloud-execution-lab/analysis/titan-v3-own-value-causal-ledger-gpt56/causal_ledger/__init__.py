# SPDX-License-Identifier: Apache-2.0
"""Fail-closed causal evidence for paired TITAN policy panels."""
from .strict import (
    VERSION, SCHEMA, REPORT_SCHEMA, GAME_SCHEMA, EvidenceError,
    canonical_bytes, digest, load_json_strict,
)
from .game import GameRecorder, GameView, validate_game
from .panel import analyze_cell, analyze_panel, seed_bank_sha256
from .cli import main

__all__ = [
    "VERSION", "SCHEMA", "REPORT_SCHEMA", "GAME_SCHEMA", "EvidenceError",
    "canonical_bytes", "digest", "load_json_strict", "GameRecorder",
    "GameView", "validate_game", "analyze_cell", "analyze_panel",
    "seed_bank_sha256", "main",
]
