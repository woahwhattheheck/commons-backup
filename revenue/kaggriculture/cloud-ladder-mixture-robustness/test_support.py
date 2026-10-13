from __future__ import annotations

import copy
import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import mixture_gate as gate

H64 = "a" * 64
H64B = "b" * 64
H64C = "c" * 64
H64D = "d" * 64
H64E = "e" * 64
H64F = "f" * 64
H40 = "1" * 40
H40B = "2" * 40


def build_document(
    effects: dict[str, list[tuple[int | str, int | str]]],
    *,
    counts: dict[str, int] | None = None,
    bounds: dict[str, tuple[str, str]] | None = None,
    radius: str = "1/5",
    minimum_seed_clusters: int = 5,
    own_floor: int | str = 0,
    margin_floor: int | str = 0,
    family_seat_own_floor: int | str = 0,
    family_seat_margin_floor: int | str = 0,
    strict: bool = True,
    require_uniform: bool = True,
    require_leave_one_family_out: bool = True,
) -> dict:
    """Build cells from per-family [(own_delta, rival_delta), ...] seed rows."""

    families = sorted(effects)
    counts = counts or {name: 1 for name in families}
    bounds = bounds or {name: ("0", "1") for name in families}
    cells = []
    for family in families:
        for seed_index, (own_delta, rival_delta) in enumerate(effects[family], start=1):
            for seat in (0, 1):
                incumbent_own = 1000 + seed_index
                incumbent_rival = 100
                candidate_own = incumbent_own + int(own_delta)
                candidate_rival = incumbent_rival + int(rival_delta)
                changed = candidate_own != incumbent_own or candidate_rival != incumbent_rival
                cells.append(
                    {
                        "status": "complete",
                        "opponent_family": family,
                        "seed": f"{family}-{seed_index}",
                        "candidate_seat": seat,
                        "incumbent_steps": 719,
                        "candidate_steps": 719,
                        "incumbent_own": incumbent_own,
                        "incumbent_rival": incumbent_rival,
                        "candidate_own": candidate_own,
                        "candidate_rival": candidate_rival,
                        "action_changed": changed,
                        "trace_changed": changed,
                    }
                )
    return {
        "schema": gate.SCHEMA,
        "release_pair": {
            "incumbent_id": "titan-v1",
            "candidate_id": "titan-v3-candidate",
            "incumbent_archive_sha256": H64,
            "candidate_archive_sha256": H64B,
            "incumbent_source_commit": H40,
            "candidate_source_commit": H40B,
        },
        "panel": {
            "panel_receipt_sha256": H64C,
            "engine_sha256": H64D,
            "evaluator_sha256": H64E,
            "loader_sha256": H64F,
            "causality_status": "CAUSAL_PASS",
            "causality_receipt_sha256": "0" * 64,
            "expected_seats": [0, 1],
            "cells": cells,
        },
        "calibration": {
            "registry_receipt_sha256": "3" * 64,
            "families": [
                {
                    "opponent_family": name,
                    "status": "CALIBRATION_PASS",
                    "receipt_sha256": (str(index + 4) * 64)[:64],
                }
                for index, name in enumerate(families)
            ],
        },
        "mixture": {
            "snapshot_id": "hosted-snapshot-test",
            "snapshot_sha256": "9" * 64,
            "total_variation_radius": radius,
            "families": [
                {
                    "opponent_family": name,
                    "hosted_count": counts[name],
                    "min_weight": bounds[name][0],
                    "max_weight": bounds[name][1],
                }
                for name in families
            ],
        },
        "gate": {
            "minimum_seed_clusters": minimum_seed_clusters,
            "minimum_seed_own_delta": own_floor,
            "minimum_seed_margin_delta": margin_floor,
            "minimum_family_seat_own_delta": family_seat_own_floor,
            "minimum_family_seat_margin_delta": family_seat_margin_floor,
            "require_strict_worst_case": strict,
            "require_uniform_family_reference": require_uniform,
            "require_leave_one_family_out": require_leave_one_family_out,
        },
    }


def quantity_fraction(result: dict, *path: str):
    value = result
    for key in path:
        value = value[key]
    return gate.Fraction(value["fraction"])
