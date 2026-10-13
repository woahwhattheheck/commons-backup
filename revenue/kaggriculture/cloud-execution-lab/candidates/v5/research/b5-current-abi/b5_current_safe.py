# SPDX-License-Identifier: Apache-2.0
"""Fail-closed current envelope around the exact B5 donor decisions."""
from __future__ import annotations

from typing import Any

from b5_current import B5CurrentABI as _DonorPair


def _worker_count(observation: Any) -> int | None:
    if not isinstance(observation, dict):
        return None
    player = observation.get("player")
    farms = observation.get("farms")
    private = observation.get("private")
    if type(player) is not int or player not in (0, 1):
        return None
    if not isinstance(farms, list) or player >= len(farms) or not isinstance(private, dict):
        return None
    farm = farms[player]
    if not isinstance(farm, dict) or "farmer" not in farm or not isinstance(farm.get("hands"), list):
        return None
    inventories = private.get("inventories")
    count = 1 + len(farm["hands"])
    if not isinstance(inventories, list) or len(inventories) != count:
        return None
    return count


def _action_matches_workers(action: Any, count: int | None) -> bool:
    if count is None or not isinstance(action, dict) or "farmer" not in action:
        return False
    hands = action.get("hands")
    if not isinstance(hands, list) or len(hands) != count - 1:
        return False
    commands = [action["farmer"], *hands]
    return all(isinstance(command, list) and command and isinstance(command[0], str)
               for command in commands)


class B5CurrentABI:
    """Current selected-action seam with strict worker/route cardinality binding.

    The historical donors ran behind a fixed R04 tape whose worker cardinality was
    already guaranteed upstream. Current V5 exposes this adapter directly, so the
    envelope makes that formerly implicit precondition explicit and fail-closed.
    """

    def __init__(self, *, carrot: bool = False, jit: bool = False):
        if type(carrot) is not bool or type(jit) is not bool:
            raise TypeError("carrot and jit must be exact bool")
        self.carrot = carrot
        self.jit = jit
        self._carrot = _DonorPair(carrot=carrot, jit=False)
        self._jit = _DonorPair(carrot=False, jit=jit)

    def transform(
        self,
        observation: Any,
        selected: Any,
        *,
        next_authored: Any = None,
        next_authored_step: Any = None,
    ):
        count = _worker_count(observation)
        if not _action_matches_workers(selected, count):
            return selected, {
                "carrot_enabled": self.carrot,
                "jit_enabled": self.jit,
                "carrot_activations": (),
                "jit_activations": (),
                "jit_route_bound": False,
                "changed": False,
                "reason": "selected_worker_envelope_invalid",
            }

        action, carrot_report = self._carrot.transform(observation, selected)
        report = dict(carrot_report)
        report["carrot_enabled"] = self.carrot
        report["jit_enabled"] = self.jit
        report["jit_activations"] = ()
        report["jit_route_bound"] = False
        report["reason"] = "identity"

        if self.jit:
            step = observation.get("step") if isinstance(observation, dict) else None
            route_bound = (
                type(step) is int
                and type(next_authored_step) is int
                and next_authored_step == step + 1
                and _action_matches_workers(next_authored, count)
            )
            report["jit_route_bound"] = route_bound
            if route_bound:
                action, jit_report = self._jit.transform(
                    observation,
                    action,
                    next_authored=next_authored,
                    next_authored_step=next_authored_step,
                )
                # The submitted JIT donor attributes every activation to the
                # exact public step. b5_current keeps donor action semantics
                # stateless, so restore that evidence field at the current-ABI
                # boundary rather than weakening the durable receipt. Put the
                # authenticated public step last so donor/report drift cannot
                # override the boundary-owned evidence identity.
                report["jit_activations"] = tuple(
                    {**activation, "step": step}
                    for activation in jit_report["jit_activations"]
                )
            else:
                report["reason"] = "jit_route_envelope_unbound"

        report["changed"] = action != selected
        if report["changed"]:
            report["reason"] = "b5_current_transform"
        return action, report
