# SPDX-License-Identifier: Apache-2.0
"""Final-step cash settlement for an already-selected Kaggriculture action.

The transform is intentionally narrow and caller-owned:

* it runs only on the final executable action (``episodeSteps - 2``);
* it calls no controller, planner, model, or future-state oracle;
* the selected market queue must contain fully funded SELL orders only;
* existing unit actions are retained except certified shed-access PASS -> DROP;
* existing SELL order positions are retained, and only the last order for a
  product may be extended; missing products are appended at the tail;
* the caller supplies the exact selected-unit projector used by its runtime.

Those conditions preserve every baseline own sale receipt under the official
per-unit lockstep market.  Any newly requested sale units occur after the
baseline units for that product and each successful sale pays at least $1.
Because the official terminal reward is cash alone, ``guaranteed_min_cash_gain``
is a literal lower bound, not a score estimate.
"""
from __future__ import annotations

from copy import deepcopy
from numbers import Real
from typing import Any, Callable, Mapping

Action = dict[str, Any]
ProjectUnits = Callable[[Mapping[str, Any], Action, Mapping[str, Any]], tuple[Any, Mapping[str, Any]]]


def _report(reason: str, **values: Any) -> dict[str, Any]:
    report = {
        "changed": False,
        "certified": False,
        "reason": reason,
        "guaranteed_min_cash_gain": 0,
        "baseline_sell_units": 0,
        "candidate_sell_units": 0,
        "dropped_actor_indices": [],
        "added_sell_units": {},
        "post_unit_shed_delta": {},
        "market_prefix_preserved": False,
    }
    report.update(values)
    return report


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed <= 0 or parsed != value:
        return None
    return parsed


def _quantity(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed < 0 or parsed != value:
        return None
    return parsed


def _shed_copy(private: Mapping[str, Any]) -> dict[str, int] | None:
    raw = private.get("shed")
    if not isinstance(raw, Mapping):
        return None
    result: dict[str, int] = {}
    for item, value in raw.items():
        if not isinstance(item, str):
            return None
        quantity = _quantity(value)
        if quantity is None:
            return None
        result[item] = quantity
    return result


def _sale_queue(
    selected: Action,
    *,
    sellable: set[str],
    maximum: int,
) -> tuple[list[list[Any]], dict[str, int], dict[str, int]] | None:
    raw = selected.get("market")
    if not isinstance(raw, list) or len(raw) > maximum:
        return None
    market: list[list[Any]] = []
    requested: dict[str, int] = {}
    last: dict[str, int] = {}
    for index, order in enumerate(raw):
        if not isinstance(order, list) or len(order) < 3 or order[0] != "SELL":
            return None
        item = order[1]
        amount = _positive_int(order[2])
        if not isinstance(item, str) or item not in sellable or amount is None:
            return None
        copied = deepcopy(order)
        # The official parser ignores trailing fields.  Preserve them byte-for-byte.
        market.append(copied)
        requested[item] = requested.get(item, 0) + amount
        last[item] = index
    return market, requested, last


def _project(
    project_units: ProjectUnits,
    observation: Mapping[str, Any],
    selected: Action,
    configuration: Mapping[str, Any],
) -> tuple[Any, Mapping[str, Any]] | None:
    try:
        projected = project_units(
            deepcopy(observation), deepcopy(selected), deepcopy(configuration)
        )
    except Exception:
        return None
    if not isinstance(projected, tuple) or len(projected) != 2:
        return None
    _, private = projected
    if not isinstance(private, Mapping):
        return None
    return projected


def _componentwise_at_least(
    candidate: Mapping[str, int], baseline: Mapping[str, int]
) -> bool:
    return all(candidate.get(item, 0) >= quantity for item, quantity in baseline.items())


def _request_totals(market: list[list[Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for order in market:
        totals[order[1]] = totals.get(order[1], 0) + int(order[2])
    return totals


def _augment_tail_sales(
    baseline_market: list[list[Any]],
    stock: Mapping[str, int],
    *,
    sellable: set[str],
    maximum: int,
    prices: Mapping[str, Any],
    required_products: set[str],
) -> tuple[list[list[Any]], set[str]]:
    """Fund all feasible stock without moving an existing market position.

    Required products (newly deposited cargo) receive the scarce append slots
    first.  Existing products are extended at their last own SELL, so all added
    units execute after that product's complete baseline request.
    """
    market = deepcopy(baseline_market)
    requested = _request_totals(market)
    last: dict[str, int] = {}
    for index, order in enumerate(market):
        last[order[1]] = index

    def rank(item: str) -> tuple[int, float, str]:
        raw_price = prices.get(item, 1)
        price = float(raw_price) if isinstance(raw_price, Real) else 1.0
        return (0 if item in required_products else 1, -price, item)

    uncovered: set[str] = set()
    products = sorted(
        (item for item in sellable if stock.get(item, 0) > requested.get(item, 0)),
        key=rank,
    )
    for item in products:
        amount = int(stock.get(item, 0)) - requested.get(item, 0)
        if amount <= 0:
            continue
        if item in last:
            index = last[item]
            market[index][2] = int(market[index][2]) + amount
            requested[item] = requested.get(item, 0) + amount
        elif len(market) < maximum:
            market.append(["SELL", item, int(stock[item])])
            last[item] = len(market) - 1
            requested[item] = int(stock[item])
        else:
            uncovered.add(item)
    return market, uncovered


def _set_actor_action(action: Action, actor_index: int, replacement: list[str]) -> None:
    if actor_index == 0:
        action["farmer"] = replacement
    else:
        action["hands"][actor_index - 1] = replacement


def _market_prices(observation: Mapping[str, Any]) -> Mapping[str, Any]:
    market = observation.get("market")
    if not isinstance(market, Mapping):
        return {}
    prices = market.get("prices")
    return prices if isinstance(prices, Mapping) else {}


def compose_terminal_settlement(
    observation: Mapping[str, Any],
    configuration: Mapping[str, Any] | None,
    selected_action: Action,
    *,
    project_units: ProjectUnits,
    max_drop_candidates: int = 8,
) -> tuple[Action, dict[str, Any]]:
    """Return a cash-dominating final action or the unchanged selected action.

    ``project_units`` must apply exactly the selected unit stage and return
    ``(farm, private)``.  The function is fail-closed: malformed state, a mixed
    market queue, an underfunded baseline sale, projection disagreement, or an
    inability to sell newly dropped cargo returns an untouched deep copy.
    """
    original = deepcopy(selected_action)
    cfg = dict(configuration or {})
    if not isinstance(observation, Mapping) or not isinstance(selected_action, dict):
        return original, _report("malformed_inputs")

    step = _quantity(observation.get("step"))
    episode_steps = _positive_int(cfg.get("episodeSteps", 720))
    if step is None or episode_steps is None or step != episode_steps - 2:
        return original, _report(
            "not_final_executable_step",
            observed_step=step,
            final_executable_step=None if episode_steps is None else episode_steps - 2,
        )

    try:
        player = int(observation["player"])
        farms = observation["farms"]
        farm = farms[player]
        positions = [farm["farmer"], *farm.get("hands", [])]
        private = observation["private"]
        inventories = private["inventories"]
    except (KeyError, TypeError, ValueError, IndexError):
        return original, _report("malformed_actor_state")

    farmer_action = selected_action.get("farmer")
    hands_actions = selected_action.get("hands")
    if (
        not isinstance(farmer_action, list)
        or not isinstance(hands_actions, list)
        or len(hands_actions) + 1 != len(positions)
        or len(inventories) != len(positions)
    ):
        return original, _report("actor_action_inventory_mismatch")

    public_market = observation.get("market")
    inventory = public_market.get("inventory") if isinstance(public_market, Mapping) else None
    if not isinstance(inventory, Mapping) or not inventory:
        return original, _report("missing_public_market_inventory")
    sellable = {item for item in inventory if isinstance(item, str)}
    if not sellable:
        return original, _report("missing_sellable_products")

    maximum = _positive_int(cfg.get("maxMarketOrdersPerTurn", 10))
    if maximum is None:
        return original, _report("invalid_market_order_cap")
    parsed = _sale_queue(selected_action, sellable=sellable, maximum=maximum)
    if parsed is None:
        return original, _report("baseline_not_valid_sale_only_queue")
    baseline_market, baseline_requested, _ = parsed

    projected = _project(project_units, observation, original, cfg)
    if projected is None:
        return original, _report("baseline_projection_failed")
    baseline_shed = _shed_copy(projected[1])
    if baseline_shed is None:
        return original, _report("baseline_projection_missing_shed")
    if any(baseline_requested.get(item, 0) > baseline_shed.get(item, 0) for item in baseline_requested):
        return original, _report(
            "baseline_sell_not_fully_funded",
            baseline_sell_units=sum(baseline_requested.values()),
        )

    prices = _market_prices(observation)
    candidate = deepcopy(original)
    candidate_market, _ = _augment_tail_sales(
        baseline_market,
        baseline_shed,
        sellable=sellable,
        maximum=maximum,
        prices=prices,
        required_products=set(),
    )
    candidate["market"] = candidate_market
    accepted_shed = baseline_shed
    accepted_requested = _request_totals(candidate_market)
    accepted_actors: list[int] = []

    board_size = _positive_int(cfg.get("boardSize", len(farm.get("tiles", []))))
    if board_size is None:
        return original, _report("invalid_board_size")
    half = board_size // 2
    access = {(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)}
    actions = [farmer_action, *hands_actions]

    eligible: list[tuple[float, int]] = []
    for actor_index, (position, action, cargo) in enumerate(zip(positions, actions, inventories)):
        try:
            at_access = tuple(position) in access
        except TypeError:
            at_access = False
        if action != ["PASS"] or not at_access or not isinstance(cargo, Mapping):
            continue
        value = 0.0
        positive = False
        for item, raw_quantity in cargo.items():
            quantity = _quantity(raw_quantity)
            if quantity is None:
                positive = False
                value = -1.0
                break
            if quantity > 0:
                positive = True
                raw_price = prices.get(item, 1)
                price = float(raw_price) if isinstance(raw_price, Real) else 1.0
                value += quantity * max(1.0, price)
        if positive and value >= 0:
            eligible.append((-value, actor_index))
    eligible.sort()
    candidate_cap = _positive_int(max_drop_candidates)
    if candidate_cap is None:
        return original, _report("invalid_drop_candidate_cap")
    considered = eligible[:candidate_cap]

    for _, actor_index in considered:
        trial = deepcopy(candidate)
        _set_actor_action(trial, actor_index, ["DROP"])
        trial_projected = _project(project_units, observation, trial, cfg)
        if trial_projected is None:
            continue
        trial_shed = _shed_copy(trial_projected[1])
        if trial_shed is None:
            continue
        # Preserve the complete baseline shed and every already accepted cargo lot.
        if not _componentwise_at_least(trial_shed, baseline_shed):
            continue
        if not _componentwise_at_least(trial_shed, accepted_shed):
            continue
        delta = {
            item: trial_shed.get(item, 0) - baseline_shed.get(item, 0)
            for item in set(trial_shed) | set(baseline_shed)
        }
        positive_delta = {item for item, amount in delta.items() if amount > 0}
        if not positive_delta or not positive_delta <= sellable:
            continue
        trial_market, uncovered = _augment_tail_sales(
            baseline_market,
            trial_shed,
            sellable=sellable,
            maximum=maximum,
            prices=prices,
            required_products=positive_delta,
        )
        trial_requested = _request_totals(trial_market)
        # Every newly deposited unit must be placed after the fully funded
        # baseline request for its product.  Otherwise the cash proof is absent.
        if uncovered & positive_delta:
            continue
        if any(
            trial_requested.get(item, 0)
            < baseline_requested.get(item, 0) + delta[item]
            for item in positive_delta
        ):
            continue
        if sum(trial_requested.values()) <= sum(accepted_requested.values()):
            continue
        candidate = trial
        candidate["market"] = trial_market
        accepted_shed = trial_shed
        accepted_requested = trial_requested
        accepted_actors.append(actor_index)

    baseline_units = sum(baseline_requested.values())
    candidate_units = sum(accepted_requested.values())
    guaranteed_gain = candidate_units - baseline_units
    if guaranteed_gain <= 0:
        return original, _report(
            "no_certified_gain",
            baseline_sell_units=baseline_units,
            candidate_sell_units=baseline_units,
        )

    added = {
        item: accepted_requested.get(item, 0) - baseline_requested.get(item, 0)
        for item in sorted(set(accepted_requested) | set(baseline_requested))
        if accepted_requested.get(item, 0) > baseline_requested.get(item, 0)
    }
    shed_delta = {
        item: accepted_shed.get(item, 0) - baseline_shed.get(item, 0)
        for item in sorted(set(accepted_shed) | set(baseline_shed))
        if accepted_shed.get(item, 0) > baseline_shed.get(item, 0)
    }
    return candidate, _report(
        "certified_terminal_cash_gain",
        changed=candidate != original,
        certified=True,
        guaranteed_min_cash_gain=guaranteed_gain,
        baseline_sell_units=baseline_units,
        candidate_sell_units=candidate_units,
        dropped_actor_indices=accepted_actors,
        added_sell_units=added,
        post_unit_shed_delta=shed_delta,
        market_prefix_preserved=True,
        final_executable_step=episode_steps - 2,
        eligible_actor_count=len(eligible),
        considered_actor_count=len(considered),
        drop_candidate_cap=candidate_cap,
        proof=(
            "baseline sale-only queue is fully funded; baseline unit and market "
            "positions are preserved; each extension occurs after that product's "
            "baseline units; every additional committed sale pays at least $1"
        ),
    )
