"""Bridge public rival-pressure evidence into bounded sale-timing stress scenarios.

Research only. This module does not predict rival actions, choose routes, mutate
TITAN actions, or authorize a runtime/default change. It consumes the public-only
PARALLAX report and expands visible standing yield into a bounded family of
partial same-product sale stresses suitable for the existing sale-horizon scorer.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

REPORT_SCHEMA = "titan-v4-public-rival-route-pressure-v1"
BRIDGE_SCHEMA = "titan-v4-gemini-public-timing-envelope-v1"
ALIGNMENTS = ("before", "paired", "after")
PRODUCTS = frozenset(
    (
        "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
        "EGG", "MILK", "WOOL", "FERTILIZER",
    )
)
MAX_RIVAL_QUANTITY = 100
MAX_TIMING_TURNS = 16


class UnsupportedBridgeEvidence(ValueError):
    """Raised when upstream research evidence is malformed or over-claims authority."""


def _strict_nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise UnsupportedBridgeEvidence(f"{label} must be a nonnegative integer")
    return value


def _strict_positive_int(value: Any, label: str) -> int:
    value = _strict_nonnegative_int(value, label)
    if value == 0:
        raise UnsupportedBridgeEvidence(f"{label} must be positive")
    return value


def _validate_report(
    report: Mapping[str, Any],
) -> tuple[list[Mapping[str, Any]], int, int]:
    if not isinstance(report, Mapping):
        raise UnsupportedBridgeEvidence("pressure report must be a mapping")
    if report.get("schema") != REPORT_SCHEMA:
        raise UnsupportedBridgeEvidence("unexpected pressure-report schema")
    if report.get("research_only") is not True:
        raise UnsupportedBridgeEvidence("pressure report must remain research-only")
    if report.get("decision_authority") is not False:
        raise UnsupportedBridgeEvidence("pressure report must have no decision authority")
    report_start = _strict_nonnegative_int(report.get("start"), "pressure report start")
    report_end = _strict_nonnegative_int(report.get("end"), "pressure report end")
    if report_end < report_start:
        raise UnsupportedBridgeEvidence("pressure report end precedes start")
    rows = report.get("incremental_sell_rows")
    if not isinstance(rows, list):
        raise UnsupportedBridgeEvidence("incremental_sell_rows must be a list")
    validated: list[Mapping[str, Any]] = []
    seen_products: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise UnsupportedBridgeEvidence("pressure row must be a mapping")
        product = row.get("product")
        if not isinstance(product, str) or product not in PRODUCTS:
            raise UnsupportedBridgeEvidence("pressure row product must be a supported product")
        if product in seen_products:
            raise UnsupportedBridgeEvidence("duplicate pressure row product")
        seen_products.add(product)
        added = _strict_nonnegative_int(
            row.get("incremental_target_sell_units"),
            "incremental_target_sell_units",
        )
        standing = _strict_nonnegative_int(
            row.get("visible_rival_standing_yield"),
            "visible_rival_standing_yield",
        )
        absorption = _strict_nonnegative_int(
            row.get("known_current_shop_absorption"),
            "known_current_shop_absorption",
        )
        pressure = _strict_nonnegative_int(
            row.get("public_pressure_units"), "public_pressure_units"
        )
        expected_pressure = max(0, added + standing - absorption)
        if pressure != expected_pressure:
            raise UnsupportedBridgeEvidence("public pressure algebra drift")
        validated.append(row)
    return validated, report_start, report_end


def build_public_partial_timing_envelope(
    pressure_report: Mapping[str, Any],
    *,
    now: int,
    end: int,
    max_rival_quantity: int = MAX_RIVAL_QUANTITY,
) -> dict[str, Any]:
    """Expand public standing yield into partial same-product timing stresses.

    Every positive integer quantity from 1 through the smaller of public standing
    yield and ``max_rival_quantity`` is crossed with every integer turn in the
    requested 1..16-turn window and the existing before/paired/after raw-row
    alignments. These are adversarial stress hypotheses only: public standing
    yield is not private shed inventory and is not evidence that the rival will
    harvest or sell any amount.

    The requested timing window must stay inside the source PARALLAX report's
    own ``start..end`` custody window. Public evidence from one route horizon is
    never replayed into an unrelated earlier or later horizon.
    """
    now = _strict_nonnegative_int(now, "now")
    end = _strict_nonnegative_int(end, "end")
    max_rival_quantity = _strict_positive_int(max_rival_quantity, "max_rival_quantity")
    if max_rival_quantity > MAX_RIVAL_QUANTITY:
        raise UnsupportedBridgeEvidence(
            f"max_rival_quantity exceeds sale-horizon bound {MAX_RIVAL_QUANTITY}"
        )
    if end < now or end - now >= MAX_TIMING_TURNS:
        raise UnsupportedBridgeEvidence("timing window must span 1..16 integer turns")

    rows, report_start, report_end = _validate_report(pressure_report)
    if now < report_start or end > report_end:
        raise UnsupportedBridgeEvidence("timing window escapes pressure-report custody")

    scenarios: list[dict[str, Any]] = []
    products: list[dict[str, Any]] = []
    for row in rows:
        product = str(row["product"])
        standing = _strict_nonnegative_int(
            row["visible_rival_standing_yield"], "visible_rival_standing_yield"
        )
        bound = min(standing, max_rival_quantity)
        if bound <= 0:
            continue
        product_count = 0
        for quantity in range(1, bound + 1):
            for step in range(now, end + 1):
                for alignment in ALIGNMENTS:
                    scenarios.append(
                        {
                            "product": product,
                            "step": step,
                            "quantity": quantity,
                            "alignment": alignment,
                            "source": "visible_rival_standing_yield",
                            "stress_only": True,
                            "not_prediction": True,
                        }
                    )
                    product_count += 1
        products.append(
            {
                "product": product,
                "visible_rival_standing_yield": standing,
                "tested_rival_quantity_max": bound,
                "partial_quantities_tested": bound,
                "scenario_count": product_count,
                "incremental_target_sell_units": _strict_nonnegative_int(
                    row["incremental_target_sell_units"],
                    "incremental_target_sell_units",
                ),
                "known_current_shop_absorption": _strict_nonnegative_int(
                    row["known_current_shop_absorption"],
                    "known_current_shop_absorption",
                ),
                "public_pressure_units": _strict_nonnegative_int(
                    row["public_pressure_units"], "public_pressure_units"
                ),
            }
        )

    return {
        "schema": BRIDGE_SCHEMA,
        "research_only": True,
        "decision_authority": False,
        "runtime_mutation_authority": False,
        "stress_not_prediction": True,
        "now": now,
        "end": end,
        "alignments": list(ALIGNMENTS),
        "products": products,
        "scenarios": scenarios,
        "scenario_count": len(scenarios),
        "upstream": {
            "schema": pressure_report.get("schema"),
            "incumbent": deepcopy(pressure_report.get("incumbent")),
            "target": deepcopy(pressure_report.get("target")),
            "start": report_start,
            "end": report_end,
        },
        "limitations": [
            "visible standing yield is not rival private inventory",
            "stress quantities are not predictions of harvest or sale",
            "future hidden-seed shop unlocks remain unknown",
            "cross-product and newly produced rival flow require separate stresses",
            "stress timing is confined to the source pressure-report horizon",
            "no action, route, default, or promotion decision is emitted",
        ],
    }


def _validate_envelope_products(
    envelope: Mapping[str, Any], *, now: int, end: int
) -> tuple[dict[str, int], int]:
    """Authenticate scenario bounds against this envelope's carried product evidence.

    The builder emits a complete quantity x step x alignment cross product for
    every retained product. The compiler must not accept a scenario packet that
    silently exceeds, substitutes, or drops that carried public-evidence bound.
    """
    if envelope.get("alignments") != list(ALIGNMENTS):
        raise UnsupportedBridgeEvidence("bridge alignment metadata is invalid")
    products = envelope.get("products")
    if not isinstance(products, list):
        raise UnsupportedBridgeEvidence("bridge products must be a list")

    bounds: dict[str, int] = {}
    expected_total = 0
    turns = end - now + 1
    for row in products:
        if not isinstance(row, Mapping):
            raise UnsupportedBridgeEvidence("bridge product row must be a mapping")
        product = row.get("product")
        if not isinstance(product, str) or product not in PRODUCTS:
            raise UnsupportedBridgeEvidence("bridge product must be supported")
        if product in bounds:
            raise UnsupportedBridgeEvidence("duplicate bridge product evidence")

        standing = _strict_nonnegative_int(
            row.get("visible_rival_standing_yield"),
            "bridge visible_rival_standing_yield",
        )
        bound = _strict_positive_int(
            row.get("tested_rival_quantity_max"),
            "tested_rival_quantity_max",
        )
        partial = _strict_nonnegative_int(
            row.get("partial_quantities_tested"),
            "partial_quantities_tested",
        )
        product_count = _strict_nonnegative_int(
            row.get("scenario_count"), "product scenario_count"
        )
        added = _strict_nonnegative_int(
            row.get("incremental_target_sell_units"),
            "bridge incremental_target_sell_units",
        )
        absorption = _strict_nonnegative_int(
            row.get("known_current_shop_absorption"),
            "bridge known_current_shop_absorption",
        )
        pressure = _strict_nonnegative_int(
            row.get("public_pressure_units"), "bridge public_pressure_units"
        )

        if bound > MAX_RIVAL_QUANTITY or bound > standing:
            raise UnsupportedBridgeEvidence("bridge product quantity bound exceeds evidence")
        if partial != bound:
            raise UnsupportedBridgeEvidence("partial quantity metadata does not match bound")
        if pressure != max(0, added + standing - absorption):
            raise UnsupportedBridgeEvidence("bridge product pressure algebra drift")
        expected_product_count = bound * turns * len(ALIGNMENTS)
        if product_count != expected_product_count:
            raise UnsupportedBridgeEvidence("bridge product scenario_count is inconsistent")

        bounds[product] = bound
        expected_total += expected_product_count
    return bounds, expected_total


def sale_horizon_scenarios(envelope: Mapping[str, Any]) -> list[tuple[str, tuple[tuple[int, int], ...], str]]:
    """Compile this bridge packet into the existing sale-horizon scenario ABI.

    The existing scorer consumes ``(name, rival_schedule, alignment)`` tuples,
    with ``rival_schedule`` represented as ``((step, quantity), ...)``. This
    adapter preserves the stress-only envelope exactly and emits no policy bit.
    Product identity stays in the deterministic scenario name so callers score
    only against the matching item-specific lot.
    """
    if not isinstance(envelope, Mapping) or envelope.get("schema") != BRIDGE_SCHEMA:
        raise UnsupportedBridgeEvidence("unexpected bridge-envelope schema")
    if envelope.get("research_only") is not True:
        raise UnsupportedBridgeEvidence("bridge envelope must remain research-only")
    if envelope.get("decision_authority") is not False:
        raise UnsupportedBridgeEvidence("bridge envelope must have no decision authority")
    if envelope.get("runtime_mutation_authority") is not False:
        raise UnsupportedBridgeEvidence("bridge envelope must have no runtime authority")
    if envelope.get("stress_not_prediction") is not True:
        raise UnsupportedBridgeEvidence("bridge envelope must remain stress-only")

    now = _strict_nonnegative_int(envelope.get("now"), "envelope now")
    end = _strict_nonnegative_int(envelope.get("end"), "envelope end")
    if end < now or end - now >= MAX_TIMING_TURNS:
        raise UnsupportedBridgeEvidence("envelope timing window is invalid")
    upstream = envelope.get("upstream")
    if not isinstance(upstream, Mapping) or upstream.get("schema") != REPORT_SCHEMA:
        raise UnsupportedBridgeEvidence("bridge upstream custody is invalid")
    upstream_start = _strict_nonnegative_int(upstream.get("start"), "upstream start")
    upstream_end = _strict_nonnegative_int(upstream.get("end"), "upstream end")
    if upstream_end < upstream_start or now < upstream_start or end > upstream_end:
        raise UnsupportedBridgeEvidence("bridge timing escapes upstream custody")

    product_bounds, expected_scenario_count = _validate_envelope_products(
        envelope, now=now, end=end
    )
    scenarios = envelope.get("scenarios")
    if not isinstance(scenarios, list):
        raise UnsupportedBridgeEvidence("bridge scenarios must be a list")
    scenario_count = _strict_nonnegative_int(
        envelope.get("scenario_count"), "scenario_count"
    )
    if scenario_count != expected_scenario_count:
        raise UnsupportedBridgeEvidence("scenario_count does not match product evidence")

    compiled: list[tuple[str, tuple[tuple[int, int], ...], str]] = []
    seen: set[tuple[str, int, int, str]] = set()
    for row in scenarios:
        if not isinstance(row, Mapping):
            raise UnsupportedBridgeEvidence("bridge scenario must be a mapping")
        product = row.get("product")
        if not isinstance(product, str) or product not in PRODUCTS:
            raise UnsupportedBridgeEvidence("bridge scenario product must be supported")
        if product not in product_bounds:
            raise UnsupportedBridgeEvidence("bridge scenario lacks product evidence")
        step = _strict_nonnegative_int(row.get("step"), "scenario step")
        if step < now or step > end:
            raise UnsupportedBridgeEvidence("scenario step escapes envelope timing")
        quantity = _strict_positive_int(row.get("quantity"), "scenario quantity")
        if quantity > product_bounds[product]:
            raise UnsupportedBridgeEvidence("scenario quantity exceeds carried product evidence")
        alignment = row.get("alignment")
        if alignment not in ALIGNMENTS:
            raise UnsupportedBridgeEvidence("unsupported scenario alignment")
        if row.get("source") != "visible_rival_standing_yield":
            raise UnsupportedBridgeEvidence("unexpected scenario evidence source")
        if row.get("stress_only") is not True or row.get("not_prediction") is not True:
            raise UnsupportedBridgeEvidence("scenario over-claims predictive authority")
        key = (product, step, quantity, str(alignment))
        if key in seen:
            raise UnsupportedBridgeEvidence("duplicate bridge scenario")
        seen.add(key)
        name = f"public_partial_{product}_{step}_{quantity}_{alignment}"
        compiled.append((name, ((step, quantity),), str(alignment)))
    if len(compiled) != scenario_count:
        raise UnsupportedBridgeEvidence("scenario_count does not match compiled envelope")
    return compiled
