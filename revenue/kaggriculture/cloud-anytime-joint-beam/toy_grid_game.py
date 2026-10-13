# SPDX-License-Identifier: Apache-2.0
"""Tiny grid game: a second, non-Kaggriculture MechanicsProvider.

Pickers move on a square grid collecting apples. Picking removes the apple, so
units compete for shared stock -- the same joint-search shape as the
Kaggriculture beam problem, with none of Kaggriculture's vocabulary. This
module exists to prove the search/evaluator interface is not
Kaggriculture-shaped: the beam core runs this title through the exact same
protocol, and the contract battery in ``game_rules`` accepts it unchanged.

Rules:
- state: ``{"size": n, "units": [[x, y], ...], "apples": [[x, y], ...],
  "baskets": [int, ...]}``
- actions: ``["N"]``, ``["S"]``, ``["E"]``, ``["W"]`` move one cell;
  ``["PICK"]`` takes the apple on the unit's cell; ``["PASS"]``.
- Moving off the grid is illegal (transition returns ``None``). ``PICK`` with
  no apple on the cell is illegal. ``PASS`` always succeeds and returns a
  fresh state equal to the input.
- Candidate enumeration is canonical-only for non-PASS canonical actions
  (mirrors the safe default of the worker-phase provider); for a PASS
  canonical it offers PASS, the on-grid moves, and PICK when an apple sits on
  the cell. The family is bounded by six and deterministic.
"""
from __future__ import annotations

from typing import Hashable, Iterable

from joint_action_beam import Action, State

_MOVES = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}
_OPS = ("N", "S", "E", "W", "PICK", "PASS")
_PASS = ["PASS"]


def initial_state(
    size: int = 3,
    units: tuple[tuple[int, int], ...] = ((0, 0), (2, 2)),
    apples: tuple[tuple[int, int], ...] = ((0, 0), (2, 2)),
) -> State:
    """Build a fresh game state. Each unit starts on an apple by default."""
    return {
        "size": int(size),
        "units": [[int(x), int(y)] for x, y in units],
        "apples": [[int(x), int(y)] for x, y in apples],
        "baskets": [0 for _ in units],
    }


def _copy_state(state: State) -> State:
    return {
        "size": int(state["size"]),
        "units": [[int(v) for v in pos] for pos in state["units"]],
        "apples": [[int(v) for v in pos] for pos in state["apples"]],
        "baskets": [int(n) for n in state["baskets"]],
    }


class ToyGridRules:
    """MechanicsProvider for the tiny apple-picking grid game."""

    def legal_actions(
        self, state: State, idx: int, canonical: Action
    ) -> Iterable[Action]:
        units = state.get("units", []) if isinstance(state, dict) else []
        if not (isinstance(canonical, list) and canonical == _PASS):
            return ()
        if not isinstance(idx, int) or not 0 <= idx < len(units):
            return ()
        size = int(state["size"])
        x, y = (int(v) for v in units[idx])
        offered: list[Action] = [_PASS]
        for name in ("N", "S", "E", "W"):
            dx, dy = _MOVES[name]
            if 0 <= x + dx < size and 0 <= y + dy < size:
                offered.append([name])
        if [x, y] in state["apples"]:
            offered.append(["PICK"])
        return tuple(offered)

    def transition(
        self, state: State, idx: int, action: Action
    ) -> State | None:
        if (
            not isinstance(state, dict)
            or not isinstance(idx, int)
            or not 0 <= idx < len(state.get("units", []))
            or not isinstance(action, list)
            or len(action) != 1
            or action[0] not in _OPS
        ):
            return None
        op = action[0]
        out = _copy_state(state)
        size = int(out["size"])
        x, y = out["units"][idx]
        if op == "PASS":
            return out
        if op == "PICK":
            if [x, y] in out["apples"]:
                out["apples"].remove([x, y])
                out["baskets"][idx] += 1
                return out
            return None
        dx, dy = _MOVES[op]
        nx, ny = x + dx, y + dy
        if not (0 <= nx < size and 0 <= ny < size):
            return None
        out["units"][idx] = [nx, ny]
        return out

    def state_key(self, state: State) -> Hashable:
        return (
            "toy-grid",
            int(state["size"]),
            tuple(tuple(int(v) for v in pos) for pos in state["units"]),
            tuple(sorted(tuple(int(v) for v in pos) for pos in state["apples"])),
            tuple(int(n) for n in state["baskets"]),
        )


class ToyScorer:
    """Evaluator: each collected apple is worth 100; movement is free."""

    def __call__(self, state: State, actions: tuple[Action, ...]) -> int:
        return 100 * sum(int(n) for n in state["baskets"])
