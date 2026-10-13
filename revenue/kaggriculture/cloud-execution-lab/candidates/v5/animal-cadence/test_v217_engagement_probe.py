import json
from pathlib import Path
import unittest

import v217_engagement_probe as probe

MOVES = "_V217_MOVES={'EAST':(1,0),'WEST':(-1,0),'NORTH':(0,-1),'SOUTH':(0,1)}\n"
SYNTH = (MOVES + "\n"
         "def _v217_farmer(tape, step):\n    return list(tape[step].get('farmer') or ['PASS'])\n\n"
         "def _v217_plan(view, st, step, action, pending):\n"
         "    tape = _POLICY.tapes[st['plan']]\n"
         "    end = min(step + 24 - step % 24, 719)\n"
         "    for planned in tape[step:end]:\n"
         "        for cmd in [planned.get('farmer') or []] + list(planned.get('hands') or []):\n"
         "            if cmd and cmd[0] == 'FEED':\n"
         "                return None\n"
         "    return 'OLD'\n\n"
         "def agent(observation, configuration=None):\n    return {}\n")
HERE = Path(__file__).resolve().parent


def loaded_module():
    source = probe.instrument_router(SYNTH.encode(), expected_sha=None)
    ns = {}
    exec(compile(source, '<instrumented>', 'exec'), ns)

    class Policy:
        pass

    policy = Policy()
    policy.players = {}
    policy.tapes = []
    ns['_POLICY'] = policy
    ns['projected_shed'] = lambda action, view: {'WHEAT': 10}
    return ns, policy


class View:
    def __init__(self, positions, tiles, wheat=1):
        self.positions = positions
        self.tiles = tiles
        self._wheat = wheat

    def inventory(self, actor):
        return {'WHEAT': self._wheat}

    def beside_shed(self, pos):
        return True


def tape_with_future_feed():
    # step 40 is hour16, so the planner sees steps 40..47.
    tape = [{'farmer': ['PASS'], 'hands': [['PASS']], 'market': []} for _ in range(719)]
    tape[42] = {'farmer': ['PASS'], 'hands': [['FEED']], 'market': []}
    return tape


class ProbeTests(unittest.TestCase):
    def test_different_target_future_feed_is_counted_but_veto_still_returns_none(self):
        ns, policy = loaded_module()
        tiles = [[None for _ in range(5)] for _ in range(5)]
        tiles[1][1] = {'animal': 'SHEEP', 'fed_today': False, 'consecutive_unfed': 1}
        tiles[3][3] = {'animal': 'COW', 'fed_today': False, 'consecutive_unfed': 1}
        policy.tapes = [tape_with_future_feed()]
        view = View([[2, 2], [3, 3]], tiles)
        action = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
        result = ns['_v217_plan'](view, {'plan': 0}, 40, action, [])
        self.assertIsNone(result)
        report = ns['_V217_PROBE_REPORT']
        self.assertEqual(report['global_feed_veto'], 1)
        self.assertEqual(report['coverage_certified'], 1)
        self.assertEqual(report['counterfactual_plan'], 1)
        self.assertEqual(report['events'][0]['target'], [1, 1])
        self.assertIn([3, 3], report['events'][0]['feed_targets'])

    def test_same_target_future_feed_does_not_claim_counterfactual(self):
        ns, policy = loaded_module()
        tiles = [[None for _ in range(5)] for _ in range(5)]
        tiles[1][1] = {'animal': 'SHEEP', 'fed_today': False, 'consecutive_unfed': 1}
        policy.tapes = [tape_with_future_feed()]
        view = View([[2, 2], [1, 1]], tiles)
        action = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
        self.assertIsNone(ns['_v217_plan'](view, {'plan': 0}, 40, action, []))
        report = ns['_V217_PROBE_REPORT']
        self.assertEqual(report['coverage_certified'], 1)
        self.assertEqual(report['counterfactual_plan'], 0)

    def test_locked_rescue_path_fails_closed(self):
        ns, policy = loaded_module()
        tiles = [[None for _ in range(5)] for _ in range(5)]
        tiles[2][0] = {'animal': 'SHEEP', 'fed_today': False, 'consecutive_unfed': 1}
        tiles[2][1] = 'LOCKED'
        tiles[3][3] = {'animal': 'COW', 'fed_today': False, 'consecutive_unfed': 1}
        policy.tapes = [tape_with_future_feed()]
        view = View([[2, 2], [3, 3]], tiles)
        action = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
        self.assertIsNone(ns['_v217_plan'](view, {'plan': 0}, 40, action, []))
        report = ns['_V217_PROBE_REPORT']
        self.assertEqual(report['coverage_certified'], 1)
        self.assertEqual(report['counterfactual_plan'], 0)

    def test_weed_rescue_path_fails_closed(self):
        ns, policy = loaded_module()
        tiles = [[None for _ in range(5)] for _ in range(5)]
        tiles[2][0] = {'animal': 'SHEEP', 'fed_today': False, 'consecutive_unfed': 1}
        tiles[2][1] = {'kind': 'WEED'}
        tiles[3][3] = {'animal': 'COW', 'fed_today': False, 'consecutive_unfed': 1}
        policy.tapes = [tape_with_future_feed()]
        view = View([[2, 2], [3, 3]], tiles)
        action = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
        self.assertIsNone(ns['_v217_plan'](view, {'plan': 0}, 40, action, []))
        report = ns['_V217_PROBE_REPORT']
        self.assertEqual(report['coverage_certified'], 1)
        self.assertEqual(report['counterfactual_plan'], 0)

    def test_malformed_starvation_state_fails_closed_across_all_own_animals(self):
        for strikes in (True, 1.0, -1):
            with self.subTest(strikes=strikes):
                ns, policy = loaded_module()
                tiles = [[None for _ in range(5)] for _ in range(5)]
                tiles[1][1] = {'animal': 'SHEEP', 'fed_today': False, 'consecutive_unfed': 1}
                tiles[3][3] = {'animal': 'COW', 'fed_today': False, 'consecutive_unfed': 1}
                tiles[4][4] = {'animal': 'GOOSE', 'fed_today': False,
                               'consecutive_unfed': strikes}
                policy.tapes = [tape_with_future_feed()]
                view = View([[2, 2], [3, 3]], tiles)
                action = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
                self.assertIsNone(ns['_v217_plan'](view, {'plan': 0}, 40, action, []))
                report = ns['_V217_PROBE_REPORT']
                self.assertEqual(report['coverage_certified'], 1)
                self.assertEqual(report['counterfactual_plan'], 0)

    def test_malformed_farmer_wheat_fails_closed(self):
        for wheat in (True, 1.0, -1):
            with self.subTest(wheat=wheat):
                ns, policy = loaded_module()
                tiles = [[None for _ in range(5)] for _ in range(5)]
                tiles[1][1] = {'animal': 'SHEEP', 'fed_today': False, 'consecutive_unfed': 1}
                tiles[3][3] = {'animal': 'COW', 'fed_today': False, 'consecutive_unfed': 1}
                policy.tapes = [tape_with_future_feed()]
                view = View([[2, 2], [3, 3]], tiles, wheat=wheat)
                action = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
                self.assertIsNone(ns['_v217_plan'](view, {'plan': 0}, 40, action, []))
                report = ns['_V217_PROBE_REPORT']
                self.assertEqual(report['coverage_certified'], 1)
                self.assertEqual(report['counterfactual_plan'], 0)

    def test_malformed_future_wheat_reservation_fails_closed(self):
        for qty in (True, 1.0, -1, '1'):
            with self.subTest(qty=qty):
                ns, policy = loaded_module()
                tiles = [[None for _ in range(5)] for _ in range(5)]
                tiles[1][1] = {'animal': 'SHEEP', 'fed_today': False, 'consecutive_unfed': 1}
                tiles[3][3] = {'animal': 'COW', 'fed_today': False, 'consecutive_unfed': 1}
                tape = tape_with_future_feed()
                tape[41]['hands'] = [['PICKUP', 'WHEAT', qty]]
                policy.tapes = [tape]
                view = View([[2, 2], [3, 3]], tiles)
                action = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
                self.assertIsNone(ns['_v217_plan'](view, {'plan': 0}, 40, action, []))
                report = ns['_V217_PROBE_REPORT']
                self.assertEqual(report['coverage_certified'], 1)
                self.assertEqual(report['counterfactual_plan'], 0)

    def test_pickup_with_same_turn_wheat_market_fails_closed(self):
        ns, policy = loaded_module()
        tiles = [[None for _ in range(5)] for _ in range(5)]
        tiles[1][1] = {'animal': 'SHEEP', 'fed_today': False, 'consecutive_unfed': 1}
        tiles[3][3] = {'animal': 'COW', 'fed_today': False, 'consecutive_unfed': 1}
        policy.tapes = [tape_with_future_feed()]
        view = View([[2, 2], [3, 3]], tiles, wheat=0)
        action = {'farmer': ['PASS'], 'hands': [['PASS']],
                  'market': [['BUY_PRODUCT', 'WHEAT', 1]]}
        self.assertIsNone(ns['_v217_plan'](view, {'plan': 0}, 40, action, []))
        report = ns['_V217_PROBE_REPORT']
        self.assertEqual(report['coverage_certified'], 1)
        self.assertEqual(report['counterfactual_plan'], 0)

    def test_any_delayed_queue_fails_closed_even_without_feed(self):
        ns, policy = loaded_module()
        tiles = [[None for _ in range(5)] for _ in range(5)]
        tiles[1][1] = {'animal': 'SHEEP', 'fed_today': False, 'consecutive_unfed': 1}
        tiles[3][3] = {'animal': 'COW', 'fed_today': False, 'consecutive_unfed': 1}
        policy.tapes = [tape_with_future_feed()]
        view = View([[2, 2], [3, 3]], tiles)
        action = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
        self.assertIsNone(ns['_v217_plan'](view, {'plan': 0}, 40, action, [['EAST']]))
        report = ns['_V217_PROBE_REPORT']
        self.assertEqual(report['global_feed_veto'], 1)
        self.assertEqual(report['coverage_certified'], 0)
        self.assertEqual(report['counterfactual_plan'], 0)

    def test_non_veto_path_remains_original(self):
        ns, policy = loaded_module()
        policy.tapes = [[{'farmer': ['PASS'], 'hands': [['PASS']], 'market': []} for _ in range(719)]]
        view = View([[2, 2], [3, 3]], [[None for _ in range(5)] for _ in range(5)])
        action = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
        self.assertEqual(ns['_v217_plan'](view, {'plan': 0}, 40, action, []), 'OLD')
        report = ns['_V217_PROBE_REPORT']
        self.assertEqual(report['global_feed_veto'], 0)
        self.assertEqual(report['counterfactual_plan'], 0)

    def test_probe_failure_is_swallowed_and_veto_still_returns_none(self):
        ns, policy = loaded_module()
        policy.tapes = [tape_with_future_feed()]
        ns['_v217_probe_observe'] = lambda *args: (_ for _ in ()).throw(RuntimeError('probe boom'))
        view = View([[2, 2], [3, 3]], [[None for _ in range(5)] for _ in range(5)])
        action = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
        self.assertIsNone(ns['_v217_plan'](view, {'plan': 0}, 40, action, []))

    def test_router_transform_rejects_duplicate_or_missing_seam(self):
        with self.assertRaisesRegex(ValueError, 'moves'):
            probe.instrument_router((SYNTH + MOVES).encode(), expected_sha=None)
        with self.assertRaisesRegex(ValueError, 'moves'):
            probe.instrument_router(SYNTH.replace(MOVES, '').encode(), expected_sha=None)

    def test_evaluator_transform_adds_sidecar_without_replacing_action(self):
        source = b'''import sys\ndef f():\n    if True:\n        if True:\n            if True:\n                send({"kind": "action", "action": action, "call_seconds": seconds,\n                      "call_cpu_seconds": cpu_seconds, **usage()})\n                actions.append(response["action"])\n'''
        out = probe.instrument_evaluator(source, expected_sha=None)
        text = out.decode()
        self.assertIn('"v217_probe": probe', text)
        self.assertIn('actions.append(response["action"])', text)
        compile(out, '<eval>', 'exec')

    def test_archive_bytes_are_deterministic(self):
        files = {'b.py': b'b', 'a.py': b'a'}
        self.assertEqual(probe.archive_bytes(files), probe.archive_bytes(files))

    def test_checked_in_authorities_bind_production_router_evaluator_and_publisher(self):
        manifest_path = HERE.parent / 'selective-carrot' / 'PRODUCTION-V3-PACKAGE-MANIFEST.json'
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest['candidate_archive_sha256'], probe.PRODUCTION_SHA)
        self.assertEqual(manifest['files'][probe.ROUTER], probe.ROUTER_SHA)
        self.assertEqual(len(manifest['files']), probe.PRODUCTION_MEMBERS)

        router_path = HERE.parent.parent / 'v4' / 'donor' / 'overlay' / probe.ROUTER
        router = router_path.read_bytes()
        self.assertEqual(probe.digest(router), probe.ROUTER_SHA)
        compile(probe.instrument_router(router), str(router_path), 'exec')

        evaluator_path = HERE.parents[3] / 'cloud-eval' / 'evaluate.py'
        evaluator = evaluator_path.read_bytes()
        self.assertEqual(probe.digest(evaluator), probe.EVALUATOR_SHA)
        compile(probe.instrument_evaluator(evaluator), str(evaluator_path), 'exec')

        publisher = HERE.parent / 'selective-carrot' / 'publication_custody.py'
        self.assertTrue(publisher.is_file())
        verifier = HERE / 'verify_v217_engagement_probe_exact.py'
        self.assertTrue(verifier.is_file())


if __name__ == '__main__':
    unittest.main()
