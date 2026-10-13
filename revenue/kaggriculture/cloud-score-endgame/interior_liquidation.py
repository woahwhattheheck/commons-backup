# SPDX-License-Identifier: Apache-2.0
"""Bounded terminal-liquidation stress hypotheses for the existing producer.

This is an explicit research family, not recovered rival inventory or a
calibrated model. It keeps the original finite family and adds interior order
positions. It does not call a controller, engine, optimizer or random sampler.
"""
from copy import deepcopy

from terminal_inputs import _config, fingerprint, stress_scenarios


def interior_liquidation_scenarios(mechanics, observation, configuration):
    """Return at most 32 current-snapshot hypotheses with original IDs intact.

    First preserve the existing stress family, byte-for-JSON including origin.
    Then add a full-shed sale of each product at floor(max_orders / 2). Finally
    add the two high/low interleavings of the existing price-ranked mixed lot.
    Empty slots remain real positions. Exact duplicate shed/queue pairs are
    omitted among additions only; no partial capacity or per-product fiction
    is used. A quantity is a stress assumption, not an observation of the rival.
    """
    cfg = _config(configuration)
    if observation.get('step') != cfg['episodeSteps'] - 2:
        raise ValueError('Terminal liquidation hypotheses require the final decision')
    if len(mechanics.PRODUCTS) != 9 or len(set(mechanics.PRODUCTS)) != 9:
        raise ValueError('This bounded family uses the pinned nine-product rules')
    original = stress_scenarios(mechanics, observation, cfg)
    result = deepcopy(original)
    seen = {fingerprint((s['shed'], s['market'])) for s in result}
    cap, limit = cfg['shedCapacity'], cfg['maxMarketOrdersPerTurn']
    additions = []
    middle = limit // 2
    for item in mechanics.PRODUCTS:
        additions.append({'id': f'interior-all-{item}-slot-{middle}',
                          'shed': {item: cap},
                          'market': [[] for _ in range(middle)] + [['SELL', item, cap]],
                          'origin': 'predeclared-terminal-interior-stress'})
    ranked = sorted(mechanics.PRODUCTS, key=lambda p: (-mechanics.market_price(
        p, observation['market']['inventory'][p], observation['market'].get('params')), p))
    lot = {p: cap // len(ranked) + int(i < cap % len(ranked)) for i, p in enumerate(ranked)}
    interleaved = []
    for i in range((len(ranked) + 1) // 2):
        interleaved.append(ranked[i])
        j = len(ranked) - 1 - i
        if j != i:
            interleaved.append(ranked[j])
    for name, order in [('high-low', interleaved), ('low-high', interleaved[::-1])]:
        additions.append({'id': 'interior-mixed-' + name, 'shed': lot.copy(),
                          'market': [['SELL', p, lot[p]] for p in order[:limit] if lot[p]],
                          'origin': 'predeclared-terminal-interior-stress'})
    for scenario in additions:
        key = fingerprint((scenario['shed'], scenario['market']))
        if key not in seen:
            seen.add(key)
            result.append(scenario)
    if len(result) > 32:
        raise ValueError('Whole family exceeds the existing 32-column interface')
    return result
