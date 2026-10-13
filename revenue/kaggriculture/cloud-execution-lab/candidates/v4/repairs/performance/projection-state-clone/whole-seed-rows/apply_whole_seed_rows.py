# SPDX-License-Identifier: Apache-2.0
"""Source-only V4 admission for executable whole-row seed chronology.

The current early-capital ranker lets every BUY_SEED row for a crop claim the
same unmet represented seed demand. It also counts the already-executed current
unit stage as future demand after projecting that stage into ``post_private``.

This adapter consumes only the repaired theorem from legacy PR #12114. It does
not revive that V3 branch, mutate the root source, activate COMPOSITION, or
publish a runtime. The existing projection-state-clone authority may run first:
that component edits ``_project_post_unit_private`` only, while this adapter is
pinned to the disjoint rank/order spans below.
"""
from __future__ import annotations

import ast
import hashlib

PRE = {
    "_rank": "4e851011d2d9e909fd0232041fa8c77fe991c630cf55a7ca60476ca67dcbd99e",
    "order_early_capital": "b1751a833a2b1d3d24534581908aec7380f4fd474c26c30c38e617ab7ae78d6b",
}
POST = {
    "_operating_seed_rows": "21573df6c0226828e1adbd8bcc1f89846f69da0a673886a8558782f108982349",
    "_rank": "3f1354acdbd049de2e442a490fac09af6a1bda77a40748b532f4891764a7ac47",
    "order_early_capital": "23c1f538dff014db22f19538cd28595cc1b6e5ee65b067b020e18c4cc81fadcf",
}

HELPER = '''def _operating_seed_rows(active, mechanics, plant_demand, seeds_held):
    """Select an executable whole-row cover for represented seed deficits.

    A market row is indivisible for ordering: once moved ahead of capital, the
    official interpreter attempts its full positive quantity before advancing.
    Therefore a row may claim OPERATING priority only when every requested unit
    fits inside the represented deficit. For each crop, choose the subset of
    positive rows with maximum total quantity not exceeding that deficit;
    lexicographically earliest authored indices break ties. This maximizes exact
    demand coverage without splitting, editing, inventing, or overbuying rows.
    """
    remaining = {}
    rows_by_crop = {}
    for crop, count in plant_demand.items():
        if crop not in mechanics.CROPS:
            continue
        need = max(0, int(count) - int(seeds_held.get(crop, 0)))
        remaining[crop] = need
        rows_by_crop[crop] = []

    for index, order in enumerate(active):
        if (not isinstance(order, list) or len(order) < 3
                or order[0] != 'BUY_SEED'):
            continue
        crop = order[1]
        if crop not in rows_by_crop:
            continue
        quantity = _qty(order)
        if quantity > 0:
            rows_by_crop[crop].append((index, quantity))

    operating = set()
    allocations = []
    for crop in sorted(rows_by_crop):
        need = remaining[crop]
        # total -> lexicographically earliest tuple of row indices producing it.
        choices = {0: ()}
        quantities = {}
        for index, quantity in rows_by_crop[crop]:
            quantities[index] = quantity
            updated = dict(choices)
            for total, indices in choices.items():
                candidate_total = total + quantity
                if candidate_total > need:
                    continue
                candidate = indices + (index,)
                incumbent = updated.get(candidate_total)
                if incumbent is None or candidate < incumbent:
                    updated[candidate_total] = candidate
            choices = updated

        covered = max(choices)
        selected_indices = choices[covered]
        for index in selected_indices:
            quantity = quantities[index]
            operating.add(index)
            allocations.append({
                'index': index,
                'crop': crop,
                'requested': quantity,
                'allocated': quantity,
            })
        remaining[crop] = need - covered

    allocations.sort(key=lambda row: row['index'])
    return operating, allocations, remaining
'''

RANK = '''def _rank(order, index, funding, seed_operating, mechanics, remaining, day):
    if not order:
        return REST
    op = order[0]
    if op == 'SELL':
        return FUNDING if index in funding else REST
    if op == 'HIRE':
        return OPERATING
    if op == 'BUY_SEED' and len(order) > 2 and order[1] in mechanics.CROPS:
        return OPERATING if index in seed_operating else REST
    if _capital_admitted(order, mechanics, remaining, day):
        return CAPITAL
    return REST
'''

ORDER = '''def order_early_capital(mechanics, observation, configuration, selected, route, decisions=()):
    """Reorder only the executable prefix of the current market tape.

    Purchases are never dropped or invented. Farmer/hands, market length, the
    multiset of active orders, and every capped suffix row remain unchanged.
    """
    report = {'changed': False, 'reason': 'init', 'moved': 0, 'reserved': 0,
              'reduced': [], 'revision': 'v6-whole-seed-rows'}
    if not isinstance(selected, dict):
        report['reason'] = 'no_action'
        return selected, report
    raw_market = selected.get('market')
    if raw_market is None:
        raw_market = []
    if not isinstance(raw_market, list):
        report['reason'] = 'unsupported_market'
        return selected, report
    market = list(raw_market)
    if not market:
        report['reason'] = 'empty_market'
        return selected, report
    limit = _market_limit(configuration)
    if limit is None:
        report['reason'] = 'unsupported_market_limit'
        return selected, report
    active_count = min(limit, len(market))
    active = market[:active_count]
    suffix = market[active_count:]
    report.update(active_limit=limit, active_rows=active_count,
                  suffix_rows=len(suffix))

    try:
        now = int(observation.get('step') if observation.get('step') is not None
                  else int(observation['day']) * _turns_per_day(configuration)
                  + int(observation['hour']))
        last = _last_step(configuration)
        turns_per_day = _turns_per_day(configuration)
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
        report['reason'] = 'unsupported_time'
        return selected, report
    if turns_per_day <= 0:
        report['reason'] = 'unsupported_time'
        return selected, report
    if now >= last:
        report['reason'] = 'terminal_window'
        return selected, report
    if not all(_active_order_supported(order, mechanics) for order in active):
        report['reason'] = 'unsupported_active_order'
        return selected, report

    post_private = _project_post_unit_private(
        mechanics, observation, configuration, selected, now)
    if post_private is None:
        report['reason'] = 'post_unit_projection_failed'
        return selected, report
    funding, funding_units = _certified_funding(active, mechanics, post_private)
    report.update(
        certified_funding_rows=sorted(funding),
        certified_funding_units=[
            {'index': index, 'item': active[index][1], 'units': funding_units[index]}
            for index in sorted(funding)
        ],
    )

    day = now // turns_per_day
    remaining = _remaining_days(now, configuration)
    seeds_held = dict(post_private.get('seeds') or {})
    try:
        horizon = _horizon_end(now, configuration, decisions)
        # The current unit stage already ran in post_private; only future route
        # PLANT actions may still consume the post-unit seed balance.
        plants = _plant_demand(None, route, now, horizon)
        seed_operating, seed_allocations, unmet_seed_demand = _operating_seed_rows(
            active, mechanics, plants, seeds_held)
        ranks = [
            _rank(order, index, funding, seed_operating, mechanics, remaining, day)
            for index, order in enumerate(active)
        ]
    except (AttributeError, IndexError, KeyError, OverflowError, TypeError, ValueError):
        report['reason'] = 'ranking_failed'
        return selected, report
    report.update(
        operating_seed_rows=sorted(seed_operating),
        seed_allocations=seed_allocations,
        unmet_seed_demand={
            crop: count for crop, count in sorted(unmet_seed_demand.items()) if count > 0
        },
    )
    if CAPITAL not in ranks:
        report['reason'] = 'no_admitted_capital'
        return selected, report

    indexed = list(enumerate(active))
    ordered = sorted(indexed, key=lambda item: (ranks[item[0]], item[0]))
    reordered_active = [order for _, order in ordered]
    reordered = reordered_active + suffix
    moved = sum(1 for old, new in zip(active, reordered_active) if old != new)
    if reordered_active == active:
        report.update(reason='already_ordered', moved=0, horizon_end=horizon,
                      remaining_days=remaining)
        return selected, report
    result = deepcopy(selected)
    result['market'] = deepcopy(reordered)
    report.update(changed=True, reason='ordered', moved=moved, reserved=0,
                  reduced=[], horizon_end=horizon, remaining_days=remaining)
    return result, report
'''


def _spans(source: str) -> dict[str, tuple[int, int, str]]:
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    found: dict[str, tuple[int, int, str]] = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in found:
                raise ValueError("duplicate top-level function: " + node.name)
            start, end = offsets[node.lineno - 1], offsets[node.end_lineno]
            found[node.name] = (start, end, source[start:end])
    return found


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply(source: str) -> str:
    """Materialize the whole-row theorem or fail before returning any postimage."""
    if not isinstance(source, str):
        raise TypeError("source must be decoded UTF-8 text")
    spans = _spans(source)
    required = {"_capital_admitted", "_rank", "order_early_capital"}
    if not required.issubset(spans):
        raise ValueError("missing early-capital source boundary")

    if "_operating_seed_rows" in spans:
        observed = {name: _sha(spans[name][2]) for name in POST}
        if observed != POST:
            raise ValueError("partially applied or changed whole-seed-row source")
        return source

    observed = {name: _sha(spans[name][2]) for name in PRE}
    if observed != PRE:
        raise ValueError("early-capital source changed; rebase explicitly: " + repr(observed))

    edits = [
        (spans["order_early_capital"][0], spans["order_early_capital"][1], ORDER),
        (spans["_rank"][0], spans["_rank"][1], RANK),
        (spans["_capital_admitted"][0], spans["_capital_admitted"][0], HELPER + "\n\n"),
    ]
    result = source
    for start, end, replacement in sorted(edits, reverse=True):
        result = result[:start] + replacement + result[end:]
    compile(result, "v4_whole_seed_rows", "exec")

    post = _spans(result)
    verified = {name: _sha(post[name][2]) for name in POST}
    if verified != POST:
        raise ValueError("unexpected whole-seed-row postimage: " + repr(verified))
    return result
