# SPDX-License-Identifier: Apache-2.0
"""Narrow development counterfactual over exact PR9997 integrated_main.

The retained Apex 9921001 trace isolates the first *realized* production split:
the integrated parent buys geese at steps 226 and 241 while Apex buys sheep.
This overlay preserves the entire parent action and changes only positive
``BUY_ANIMAL GOOSE n`` orders to ``BUY_ANIMAL SHEEP n``.  Every trigger uses an
action the parent authored from the real observation; no rival-private state,
seed, score, or future event is consulted.

This is an experiment in cloud-widefield-lab, not an integration change.  It is
loaded from beside the sibling cloud-execution-lab source so that the dependency
is the landed PR9997 implementation rather than a private reconstruction.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys

_BASE = None


def _base():
    global _BASE
    if _BASE is None:
        path = Path(__file__).resolve().parent.parent / "cloud-execution-lab" / "integrated_main.py"
        spec = importlib.util.spec_from_file_location("widefield_pr9997_integrated_main", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"exact PR9997 integrated_main not found: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _BASE = module.agent
    return _BASE


def _transform(obs, cfg, mode):
    action = copy.deepcopy(_base()(obs, cfg))
    market = []
    for order in action.get("market", []):
        if (isinstance(order, list) and len(order) >= 3 and
                order[0] == "BUY_ANIMAL" and order[1] == "GOOSE" and
                isinstance(order[2], (int, float)) and order[2] > 0):
            if mode == "no_goose":
                continue
            if mode == "all":
                order[1] = "SHEEP"
            elif mode == "single_upgrade" and order[2] == 1:
                order[1] = "SHEEP"
            elif mode == "budget_neutral" and order[2] >= 2:
                # Two geese cost 600; one sheep costs 500.  Keep the animal
                # purchase within the budget the parent already committed.
                order[1], order[2] = "SHEEP", 1
            elif mode == "two_sheep_budget":
                # Across the reached 1-goose and 2-goose lots this spends 1000,
                # only 100 above the parent's 900, for two sheep total.
                order[1], order[2] = "SHEEP", 1
            elif mode == "late_upgrade" and order[2] >= 2:
                order[1] = "SHEEP"
        market.append(order)
    action["market"] = market
    return action


def agent(obs, cfg=None):
    """Unbounded substitution, retained as the falsified first experiment."""
    return _transform(obs, cfg, "all")


def agent_single_upgrade(obs, cfg=None):
    """Upgrade only one-goose orders; do not expand multi-order spend."""
    return _transform(obs, cfg, "single_upgrade")


def agent_budget_neutral(obs, cfg=None):
    """Replace a >=2-goose lot with one sheep inside its authored budget."""
    return _transform(obs, cfg, "budget_neutral")


def agent_no_goose(obs, cfg=None):
    """Suppress goose capital spend while preserving every other parent order."""
    return _transform(obs, cfg, "no_goose")


def agent_two_sheep_budget(obs, cfg=None):
    """One sheep per authored goose-buy turn, limiting the total capital delta."""
    return _transform(obs, cfg, "two_sheep_budget")


def agent_late_upgrade(obs, cfg=None):
    """Keep the first goose; upgrade only later multi-goose capital lots."""
    return _transform(obs, cfg, "late_upgrade")


def agent_consistent_deposit(obs, cfg=None):
    """Repair the reached goose-route product mismatch using own inventory only."""
    action = copy.deepcopy(_base()(obs, cfg))
    inventories = obs.get("private", {}).get("inventories", [])
    unit_actions = [action.get("farmer", ["PASS"]), *action.get("hands", [])]
    for index, unit_action in enumerate(unit_actions):
        if (not isinstance(unit_action, list) or len(unit_action) < 2 or
                unit_action[0] != "PLACE" or unit_action[1] != "WOOL" or
                index >= len(inventories)):
            continue
        inv = inventories[index]
        wool, eggs = int(inv.get("WOOL", 0)), int(inv.get("EGG", 0))
        if wool == 0 and eggs > 0:
            unit_action[1] = "EGG"
            if len(unit_action) >= 3:
                unit_action[2] = min(int(unit_action[2]), eggs)
    return action
