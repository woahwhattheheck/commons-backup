# SPDX-License-Identifier: Apache-2.0
"""Verify the exact S1 donor and route port through its real helper functions.

This is a component test, NOT an official-engine or full-package test. It uses
real _farm/_targets/_consider_hire/wrap/_hand_command code, but fixture updates
apply emitted moves and collections directly. It never runs apply_v3/apply_v4.
Usage: python verify_s1_donor_route.py PATH_TO_EXACT_f14_S1_SOURCE
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import types
import unittest

import apply_s1_route as port

TARGETS = ((4, 3), (2, 4), (2, 5))
STARTS = ((4, 4), (5, 4), (4, 5), (5, 5))
CONFIG = {'episodeSteps': 720, 'turnsPerDay': 24, 'boardSize': 10,
          'shedCapacity': 100, 'maxMarketOrdersPerTurn': 10, 'farmHandCostMult': 1}
_SOURCE = ''


def blob_id(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def helper(patched):
    source = port.port_source(_SOURCE) if patched else _SOURCE
    module = types.ModuleType('_s1_route_component_' + str(patched))
    exec(compile(source, '<exact-s1-route-component>', 'exec'), module.__dict__)
    return module


def observation(player=0):
    tiles = [[{'kind': 'EMPTY'} for _ in range(10)] for _ in range(10)]
    for x, y in TARGETS:
        tiles[y][x] = {'kind': 'PASTURE', 'animal': 'COW', 'fertilizer_available': True}
    farm = {'farmer': [4, 4], 'hands': [], 'tiles': tiles,
            'hires_today': 0, 'money': 10000.0}
    return {'step': 4 * 24 + 17, 'player': player,
            'farms': [copy.deepcopy(farm), copy.deepcopy(farm)],
            'private': {'shed': {}, 'inventories': [{}]},
            'market': {'prices': {'FERTILIZER': 100}}}


def parent_action():
    return {'farmer': ['PASS'], 'hands': [], 'market': []}


def tape():
    return [parent_action() for _ in range(719)]


class DonorRouteTests(unittest.TestCase):
    def test_exact_donor_and_only_two_changed_functions(self):
        self.assertEqual(blob_id(_SOURCE.encode()), port.DONOR_BLOB)
        expected = _SOURCE.replace(port.OLD_COUNT, port.NEW_COUNT, 1)
        expected = expected.replace(port.OLD_COMMAND, port.NEW_COMMAND, 1)
        self.assertEqual(port.port_source(_SOURCE), expected)
        self.assertEqual(port.port_source(expected), expected)

    def test_real_target_filter_and_admission_witness(self):
        for player in (0, 1):
            original, changed = helper(False), helper(True)
            obs = observation(player)
            before = copy.deepcopy(obs)
            action = parent_action()
            points = original._targets(obs['farms'][player])
            self.assertEqual(set(points), set(TARGETS))
            self.assertEqual([original._reachable_count(s, points, 6) for s in STARTS],
                             [2, 1, 1, 1])
            self.assertEqual([changed._reachable_count(s, points, 6) for s in STARTS],
                             [2, 2, 2, 2])
            self.assertIs(original._consider_hire(obs, action, original._Day(4), tape(), CONFIG), action)
            state = changed._Day(4)
            result = changed._consider_hire(obs, action, state, tape(), CONFIG)
            self.assertEqual(result['market'], [['HIRE']])
            self.assertEqual(result['farmer'], action['farmer'])
            self.assertEqual(result['hands'], action['hands'])
            self.assertEqual(state.pending, 0)
            self.assertEqual(obs, before)
            self.assertEqual(action, parent_action())

    def test_real_wrapper_hides_hand_and_collects_two_both_seats_all_spawns(self):
        movement = {'EAST': (1, 0), 'WEST': (-1, 0), 'NORTH': (0, -1), 'SOUTH': (0, 1)}
        for player in (0, 1):
            for start in STARTS:
                changed = helper(True)
                obs = observation(player)
                seen = []
                def parent(view, configuration):
                    seen.append((len(view['farms'][player]['hands']),
                                 len(view['private']['inventories'])))
                    return parent_action()
                agent = changed.wrap(parent, tape_of=lambda _obs: tape())
                self.assertEqual(agent(obs, CONFIG)['market'], [['HIRE']])
                farm = obs['farms'][player]
                # Fixture applies successful HIRE and its chosen legal spawn.
                farm['hands'] = [list(start)]
                farm['money'] -= 1
                farm['hires_today'] = 1
                obs['private']['inventories'].append({})
                for step in range(4 * 24 + 18, 5 * 24):
                    obs['step'] = step
                    before = copy.deepcopy(obs)
                    action = agent(obs, CONFIG)
                    self.assertEqual(obs, before)
                    self.assertEqual(action['farmer'], ['PASS'])
                    self.assertEqual(action['market'], [])
                    self.assertEqual(len(action['hands']), 1)
                    command = action['hands'][0]
                    if command == ['COLLECT_FERTILIZER']:
                        x, y = farm['hands'][0]
                        tile = farm['tiles'][y][x]
                        self.assertTrue(tile['fertilizer_available'])
                        tile['fertilizer_available'] = False
                        inv = obs['private']['inventories'][1]
                        inv['FERTILIZER'] = inv.get('FERTILIZER', 0) + 1
                    elif command[0] in movement:
                        dx, dy = movement[command[0]]
                        farm['hands'][0][0] += dx
                        farm['hands'][0][1] += dy
                    else:
                        self.assertEqual(command, ['PASS'])
                self.assertEqual(obs['private']['inventories'][1]['FERTILIZER'], 2)
                self.assertEqual(changed.REPORT['collections'], 2)
                self.assertEqual(changed.REPORT['hires'], 1)
                self.assertEqual(seen, [(0, 1)] * 7)

    def test_existing_cash_capacity_and_parent_obligations_still_veto(self):
        for case in ('cash', 'capacity', 'current_buy', 'future_collect', 'future_pickup'):
            changed = helper(True)
            obs, action, authored = observation(), parent_action(), tape()
            if case == 'cash':
                obs['farms'][0]['money'] = 50
            elif case == 'capacity':
                obs['private']['shed'] = {'WHEAT': 87}
            elif case == 'current_buy':
                action['market'] = [['BUY_PRODUCT', 'WHEAT', 1]]
            elif case == 'future_collect':
                authored[114]['farmer'] = ['COLLECT_FERTILIZER']
            else:
                authored[114]['farmer'] = ['PICKUP', 'WHEAT', 1]
            before = copy.deepcopy((obs, action, authored))
            self.assertIs(changed._consider_hire(obs, action, changed._Day(4), authored, CONFIG), action)
            self.assertEqual((obs, action, authored), before)

    def test_nonstandard_config_is_exact_parent_identity(self):
        changed = helper(True)
        action = parent_action()
        for value in (None, True, 720.0, 719):
            config = dict(CONFIG, episodeSteps=value)
            agent = changed.wrap(lambda _obs, _config: action, tape_of=lambda _obs: tape())
            self.assertIs(agent(observation(), config), action)


def main(argv=None):
    global _SOURCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args(argv)
    raw = args.source.read_bytes()
    if blob_id(raw) != port.DONOR_BLOB:
        parser.error('source is not exact audited f14 donor; do not execute a replacement silently')
    _SOURCE = raw.decode('utf-8')
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(DonorRouteTests))
    if not result.wasSuccessful():
        return 1
    post = port.port_source(_SOURCE).encode()
    print(json.dumps({'donor_blob': blob_id(raw), 'postimage_blob': blob_id(post),
                      'postimage_sha256': hashlib.sha256(post).hexdigest(),
                      'postimage_bytes': len(post), 'tests': result.testsRun,
                      'scope': 'real S1 helper; fixture transitions; not official engine'}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
