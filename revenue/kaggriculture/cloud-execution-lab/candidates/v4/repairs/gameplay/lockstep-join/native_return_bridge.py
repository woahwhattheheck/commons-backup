"""Two-phase current-native lockstep join bridge for TITAN V4.

This module does not infer opponent intent or authorize promotion.  It consumes
only the separately landed effective-flow and raw-slot certificates.  Proposal
is side-effect free.  Commit binds the exact candidate action to the native
FrozenSelected planned/pending debt only while the canonical outer entrypoint
timer is still active; if the timer cancels afterward, main.py discards the
entire agent instance.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Callable

EFFECTIVE_FLOW_BLOB = "e24dd03a88a71ba4cf6f8d5da1082b89490b5a94"
JOIN_QUEUE_BLOB = "ac91d3c65deeabadaa60ee83c4a7a84286849150"
SUPPORTED_PRODUCTS = ("CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL")


def git_blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _load_exact(name: str, path: Path, expected_blob: str):
    data = path.read_bytes()
    actual = git_blob_id(data)
    if actual != expected_blob:
        raise ValueError(f"{path.name} blob drift: {actual} != {expected_blob}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    missing = object()
    previous = sys.modules.get(name, missing)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if sys.modules.get(name) is module:
            if previous is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        raise
    return module


def load_authorities(root: str | Path):
    """Load only exact landed ESTUARY/CROSSCURRENT authority bytes.

    A composed standalone package may place the exact dependency bytes beside
    this module.  Source-tree execution instead reads their canonical V4 paths.
    """
    root = Path(root).resolve()
    flow = root / "lockstep_effective_flow_bounds.py"
    queue = root / "lockstep_join_queue_contract.py"
    if not flow.is_file():
        flow = root / "candidates/v4/research/lockstep-scale/effective_flow_bounds.py"
    if not queue.is_file():
        queue = root / "candidates/v4/research/lockstep-scale/join_queue_contract.py"
    flow_mod = _load_exact("_titan_lockstep_effective_flow", flow, EFFECTIVE_FLOW_BLOB)
    queue_mod = _load_exact("_titan_lockstep_queue_contract", queue, JOIN_QUEUE_BLOB)
    return flow_mod.effective_flow_bounds, flow_mod.confirmed_net_sells, queue_mod.certify_join_queue


def _action_digest(action: Any) -> str | None:
    try:
        raw = json.dumps(action, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, OverflowError, RecursionError):
        return None
    return hashlib.sha256(raw).hexdigest()


def _public_flow_observation(obs: Any) -> dict | None:
    try:
        if type(obs) is not dict:
            return None
        step, player = obs["step"], obs["player"]
        if type(step) is not int or type(player) is not int or player not in (0, 1):
            return None
        inventory = obs["market"]["inventory"]
        shops = obs["town"]["unlocked_shops"]
        if type(inventory) is not dict or type(shops) is not list:
            return None
        clean_inventory = {}
        for key, value in inventory.items():
            if type(key) is not str or type(value) is not int:
                return None
            clean_inventory[key] = value
        if any(type(shop) is not str for shop in shops):
            return None
        return {"step": step, "player": player,
                "market": {"inventory": clean_inventory},
                "town": {"unlocked_shops": list(shops)}}
    except (KeyError, TypeError, AttributeError):
        return None


def _plan_snapshot(rows: Any) -> tuple[tuple[int, int], ...] | None:
    if type(rows) is not list:
        return None
    result = []
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            return None
        step, quantity = row
        if type(step) is not int or type(quantity) is not int:
            return None
        result.append((step, quantity))
    return tuple(result)


@dataclass(frozen=True)
class Proposal:
    step: int
    player: int
    item: str
    quantity: int
    due_step: int
    plan_index: int
    planned_before: tuple[tuple[int, int], ...]
    pending_before: int
    baseline_sha256: str
    candidate_sha256: str
    signal_lower_bound: int


class ReturnBridge:
    """Stateful per-agent bridge; no state is shared across evaluator loads."""
    def __init__(self, flow_bounds: Callable, confirmed_net_sells: Callable,
                 certify_join_queue: Callable, *, threshold: int = 150,
                 max_pull: int = 1000):
        if type(threshold) is not int or threshold <= 0:
            raise ValueError("threshold must be a positive int")
        if type(max_pull) is not int or not 1 <= max_pull <= 1000:
            raise ValueError("max_pull must be 1..1000")
        self.flow_bounds = flow_bounds
        self.confirmed_net_sells = confirmed_net_sells
        self.certify_join_queue = certify_join_queue
        self.threshold = threshold
        self.max_pull = max_pull
        self.previous_observation = None
        self.previous_action = None
        self.previous_config = None
        self.signal_step = None
        self.confirmed = {}
        self.last_report = {"enabled": True, "changed": False, "reason": "cold_start"}

    def _clear_signal(self, reason: str):
        self.signal_step = None
        self.confirmed = {}
        self.last_report = {"enabled": True, "changed": False, "reason": reason}

    def observe(self, observation: Any, configuration: Any = None) -> dict:
        """Convert the last successfully returned action + current obs into bounds."""
        current = _public_flow_observation(observation)
        if current is None:
            self._clear_signal("invalid_current_observation")
            return {}
        if current["step"] == 0:
            self.previous_observation = None
            self.previous_action = None
            self.previous_config = None
            self._clear_signal("episode_reset")
            return {}
        if self.previous_observation is None or self.previous_action is None:
            self._clear_signal("no_completed_previous_transition")
            return {}
        bounds = self.flow_bounds(self.previous_observation, self.previous_action,
                                  current, self.previous_config or {})
        confirmed = self.confirmed_net_sells(bounds, self.threshold)
        if type(confirmed) is not dict:
            confirmed = {}
        self.signal_step = current["step"] if confirmed else None
        self.confirmed = {k: v for k, v in confirmed.items()
                          if k in SUPPORTED_PRODUCTS and type(v) is int and v >= self.threshold}
        if not self.confirmed:
            self._clear_signal("no_certified_supported_flow")
            return {}
        self.last_report = {"enabled": True, "changed": False, "reason": "flow_certified",
                            "step": current["step"], "confirmed": dict(self.confirmed)}
        return dict(self.confirmed)

    @staticmethod
    def _post_unit_shed(instance: Any, obs: dict, action: dict) -> dict | None:
        consumer = getattr(instance, "consumer", None)
        pair = getattr(consumer, "selected_post_units", None)
        binding = getattr(consumer, "selected_post_units_binding", None)
        if pair is not None and binding is not None:
            try:
                if (binding[:2] == (int(obs["step"]), int(obs["player"]))
                        and binding[2:] == (action["farmer"], action.get("hands", []))):
                    private = pair[1]
                    shed = private["shed"]
                    return shed if type(shed) is dict else None
            except (KeyError, TypeError, ValueError):
                return None
        try:
            if action["farmer"] == ["PASS"] and all(a == ["PASS"] for a in action.get("hands", [])):
                shed = obs["private"]["shed"]
                return shed if type(shed) is dict else None
        except (KeyError, TypeError):
            return None
        return None

    def propose(self, instance: Any, observation: Any, configuration: Any,
                baseline: Any) -> tuple[Any, Proposal | None]:
        """Prepare one row-0 pull with zero native-state mutation."""
        if type(observation) is not dict or type(baseline) is not dict:
            self._clear_signal("invalid_proposal_input")
            return baseline, None
        now, player = observation.get("step"), observation.get("player")
        if type(now) is not int or type(player) is not int or self.signal_step != now:
            self.last_report = {"enabled": True, "changed": False, "reason": "no_current_flow_signal"}
            return baseline, None
        diagnostics = getattr(instance, "diagnostics", {}) or {}
        if diagnostics.get("status") != "completed":
            self.last_report = {"enabled": True, "changed": False, "reason": "native_action_not_completed"}
            return baseline, None
        features = getattr(instance, "features", None)
        if (getattr(features, "consumer", None) != "frozen"
                or getattr(features, "terminal_route", False)):
            self.last_report = {"enabled": True, "changed": False, "reason": "unsupported_native_consumer"}
            return baseline, None
        consumer = getattr(instance, "consumer", None)
        planned = getattr(consumer, "planned", None)
        pending = getattr(consumer, "pending", None)
        if type(planned) is not dict or type(pending) is not dict:
            self.last_report = {"enabled": True, "changed": False, "reason": "missing_native_debt_ledger"}
            return baseline, None
        shed = self._post_unit_shed(instance, observation, baseline)
        if shed is None:
            self.last_report = {"enabled": True, "changed": False, "reason": "no_exact_post_unit_stock"}
            return baseline, None

        choices = []
        for item, lower in self.confirmed.items():
            rows = _plan_snapshot(planned.get(item))
            pend = pending.get(item)
            stock = shed.get(item, 0)
            if rows is None or type(pend) is not int or type(stock) is not int:
                continue
            if pend <= 0 or stock <= 0:
                continue
            future = [(index, step, quantity) for index, (step, quantity) in enumerate(rows)
                      if step > now and quantity > 0]
            if not future:
                continue
            index, due, quantity = min(future, key=lambda row: (row[1], row[0]))
            pull = min(quantity, pend, stock, self.max_pull)
            if pull > 0:
                choices.append((-lower, due, item, index, pull, rows, pend, lower))
        if not choices:
            self.last_report = {"enabled": True, "changed": False, "reason": "no_owned_future_sale_debt"}
            return baseline, None
        _neg, due, item, index, quantity, rows, pend, lower = min(choices)

        candidate = deepcopy(baseline)
        market = candidate.get("market", [])
        if type(market) is not list:
            self.last_report = {"enabled": True, "changed": False, "reason": "market_not_list"}
            return baseline, None
        if market:
            market[0] = ["SELL", item, quantity]
        else:
            candidate["market"] = [["SELL", item, quantity]]
        try:
            certificate = self.certify_join_queue(
                baseline, candidate, item=item, quantity=quantity,
                max_orders=dict(configuration or {}).get("maxMarketOrdersPerTurn", 10))
        except Exception:
            self.last_report = {"enabled": True, "changed": False, "reason": "queue_certificate_error"}
            return baseline, None
        if not getattr(certificate, "slot_safe", False):
            self.last_report = {"enabled": True, "changed": False,
                                "reason": "queue_unsafe:" + str(getattr(certificate, "reason", "unknown"))}
            return baseline, None
        if getattr(certificate, "resource_sensitive_slots", ()):
            self.last_report = {"enabled": True, "changed": False, "reason": "later_resource_order"}
            return baseline, None
        if getattr(certificate, "same_product_slots", ()):
            self.last_report = {"enabled": True, "changed": False, "reason": "later_same_product_order"}
            return baseline, None
        baseline_digest, candidate_digest = _action_digest(baseline), _action_digest(candidate)
        if baseline_digest is None or candidate_digest is None or baseline_digest == candidate_digest:
            self.last_report = {"enabled": True, "changed": False, "reason": "invalid_or_unchanged_candidate"}
            return baseline, None
        proposal = Proposal(now, player, item, quantity, due, index, rows, pend,
                            baseline_digest, candidate_digest, lower)
        self.last_report = {"enabled": True, "changed": False, "reason": "proposal_prepared",
                            "step": now, "item": item, "quantity": quantity,
                            "due_step": due, "signal_lower_bound": lower}
        return candidate, proposal

    def _record_transition(self, instance: Any, observation: Any, configuration: Any,
                           returned_action: Any) -> None:
        # Only a fully completed native action can seed the next flow inference.
        diagnostics = getattr(instance, "diagnostics", {}) or {}
        public = _public_flow_observation(observation)
        digest = _action_digest(returned_action)
        if diagnostics.get("status") != "completed" or public is None or digest is None:
            self.previous_observation = None
            self.previous_action = None
            self.previous_config = None
            return
        self.previous_observation = public
        self.previous_action = deepcopy(returned_action)
        try:
            self.previous_config = dict(configuration or {})
        except Exception:
            self.previous_observation = None
            self.previous_action = None
            self.previous_config = None

    def commit(self, instance: Any, observation: Any, configuration: Any,
               baseline: Any, candidate: Any, proposal: Proposal | None) -> Any:
        """Atomically bind debt to candidate; otherwise return exact baseline.

        This must run inside the canonical outer entrypoint timer after
        ``instance.act`` returns.  If that timer subsequently cancels, main.py's
        existing handler discards the whole instance, including this bridge and
        any committed debt.
        """
        returned = baseline
        reason = "no_proposal"
        if proposal is not None:
            consumer = getattr(instance, "consumer", None)
            planned = getattr(consumer, "planned", None)
            pending = getattr(consumer, "pending", None)
            current_rows = None if type(planned) is not dict else _plan_snapshot(planned.get(proposal.item))
            current_pending = None if type(pending) is not dict else pending.get(proposal.item)
            valid = (
                type(observation) is dict
                and observation.get("step") == proposal.step
                and observation.get("player") == proposal.player
                and _action_digest(baseline) == proposal.baseline_sha256
                and _action_digest(candidate) == proposal.candidate_sha256
                and current_rows == proposal.planned_before
                and current_pending == proposal.pending_before
                and 0 <= proposal.plan_index < len(proposal.planned_before)
                and proposal.pending_before >= proposal.quantity
            )
            if valid:
                row_step, row_quantity = proposal.planned_before[proposal.plan_index]
                valid = (row_step == proposal.due_step and row_quantity >= proposal.quantity)
            if valid:
                new_rows = list(proposal.planned_before)
                remaining = new_rows[proposal.plan_index][1] - proposal.quantity
                if remaining:
                    new_rows[proposal.plan_index] = (proposal.due_step, remaining)
                else:
                    new_rows.pop(proposal.plan_index)
                old_rows = deepcopy(planned.get(proposal.item))
                old_pending = pending.get(proposal.item)
                old_checkpoint = deepcopy(getattr(instance, "_completed_seller_state", None))
                try:
                    if new_rows:
                        planned[proposal.item] = list(new_rows)
                    else:
                        planned.pop(proposal.item, None)
                    pending[proposal.item] = proposal.pending_before - proposal.quantity
                    instance._commit_seller_state()
                except BaseException:
                    if old_rows is None:
                        planned.pop(proposal.item, None)
                    else:
                        planned[proposal.item] = old_rows
                    if old_pending is None:
                        pending.pop(proposal.item, None)
                    else:
                        pending[proposal.item] = old_pending
                    instance._completed_seller_state = old_checkpoint
                    reason = "native_debt_commit_failed"
                else:
                    returned = candidate
                    reason = "committed"
            else:
                reason = "stale_or_invalid_native_debt"
        self._record_transition(instance, observation, configuration, returned)
        report = dict(self.last_report)
        report.update(changed=returned is candidate and proposal is not None,
                      commit_reason=reason,
                      returned_sha256=_action_digest(returned))
        self.last_report = report
        try:
            diagnostics = dict(getattr(instance, "diagnostics", {}) or {})
            diagnostics["lockstep_join"] = deepcopy(report)
            instance.diagnostics = diagnostics
        except Exception:
            pass
        return returned
