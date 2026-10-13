# SPDX-License-Identifier: Apache-2.0
"""Default-OFF boundary adapter for the exact preserved S13 tail donor.

This is NOT production plumbing, a unit projector, a future-demand provider, or
an economic promotion. The caller must supply an exact selected-unit projector;
shop_consumed, when supplied, must cover every shop product through the horizon.
None is conservative. Raw, net-new and reserve arithmetic remains donor-owned.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from functools import lru_cache
import importlib.util
from pathlib import Path
from typing import Any, Callable

DONOR_SHA256 = "ead794d663a01967723932613fef800a0345b67daabefcf6799c812c933a6a54"
PRODUCTS = frozenset(("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
                      "EGG", "MILK", "WOOL", "FERTILIZER"))


@lru_cache(maxsize=1)
def _donor() -> Any:
    """Load only the locally preserved, byte-pinned original on enabled calls."""
    import hashlib
    source = Path(__file__).resolve().parent / "legacy" / "tail_settlement.py"
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != DONOR_SHA256:
        raise ValueError("S13 donor byte custody mismatch")
    spec = importlib.util.spec_from_file_location("_titan_v4_s13_donor", source)
    if spec is None or spec.loader is None:
        raise ImportError("S13 donor loader unavailable")
    module = importlib.util.module_from_spec(spec)
    # Execute the bytes just verified, not a second filesystem read or stale pyc.
    exec(compile(data, str(source), "exec"), module.__dict__)
    return module


def _unchanged(action: Any, reason: str) -> tuple[Any, dict[str, Any]]:
    return action, {"changed": False, "execution_certified": False,
                    "reason": reason, "adapter": "s13-boundary/v1"}


def _positive(value: Any) -> bool:
    return type(value) is int and value > 0


def compose_tail_settlement(
    observation: Mapping[str, Any],
    configuration: Mapping[str, Any] | None,
    selected_action: dict[str, Any],
    *,
    project_units: Callable[..., Any],
    enabled: bool = False,
    window: int = 48,
    shop_interval: int | None = None,
    town_interval: int | None = None,
    shop_consumed: Any = None,
    consumption_safe: bool = True,
    net_new_only: bool = False,
    reserve: Mapping[str, int] | None = None,
    require_certified_reserve: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Guard donor admission; preserve exact parent identity on every no-op.

    Clocks come from engine configuration, not independent default arguments.
    An explicit legacy clock argument must equal the configured value. The town
    center clock applies to shop-consumed products too; use the later last tick.
    Only the raw executable market prefix is passed to the sale-only donor. Its
    inert suffix is reattached unchanged, without filtering or shifting slots.
    Flags must be literal bools. Malformed evidence never widens admission.
    """
    if enabled is False:
        return _unchanged(selected_action, "disabled")
    if enabled is not True or any(type(flag) is not bool for flag in
            (consumption_safe, net_new_only, require_certified_reserve)):
        return _unchanged(selected_action, "invalid_flags")
    if (not isinstance(observation, Mapping)
            or not isinstance(selected_action, dict)
            or (configuration is not None and not isinstance(configuration, Mapping))):
        return _unchanged(selected_action, "malformed_inputs")
    if not callable(project_units):
        return _unchanged(selected_action, "invalid_projector")
    try:
        cfg = dict(configuration) if configuration is not None else {}
        step = observation.get("step")
        horizon = cfg.get("episodeSteps", 720)
        cap = cfg.get("maxMarketOrdersPerTurn", 10)
        shop = cfg.get("townShopSellInterval", 4)
        town = cfg.get("townCenterSellInterval", 24)
        if (type(step) is not int or step < 0 or not _positive(horizon)
                or horizon < 2 or not all(_positive(v) for v in (cap, shop, town, window))):
            return _unchanged(selected_action, "invalid_calendar_or_cap")
        if any(explicit is not None and (not _positive(explicit) or explicit != actual)
               for explicit, actual in ((shop_interval, shop), (town_interval, town))):
            return _unchanged(selected_action, "clock_configuration_mismatch")
        if shop_consumed is None:
            consumed = None
        elif (type(shop_consumed) not in (set, frozenset, list, tuple)
              or any(type(item) is not str or item not in PRODUCTS for item in shop_consumed)):
            return _unchanged(selected_action, "invalid_shop_consumed")
        else:
            consumed = set(shop_consumed)
        if reserve is not None and (not isinstance(reserve, Mapping) or any(
                type(k) is not str or k not in PRODUCTS or type(v) is not int or v < 0
                for k, v in reserve.items())):
            return _unchanged(selected_action, "invalid_reserve")
        raw = selected_action.get("market")
        if not isinstance(raw, list):
            return _unchanged(selected_action, "invalid_market")
        public_market = observation.get("market")
        inventory = public_market.get("inventory") if isinstance(public_market, Mapping) else None
        if not isinstance(inventory, Mapping) or not inventory or any(
                type(item) is not str or item not in PRODUCTS for item in inventory):
            return _unchanged(selected_action, "invalid_public_products")
        if any(not isinstance(row, list) or len(row) < 3 or row[0] != "SELL"
               or type(row[1]) is not str or row[1] not in PRODUCTS or not _positive(row[2])
               for row in raw[:cap]):
            return _unchanged(selected_action, "invalid_executable_sale_prefix")
        final = horizon - 2
        # The later clock is sufficient for every product in this conservative
        # adapter. Use its period for the donor's shop branch, not an invented tick.
        effective_shop = shop if (final // shop) * shop >= (final // town) * town else town
        narrowed = deepcopy(selected_action)
        narrowed["market"] = deepcopy(raw[:cap])
        result, report = _donor().compose_tail_settlement(
            observation, cfg, narrowed, project_units=project_units,
            window=window, shop_interval=effective_shop, town_interval=town,
            shop_consumed=consumed, consumption_safe=consumption_safe,
            net_new_only=net_new_only, reserve=reserve,
            require_certified_reserve=require_certified_reserve,
        )
        report = dict(report, adapter="s13-boundary/v1",
                      configured_shop_interval=shop, configured_town_interval=town,
                      effective_last_shop_or_center_tick=max(
                          (final // shop) * shop, (final // town) * town),
                      ignored_suffix_rows=max(0, len(raw) - cap))
        if not report.get("changed"):
            return selected_action, report
        # All unit/metadata surfaces are still exactly those chosen by the parent.
        candidate = dict(selected_action)
        candidate["market"] = result["market"] + deepcopy(raw[cap:])
        return candidate, report
    except Exception:
        return _unchanged(selected_action, "adapter_or_projection_failed")
