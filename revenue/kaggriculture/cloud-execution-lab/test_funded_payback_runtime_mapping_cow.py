# SPDX-License-Identifier: Apache-2.0
"""Allocation/identity contracts for the ECON runtime route adapter."""
from __future__ import annotations

from types import MappingProxyType
import unittest

import funded_payback_runtime


def _row(*market):
    return {'farmer': ['PASS'], 'hands': [], 'market': [list(order) for order in market]}


class _Base:
    def __init__(self):
        self.seconds = 1.0
        self.seen_routes = None

    def __call__(self, mechanics, observation, configuration, routes, proposals):
        self.seen_routes = routes
        return routes


class FundedPaybackAllocationCowTests(unittest.TestCase):
    def admission(self):
        return funded_payback_runtime.make_admission(_Base)()

    def test_clean_plain_dict_and_list_routes_preserve_identity(self):
        first = [_row(('HIRE',)), _row(('SELL', 'WHEAT', 2))]
        second = [_row(('PASS',)), _row(('BUY_SEED', 'CARROT', 3))]
        routes = {'first': first, 'second': second}

        admission = self.admission()
        returned = admission(None, {}, {}, routes, [])

        self.assertIs(returned, routes)
        self.assertIs(admission.seen_routes, routes)
        self.assertIs(returned['first'], first)
        self.assertIs(returned['second'], second)

    def test_first_translation_lazily_clones_mapping_and_changed_route_only(self):
        clean = [_row(('HIRE',)), _row(('SELL', 'WHEAT', 2))]
        dirty = [_row(('PASS',)), _row(('SELL', 'WHEAT', 0), ('HIRE',))]
        routes = {'clean': clean, 'dirty': dirty}

        admission = self.admission()
        returned = admission(None, {}, {}, routes, [])

        self.assertIsNot(returned, routes)
        self.assertIs(returned['clean'], clean)
        self.assertIsNot(returned['dirty'], dirty)
        self.assertIs(returned['dirty'][0], dirty[0])
        self.assertIsNot(returned['dirty'][1], dirty[1])
        self.assertEqual(returned['dirty'][1]['market'], [['PASS'], ['HIRE']])

        returned['dirty'][1]['market'][1].append('mutated')
        self.assertEqual(dirty[1]['market'], [['SELL', 'WHEAT', 0], ['HIRE']])
        self.assertEqual(routes['clean'][0]['market'], [['HIRE']])

    def test_arbitrary_mapping_keeps_historical_plain_dict_contract(self):
        route = [_row(('HIRE',))]
        original = {'main': route}
        routes = MappingProxyType(original)

        returned = self.admission()(None, {}, {}, routes, [])

        self.assertIs(type(returned), dict)
        self.assertIsNot(returned, routes)
        self.assertIs(returned['main'], route)

    def test_non_list_sequence_route_keeps_historical_list_contract(self):
        route = (_row(('HIRE',)), _row(('PASS',)))
        routes = {'tuple': route}

        returned = self.admission()(None, {}, {}, routes, [])

        self.assertIsNot(returned, routes)
        self.assertIs(type(returned['tuple']), list)
        self.assertEqual(returned['tuple'], list(route))


if __name__ == '__main__':
    unittest.main()
