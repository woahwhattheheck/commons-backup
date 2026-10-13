# SPDX-License-Identifier: Apache-2.0
"""Current-ABI row-shed SELL ordering donor for TITAN V4.

This module ports only the V3.1 S33/S34 ordering theorem. It does not construct
or invoke a production controller and it never mutates the selected action.

The caller must supply the *post-unit* shed projection already owned by the
current selected-action stack. Only the executable leading contiguous SELL
block may be reordered; engine-inert market suffix rows are byte-preserved.
Falsey rows, zero-quantity engine-dead SELL rows, and the first non-SELL row are
hard barriers.
"""
from __future__ import annotations

from copy import deepcopy
import mechanics


def _plain_nonnegative_int(value):
    return type(value) is int and value >= 0


def _plain_positive_int(value):
    return type(value) is int and value > 0


def _market_prefix_limit(configuration):
    """Return the official minimum-one executable market prefix length.

    Missing configuration keeps the engine default of 10. Type-poison fails
    closed instead of inheriting Python ``int(...)`` coercions.
    """
    if configuration is None:
        return 10
    value = configuration.get("maxMarketOrdersPerTurn", 10)
    if type(value) is not int:
        raise ValueError("maxMarketOrdersPerTurn must be a plain int")
    return max(1, value)


def _fallback_copy(selected_action, fallback_action):
    return deepcopy(selected_action if fallback_action is None else fallback_action)


class RowShedSellOrder:
    """Rank executable leading SELL rows by the price drop they can fill.

    This is deliberately a transform, not a controller. It is intended to sit
    after the caller-owned unit projection and before the current SELL optimizer.
    Missing or ambiguous evidence returns the caller's fallback action unchanged.
    """

    def __init__(self, price_fn=None):
        self.price_fn = mechanics.market_price if price_fn is None else price_fn
        self.diagnostics = {}

    def transform(self, observation, configuration, selected_action, *,
                  post_unit_shed=None, fallback_action=None):
        fallback = _fallback_copy(selected_action, fallback_action)
        self.diagnostics = {
            "status": "fallback",
            "reason": None,
            "leading_sell_count": 0,
            "market_prefix_limit": None,
            "scores": [],
        }

        try:
            if not isinstance(observation, dict):
                raise ValueError("observation must be a dict")
            if configuration is not None and not isinstance(configuration, dict):
                raise ValueError("configuration must be a dict or None")
            if not isinstance(selected_action, dict):
                raise ValueError("selected action must be a dict")
            if not isinstance(post_unit_shed, dict):
                raise ValueError("post_unit_shed must be a dict")

            rows = selected_action.get("market", [])
            if not isinstance(rows, list):
                raise ValueError("market orders must be a list")

            market_prefix_limit = _market_prefix_limit(configuration)
            self.diagnostics["market_prefix_limit"] = market_prefix_limit

            # The official interpreter truncates each player's market queue to
            # the executable prefix *before* parsing rows. Truthy malformed
            # suffix values are therefore engine-inert evidence and cannot veto
            # a valid reorder inside the prefix; preserve them byte-for-byte.
            if any(
                row and not isinstance(row, list)
                for row in rows[:market_prefix_limit]
            ):
                raise ValueError("truthy executable market row must be a list")

            market = observation.get("market")
            if not isinstance(market, dict):
                raise ValueError("observation market must be a dict")
            inventory = market.get("inventory")
            if not isinstance(inventory, dict):
                raise ValueError("market inventory must be a dict")
            params = market.get("params")
            if params is not None and not isinstance(params, dict):
                raise ValueError("market params must be a dict or None")

            lead = 0
            executable_stop = min(len(rows), market_prefix_limit)
            while lead < executable_stop:
                row = rows[lead]
                if not row:
                    break
                if row[0] != "SELL":
                    break
                # The official interpreter rejects every SELL quantity <= 0.
                # A plain non-positive quantity therefore occupies an
                # engine-dead row and is a hard ordering barrier: never move a
                # live SELL across it.
                if len(row) >= 3 and type(row[2]) is int and row[2] <= 0:
                    break
                lead += 1
            self.diagnostics["leading_sell_count"] = lead

            if lead < 2:
                self.diagnostics.update(status="identity", reason="leading_sell_block_lt_2")
                return deepcopy(selected_action)

            scored = []
            for index, row in enumerate(rows[:lead]):
                if len(row) < 3:
                    raise ValueError("leading SELL row is missing item or quantity")
                item, requested = row[1], row[2]
                if not isinstance(item, str) or not item:
                    raise ValueError("SELL item must be a non-empty string")
                if not _plain_positive_int(requested):
                    raise ValueError("SELL quantity must be a plain positive int")
                if item not in post_unit_shed:
                    raise ValueError("projected shed is incomplete for leading SELL block")
                stock = post_unit_shed[item]
                if not _plain_nonnegative_int(stock):
                    raise ValueError("projected shed count must be a plain non-negative int")
                if item not in inventory:
                    raise ValueError("market inventory is incomplete for leading SELL block")
                level = inventory[item]
                if not _plain_nonnegative_int(level):
                    raise ValueError("market inventory count must be a plain non-negative int")
                fill = min(requested, stock)

                before = self.price_fn(item, level, params)
                after = self.price_fn(item, level + fill, params)
                if (type(before) is not int or type(after) is not int
                        or before < 0 or after < 0):
                    raise ValueError("market price must be a plain non-negative int")
                impact = (before - after) * fill
                scored.append((impact, index, row))

            # Python sort is stable. Equal scores therefore preserve the exact
            # incumbent relative order, one of the S33 donor invariants.
            ordered = sorted(scored, key=lambda entry: entry[0], reverse=True)
            result = deepcopy(selected_action)
            result["market"][:lead] = [deepcopy(row) for _, _, row in ordered]
            self.diagnostics.update(
                status="applied",
                reason="row_shed_price_impact",
                scores=[{
                    "original_index": index,
                    "item": row[1],
                    "requested": row[2],
                    "fillable": min(row[2], post_unit_shed[row[1]]),
                    "impact": impact,
                } for impact, index, row in scored],
            )
            return result
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError) as error:
            self.diagnostics["reason"] = str(error)
            return fallback

    act = transform


def transform(observation, configuration, selected_action, **kwargs):
    """Stateless convenience call matching the current selected-action ABI."""
    return RowShedSellOrder().transform(
        observation, configuration, selected_action, **kwargs
    )
