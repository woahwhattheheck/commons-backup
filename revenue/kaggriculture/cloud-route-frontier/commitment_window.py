# SPDX-License-Identifier: Apache-2.0
"""Read complete producer programs to locate their last equal-prefix choice.

This measures scheduled-command compatibility, not physical state, profitability,
or permission. The controller's existing predicate is reported without calling
its action method, constructing a controller, or changing its current route.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence


def _integer(value: int, name: str, lower: int = 0) -> int:
    if type(value) is not int or value < lower:
        raise ValueError(f"{name} must be an integer >= {lower}")
    return value


def _encoded(program: Any) -> str:
    # Key order is preserved for a lossless source fingerprint. Comparisons below
    # deliberately use the supplied controller's dict/list equality convention.
    return json.dumps(program, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


@dataclass(frozen=True)
class ProgramBoundary:
    decision_stop: int  # exclusive: episodeSteps - 1 for the pinned engine
    first_difference: int | None
    last_equal_prefix_checkpoint: int
    first_farmer_difference: int | None
    first_hands_difference: int | None
    first_market_difference: int | None
    first_market_slot: int | None  # zero-based, only on first differing market turn
    same_object: bool
    current_sha256: str
    target_sha256: str
    current_difference_json: str | None
    target_difference_json: str | None

    def prefix_matches(self, now: int) -> bool:
        """A checkpoint is BEFORE its action, hence the first difference is inclusive."""
        _integer(now, "now")
        return (now < self.decision_stop and
                (self.first_difference is None or now <= self.first_difference))

    def can_wait_one(self, now: int) -> bool:
        """Retain structural choice after one more unchanged current-route action."""
        return not self.same_object and self.prefix_matches(now) and self.prefix_matches(now + 1)

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for side in ("current", "target"):
            text = result.pop(side + "_difference_json")
            result[side + "_at_first_difference"] = json.loads(text) if text is not None else None
        return result


def program_boundary(current: Sequence[Mapping[str, Any]],
                     target: Sequence[Mapping[str, Any]], *,
                     decision_stop: int = 719, max_steps: int = 720) -> ProgramBoundary:
    """Compare full programs from turn zero, including all ordered market commands.

    A late identical action does not erase an earlier difference. Missing tail
    elements are not synthesized as PASS. The terminal, non-executed program row
    is excluded by decision_stop. This is a source comparison, not a rollout.
    """
    _integer(decision_stop, "decision_stop", 1)
    _integer(max_steps, "max_steps", 1)
    if decision_stop > max_steps:
        raise ValueError("decision range exceeds max_steps")
    if len(current) < decision_stop or len(target) < decision_stop:
        raise ValueError("both programs must cover the complete decision range")
    same_object = current is target
    a, b = list(current[:decision_stop]), list(target[:decision_stop])
    if not all(isinstance(row, Mapping) for row in a + b):
        raise ValueError("each program row must be an action mapping")
    encoded_a, encoded_b = _encoded(a), _encoded(b)
    first = next((t for t in range(decision_stop) if a[t] != b[t]), None)
    fields = [next((t for t in range(decision_stop) if a[t].get(field) != b[t].get(field)), None)
              for field in ("farmer", "hands", "market")]
    slot = None
    if fields[2] is not None:
        left, right = a[fields[2]].get("market") or [], b[fields[2]].get("market") or []
        slot = next((i for i in range(max(len(left), len(right)))
                     if i >= len(left) or i >= len(right) or left[i] != right[i]), None)
    return ProgramBoundary(
        decision_stop, first, first if first is not None else decision_stop - 1,
        *fields, slot, same_object,
        hashlib.sha256(encoded_a.encode()).hexdigest(), hashlib.sha256(encoded_b.encode()).hexdigest(),
        _encoded(a[first]) if first is not None else None,
        _encoded(b[first]) if first is not None else None,
    )


def inspect_commitment(controller: Any, target: str, now: int, *,
                       decision_stop: int = 719, max_steps: int = 720) -> dict[str, Any]:
    """Use the supplied original controller; report its single current predicate.

    Intended consumer: HAZEL's selector closure can bind controller.R[route_id]
    alongside its dated RouteQuote. This function does not select or defer a
    route. Existing state-aware feasibility and economic scoring remain separate.
    """
    _integer(now, "now")
    current = controller.cur
    boundary = program_boundary(controller.R[current], controller.R[target],
                                decision_stop=decision_stop, max_steps=max_steps)
    structural = not boundary.same_object and boundary.prefix_matches(now)
    # Avoid calling the historical predicate outside its meaningful index range.
    observed = bool(controller._switch_ok(target, now)) if now < decision_stop else None
    result = boundary.as_dict()
    result.update(current_route=current, target_route=target, now=now,
                  structural_choice_now=structural, controller_accepts_now=observed,
                  predicate_agrees=(observed == structural) if observed is not None else None,
                  can_wait_one_structurally=boundary.can_wait_one(now),
                  scope="scheduled_prefix_only_not_realized_state_or_economic_value")
    return deepcopy(result)
