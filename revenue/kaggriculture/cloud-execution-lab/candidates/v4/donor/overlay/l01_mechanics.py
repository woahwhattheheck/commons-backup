# SPDX-License-Identifier: Apache-2.0
"""L01 leader mechanisms over the canonical Arlene MAIN tape, as V3 keys.

Lineage: Grok Build #5, PR #11459 (candidates/v3-l01-leader-mechanics on canonical
3b4b; the a055fd56 canonical carries the same MAIN tape 7015cc00acfa4922) -> V3.

Keys (all default off, read through Features, no environment reads):
  l01_land       append ["BUY_LAND"] at tape steps 74 and 98; the 150/265 posts stay
  l01_sheep      rewrite every BUY_ANIMAL COW after step 1 to SHEEP (opening COW 2 kept)
  l01_day0buy    reject the historical engine-invalid SpaTaro product basket fail-closed
  l01_leanplant  convert the last 92 PLANT WHEAT units to PASS (164 -> 72 wheat, 240 -> 148)
  l01_tranche    live: from day 28 and before step 718 ensure SELL WHEAT min(shed,57) and
                 SELL CARROT min(shed,32) and pack every other shed product except FERTILIZER

The four tape keys mutate `controller.R` once, at TitanAgent._initialize (seam
`_v3_l01_install`).  l01_tranche edits the returned queue at TitanAgent._v3_post_final,
after _finish_production, where the L01 lane measured it.  Every flag off is a documented
no-op: routes are not touched (reason `L01_noop:flag_off`) and apply_tranche returns the
same action object.
"""
from __future__ import annotations

from collections import Counter

LAND_STEPS = (74, 98)
LAND_FALLBACK_STEPS = (150, 265)
KEEP_WHEAT_PLANTS = 72  # 164 wheat -> 72; 240-92 = 148 total plants
DAY0_BUY_PRODUCT_ITEMS = frozenset(('WHEAT', 'FERTILIZER'))
DAY0_REJECT_PREFIX = 'L01_noop:day0buy_rejected'
DAY0_BASKET = (
    ('CARROT', 14),
    ('MELON', 20),
    ('MILK', 40),
    ('STRAWBERRY', 8),
    ('TOMATO', 12),
    ('WHEAT', 2),
)
TRANCHE_WHEAT = 57
TRANCHE_CARROT = 32
TRANCHE_DAY_FROM = 28
MAX_ORDERS = 10
FINAL_EXECUTABLE_STEP = 718
MAIN = '7015cc00acfa4922'
NOOP = 'L01_noop:flag_off'
FLAG_KEYS = ('LAND', 'SHEEP', 'DAY0BUY', 'TRANCHE', 'LEANPLANT')
FEATURE_KEYS = {
    'LAND': 'l01_land',
    'SHEEP': 'l01_sheep',
    'DAY0BUY': 'l01_day0buy',
    'TRANCHE': 'l01_tranche',
    'LEANPLANT': 'l01_leanplant',
}

PRODUCTS = (
    'WHEAT', 'CARROT', 'TOMATO', 'STRAWBERRY', 'MELON',
    'EGG', 'MILK', 'WOOL', 'FERTILIZER',
)


def flags_from_features(features):
    """Explicit flag dict from the package Features (never from the environment)."""
    return {flag: bool(getattr(features, key, False)) for flag, key in FEATURE_KEYS.items()}


def _units(row):
    farmer = row.get('farmer') or ['PASS']
    hands = list(row.get('hands') or [])
    return [farmer, *hands]


def _set_unit(row, index, action):
    if index == 0:
        row['farmer'] = action
        return
    hands = row.setdefault('hands', [])
    while len(hands) < index:
        hands.append(['PASS'])
    hands[index - 1] = action


def _has_buy_land(market):
    return any(o and o[0] == 'BUY_LAND' for o in (market or []))


def day0_basket_issues(orders):
    """Return deterministic grammar defects for a static BUY_PRODUCT basket."""
    issues = []
    if not isinstance(orders, (list, tuple)):
        return ((-1, 'orders_not_sequence'),)
    if len(orders) > MAX_ORDERS:
        issues.append((MAX_ORDERS, 'prefix_truncation'))
    for index, order in enumerate(orders[:MAX_ORDERS]):
        if not isinstance(order, (list, tuple)) or len(order) != 3:
            issues.append((index, 'malformed_row'))
            continue
        op, item, quantity = order
        if op != 'BUY_PRODUCT':
            issues.append((index, 'unsupported_op'))
            continue
        if item not in DAY0_BUY_PRODUCT_ITEMS:
            issues.append((index, 'unsupported_product:' + repr(item)))
            continue
        if isinstance(quantity, bool) or type(quantity) is not int or quantity <= 0:
            issues.append((index, 'noncanonical_quantity'))
    return tuple(issues)


def _day0_rejection_reason(issues):
    codes = ','.join(f'{index}:{code}' for index, code in issues)
    return f'{DAY0_REJECT_PREFIX}[{codes}]'


def patch_routes(routes, flags, activations, reasons):
    """Mutate every tape in `routes` in place. Shared step objects convert once."""
    route_on = any(flags.get(k) for k in ('LAND', 'SHEEP', 'DAY0BUY', 'LEANPLANT'))
    if not route_on:
        if not any(flags.values()):
            reasons.append(NOOP)
        return
    day0_wanted = [['BUY_PRODUCT', item, n] for item, n in DAY0_BASKET]
    day0_issues = day0_basket_issues(day0_wanted) if flags.get('DAY0BUY') else ()
    if day0_issues:
        reason = _day0_rejection_reason(day0_issues)
        if reason not in reasons:
            reasons.append(reason)
    for route in list(routes.values()):
        if not route:
            continue
        if flags.get('LAND'):
            for t in LAND_STEPS:
                if t >= len(route):
                    continue
                market = route[t].setdefault('market', [])
                if _has_buy_land(market):
                    continue
                if len(market) < MAX_ORDERS:
                    market.append(['BUY_LAND'])
                    activations['LAND'] += 1
        if flags.get('SHEEP'):
            for t, row in enumerate(route):
                if t <= 1:
                    continue
                for o in (row.get('market') or []):
                    if o and o[0] == 'BUY_ANIMAL' and len(o) > 1 and o[1] == 'COW':
                        o[1] = 'SHEEP'
                        activations['SHEEP'] += 1
        if flags.get('DAY0BUY') and not day0_issues and len(route) > 0:
            market = route[0].setdefault('market', [])
            if market != day0_wanted:
                market[:] = [list(x) for x in day0_wanted]
                activations['DAY0BUY'] += 1
        if flags.get('LEANPLANT'):
            sites = []
            for t, row in enumerate(route):
                for i, act in enumerate(_units(row)):
                    if act and act[0] == 'PLANT' and len(act) > 1 and act[1] == 'WHEAT':
                        sites.append((t, i))
            extra = max(0, len(sites) - KEEP_WHEAT_PLANTS)
            if extra <= 0:
                continue
            for t, i in sites[-extra:]:
                _set_unit(route[t], i, ['PASS'])
                activations['LEANPLANT'] += 1


def apply_tranche(action, obs, flags, activations, shed=None):
    """Live multi-product sale enlargement. Identity when TRANCHE is off."""
    if not flags.get('TRANCHE'):
        return action
    step = obs.get('step')
    if step is None:
        step = int(obs.get('day', 0)) * 24 + int(obs.get('hour', 0))
    step = int(step)
    day = int(obs.get('day', step // 24))
    if day < TRANCHE_DAY_FROM or step >= FINAL_EXECUTABLE_STEP:
        return action
    if shed is None:
        shed = dict((obs.get('private') or {}).get('shed') or {})
    out = action
    market = list(out.get('market') or [])
    market = [list(o) if o else o for o in market]
    changed = False

    def ensure(item, target):
        nonlocal changed
        have = min(max(0, int(shed.get(item, 0) or 0)), int(target))
        if have <= 0:
            return
        for o in market:
            if o and o[0] == 'SELL' and len(o) > 1 and o[1] == item:
                cur = max(0, int(o[2]) if len(o) > 2 else 0)
                if cur < have:
                    o[2] = have
                    activations['TRANCHE'] += 1
                    changed = True
                return
        if len(market) < MAX_ORDERS:
            market.append(['SELL', item, have])
            activations['TRANCHE'] += 1
            changed = True

    ensure('WHEAT', TRANCHE_WHEAT)
    ensure('CARROT', TRANCHE_CARROT)
    for item in PRODUCTS:
        if item in ('WHEAT', 'CARROT', 'FERTILIZER'):
            continue
        q = max(0, int(shed.get(item, 0) or 0))
        if q <= 0:
            continue
        if any(o and o[0] == 'SELL' and len(o) > 1 and o[1] == item for o in market):
            continue
        if len(market) < MAX_ORDERS:
            market.append(['SELL', item, q])
            activations['TRANCHE'] += 1
            changed = True
    if not changed:
        return action
    out = dict(action)
    out['market'] = market
    return out


def install(agent, flags, state=None):
    """Patch the agent's route tapes once. Returns the state record (activations, reasons)."""
    state = state or {'activations': Counter(), 'reasons': []}
    controller = getattr(agent, 'controller', None)
    if controller is None or not getattr(controller, 'R', None):
        state['reasons'].append('L01_noop:no_controller')
        return state
    patch_routes(controller.R, flags, state['activations'], state['reasons'])
    if not any(flags.values()):
        if NOOP not in state['reasons']:
            state['reasons'].append(NOOP)
    return state


def shed_snapshot(agent, obs):
    """The shed the L01 lane read: the consumer's selected post-units snapshot, else the observation."""
    consumer = getattr(agent, 'consumer', None)
    snap = getattr(consumer, 'selected_post_units', None) if consumer is not None else None
    if snap is not None:
        try:
            shed = snap[1].get('shed')
            if shed is not None:
                return dict(shed)
        except (AttributeError, IndexError, TypeError):
            pass
    return dict((obs.get('private') or {}).get('shed') or {})


def plant_counts(route):
    counts = Counter()
    for row in route:
        for act in _units(row):
            if act and act[0] == 'PLANT' and len(act) > 1:
                counts[act[1]] += 1
    return counts


def animal_buys(route):
    counts = Counter()
    events = []
    for t, row in enumerate(route):
        for o in (row.get('market') or []):
            if o and o[0] == 'BUY_ANIMAL' and len(o) > 2:
                counts[o[1]] += int(o[2])
                events.append((t, o[1], int(o[2])))
    return counts, events
