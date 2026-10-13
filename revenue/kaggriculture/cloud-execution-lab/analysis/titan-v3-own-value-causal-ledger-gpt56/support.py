# SPDX-License-Identifier: Apache-2.0
"""Synthetic exact-ledger fixtures shared by focused contracts."""
from __future__ import annotations

from copy import deepcopy
import causal_ledger as ledger

def hx(ch: str) -> str:
    return ch * 64


PANEL_PROVENANCE = {
    "engine_sha256": hx("a"),
    "loader_sha256": hx("b"),
    "evaluator_sha256": hx("c"),
    "control_runtime_tree_sha256": hx("d"),
    "control_entry_sha256": hx("e"),
    "candidate_runtime_tree_sha256": hx("f"),
    "candidate_entry_sha256": hx("0"),
    "opponent_tree_sha256": {
        "arlene": hx("1"),
        "v1": hx("2"),
    },
}


def arm_provenance(arm: str, opponent: str) -> dict[str, str]:
    return {
        "engine_sha256": PANEL_PROVENANCE["engine_sha256"],
        "loader_sha256": PANEL_PROVENANCE["loader_sha256"],
        "evaluator_sha256": PANEL_PROVENANCE["evaluator_sha256"],
        "runtime_tree_sha256": PANEL_PROVENANCE[f"{arm}_runtime_tree_sha256"],
        "entry_sha256": PANEL_PROVENANCE[f"{arm}_entry_sha256"],
        "opponent_tree_sha256": PANEL_PROVENANCE["opponent_tree_sha256"][opponent],
    }


def oriented_scores(seat: int, own: int, rival: int) -> list[int]:
    return [own, rival] if seat == 0 else [rival, own]


def make_game(
    *,
    opponent: str,
    seed: int,
    seat: int,
    arm: str,
    own: int,
    rival: int,
    action_changed: bool,
    realized: bool = True,
    rival_changed: bool = False,
    preworld_changed: bool = False,
    prefix_drift: bool = False,
) -> dict:
    identity = {
        "opponent": opponent,
        "seed": seed,
        "candidate_seat": seat,
        "arm": arm,
    }
    tested_control = {"farmer": ["PASS"], "hands": [], "market": []}
    tested_candidate = {
        "farmer": ["PASS"],
        "hands": [],
        "market": [["SELL", "MILK", 1]],
    }
    rival_control = {"farmer": ["PASS"], "hands": [], "market": []}
    rival_candidate = (
        {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WOOL", 1]]}
        if rival_changed
        else deepcopy(rival_control)
    )
    tested = tested_control
    rival_action = rival_control
    if arm == "candidate" and action_changed:
        tested = tested_candidate
    if arm == "candidate":
        rival_action = rival_candidate

    root = {"step": 0, "engine": "state", "rng": 7}
    if arm == "candidate" and preworld_changed:
        root = {"step": 0, "engine": "state", "rng": 8}
    observations = [
        {"seat": 0, "public": "root"},
        {"seat": 1, "public": "root"},
    ]
    actions = [tested, rival_action] if seat == 0 else [rival_action, tested]
    branch = "common"
    if arm == "candidate" and action_changed and realized:
        branch = "candidate-effect"
    first_post = {"step": 1, "branch": branch, "rng": 7}
    if arm == "candidate" and prefix_drift:
        first_post = {"step": 1, "branch": "hidden-prefix-drift", "rng": 7}

    scores = oriented_scores(seat, own, rival)
    terminal = {
        "step": 2,
        "branch": branch,
        "money": scores,
        "rng": 7,
    }
    second_actions = [deepcopy(tested_control), deepcopy(rival_control)]
    steps = [
        {
            "step": 0,
            "preworld": root,
            "observations": observations,
            "actions": actions,
            "postworld": first_post,
            "bank": [0, 0],
        },
        {
            "step": 1,
            "preworld": deepcopy(first_post),
            "observations": [
                {"seat": 0, "public": branch},
                {"seat": 1, "public": branch},
            ],
            "actions": second_actions,
            "postworld": terminal,
            "bank": scores,
        },
    ]
    return {
        "schema": ledger.GAME_SCHEMA,
        "complete": True,
        "identity": identity,
        "provenance": arm_provenance(arm, opponent),
        "steps": steps,
        "terminal_bank": deepcopy(scores),
        "scores": deepcopy(scores),
    }


def make_cell(
    opponent: str,
    seed: int,
    seat: int,
    *,
    control_own: int = 100,
    control_rival: int = 90,
    own_delta: int = 10,
    rival_delta: int = -2,
    action_changed: bool = True,
    realized: bool = True,
    replays: bool = True,
) -> dict:
    control = make_game(
        opponent=opponent,
        seed=seed,
        seat=seat,
        arm="control",
        own=control_own,
        rival=control_rival,
        action_changed=False,
    )
    candidate = make_game(
        opponent=opponent,
        seed=seed,
        seat=seat,
        arm="candidate",
        own=control_own + own_delta,
        rival=control_rival + rival_delta,
        action_changed=action_changed,
        realized=realized,
    )
    return {
        "opponent": opponent,
        "seed": seed,
        "candidate_seat": seat,
        "control": {
            "primary": control,
            "replay": deepcopy(control) if replays else None,
        },
        "candidate": {
            "primary": candidate,
            "replay": deepcopy(candidate) if replays else None,
        },
    }


def make_panel(
    *,
    opponents: list[str] | None = None,
    seeds: list[int] | None = None,
    action_changed: bool = True,
    own_delta: int = 10,
    rival_delta: int = -2,
    replays: bool = True,
    gate: dict | None = None,
) -> dict:
    opponents = opponents or ["arlene"]
    seeds = seeds or list(range(8))
    seats = [0, 1]
    label = "fresh-own-value-successor-bank"
    cells = [
        make_cell(
            opponent,
            seed,
            seat,
            own_delta=own_delta,
            rival_delta=rival_delta,
            action_changed=action_changed,
            replays=replays,
        )
        for opponent in opponents
        for seed in seeds
        for seat in seats
    ]
    provenance = deepcopy(PANEL_PROVENANCE)
    provenance["opponent_tree_sha256"] = {
        name: PANEL_PROVENANCE["opponent_tree_sha256"][name]
        for name in opponents
    }
    return {
        "schema": ledger.SCHEMA,
        "experiment": {
            "id": "titan-v3-own-value-causal-successor",
            "hypothesis_sha256": hx("3"),
            "seed_bank_label": label,
            "seed_bank_sha256": ledger.seed_bank_sha256(
                label=label,
                opponents=opponents,
                seeds=seeds,
                candidate_seats=seats,
            ),
            "git_head": "4" * 40,
            "parent_head": "5" * 40,
            "run_id": 123456,
            "run_attempt": 1,
        },
        "expected_action_steps": 2,
        "opponents": opponents,
        "seeds": seeds,
        "candidate_seats": seats,
        "provenance": provenance,
        "gate": gate or {
            "min_seed_own_mean": 0,
            "min_seed_margin_mean": 0,
            "max_seed_own_positive_tail_p": 0.05,
            "max_seed_margin_positive_tail_p": 0.05,
        },
        "cells": cells,
    }
