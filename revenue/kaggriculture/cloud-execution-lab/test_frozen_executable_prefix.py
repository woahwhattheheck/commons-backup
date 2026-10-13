# SPDX-License-Identifier: Apache-2.0
"""Predecessor-killing contracts for frozen seller market-prefix custody."""

import frozen_selected as frozen


def test_materialize_preserves_inert_suffix_bytes():
    suffix = ['SELL', 'MILK', 99]
    result = frozen.materialize_sales(
        [['SELL', 'MILK', 1], suffix],
        {'MILK': 4}, {'MILK': 4}, {'MILK'}, 1,
    )
    assert result == [['SELL', 'MILK', 1], suffix]


def test_zero_cap_uses_engine_effective_slot_zero():
    result = frozen.materialize_sales(
        [], {'MILK': 2}, {'MILK': 2}, {'MILK'}, 0,
    )
    assert result == [['SELL', 'MILK', 2]]


def test_horizon_ignores_suffix_sell_when_prefix_is_full():
    route = [{'market': []} for _ in range(10)]
    route[9]['market'] = [['HIRE'], ['SELL', 'MILK', 1]]
    original = frozen.absorption
    frozen.absorption = lambda item, step, shops, config: True
    try:
        end, report = frozen.event_aware_horizon(
            0, 20, route, {'MILK'}, [], {'maxMarketOrdersPerTurn': 1},
        )
    finally:
        frozen.absorption = original
    assert end == report['baseline_end']
    assert report['service_dates'] == {}


def test_represented_market_uses_engine_floor_and_ignores_suffix():
    farm = {'hands': []}
    private = {'shed': {'WHEAT': 0}, 'inventories': []}
    frozen.apply_represented_market(
        farm, private,
        [['BUY_PRODUCT', 'WHEAT', 1], ['BUY_PRODUCT', 'WHEAT', 3]],
        10, 0,
    )
    assert private['shed']['WHEAT'] == 1


def test_represented_market_non_list_queue_is_inert():
    farm = {'hands': []}
    private = {'shed': {'WHEAT': 2}, 'inventories': []}
    frozen.apply_represented_market(farm, private, 7, 10, 3)
    assert private['shed']['WHEAT'] == 2
