# SPDX-License-Identifier: Apache-2.0
"""Executable-prefix guard for the current operating-stock helper.

The official engine executes only the first ``maxMarketOrdersPerTurn`` market rows.
This adapter gives the existing fertilizer operating-stock delegate exactly that view
for the current action and every inspected future route row, then restores the raw
current-action suffix unchanged.  It adds no economics and ships unwired/defaultless.
"""
from __future__ import annotations

from copy import deepcopy


def _limit(configuration):
    cfg = configuration or {}
    value = cfg.get("maxMarketOrdersPerTurn", 10)
    if type(value) is not int or value <= 0:
        raise ValueError("invalid_max_market_orders")
    return value


def _bounded_row(row, limit):
    if not isinstance(row, dict):
        return row
    market = row.get("market")
    if not isinstance(market, list):
        return row
    out = dict(row)
    # Future route views are isolated too: a delegate must never mutate the
    # producer-owned route while inspecting the executable prefix.
    out["market"] = deepcopy(market[:limit])
    return out


class ExecutablePrefixRoute:
    """Read-only sequence view that hides engine-dead market suffix rows."""

    def __init__(self, route, limit):
        self._route = route
        self._limit = limit

    def __len__(self):
        return len(self._route)

    def __getitem__(self, key):
        if isinstance(key, slice):
            return [_bounded_row(row, self._limit) for row in self._route[key]]
        return _bounded_row(self._route[key], self._limit)


def protect_operating_stock_prefix(
    delegate,
    mechanics,
    observation,
    configuration,
    selected,
    post_farm,
    post_private,
    route,
    checkpoints=(),
):
    """Call ``delegate`` on executable prefixes and restore the raw suffix.

    Fail closed to the exact original ``selected`` object if configuration, input,
    or delegate output is malformed.  The adapter authorizes market-prefix edits only;
    unit actions and all other selected-action fields remain owned by the caller.
    """
    guard = {"executable_prefix_guard": True, "changed": False}
    try:
        limit = _limit(configuration)
        if not isinstance(selected, dict):
            raise ValueError("selected_not_mapping")
        market = selected.get("market")
        if not isinstance(market, list):
            raise ValueError("selected_market_not_list")
        prefix = deepcopy(market[:limit])
        suffix = deepcopy(market[limit:])
        bounded = deepcopy(selected)
        bounded["market"] = prefix
        view = ExecutablePrefixRoute(route, limit)
        result, report = delegate(
            mechanics,
            observation,
            configuration,
            bounded,
            post_farm,
            post_private,
            view,
            checkpoints,
        )
        if not isinstance(result, dict) or not isinstance(report, dict):
            raise ValueError("delegate_shape")
        result_market = result.get("market")
        if not isinstance(result_market, list):
            raise ValueError("delegate_market_not_list")
        # A full executable prefix has no insertion room.  Shortening it would shift
        # a raw suffix row into execution when the suffix is restored.
        if len(prefix) == limit and len(result_market) != limit:
            raise ValueError("delegate_changed_full_prefix_length")
        if len(result_market) > limit:
            raise ValueError("delegate_exceeded_executable_prefix")
        before_other = {k: v for k, v in bounded.items() if k != "market"}
        after_other = {k: v for k, v in result.items() if k != "market"}
        if after_other != before_other:
            raise ValueError("delegate_changed_nonmarket_fields")
        if result_market == prefix:
            merged = dict(report)
            merged.update(guard, executable_prefix_limit=limit,
                          raw_suffix_rows=len(suffix), reason=report.get("reason"))
            return selected, merged
        out = deepcopy(result)
        out["market"] = deepcopy(result_market) + suffix
        merged = dict(report)
        merged.update(executable_prefix_guard=True, executable_prefix_limit=limit,
                      raw_suffix_rows=len(suffix), changed=True)
        return out, merged
    except (ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
        guard.update(reason=str(error))
        return selected, guard
