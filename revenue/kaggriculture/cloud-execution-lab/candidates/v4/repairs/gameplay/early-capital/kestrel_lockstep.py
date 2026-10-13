# SPDX-License-Identifier: Apache-2.0
"""Fail-closed current-V4 admission for early-capital market reordering.

This is a current-ABI recovery of the reviewed KESTREL lockstep theorem.  It
wraps the existing ``early_capital.order_early_capital`` helper; it does not
implement a second capital policy.  Disabled and rejected cases return the
exact parent action object.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha1
from pathlib import Path
from typing import Any, Callable
import json
import math

DONOR_LOCKSTEP_GIT_BLOB = "4999efe1506fa0aa49e5ce9f21c68bdebe5424b4"
CANONICAL_CANDIDATE_GIT_BLOB = "c87f1d1c9d7b416c5316837634f7e721c85811fa"
PRODUCTION_EARLY_CAPITAL_GIT_BLOB = "1161859ac5af617eca65aec3f732b5c1396cad37"
CURRENT_EARLY_CAPITAL_TEST_GIT_BLOB = "89b451c47da299a68a755d49596a262aa507bbca"
CURRENT_RUNTIME_GIT_BLOB = "6d9720f4aa1e6b46e92ee5183897074d8e9ea5a0"
CURRENT_CONFIG_GIT_BLOB = "3a3bef83899d3010fad623b628d9e95d9978111b"
OFFICIAL_ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"

BUYABLE_PRODUCTS = frozenset(("WHEAT", "FERTILIZER"))
CAPITAL_OPS = frozenset(("BUY_LAND", "BUY_ANIMAL"))
MAX_CERTIFIED_SHED_CAPACITY = 256

CANONICAL_REL = "candidates/v4/repairs/gameplay/early-capital/early_capital.py"
BOUND_PATHS = {
    CANONICAL_REL: CANONICAL_CANDIDATE_GIT_BLOB,
    "early_capital.py": PRODUCTION_EARLY_CAPITAL_GIT_BLOB,
    "test_early_capital.py": CURRENT_EARLY_CAPITAL_TEST_GIT_BLOB,
    "titan_runtime.py": CURRENT_RUNTIME_GIT_BLOB,
    "TITAN-CONFIG.json": CURRENT_CONFIG_GIT_BLOB,
    "reference/engine/kaggriculture.py": OFFICIAL_ENGINE_GIT_BLOB,
}


def git_blob_sha1(data: bytes) -> str:
    return sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def verify_current_bindings(cloud_lab: str | Path) -> dict[str, Any]:
    """Authenticate the source graph required by this recovery theorem."""
    root = Path(cloud_lab)
    observed: dict[str, str | None] = {}
    for rel, expected in BOUND_PATHS.items():
        path = root / rel
        try:
            actual = git_blob_sha1(path.read_bytes())
        except OSError:
            actual = None
        observed[rel] = actual
        if actual != expected:
            return {
                "ok": False,
                "reason": "source_binding_mismatch",
                "path": rel,
                "expected": expected,
                "actual": actual,
                "observed": observed,
            }
    return {"ok": True, "reason": "authenticated", "observed": observed}


def _is_pass(order: Any) -> bool:
    return order is None or order == [] or order == ["PASS"]


def _canonical_order(order: Any) -> str:
    try:
        return json.dumps(order, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("uncanonicalizable market order") from exc


def _same_order_multiset(left: list[Any], right: list[Any]) -> bool:
    if len(left) != len(right):
        return False
    return sorted(_canonical_order(row) for row in left) == sorted(
        _canonical_order(row) for row in right
    )


def _order_op(order: Any) -> str:
    if _is_pass(order):
        return "PASS"
    if isinstance(order, list) and order and isinstance(order[0], str):
        return order[0]
    return "MALFORMED"


def _sell_parts(order: Any) -> tuple[str, int] | None:
    if not (isinstance(order, list) and order and order[0] == "SELL"):
        return None
    if len(order) < 3 or not isinstance(order[1], str) or not order[1]:
        raise ValueError("malformed SELL")
    qty = order[2]
    if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
        raise ValueError("invalid SELL quantity")
    return order[1], qty


def _sale_units_never_move_later(original: list[Any], candidate: list[Any],
                                 products: set[str]) -> bool:
    before = {item: 0 for item in products}
    after = {item: 0 for item in products}
    for old, new in zip(original, candidate):
        sold_old = _sell_parts(old)
        sold_new = _sell_parts(new)
        if sold_old is not None and sold_old[0] in before:
            before[sold_old[0]] += sold_old[1]
        if sold_new is not None and sold_new[0] in after:
            after[sold_new[0]] += sold_new[1]
        if any(after[item] < before[item] for item in products):
            return False
    return before == after


def _configuration_int(configuration: Mapping | None, key: str, default: int) -> int:
    raw = default if not isinstance(configuration, Mapping) else configuration.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"invalid {key}")
    return raw


def _checked_market_price(mechanics: Any, item: str, inventory: int,
                          params: Mapping | None) -> float:
    value = mechanics.market_price(item, inventory, params)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("non-numeric market price")
    value = float(value)
    if not math.isfinite(value) or value < 1:
        raise ValueError("invalid market price")
    return value


def rival_lockstep_certificate(mechanics: Any, observation: Mapping,
                               configuration: Mapping | None,
                               original_action: Mapping,
                               candidate_action: Mapping) -> tuple[bool, dict[str, Any]]:
    """Prove a changed queue cannot lose an original own execution.

    This intentionally certifies only the historical KESTREL shape: non-buyable
    product SELLs + PASS + exactly one fixed-cost capital row.  Any operating
    BUY/HIRE/SEED row makes the candidate unprovable and therefore rejected.
    """
    report: dict[str, Any] = {
        "schema": "titan-v4-kestrel-lockstep/v1",
        "certified": False,
        "barriers": [],
        "products": [],
    }
    if not isinstance(original_action, Mapping) or not isinstance(candidate_action, Mapping):
        report["barriers"].append("malformed_action")
        return False, report
    original_market = original_action.get("market")
    candidate_market = candidate_action.get("market")
    if not isinstance(original_market, list) or not isinstance(candidate_market, list):
        report["barriers"].append("malformed_market")
        return False, report

    other_keys = (set(original_action) | set(candidate_action)) - {"market"}
    if any(original_action.get(k) != candidate_action.get(k) for k in other_keys):
        report["barriers"].append("non_market_mutation")

    try:
        limit = max(1, _configuration_int(configuration, "maxMarketOrdersPerTurn", 10))
        capacity = _configuration_int(configuration, "shedCapacity", 100)
    except ValueError as exc:
        report["barriers"].append(str(exc).replace(" ", "_"))
        return False, report
    report["active_prefix_limit"] = limit
    report["shed_capacity"] = capacity
    if capacity < 1 or capacity > MAX_CERTIFIED_SHED_CAPACITY:
        report["barriers"].append("unsupported_shed_capacity")
        return False, report

    original_active = original_market[:limit]
    candidate_active = candidate_market[:limit]
    if original_market[limit:] != candidate_market[limit:]:
        report["barriers"].append("inactive_tail_changed")
    try:
        if not _same_order_multiset(original_active, candidate_active):
            report["barriers"].append("active_prefix_membership_changed")
    except ValueError:
        report["barriers"].append("uncanonicalizable_order")

    original_capital: list[tuple[int, Any]] = []
    candidate_capital: list[tuple[int, Any]] = []
    products: set[str] = set()
    for side, active, capitals in (
        ("original", original_active, original_capital),
        ("candidate", candidate_active, candidate_capital),
    ):
        for index, order in enumerate(active):
            try:
                sale = _sell_parts(order)
            except ValueError:
                report["barriers"].append(f"invalid_sell:{side}:{index}")
                continue
            if sale is not None:
                products.add(sale[0])
                if sale[0] in BUYABLE_PRODUCTS:
                    report["barriers"].append(f"rival_buyable_sale:{sale[0]}")
                continue
            if _is_pass(order):
                continue
            op = _order_op(order)
            if op in CAPITAL_OPS:
                capitals.append((index, order))
            else:
                report["barriers"].append(f"unsupported_active_op:{op}")

    report["products"] = sorted(products)
    if len(original_capital) != 1 or len(candidate_capital) != 1:
        report["barriers"].append("requires_exactly_one_capital_order")
    else:
        try:
            same_capital = _canonical_order(original_capital[0][1]) == _canonical_order(candidate_capital[0][1])
        except ValueError:
            same_capital = False
        if not same_capital:
            report["barriers"].append("capital_order_changed")
        else:
            old_i, capital = original_capital[0]
            new_i = candidate_capital[0][0]
            report["capital"] = {
                "op": capital[0],
                "item": capital[1] if len(capital) > 1 else None,
                "quantity": capital[2] if len(capital) > 2 else 1,
                "original_index": old_i,
                "candidate_index": new_i,
            }
            if any(not _is_pass(row) for row in candidate_active[new_i + 1:]):
                report["barriers"].append("effectful_order_after_capital")

    try:
        if not _sale_units_never_move_later(original_active, candidate_active, products):
            report["barriers"].append("sale_units_moved_later")
    except ValueError:
        report["barriers"].append("invalid_sell_quantity")

    market = observation.get("market") if isinstance(observation, Mapping) else None
    inventory = market.get("inventory") if isinstance(market, Mapping) else None
    prices = market.get("prices") if isinstance(market, Mapping) else None
    params = market.get("params") if isinstance(market, Mapping) else None
    if (not isinstance(market, Mapping) or not isinstance(inventory, Mapping)
            or not isinstance(prices, Mapping)
            or (params is not None and not isinstance(params, Mapping))):
        report["barriers"].append("malformed_public_market")
        report["barriers"] = sorted(set(report["barriers"]))
        return False, report

    horizon = 2 * capacity
    curves: dict[str, Any] = {}
    for item in sorted(products):
        if item in BUYABLE_PRODUCTS:
            continue
        start = inventory.get(item)
        visible = prices.get(item)
        if (isinstance(start, bool) or not isinstance(start, int)
                or isinstance(visible, bool) or not isinstance(visible, (int, float))
                or not math.isfinite(float(visible)) or float(visible) < 1):
            report["barriers"].append(f"invalid_public_quote:{item}")
            continue
        try:
            curve = [_checked_market_price(mechanics, item, start + offset, params)
                     for offset in range(horizon + 1)]
        except (ArithmeticError, LookupError, TypeError, ValueError, OverflowError):
            report["barriers"].append(f"unavailable_price_curve:{item}")
            continue
        if curve[0] != float(visible):
            report["barriers"].append(f"stale_public_quote:{item}")
        if any(later > earlier for earlier, later in zip(curve, curve[1:])):
            report["barriers"].append(f"nonmonotone_price_curve:{item}")
        curves[item] = {"inventory_start": start, "inventory_end": start + horizon,
                        "visible_price": float(visible), "end_price": curve[-1]}
    report["curve_checks"] = curves
    report["barriers"] = sorted(set(report["barriers"]))
    report["certified"] = not report["barriers"]
    if report["certified"]:
        report["proof"] = (
            "Requested non-buyable sale units move no later; rival supply can only "
            "weakly lower the checked sale curves; the sole fixed-cost capital row "
            "is the last effectful candidate row. Original own executions therefore "
            "cannot be lost under the same hidden rival queue."
        )
    return report["certified"], report


def order_early_capital_lockstep(mechanics: Any, observation: Mapping,
                                 configuration: Mapping | None, selected: Any,
                                 route: Any, decisions: Any = (), *,
                                 enabled: bool = False,
                                 base_order: Callable[..., tuple[Any, Any]] | None = None):
    """Run current early-capital then admit only a lockstep-certified change."""
    if enabled is not True:
        return selected, {
            "schema": "titan-v4-kestrel-lockstep/v1",
            "changed": False,
            "reason": "disabled",
            "certified": False,
        }
    if base_order is None:
        import importlib.util
        source = Path(__file__).with_name("early_capital.py")
        spec = importlib.util.spec_from_file_location("titan_v4_canonical_early_capital", source)
        if spec is None or spec.loader is None:
            return selected, {
                "schema": "titan-v4-kestrel-lockstep/v1",
                "changed": False,
                "reason": "canonical_base_unavailable",
                "certified": False,
            }
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        base_order = module.order_early_capital

    candidate, base_report = base_order(
        mechanics, observation, configuration, selected, route, decisions
    )
    if candidate == selected:
        return selected, {
            "schema": "titan-v4-kestrel-lockstep/v1",
            "changed": False,
            "reason": "base_identity",
            "base_report": base_report,
            "lockstep_certificate": {"certified": True, "kind": "identity"},
        }
    if not (isinstance(base_report, Mapping)
            and base_report.get("changed") is True
            and base_report.get("reason") == "ordered"
            and base_report.get("revision") == "v6-commit-real-capital"
            and base_report.get("capital_certificate_reason") == "certified"):
        return selected, {
            "schema": "titan-v4-kestrel-lockstep/v1",
            "changed": False,
            "reason": "canonical_base_unproven",
            "base_report": base_report,
            "lockstep_certificate": {"certified": False, "kind": "base_report_rejected"},
        }
    certified, certificate = rival_lockstep_certificate(
        mechanics, observation, configuration, selected, candidate
    )
    if not certified:
        return selected, {
            "schema": "titan-v4-kestrel-lockstep/v1",
            "changed": False,
            "reason": "rival_interleaving_unproven",
            "base_report": base_report,
            "lockstep_certificate": certificate,
        }
    return candidate, {
        "schema": "titan-v4-kestrel-lockstep/v1",
        "changed": True,
        "reason": "rival_lockstep_nonregression_proved",
        "base_report": base_report,
        "lockstep_certificate": certificate,
    }


__all__ = [
    "BOUND_PATHS",
    "CANONICAL_CANDIDATE_GIT_BLOB",
    "DONOR_LOCKSTEP_GIT_BLOB",
    "order_early_capital_lockstep",
    "rival_lockstep_certificate",
    "verify_current_bindings",
]
