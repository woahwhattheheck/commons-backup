# SPDX-License-Identifier: Apache-2.0
"""Fail-closed final-action novelty admission for STRATUM row-shed ordering.

STRATUM is injected inside ``FrozenSelected.transform``. After that seam the
existing seller may resize, blank, append or reorder market rows before TITAN
applies canonical market pressure. Therefore neither an intermediate rank
comparison nor a direct pressure replay from the STRATUM seam proves that
STRATUM changes the action ultimately returned to the engine.

This module deliberately does not replay that stateful suffix. Its caller must
supply the two already-produced final returned actions from an authenticated,
isolated dual-arm execution of the complete canonical suffix. Admission then
requires both of these independent facts:

* the STRATUM candidate changed only a leading executable positive-quantity
  SELL block inside the official market prefix; and
* the two final returned actions still differ in engine-effective market
  semantics inside that executable prefix after all remaining seller economics
  and pressure.

Final rows are compared by the pinned official market parser/quote semantics,
not raw syntax: parser-dead rows are inert, HIRE/BUY_LAND ignore extra tokens,
positive BUY/SELL quantities use ``int(...)`` coercion, unsupported item/op
combinations are inert, and trailing inert slots are behaviorally irrelevant.
Interior inert slots are retained because row index controls lockstep timing.

Suffix-only differences never establish novelty. Missing, malformed or
non-comparable evidence fails closed to exact parent identity. This is an
evidence/admission primitive, not a controller and not a second seller/pressure
implementation.
"""
from __future__ import annotations

from copy import deepcopy


class NoveltyEvidenceError(ValueError):
    """Supplied STRATUM/final-action evidence is not auditable."""


# Official engine market domains for reference/engine/kaggriculture.py
# blob 3c202c7ee921da239356789e266b694635103fc4. Keep this helper fail-closed
# rather than treating an unknown item as executable novelty.
_ENGINE_PRODUCTS = frozenset({
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
    "EGG", "MILK", "WOOL", "FERTILIZER",
})
_ENGINE_CROPS = frozenset({"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"})
_ENGINE_ANIMALS = frozenset({"GOOSE", "COW", "SHEEP"})
_ENGINE_BUY_PRODUCTS = frozenset({"WHEAT", "FERTILIZER"})
_ENGINE_QUANTITY_OPS = frozenset({"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL"})


def _market_prefix_limit(configuration):
    if configuration is None:
        return 10
    if not isinstance(configuration, dict):
        raise NoveltyEvidenceError("configuration must be a dict or None")
    raw = configuration.get("maxMarketOrdersPerTurn", 10)
    # Deliberately stricter than int(...): ambiguous/coercible public evidence
    # cannot authorize this admission helper.
    if type(raw) is not int:
        raise NoveltyEvidenceError("maxMarketOrdersPerTurn must be a plain int")
    return max(1, raw)


def _truthy_malformed_market_row(rows):
    return any(row and not isinstance(row, list) for row in rows)


def _same_rows_with_duplicates(left, right):
    if len(left) != len(right):
        return False
    used = [False] * len(right)
    for row in left:
        for index, other in enumerate(right):
            if not used[index] and type(row) is type(other) and row == other:
                used[index] = True
                break
        else:
            return False
    return True


def _same_non_market_surface(left, right):
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    if set(left) != set(right):
        return False
    return all(left[key] == right[key] for key in left if key != "market")


def _parent_shape(action, limit):
    if not isinstance(action, dict):
        raise NoveltyEvidenceError("action must be a dict")
    rows = action.get("market")
    if not isinstance(rows, list):
        raise NoveltyEvidenceError("action market must be a list")
    # The official engine truncates the market queue before parsing rows.
    # Malformed values beyond the executable prefix are inert evidence and may
    # be preserved raw, but malformed values inside the prefix fail closed.
    if _truthy_malformed_market_row(rows[:limit]):
        raise NoveltyEvidenceError("truthy executable market row must be a list")

    lead = 0
    for row in rows[:limit]:
        if not row:
            break
        if not isinstance(row, list) or row[0] != "SELL":
            break
        if len(row) < 3:
            raise NoveltyEvidenceError("leading SELL row is missing item or quantity")
        item, requested = row[1], row[2]
        if not isinstance(item, str) or not item:
            raise NoveltyEvidenceError("leading SELL item must be a non-empty string")
        # Official _process_market only quotes SELL when item in PRODUCTS.
        # Unsupported SELL is quote-stage inert: a hard barrier, not sortable
        # SELL evidence, matching zero-quantity dead rows.
        if item not in _ENGINE_PRODUCTS:
            break
        # Official order parsing treats n <= 0 as a dead row. It is a barrier,
        # not a sortable SELL, because crossing it changes lockstep timing.
        if type(requested) is not int or requested <= 0:
            break
        lead += 1
    return rows, lead


def _validate_row_shed_candidate(parent, candidate, lead, limit):
    if not isinstance(candidate, dict):
        raise NoveltyEvidenceError("row-shed candidate must be a dict")
    if not _same_non_market_surface(parent, candidate):
        raise NoveltyEvidenceError("row-shed changed a non-market action surface")

    parent_rows = parent["market"]
    rows = candidate.get("market")
    if not isinstance(rows, list) or len(rows) != len(parent_rows):
        raise NoveltyEvidenceError("row-shed market cardinality differs from parent")
    if _truthy_malformed_market_row(rows[:limit]):
        raise NoveltyEvidenceError("truthy executable row-shed market row must be a list")

    # Protect both the first hard barrier and every engine-inert suffix row.
    # STRATUM may only permute the authenticated executable SELL block. Raw
    # suffix bytes remain exact even when the engine will never parse them.
    if rows[lead:] != parent_rows[lead:]:
        raise NoveltyEvidenceError(
            "row-shed changed a barrier or row outside executable SELL block"
        )

    block = rows[:lead]
    if any(
        not row
        or not isinstance(row, list)
        or len(row) < 3
        or row[0] != "SELL"
        or not isinstance(row[1], str)
        or not row[1]
        or row[1] not in _ENGINE_PRODUCTS
        or type(row[2]) is not int
        or row[2] <= 0
        for row in block
    ):
        raise NoveltyEvidenceError("row-shed executable block is not valid SELL rows")
    if not _same_rows_with_duplicates(block, parent_rows[:lead]):
        raise NoveltyEvidenceError(
            "row-shed did not preserve executable SELL rows with multiplicity"
        )


def _engine_effective_market_order(row):
    """Canonicalize one final market row to the official engine effect shape.

    ``None`` means the row is parser/quote-stage inert. A truthy non-list is
    rejected rather than normalized because the surrounding final-action
    evidence is malformed. Quantity coercion intentionally mirrors
    ``_parse_order``; overflow is fail-closed because the engine does not
    recover from it either.
    """
    if not row:
        return None
    if not isinstance(row, list):
        raise NoveltyEvidenceError("truthy final market row must be a list")

    op = row[0]
    if op == "HIRE":
        return ("HIRE",)
    if op == "BUY_LAND":
        return ("BUY_LAND",)
    if op not in _ENGINE_QUANTITY_OPS:
        return None
    if len(row) < 3:
        return None

    try:
        requested = int(row[2])
    except (TypeError, ValueError):
        return None
    except OverflowError as error:
        raise NoveltyEvidenceError(
            "final market quantity overflows official parser"
        ) from error
    if requested <= 0:
        return None

    item = row[1]
    if not isinstance(item, str):
        raise NoveltyEvidenceError("final market item must be a string")
    if op == "SELL":
        live = item in _ENGINE_PRODUCTS
    elif op == "BUY_PRODUCT":
        live = item in _ENGINE_BUY_PRODUCTS
    elif op == "BUY_SEED":
        live = item in _ENGINE_CROPS
    else:  # BUY_ANIMAL
        live = item in _ENGINE_ANIMALS
    if not live:
        return None
    return (op, item, requested)


def _final_executable_prefix(action, limit):
    if not isinstance(action, dict):
        raise NoveltyEvidenceError("final action must be a dict")
    rows = action.get("market")
    if not isinstance(rows, list):
        raise NoveltyEvidenceError("final action market must be a list")
    if _truthy_malformed_market_row(rows[:limit]):
        raise NoveltyEvidenceError("truthy executable final market row must be a list")

    # Keep interior inert slots: market orders execute in row-index lockstep and
    # moving a later live order across an inert row can change relative timing.
    # Trim only trailing inert slots because they cause no market state change.
    prefix = [_engine_effective_market_order(row) for row in rows[:limit]]
    while prefix and prefix[-1] is None:
        prefix.pop()
    return prefix


class FinalActionNoveltyGuard:
    """Admit STRATUM only when complete-pipeline returned actions stay novel."""

    def __init__(self):
        self.diagnostics = {}

    def choose(
        self,
        parent_action,
        row_shed_action,
        incumbent_final_action,
        row_shed_final_action,
        configuration,
    ):
        self.diagnostics = {
            "status": "identity",
            "reason": None,
            "market_prefix_limit": None,
            "leading_sell_count": 0,
            "incumbent_final_prefix": [],
            "row_shed_final_prefix": [],
        }
        try:
            limit = _market_prefix_limit(configuration)
            self.diagnostics["market_prefix_limit"] = limit
            parent_rows, lead = _parent_shape(parent_action, limit)
            parent = deepcopy(parent_action)
            parent["market"] = deepcopy(parent_rows)
            self.diagnostics["leading_sell_count"] = lead

            if lead < 2:
                self.diagnostics["reason"] = "executable_leading_sell_block_lt_2"
                return deepcopy(parent_action)

            _validate_row_shed_candidate(parent, row_shed_action, lead, limit)
            if row_shed_action == parent_action:
                self.diagnostics["reason"] = "row_shed_identity"
                return deepcopy(parent_action)

            if not _same_non_market_surface(
                incumbent_final_action, row_shed_final_action
            ):
                raise NoveltyEvidenceError(
                    "final arms differ on non-market action surface"
                )

            incumbent_prefix = _final_executable_prefix(
                incumbent_final_action, limit
            )
            row_shed_prefix = _final_executable_prefix(
                row_shed_final_action, limit
            )
            self.diagnostics.update(
                incumbent_final_prefix=incumbent_prefix,
                row_shed_final_prefix=row_shed_prefix,
            )

            if incumbent_prefix == row_shed_prefix:
                self.diagnostics["reason"] = "collapsed_before_engine_execution"
                return deepcopy(parent_action)

            self.diagnostics.update(
                status="applied",
                reason="survives_complete_suffix_in_executable_prefix",
            )
            return deepcopy(row_shed_action)
        except (NoveltyEvidenceError, KeyError, TypeError, IndexError) as error:
            self.diagnostics["reason"] = str(error)
            return deepcopy(parent_action)


# Compatibility aliases for the earlier rank-only/direct-pressure carrier. The
# semantics are intentionally stricter now: callers must supply final returned
# actions from the complete remaining canonical pipeline.
PressureNoveltyGuard = FinalActionNoveltyGuard
NovelRankGuard = FinalActionNoveltyGuard


def choose(
    parent_action,
    row_shed_action,
    incumbent_final_action,
    row_shed_final_action,
    configuration,
):
    """Stateless convenience wrapper."""
    return FinalActionNoveltyGuard().choose(
        parent_action,
        row_shed_action,
        incumbent_final_action,
        row_shed_final_action,
        configuration,
    )
