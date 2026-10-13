# SPDX-License-Identifier: Apache-2.0
"""Tail-window SELL completeness for an already-selected Kaggriculture action.

This is the pre-terminal companion to ``terminal_settlement.compose_terminal_settlement``.
Terminal settlement runs only on the final executable step (``episodeSteps - 2``)
and is justified by a proof that unsold shed stock has *zero* terminal reward, so
liquidating everything can only help.  That proof does not hold before the final
step, so this transform does something strictly narrower and provable at every
step in a late window:

    For each product the selected policy is *already selling this turn* on an
    engine-executable market row, grow that row's quantity so it equals the exact
    projected shed quantity of that product this turn.

Nothing else changes.  No new product is introduced, no order outside the
engine-executable prefix is touched, no farmer/hand unit action is altered, no
route/controller/model is consulted.  The transform captures the same-turn
production that reached the shed via the official ``_commit_unit`` path but that
an exact visible/projected SELL quantity under-caught, which is the measured
leader-tape motif (oversized all-product SELL catchers from ~step 670).  It does
so with disciplined funded quantities rather than a blind qty-1000, so no order
is ever rejected and no receipt is invented.

Three arms share this file; pick with flags (Yusuf/Ibis, 21:18-21:19):

  * *raw* (default): grow to the full projected shed.  Note this is a **late
    full-inventory liquidation** of any product the baseline already sells at
    least once -- on a no-production turn (shed WHEAT 10 unchanged, SELL WHEAT 1)
    it still grows to SELL WHEAT 10.  Measure it as-is to learn whether aggressive
    liquidation / rival price pressure itself does the work; do not "fix" it first.
  * *net_new_only=True*: cap the added quantity by the unit-stage net shed increase
    (``post_unit_shed - pre_unit_shed``), so a no-production turn stays
    byte-identical.  This is the true "exact rows under-catch same-turn
    production" mechanism.
  * *require_certified_reserve=True* with ``reserve``: withhold caller-certified
    future operational demand (see below).

What this transform does *not* claim: it does not forecast price, and it does not
assert a monotone whole-game cash bound (that is false before the terminal step,
because a unit swept now can have shadow value as a later production input or
under a later, shop-lifted quote).  The single-turn property it *does* guarantee
-- ``execution_certified``, not economically-safe (Ibis) -- is:

  1. no product's engine-executed sold quantity this turn is reduced;
  2. every added unit is backed by projected shed stock, so it is a funded order
     the engine will execute, not a rejected or fabricated sale.

Whole-game W/T/L on current TITAN bytes is a matched paired-panel question.  The
transform is default-off and caller-owned.  Because it leaves the action
byte-identical on every turn where nothing is added, paired arms stay coupled
except on turns where the chosen arm actually fires -- so the existing paired game
gate can measure it, unlike a route key that decorrelates the arms at the
shop-plan branch.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

Action = dict[str, Any]
ProjectUnits = Callable[[Mapping[str, Any], Action, Mapping[str, Any]], tuple[Any, Mapping[str, Any]]]


def _report(reason: str, **values: Any) -> dict[str, Any]:
    report = {
        "changed": False,
        "execution_certified": False,
        "reason": reason,
        "window_first_step": None,
        "final_executable_step": None,
        "observed_step": None,
        "baseline_sell_units": 0,
        "candidate_sell_units": 0,
        "added_sell_units": {},
        "swept_products": [],
        "reserved_products": [],
        "held_for_consumption": [],
        "executable_prefix": None,
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


def _sale_only_market(
    selected: Action,
    *,
    sellable: set[str],
) -> list[list[Any]] | None:
    """Validate every row is a well-formed sellable SELL order; return a copy.

    The length is intentionally *not* capped against ``maxMarketOrdersPerTurn``.
    The official engine executes only the leading prefix and ignores the rest, so
    a selected action legitimately carries engine-inactive suffix SELL rows (the
    exact scenario the executable-sell-custody candidate quarantines).  This
    transform tolerates that suffix and never touches it.
    """
    raw = selected.get("market")
    if not isinstance(raw, list):
        return None
    market: list[list[Any]] = []
    for order in raw:
        if not isinstance(order, list) or len(order) < 3 or order[0] != "SELL":
            return None
        item = order[1]
        amount = _positive_int(order[2])
        if not isinstance(item, str) or item not in sellable or amount is None:
            return None
        market.append(deepcopy(order))
    return market


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


def _request_totals(market: list[list[Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for order in market:
        totals[order[1]] = totals.get(order[1], 0) + int(order[2])
    return totals


def _pass_unit_variant(selected: Action) -> Action:
    """A copy of the action whose unit stage is all-PASS.

    Projecting this yields the shed *before* this turn's unit stage, so
    ``post_unit_shed - pre_unit_shed`` is the net stock the unit stage produced
    (or consumed) this turn -- the cap the net-new-only arm uses.
    """
    variant = deepcopy(selected)
    variant["farmer"] = ["PASS"]
    hands = variant.get("hands")
    if isinstance(hands, list):
        variant["hands"] = [["PASS"] for _ in hands]
    return variant


def compose_tail_settlement(
    observation: Mapping[str, Any],
    configuration: Mapping[str, Any] | None,
    selected_action: Action,
    *,
    project_units: ProjectUnits,
    window: int = 48,
    shop_interval: int = 4,
    town_interval: int = 24,
    shop_consumed: Any = None,
    consumption_safe: bool = True,
    net_new_only: bool = False,
    reserve: Mapping[str, int] | None = None,
    require_certified_reserve: bool = False,
) -> tuple[Action, dict[str, Any]]:
    """Return an action whose already-executed SELL rows sweep all projected shed
    stock of the products they name, or the unchanged selected action.

    ``project_units`` must apply exactly the selected unit stage and return
    ``(farm, private)``.  The function is fail-closed: malformed state, a mixed or
    over-cap market queue, a step outside the tail window, projection failure, or
    an already-complete queue returns an untouched deep copy of the input.

    ``window`` is the number of pre-terminal steps (inclusive of the final
    executable step) on which the transform is *eligible* to act.  The default 48
    covers the measured leader motif onset (~step 670 in the 720-state config).

    ``consumption_safe`` (default True) enforces the engine-derived boundary that
    makes a bulk residual sweep economically sound.  The market price is
    quantity-declining within a turn, and consumption after market absorbs supply
    and lifts later quotes, so metering across a consumption tick can beat selling
    everything now (the engine's own measurement: 12 MILK sold-all-now $1026 vs
    sell-6/consume/sell-6 $1078).  A bulk sweep forgoes nothing only *after a
    product's last consumption tick at or before the final step*.  There are two
    consumption clocks (Opus TITAN seat, 21:27): each unlocked **shop** consumes
    its products every ``shop_interval`` steps (``townShopSellInterval``, 4 by
    default -> ticks 700, 704, ... 716), and the **town center** consumes one
    non-fertilizer product every ``town_interval`` steps (24 -> ... 696).

    The guard is therefore *per product*.  ``shop_consumed`` is the caller-supplied
    set of products an unlocked shop takes (read from the observation); the sweep
    of such a product is clamped past its last shop tick (step 717 in the default
    config).  A product not in ``shop_consumed`` is clamped only past the town
    tick (step 697).  When ``shop_consumed`` is ``None`` the guard is conservative
    and treats *every* product as shop-consumed (clamp 717) -- so supply the set to
    widen the window.  ``consumption_safe=False`` removes the clamp entirely (raw).

    ``consumption_safe`` only closes the *shop-absorption timing* objection.  It
    does not close the *future operational-demand* objection (Yusuf, 21:15): a
    unit sold now has shadow value if the policy's own later stages feed, pick up,
    or otherwise consume that product before terminal.  ``reserve`` is the
    caller-certified per-product quantity to withhold from the sweep for that
    demand: the sweep grows a row only up to ``projected_shed - reserve[item]``,
    never below the baseline request.  With ``require_certified_reserve=True`` any
    product absent from ``reserve`` is left identity for the turn (fail closed), so
    the changed bytes carry two certificates -- no future shop batching benefit and
    no known future operational demand.  The default (empty reserve, flag off) is
    the raw sweep; flipping the flag on with a supplied reserve is the reserve-aware
    arm, and the two are a clean 1:1 gauntlet comparison on identical seeds.
    """
    original = deepcopy(selected_action)
    cfg = dict(configuration or {})
    if not isinstance(observation, Mapping) or not isinstance(selected_action, dict):
        return original, _report("malformed_inputs")

    window_span = _positive_int(window)
    if window_span is None:
        return original, _report("invalid_window")
    shop_period = _positive_int(shop_interval)
    town_period = _positive_int(town_interval)
    if shop_period is None or town_period is None:
        return original, _report("invalid_consumption_interval")
    shop_set: set[str] | None
    if shop_consumed is None:
        shop_set = None
    else:
        try:
            shop_set = {item for item in shop_consumed if isinstance(item, str)}
        except TypeError:
            return original, _report("invalid_shop_consumed")
    reserve_map: dict[str, int] = {}
    if reserve is not None:
        if not isinstance(reserve, Mapping):
            return original, _report("invalid_reserve")
        for item, value in reserve.items():
            amount = _quantity(value)
            if not isinstance(item, str) or amount is None:
                return original, _report("invalid_reserve")
            reserve_map[item] = amount

    step = _quantity(observation.get("step"))
    episode_steps = _positive_int(cfg.get("episodeSteps", 720))
    if step is None or episode_steps is None:
        return original, _report("malformed_step")
    final_step = episode_steps - 2
    first_step = final_step - (window_span - 1)
    # Two consumption clocks.  A product forgoes a batching gain only until its
    # own last tick <= final_step; after that no absorption remains.
    last_shop_tick = (final_step // shop_period) * shop_period
    last_town_tick = (final_step // town_period) * town_period

    def _product_first(item: str) -> int:
        # The earliest step at which sweeping this product forgoes no batching.
        if not consumption_safe:
            return first_step
        if shop_set is None or item in shop_set:
            tick = last_shop_tick          # conservative / known shop-consumed
        else:
            tick = last_town_tick          # only the town clock applies
        return max(first_step, tick + 1)

    # Global admission: the widest any product could act is ``first_step``.
    if step < first_step or step > final_step:
        return original, _report(
            "outside_tail_window",
            observed_step=step,
            window_first_step=first_step,
            last_shop_tick=last_shop_tick,
            last_town_tick=last_town_tick,
            final_executable_step=final_step,
        )

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
    # The official engine normalizes the cap to at least one and executes only the
    # leading prefix ``market[:prefix]``.  Rows after that never sell, so growing
    # them would be a fabricated receipt; the transform never touches them.
    prefix = max(1, maximum)

    baseline_market = _sale_only_market(selected_action, sellable=sellable)
    if baseline_market is None:
        return original, _report("baseline_not_valid_sale_only_queue")

    projected = _project(project_units, observation, original, cfg)
    if projected is None:
        return original, _report("baseline_projection_failed")
    baseline_shed = _shed_copy(projected[1])
    if baseline_shed is None:
        return original, _report("baseline_projection_missing_shed")

    # net_new_only caps the added quantity by this turn's unit-stage net shed
    # increase, so a no-production turn stays byte-identical (Yusuf's arm 2).
    extra_cap: dict[str, int] | None = None
    if net_new_only:
        pre_projected = _project(project_units, observation, _pass_unit_variant(original), cfg)
        if pre_projected is None:
            return original, _report("pre_unit_projection_failed")
        pre_unit_shed = _shed_copy(pre_projected[1])
        if pre_unit_shed is None:
            return original, _report("pre_unit_projection_missing_shed")
        extra_cap = {
            item: max(0, baseline_shed.get(item, 0) - pre_unit_shed.get(item, 0))
            for item in baseline_shed
        }

    executable = baseline_market[:prefix]
    # Requested totals over only the rows the engine actually executes.
    baseline_requested = _request_totals(executable)
    # The executed prefix must already be funded from the projected shed; this
    # keeps every added unit honest and matches the terminal certificate's spirit.
    if any(baseline_requested.get(item, 0) > baseline_shed.get(item, 0) for item in baseline_requested):
        return original, _report(
            "baseline_sell_not_fully_funded",
            baseline_sell_units=sum(baseline_requested.values()),
        )

    # Last executable-prefix order index for each product actually sold this turn.
    last_exec: dict[str, int] = {}
    for index, order in enumerate(executable):
        last_exec[order[1]] = index

    candidate_market = deepcopy(baseline_market)
    swept: list[str] = []
    reserved: list[str] = []
    held_for_consumption: list[str] = []
    for item, index in last_exec.items():
        available = baseline_shed.get(item, 0)
        current_total = baseline_requested.get(item, 0)
        if step < _product_first(item):
            # This product still has a consumption tick ahead; sweeping it now
            # could forgo the batching gain, so leave it as the policy chose.
            held_for_consumption.append(item)
            continue
        if require_certified_reserve and item not in reserve_map:
            # No certified operational-demand reserve for this product: leave it
            # exactly as the policy chose (fail closed on the shadow-value axis).
            reserved.append(item)
            continue
        # Withhold the caller-certified operational-demand reserve, then sell the
        # rest of the projected shed.  Never shrink the baseline request.
        sell_cap = available - reserve_map.get(item, 0)
        target_total = max(current_total, sell_cap)
        added = target_total - current_total
        if extra_cap is not None:
            # net_new_only: no more than this turn's unit-stage net production.
            added = min(added, extra_cap.get(item, 0))
        if added <= 0:
            continue  # nothing to add under the active caps
        # Grow only this product's last executable order.  Every other order for
        # the product is left untouched, so the added units land after its prior
        # units, and the new quantity never exceeds projected shed minus reserve.
        candidate_market[index][2] = int(candidate_market[index][2]) + added
        swept.append(item)

    if not swept:
        return original, _report(
            "queue_already_complete",
            observed_step=step,
            window_first_step=first_step,
            final_executable_step=final_step,
            executable_prefix=prefix,
            baseline_sell_units=sum(baseline_requested.values()),
            candidate_sell_units=sum(baseline_requested.values()),
            reserved_products=sorted(reserved),
            held_for_consumption=sorted(held_for_consumption),
            market_prefix_preserved=True,
        )

    candidate = deepcopy(original)
    candidate["market"] = candidate_market
    candidate_requested = _request_totals(candidate_market[:prefix])

    baseline_units = sum(baseline_requested.values())
    candidate_units = sum(candidate_requested.values())
    added = {
        item: candidate_requested.get(item, 0) - baseline_requested.get(item, 0)
        for item in sorted(swept)
        if candidate_requested.get(item, 0) > baseline_requested.get(item, 0)
    }
    return candidate, _report(
        "tail_sweep_applied",
        changed=candidate != original,
        execution_certified=True,
        observed_step=step,
        window_first_step=first_step,
        final_executable_step=final_step,
        executable_prefix=prefix,
        baseline_sell_units=baseline_units,
        candidate_sell_units=candidate_units,
        added_sell_units=added,
        swept_products=sorted(swept),
        reserved_products=sorted(reserved),
        held_for_consumption=sorted(held_for_consumption),
        market_prefix_preserved=True,
        proof=(
            "each grown row is an engine-executable prefix SELL the baseline "
            "already places; its new quantity never exceeds projected shed stock "
            "(and, under net_new_only/reserve, is capped below it), so no unit is "
            "unfunded; no other order, product, or unit action changes; this is an "
            "execution/funding certificate only -- whole-game economics are the "
            "paired-panel measurement"
        ),
    )
