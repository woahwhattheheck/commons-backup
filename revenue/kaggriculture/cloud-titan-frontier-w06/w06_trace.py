"""Interpreter transition capture, loss-onset analysis, and action interventions."""
from __future__ import annotations

import copy
import math
from typing import Any, Iterable

from w06_common import canonical, plain

LOSS_THRESHOLDS = (0.10, 0.25, 0.50, 0.75, 1.00)


def money(observation: dict[str, Any], player: int) -> float | None:
    try:
        value = float(observation["farms"][player]["money"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _clock(observation: dict[str, Any]) -> dict[str, int | None]:
    def integer(key: str) -> int | None:
        value = observation.get(key)
        return int(value) if isinstance(value, (int, float)) and math.isfinite(value) else None
    return {"step": integer("step"), "day": integer("day"), "hour": integer("hour")}


def _action_summary(action: dict[str, Any]) -> dict[str, Any]:
    market = action.get("market") if isinstance(action, dict) else None
    hands = action.get("hands") if isinstance(action, dict) else None
    farmer = action.get("farmer") if isinstance(action, dict) else None
    market = market if isinstance(market, list) else []
    hands = hands if isinstance(hands, list) else []
    operations: dict[str, int] = {}
    for order in market:
        name = order[0] if isinstance(order, list) and order else "MALFORMED"
        operations[str(name)] = operations.get(str(name), 0) + 1
    return {"farmer": farmer, "hands": hands, "market": market, "market_operations": operations}


def _pass_units(action: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(action)
    hands = result.get("hands") if isinstance(result.get("hands"), list) else []
    result["farmer"] = ["PASS"]
    result["hands"] = [["PASS"] for _ in hands]
    return result


def apply_intervention(action: dict[str, Any], intervention: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(action)
    mode = intervention["mode"]
    if mode == "market_pass":
        result["market"] = []
    elif mode == "units_pass":
        result = _pass_units(result)
    elif mode == "full_pass":
        result = _pass_units(result)
        result["market"] = []
    elif mode == "drop_market_order":
        orders = result.get("market")
        index = intervention.get("order_index")
        if not isinstance(orders, list) or not isinstance(index, int) or not (0 <= index < len(orders)):
            raise ValueError("drop_market_order needs an in-range order_index")
        del orders[index]
    else:
        raise ValueError(f"unknown intervention mode: {mode}")
    return result


class InterpreterTrace:
    def __init__(self, candidate_seat: int, intervention: dict[str, Any] | None = None):
        self.candidate_seat = candidate_seat
        self.intervention = intervention
        self.transitions: list[dict[str, Any]] = []
        self.applied = False

    def wrap(self, original):
        def traced(state, env):
            invocation = len(self.transitions)
            game_step = invocation - 1
            before = [plain(item.observation) for item in state]
            original_actions = [plain(item.action) for item in state]
            applied_actions = copy.deepcopy(original_actions)
            intervention_record = None
            if self.intervention is not None and not self.applied and game_step == self.intervention["game_step"]:
                candidate_action = original_actions[self.candidate_seat]
                changed = apply_intervention(candidate_action, self.intervention)
                state[self.candidate_seat].action = changed
                applied_actions[self.candidate_seat] = plain(changed)
                self.applied = True
                intervention_record = {
                    "spec": plain(self.intervention),
                    "original_action": candidate_action,
                    "applied_action": plain(changed),
                }
            result = original(state, env)
            after = [plain(item.observation) for item in state]
            self.transitions.append({
                "invocation": invocation,
                "game_step": game_step if game_step >= 0 else None,
                "before": before,
                "original_actions": original_actions,
                "applied_actions": applied_actions,
                "intervention": intervention_record,
                "after": after,
                "status": [item.status for item in state],
                "reward": [item.reward for item in state],
                "done": bool(getattr(env, "done", False)),
            })
            return result
        return traced


def transition_rows(transitions: Iterable[dict[str, Any]], candidate_seat: int) -> list[dict[str, Any]]:
    rival = 1 - candidate_seat
    rows: list[dict[str, Any]] = []
    previous_margin = previous_candidate_money = previous_rival_money = None
    for transition in transitions:
        step = transition["game_step"]
        if step is None:
            continue
        observation = transition["after"][candidate_seat]
        candidate_money = money(observation, candidate_seat)
        rival_money = money(observation, rival)
        margin = None if candidate_money is None or rival_money is None else candidate_money - rival_money
        row = {
            "game_step": step,
            "clock": _clock(observation),
            "candidate_money": candidate_money,
            "rival_money": rival_money,
            "money_margin": margin,
            "money_margin_delta": None if margin is None or previous_margin is None else margin - previous_margin,
            "candidate_money_delta": None if candidate_money is None or previous_candidate_money is None else candidate_money - previous_candidate_money,
            "rival_money_delta": None if rival_money is None or previous_rival_money is None else rival_money - previous_rival_money,
            "candidate_action": _action_summary(transition["applied_actions"][candidate_seat]),
            "rival_action": _action_summary(transition["applied_actions"][rival]),
        }
        rows.append(row)
        previous_margin, previous_candidate_money, previous_rival_money = margin, candidate_money, rival_money
    return rows


def _event(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "game_step", "clock", "candidate_money", "rival_money", "money_margin",
        "money_margin_delta", "candidate_money_delta", "rival_money_delta",
        "candidate_action", "rival_action",
    )
    return {key: row[key] for key in keys}


def analyze_transitions(transitions: Iterable[dict[str, Any]], candidate_seat: int) -> dict[str, Any]:
    rows = transition_rows(transitions, candidate_seat)
    finite = [row for row in rows if row["money_margin"] is not None]
    terminal_margin = finite[-1]["money_margin"] if finite else None
    permanent_deficit = None
    for index, row in enumerate(finite):
        if row["money_margin"] < 0 and all(later["money_margin"] < 0 for later in finite[index:]):
            permanent_deficit = _event(row)
            break
    threshold_crossings = []
    if terminal_margin is not None and terminal_margin < 0:
        loss = -terminal_margin
        for fraction in LOSS_THRESHOLDS:
            target = -loss * fraction
            row = next((item for item in finite if item["money_margin"] <= target), None)
            threshold_crossings.append({
                "fraction_of_terminal_money_deficit": fraction,
                "target_margin": target,
                "event": _event(row) if row else None,
            })
    negative_widening = sorted(
        (row for row in finite if row["money_margin_delta"] is not None and row["money_margin_delta"] < 0),
        key=lambda row: (row["money_margin_delta"], row["game_step"]),
    )
    cash_outflows = sorted(
        (row for row in finite if row["candidate_money_delta"] is not None and row["candidate_money_delta"] < 0),
        key=lambda row: (row["candidate_money_delta"], row["game_step"]),
    )
    return {
        "candidate_seat": candidate_seat,
        "recorded_steps": len(rows),
        "terminal_money_margin": terminal_margin,
        "permanent_deficit_onset": permanent_deficit,
        "threshold_crossings": threshold_crossings,
        "largest_one_step_deficit_expansions": [_event(row) for row in negative_widening[:12]],
        "largest_candidate_cash_outflows": [_event(row) for row in cash_outflows[:12]],
    }


def _action_identity(action: dict[str, Any]) -> bytes:
    """Canonical bytes for the exact action sent to the engine."""
    return canonical({
        "farmer": action.get("farmer"),
        "hands": action.get("hands"),
        "market": action.get("market"),
    })


def intervention_candidates(analysis: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    candidates: list[dict[str, Any]] = []
    seen_specs: set[tuple[Any, ...]] = set()
    seen_actions: set[tuple[int, bytes]] = set()
    events = analysis["largest_candidate_cash_outflows"] + analysis["largest_one_step_deficit_expansions"]
    for event in events:
        step = event["game_step"]
        action = event["candidate_action"]
        market = action["market"]
        for index, order in enumerate(market):
            spec = {"mode": "drop_market_order", "order_index": index}
            action_key = (step, _action_identity(apply_intervention(action, spec)))
            if action_key in seen_actions:
                continue
            candidates.append({
                "game_step": step,
                **spec,
                "target_order": order,
                "selection_basis": {
                    "candidate_money_delta": event["candidate_money_delta"],
                    "money_margin_delta": event["money_margin_delta"],
                },
            })
            seen_actions.add(action_key)
            if len(candidates) >= limit:
                return candidates
        if market:
            key = (step, "market_pass", None)
            action_key = (step, _action_identity(apply_intervention(action, {"mode": "market_pass"})))
            if key not in seen_specs and action_key not in seen_actions:
                candidates.append({
                    "game_step": step,
                    "mode": "market_pass",
                    "selection_basis": {
                        "candidate_money_delta": event["candidate_money_delta"],
                        "money_margin_delta": event["money_margin_delta"],
                    },
                })
                seen_specs.add(key)
                seen_actions.add(action_key)
                if len(candidates) >= limit:
                    return candidates
        farmer, hands = action["farmer"], action["hands"]
        unit_nonpass = (
            isinstance(farmer, list) and farmer and farmer[0] != "PASS"
        ) or any(isinstance(item, list) and item and item[0] != "PASS" for item in hands)
        if unit_nonpass:
            key = (step, "units_pass", None)
            action_key = (step, _action_identity(apply_intervention(action, {"mode": "units_pass"})))
            if key not in seen_specs and action_key not in seen_actions:
                candidates.append({
                    "game_step": step,
                    "mode": "units_pass",
                    "selection_basis": {
                        "candidate_money_delta": event["candidate_money_delta"],
                        "money_margin_delta": event["money_margin_delta"],
                    },
                })
                seen_specs.add(key)
                seen_actions.add(action_key)
                if len(candidates) >= limit:
                    return candidates
    return candidates
