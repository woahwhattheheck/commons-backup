"""Bind explicit town-draw paths to the existing ROUTE-FLOW consumer.

This module translates arrival times only. ROUTE-FLOW still owns all trading,
prices, town consumption and receipts; DATE owns ranking. No probability,
controller, hidden future or additional inventory delta is introduced.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping, Sequence

from town_demand import DemandRules, build_schedule


def make_flow_scenario(
    observation: Any,
    configuration: Any,
    mechanics: Any,
    scenario_factory: Callable[..., Any],
    *,
    name: str,
    future_shops: Sequence[str] | None,
    rival_orders: Mapping[int, Sequence[Sequence[Any]]] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Return ROUTE-FLOW Scenario plus the explicit town-path provenance.

    Supply each remaining draw through episodeSteps-2, with repeated names
    preserved. A shop unlocked AFTER action t becomes available BEFORE t+1;
    FLOW itself applies consumption after that later turn's market. Arrivals
    after the final market remain in provenance but have no consumer entry.

    Unknown remaining draws are not converted into a complete future. None is
    accepted only when the window contains no remaining unlock. A supplied path
    is ONE declared scenario, not exhaustive support or a calibrated prediction.
    The caller's existing Scenario class is injected, avoiding another model.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("A nonempty scenario name is needed")
    if rival_orders is not None and not isinstance(rival_orders, Mapping):
        raise ValueError("rival_orders must be a dated mapping")
    rules = DemandRules.from_engine(mechanics)
    schedule = build_schedule(observation, configuration, rules,
                              future_shops=future_shops)
    if schedule.start_step > schedule.end_step:
        raise ValueError("No executable market remains in this observation")
    if schedule.coverage != "specified_future_scenario":
        raise ValueError("Unknown future draws cannot form a complete flow scenario")
    arrivals = tuple(zip(schedule.unlock_after_steps, schedule.future_shops))
    additions = {step + 1: (shop,) for step, shop in arrivals
                 if step + 1 <= schedule.end_step}
    scenario = scenario_factory(
        name=name,
        rival_orders=deepcopy(dict(rival_orders or {})),
        shop_additions=additions,
        description="Explicit complete town path; supplied rival trades; no probabilities",
    )
    report = {
        "schema": "town.flow-binding.v1",
        "schedule": schedule.as_dict(),
        "first_active_shop_additions": deepcopy(additions),
        "arrivals_after_final_market": [
            {"after_step": step, "shop": shop} for step, shop in arrivals
            if step + 1 > schedule.end_step
        ],
        "inventory_deltas_applied_by_adapter": False,
        "scenario_bank_exhaustive": False,
        "probabilities": None,
        "public_observations_interchangeable": False,
    }
    return scenario, report
