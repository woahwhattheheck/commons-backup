"""Read-only diagnostics for projected shop-demand equivalence.

This does not choose routes or prices. It checks whether a town-only projection
retains the product dimensions used by the caller's fixed cash-flow orders.
It never treats equal demand as equal public observations or adaptive policies.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence


def _field(obj: Any, name: str) -> Any:
    return obj[name] if isinstance(obj, Mapping) else getattr(obj, name)


def cash_products(offers: Sequence[Any], rival_orders: Mapping[int, Sequence] | None,
                  product_order: Sequence[str]) -> tuple[str, ...]:
    """Conservative product closure of nonzero fixed own AND rival cash trades.

    Own fixed-cost rows are already priced by the upstream offer and do not
    introduce a new town-demand dimension. Rival order quantities are declared
    scenario inputs, never inferred from private data. Zero quantities do not
    affect receipts. This does not validate physical execution or funding.
    """
    needed: set[str] = set()
    valid = set(product_order)
    for own in (True, False):
        rows = ([row['order'] for offer in offers for row in _field(offer, 'orders')]
                if own else [order for queue in (rival_orders or {}).values() for order in queue])
        for order in rows:
            if not isinstance(order, (list, tuple)) or not order:
                raise ValueError('Malformed fixed-flow order')
            if order[0] not in ('SELL', 'BUY_PRODUCT'):
                continue
            if len(order) != 3 or order[1] not in valid:
                raise ValueError('Unknown cash-trade product')
            quantity = order[2]
            if type(quantity) is not int or quantity < 0:
                raise ValueError('Cash-trade quantity must be a nonnegative integer')
            if quantity:
                needed.add(order[1])
    return tuple(p for p in product_order if p in needed)


def inspect_cash_projection(family: Any, rules: Any, offers: Sequence[Any], *,
                            rival_orders: Mapping[int, Sequence] | None = None) -> dict:
    """Classify a supplied AMBER family without changing its grouping.

    A true result is only a sufficient separability condition for the pinned
    fixed-quantity ROUTE-FLOW model, whose price function is product-local.
    It is NOT an assertion about adaptive controllers, actual fills, operating
    cash, entire market observations or hypothetical scenario probabilities.
    """
    relevant = cash_products(offers, rival_orders, rules.products)
    classes: dict[tuple[int, ...], list[str]] = defaultdict(list)
    for name, _ in rules.shops:
        classes[rules.signature(name, relevant)].append(name)
    split = []
    for group in family.groups:
        members: dict[tuple[int, ...], list[str]] = defaultdict(list)
        for name in group.shop_names:
            members[rules.signature(name, relevant)].append(name)
        if len(members) > 1:
            split.append({
                'projected_signature': list(group.per_shop_tick),
                'projected_members': list(group.shop_names),
                'cash_distinct_subgroups': [
                    {'signature': list(sig), 'members': names}
                    for sig, names in sorted(members.items())],
            })
    future_count = len(family.unlock_after_steps)
    return {
        'schema': 'town-demand.cash-projection-audit.v1',
        'scope': 'sufficient_fixed_quantity_flow_cash_dimension_check_only',
        'projected_products': list(family.products),
        'cash_relevant_products': list(relevant),
        'omitted_cash_products': [p for p in relevant if p not in family.products],
        'future_draws': future_count,
        'projected_signature_sequences': family.total_scenarios,
        'cash_signature_classes': len(classes),
        'cash_signature_sequences': len(classes) ** future_count,
        'sufficient_for_fixed_flow_cash': not split or future_count == 0,
        'split_groups': split,
        'public_observations_interchangeable': False,
        'physical_feasibility_established': False,
        'probabilities': None,
    }
