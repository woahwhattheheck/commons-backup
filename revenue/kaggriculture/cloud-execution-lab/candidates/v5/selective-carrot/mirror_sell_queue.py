# SPDX-License-Identifier: Apache-2.0
"""Default-off production-v3 mirror SELL queue experiment.

This transform consumes the already-landed exact mirror-assignment theorem. It
never predicts hidden rival actions and never changes sale quantities: when the
explicit experiment flag is true, it may only permute a certified leading block
of already-executable unique-product SELL rows. Missing, malformed, duplicate,
or non-positive evidence fails closed to the caller-owned fallback action.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

FEATURE = "r04_mirror_sell_queue"
REPORT_SCHEMA = "titan.v4.rowshed.mirror-collision-value.v2"
ASSIGNMENT_SCHEMA = "titan.v4.rowshed.mirror-assignment.v2"
ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"


def _plain_nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a plain nonnegative int")
    return value


def _plain_positive_int(value: Any, label: str) -> int:
    value = _plain_nonnegative_int(value, label)
    if value == 0:
        raise ValueError(f"{label} must be positive")
    return value


def _market_limit(configuration: dict[str, Any]) -> int:
    value = configuration.get("maxMarketOrdersPerTurn", 10)
    if type(value) is not int:
        raise ValueError("maxMarketOrdersPerTurn must be a plain int")
    return max(1, value)


def _fallback(selected_action: Any, fallback_action: Any) -> Any:
    return deepcopy(selected_action if fallback_action is None else fallback_action)


class MirrorSellQueue:
    """Permute one certified executable SELL prefix under a default-off flag."""

    def __init__(
        self,
        *,
        price_fn: Callable[..., Any] | None = None,
        analyzer: Callable[..., Any] | None = None,
    ) -> None:
        self.price_fn = price_fn
        self.analyzer = analyzer
        self.diagnostics: dict[str, Any] = {}

    @staticmethod
    def _load_analyzer() -> Callable[..., Any]:
        from mirror_collision_value import analyze_rows

        return analyze_rows

    @staticmethod
    def _load_price_fn() -> Callable[..., Any]:
        import mechanics

        return mechanics.market_price

    def transform(
        self,
        observation: Any,
        configuration: Any,
        selected_action: Any,
        *,
        post_unit_shed: Any = None,
        fallback_action: Any = None,
    ) -> Any:
        fallback = _fallback(selected_action, fallback_action)
        self.diagnostics = {"status": "identity", "reason": "feature_off"}

        config = {} if configuration is None else configuration
        if not isinstance(config, dict) or config.get(FEATURE) is not True:
            return fallback if not isinstance(config, dict) else deepcopy(selected_action)

        self.diagnostics = {"status": "fallback", "reason": None}
        try:
            if not isinstance(observation, dict):
                raise ValueError("observation must be a dict")
            if not isinstance(selected_action, dict):
                raise ValueError("selected action must be a dict")
            if not isinstance(post_unit_shed, dict):
                raise ValueError("post_unit_shed must be a dict")

            market_rows = selected_action.get("market", [])
            if not isinstance(market_rows, list):
                raise ValueError("market orders must be a list")
            limit = _market_limit(config)
            executable_stop = min(len(market_rows), limit)

            lead = 0
            while lead < executable_stop:
                row = market_rows[lead]
                if not row:
                    break
                if not isinstance(row, list):
                    raise ValueError("truthy executable market row must be a list")
                if len(row) < 3 or row[0] != "SELL":
                    break
                quantity = row[2]
                if type(quantity) is not int or quantity <= 0:
                    break
                lead += 1

            self.diagnostics.update(leading_sell_count=lead, market_prefix_limit=limit)
            if lead < 2:
                self.diagnostics.update(status="identity", reason="leading_sell_block_lt_2")
                return deepcopy(selected_action)

            public_market = observation.get("market")
            if not isinstance(public_market, dict):
                raise ValueError("observation market must be a dict")
            inventory = public_market.get("inventory")
            if not isinstance(inventory, dict):
                raise ValueError("market inventory must be a dict")
            params = public_market.get("params")
            if params is not None and not isinstance(params, dict):
                raise ValueError("market params must be a dict or None")

            evidence: list[dict[str, Any]] = []
            seen_items: set[str] = set()
            original_rows = market_rows[:lead]
            for index, row in enumerate(original_rows):
                item = row[1]
                if not isinstance(item, str) or not item:
                    raise ValueError("SELL item must be a nonempty string")
                if item in seen_items:
                    self.diagnostics.update(
                        status="identity", reason="duplicate_product_rows_outside_assignment_theorem"
                    )
                    return deepcopy(selected_action)
                seen_items.add(item)
                requested = _plain_positive_int(row[2], f"SELL quantity {index}")
                if item not in post_unit_shed or item not in inventory:
                    raise ValueError("shed or market inventory is incomplete for SELL block")
                stock = _plain_nonnegative_int(post_unit_shed[item], f"shed[{item}]")
                level = _plain_nonnegative_int(inventory[item], f"market.inventory[{item}]")
                fill = min(requested, stock)
                if fill <= 0:
                    self.diagnostics.update(status="identity", reason="zero_fill_in_sell_block")
                    return deepcopy(selected_action)
                evidence.append({"item": item, "public_inventory": level, "fillable": fill})

            analyzer = self.analyzer or self._load_analyzer()
            price_fn = self.price_fn or self._load_price_fn()

            def quote(item: str, level: int) -> int:
                # Runtime authority is the shipped three-argument mechanics ABI.
                # Never retry a TypeError with a different call shape: malformed
                # market params must fail closed rather than silently reprice.
                value = price_fn(item, level, params)
                if type(value) is not int or value < 1:
                    raise ValueError("market price must be a plain positive int")
                return value

            report = analyzer(evidence, price_fn=quote)
            if not isinstance(report, dict):
                raise ValueError("mirror analyzer must return a dict")
            if report.get("schema") != REPORT_SCHEMA:
                raise ValueError("mirror report schema drift")
            if report.get("engine_git_blob") != ENGINE_GIT_BLOB:
                raise ValueError("mirror engine authority drift")
            assignment = report.get("mirror_assignment")
            if not isinstance(assignment, dict):
                raise ValueError("mirror assignment is missing")
            if assignment.get("schema") != ASSIGNMENT_SCHEMA:
                raise ValueError("mirror assignment schema drift")
            if assignment.get("certified") is not True:
                self.diagnostics.update(
                    status="identity",
                    reason=str(assignment.get("reason") or "assignment_not_certified"),
                )
                return deepcopy(selected_action)

            permutation = assignment.get("optimal_permutation_indices")
            if not isinstance(permutation, list) or any(type(x) is not int for x in permutation):
                raise ValueError("optimal permutation must be a plain-int list")
            if sorted(permutation) != list(range(lead)):
                raise ValueError("optimal permutation is not a complete SELL-block permutation")
            edge = assignment.get("predicted_mirror_edge")
            if type(edge) is not int or edge < 0:
                raise ValueError("predicted mirror edge must be a plain nonnegative int")
            if edge == 0 or permutation == list(range(lead)):
                self.diagnostics.update(status="identity", reason="no_positive_assignment_edge")
                return deepcopy(selected_action)

            result = deepcopy(selected_action)
            result["market"][:lead] = [deepcopy(original_rows[index]) for index in permutation]

            # Defensive action-boundary invariants: this experiment is only a
            # permutation. It cannot change quantities, non-market actions, or
            # anything after the certified leading block.
            if result.get("farmer") != selected_action.get("farmer"):
                raise ValueError("farmer action changed")
            if result.get("hands") != selected_action.get("hands"):
                raise ValueError("hand actions changed")
            if result["market"][lead:] != selected_action["market"][lead:]:
                raise ValueError("market suffix changed")
            if sorted(map(repr, result["market"][:lead])) != sorted(map(repr, original_rows)):
                raise ValueError("SELL block ceased to be a pure permutation")

            self.diagnostics.update(
                status="applied",
                reason="certified_exact_mirror_assignment",
                predicted_mirror_edge=edge,
                permutation=list(permutation),
                evidence=evidence,
            )
            return result
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError) as error:
            self.diagnostics["reason"] = str(error)
            return fallback

    act = transform


def transform(observation: Any, configuration: Any, selected_action: Any, **kwargs: Any) -> Any:
    return MirrorSellQueue().transform(observation, configuration, selected_action, **kwargs)
