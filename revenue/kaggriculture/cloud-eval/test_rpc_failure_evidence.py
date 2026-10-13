# SPDX-License-Identifier: Apache-2.0
"""Real worker/pipe checks for failed RPC evidence; no scored game or engine install.

Point TITAN_EVALUATOR_PATH at an exact alternate evaluator for a differential.
The small engine below is only a result-plumbing fixture, not a game simulator.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import textwrap
import time
import unittest
from unittest.mock import patch

TARGET = Path(os.environ.get('TITAN_EVALUATOR_PATH', Path(__file__).with_name('evaluate.py'))).resolve()
spec = importlib.util.spec_from_file_location('rpc_evidence_evaluator', TARGET)
E = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = E
spec.loader.exec_module(E)
WITNESSES = []


def digest(data):
    return hashlib.sha256(data).hexdigest()


class FailureEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rpc-evidence-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.actors = []
        self.addCleanup(self.close_actors)
        self.obs = {'step': 17, 'player': 1, 'day': 0, 'hour': 17,
                    'private': {'shed': {'WHEAT': 7}}, 'marker': 'unicode: \u03bb'}
        self.cfg = {'turnsPerDay': 24, 'seed': None, 'remaining': [1, 2]}

    def close_actors(self):
        for actor in self.actors:
            actor.close()

    def actor(self, source, *, startup_timeout=3.0):
        path = self.root / ('actor-' + str(len(self.actors)) + '.py')
        path.write_text(textwrap.dedent(source), encoding='utf-8')
        actor = E.Actor(str(path), self.root, self.root / 'unused-loader.py',
                        20260907, startup_timeout=startup_timeout)
        self.actors.append(actor)
        return actor

    def failure(self, actor, *, timeout=0.08, observation=None):
        response = actor.act(self.obs if observation is None else observation, self.cfg, timeout)
        self.assertNotEqual(response.get('kind'), 'action')
        self.assertIn('rpc_failure', response)
        evidence = response['rpc_failure']
        self.assertEqual(evidence['scope'], 'parent_observed_failed_rpc')
        self.assertIsNone(evidence['worker_call_seconds'])
        self.assertIsNone(evidence['worker_call_cpu_seconds'])
        self.assertIsNone(evidence['worker_stage'])
        return response, evidence

    def assert_request(self, evidence, observation=None):
        request = {'observation': self.obs if observation is None else observation,
                   'configuration': self.cfg}
        wire = E.encoded(request) + b'\n'
        found = evidence['request']
        self.assertEqual(found['disposition'], 'complete')
        self.assertEqual(found['wire_utf8'].encode(), wire)
        self.assertEqual(found['wire_sha256'], digest(wire))
        self.assertEqual(found['wire_bytes'], len(wire))
        self.assertEqual(json.loads(found['wire_utf8']), request)

    def test_timeout_retains_exact_request_and_no_invented_child_timing(self):
        actor = self.actor('import time\ndef agent(obs,cfg): time.sleep(10)\n')
        response, evidence = self.failure(actor)
        self.assertEqual(response['kind'], 'timeout')
        self.assert_request(evidence)
        t = evidence['transport']
        self.assertEqual(t['request_bytes_written'], evidence['request']['wire_bytes'])
        self.assertIsNotNone(t['write_complete_seconds'])
        self.assertIsNone(t['first_response_seconds'])
        self.assertGreaterEqual(t['exchange_seconds'], t['timeout_seconds'])
        self.assertEqual(actor.stats['call_seconds'], [])
        WITNESSES.append({'case': 'timeout', 'response': response})

    def test_failure_packet_detached_from_later_caller_mutation(self):
        actor = self.actor('import time\ndef agent(obs,cfg): time.sleep(10)\n')
        _, evidence = self.failure(actor)
        saved = deepcopy(evidence)
        self.obs['private']['shed']['WHEAT'] = 900
        self.cfg['remaining'].append(3)
        self.assertEqual(evidence, saved)
        self.assertEqual(json.loads(saved['request']['wire_utf8'])['observation']['private']['shed']['WHEAT'], 7)

    def test_success_unchanged_and_no_request_retained_between_calls(self):
        actor = self.actor('def agent(obs,cfg): return {"farmer":["PASS"],"hands":[],"market":[]}\n')
        self.assertEqual(actor.ready['kind'], 'ready')
        self.assertNotIn('rpc_failure', actor.ready)
        result = actor.act(self.obs, self.cfg, 1.0)
        self.assertEqual(result['action'], {'farmer': ['PASS'], 'hands': [], 'market': []})
        self.assertEqual(set(result), {'kind', 'action', 'call_seconds', 'call_cpu_seconds', 'cpu_seconds', 'peak_rss_kib'})
        self.assertNotIn('rpc_failure', actor.report())
        self.assertEqual(actor.stats['calls'], 1)
        self.assertIsNone(getattr(actor, '_last_exchange', 'missing'))

    def test_crash_keeps_original_error_and_exact_returned_packet(self):
        actor = self.actor('def agent(obs,cfg): raise TypeError("body-sentinel")\n')
        response, evidence = self.failure(actor, timeout=1.0)
        self.assertEqual(response['kind'], 'crash')
        self.assertEqual(response['error'], 'TypeError: body-sentinel')
        self.assert_request(evidence)
        raw = base64.b64decode(evidence['response']['prefix_base64'])
        self.assertTrue(raw.endswith(b'\n'))
        self.assertEqual(json.loads(raw)['kind'], 'crash')
        self.assertEqual(evidence['response']['observed_sha256'], digest(raw))
        self.assertEqual(actor.stats['calls'], 1)

    def test_partial_non_utf8_response_preserved_losslessly(self):
        actor = self.actor('''
            import sys,time
            def agent(obs,cfg):
                sys.__stdout__.buffer.write(b'\\xff\\x00{"partial":')
                sys.__stdout__.buffer.flush()
                time.sleep(10)
        ''')
        response, evidence = self.failure(actor, timeout=0.2)
        self.assertEqual(response['kind'], 'timeout')
        raw = base64.b64decode(evidence['response']['prefix_base64'])
        self.assertEqual(raw, b'\xff\x00{"partial":')
        self.assertFalse(evidence['response']['complete_line'])
        self.assertIsNotNone(evidence['transport']['first_response_seconds'])
        self.assertIsNone(evidence['transport']['response_complete_seconds'])
        self.assertEqual(evidence['response']['observed_sha256'], digest(raw))
        WITNESSES.append({'case': 'partial_response', 'response': response})

    def test_malformed_complete_line_not_lost_after_buffer_partition(self):
        actor = self.actor('''
            import sys,time
            def agent(obs,cfg):
                sys.__stdout__.buffer.write(b'not-json\\n')
                sys.__stdout__.buffer.flush()
                time.sleep(10)
        ''')
        response, evidence = self.failure(actor, timeout=1.0)
        self.assertEqual(response['kind'], 'protocol_error')
        self.assertTrue(evidence['response']['complete_line'])
        self.assertEqual(base64.b64decode(evidence['response']['prefix_base64']), b'not-json\n')
        self.assertEqual(actor.buffer, bytearray())

    def test_non_object_protocol_line_is_retained(self):
        actor = self.actor('''
            import sys,time
            def agent(obs,cfg):
                sys.__stdout__.write('[]\\n');sys.__stdout__.flush();time.sleep(10)
        ''')
        response, evidence = self.failure(actor, timeout=1.0)
        self.assertEqual(response['kind'], 'protocol_error')
        self.assertEqual(base64.b64decode(evidence['response']['prefix_base64']), b'[]\n')

    def test_invalid_action_response_timing_keeps_the_rejected_frame(self):
        actor = self.actor('''
            import sys,json,time
            def agent(obs,cfg):
                sys.__stdout__.write(json.dumps({'kind':'action','action':{},'call_seconds':-1,'call_cpu_seconds':0})+'\\n')
                sys.__stdout__.flush();time.sleep(10)
        ''')
        response, evidence = self.failure(actor, timeout=1.0)
        self.assertEqual(response['error'], 'Invalid action response or timing')
        self.assertEqual(json.loads(base64.b64decode(evidence['response']['prefix_base64']))['call_seconds'], -1)
        self.assert_request(evidence)
        self.assertEqual(actor.stats['call_seconds'], [])

    def test_parent_evidence_overrides_forged_worker_diagnostics(self):
        actor = self.actor('''
            import sys,json,time
            def agent(obs,cfg):
                sys.__stdout__.write(json.dumps({'kind':'crash','error':'sentinel','rpc_failure':{'scope':'forged'}})+'\\n')
                sys.__stdout__.flush();time.sleep(10)
        ''')
        _, evidence = self.failure(actor, timeout=1.0)
        self.assert_request(evidence)
        self.assertEqual(json.loads(base64.b64decode(evidence['response']['prefix_base64']))['rpc_failure']['scope'], 'forged')

    def test_request_over_limit_has_digest_but_no_unbounded_copy(self):
        actor = self.actor('def agent(obs,cfg): return {}\n')
        obs = {'padding': 'x' * E.MAX_PACKET}
        response, evidence = self.failure(actor, observation=obs)
        self.assertEqual(response['kind'], 'protocol_error')
        request = evidence['request']
        wire = E.encoded({'observation': obs, 'configuration': self.cfg}) + b'\n'
        self.assertEqual(request['disposition'], 'over_packet_limit')
        self.assertIsNone(request['wire_utf8'])
        self.assertEqual(request['wire_sha256'], digest(wire))
        self.assertEqual(evidence['transport']['request_bytes_written'], 0)
        self.assertLess(len(json.dumps(response)), 5000)

    def test_unserializable_request_does_not_fabricate_packet(self):
        actor = self.actor('def agent(obs,cfg): return {}\n')
        response, evidence = self.failure(actor, observation={'bad': {1, 2}})
        self.assertEqual(response['kind'], 'protocol_error')
        self.assertEqual(evidence['request']['disposition'], 'serialization_failed')
        self.assertIsNone(evidence['request']['wire_utf8'])
        self.assertIsNone(evidence['request']['wire_sha256'])
        self.assertIsNone(evidence['request']['wire_bytes'])
        self.assertEqual(evidence['transport']['request_bytes_written'], 0)

    def test_response_over_limit_is_hashed_and_prefix_bounded(self):
        actor = self.actor('''
            import sys,time
            def agent(obs,cfg):
                sys.__stdout__.buffer.write(b'x' * (2*1024*1024+100))
                sys.__stdout__.buffer.flush();time.sleep(10)
        ''')
        response, evidence = self.failure(actor, timeout=2.0)
        self.assertEqual(response['kind'], 'protocol_error')
        observed = evidence['response']['observed_bytes']
        self.assertGreater(observed, E.MAX_PACKET)
        self.assertLessEqual(observed, E.MAX_PACKET + 65536)
        self.assertEqual(evidence['response']['retained_bytes'], 64 * 1024)
        self.assertTrue(evidence['response']['truncated'])
        self.assertEqual(evidence['response']['observed_sha256'], digest(b'x' * observed))
        self.assert_request(evidence)

    def test_write_backpressure_records_partial_transmission(self):
        actor = self.actor('''
            import sys,json,time
            def agent(obs,cfg):
                sys.__stdout__.write(json.dumps({'kind':'action','action':{},'call_seconds':0,'call_cpu_seconds':0})+'\\n')
                sys.__stdout__.flush();time.sleep(10)
        ''')
        self.assertEqual(actor.act(self.obs, self.cfg, 1.0)['kind'], 'action')
        obs = {'padding': 'x' * (E.MAX_PACKET // 2)}
        response, evidence = self.failure(actor, observation=obs, timeout=0.15)
        self.assertEqual(response['kind'], 'timeout')
        self.assert_request(evidence, obs)
        self.assertGreater(evidence['transport']['request_bytes_written'], 0)
        self.assertLess(evidence['transport']['request_bytes_written'], evidence['request']['wire_bytes'])
        self.assertIsNone(evidence['transport']['write_complete_seconds'])
        self.assertIsNone(evidence['transport']['first_response_seconds'])
        WITNESSES.append({'case': 'write_backpressure', 'transport': evidence['transport'],
                          'request_bytes': evidence['request']['wire_bytes']})

    def test_process_exit_preserves_request_and_final_resource_collection(self):
        actor = self.actor('import os\ndef agent(obs,cfg): os._exit(7)\n')
        response, evidence = self.failure(actor, timeout=1.0)
        self.assertEqual(response['kind'], 'process_exit')
        self.assert_request(evidence)
        actor.close()
        self.assertEqual(actor.report()['exit_code'], 7)
        self.assertEqual(evidence['response']['observed_bytes'], 0)

    def test_startup_error_has_no_invented_observation(self):
        actor = self.actor('raise RuntimeError("startup-sentinel")\n')
        response = actor.ready
        self.assertEqual(response['kind'], 'load_error')
        self.assertIn('rpc_failure', response)
        self.assertEqual(response['rpc_failure']['request']['disposition'], 'startup_no_request')
        self.assertIsNone(response['rpc_failure']['request']['wire_utf8'])
        self.assertEqual(json.loads(base64.b64decode(response['rpc_failure']['response']['prefix_base64']))['kind'], 'load_error')

    def test_failure_after_success_captures_current_not_previous_request(self):
        actor = self.actor('''
            import time
            def agent(obs,cfg):
                if obs['step'] == 18: time.sleep(10)
                return {'step':obs['step']}
        ''')
        self.assertEqual(actor.act(self.obs, self.cfg, 1.0)['kind'], 'action')
        self.obs['step'] = 18
        response, evidence = self.failure(actor)
        self.assert_request(evidence)
        self.assertEqual(json.loads(evidence['request']['wire_utf8'])['observation']['step'], 18)
        self.assertEqual(actor.stats['calls'], 2)
        self.assertEqual(len(actor.stats['call_seconds']), 1)

    def test_failure_evidence_serialization_is_outside_recorded_rpc(self):
        actor = self.actor('def agent(obs,cfg): raise ValueError("sentinel")\n')
        original = getattr(actor, '_retain_rpc_failure', None)
        self.assertIsNotNone(original)
        def delayed(result):
            time.sleep(0.2)
            return original(result)
        with patch.object(actor, '_retain_rpc_failure', delayed):
            started = time.perf_counter()
            response, _ = self.failure(actor, timeout=1.0)
            elapsed = time.perf_counter() - started
        self.assertGreaterEqual(elapsed - actor.stats['rpc_seconds'][-1], 0.19)
        self.assertEqual(response['kind'], 'crash')

    def test_play_and_atomic_report_retain_failed_seat_only(self):
        # Explicit result-plumbing fixture; no official engine or game seed used.
        class Engine:
            specification = {'configuration': {'episodeSteps': {'default': 3},
                                               'turnsPerDay': {'default': 24}}}
            @staticmethod
            def interpreter(state, env):
                env.configuration.seed = None
                for seat, s in enumerate(state):
                    s.observation.update(player=seat, farms=[{'money': 10}, {'money': 20}],
                                         private={'seat_marker': seat})
        good = self.root / 'good.py'; good.write_text('def agent(obs,cfg): return {}\n')
        bad = self.root / 'bad.py'; bad.write_text('import time\ndef agent(obs,cfg): time.sleep(10)\n')
        result = E.play(Engine(), [str(good), str(bad)], self.root, self.root/'unused',
                        None, 1, action_timeout=0.08)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['failure']['seat'], 1)
        self.assertEqual(result['failure']['step'], 0)
        self.assertIn('rpc_failure', result['failure'])
        request = json.loads(result['failure']['rpc_failure']['request']['wire_utf8'])
        self.assertEqual(request['observation']['private'], {'seat_marker': 1})
        self.assertEqual(request['observation']['remainingOverageTime'], 0)
        self.assertIsNone(request['configuration']['seed'])
        self.assertNotIn('info', request)
        self.assertIsNone(result['scores'])
        self.assertEqual(len(result['actors']), 2)
        out = self.root / 'report.json'
        E.write_report(out, {'games': [result]})
        self.assertEqual(json.loads(out.read_text())['games'][0]['failure'], result['failure'])
        self.assertEqual(list(self.root.glob('*.tmp')), [])
        WITNESSES.append({'case': 'play_report_failure', 'failure': result['failure']})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FailureEvidenceTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({
            'scope': 'real_worker_and_pipe_tests_plus_result_plumbing_fixture',
            'evaluator_sha256': digest(TARGET.read_bytes()),
            'test_sha256': digest(Path(__file__).read_bytes()),
            'python': sys.version, 'platform': sys.platform,
            'tests': {'run': result.testsRun, 'failures': len(result.failures),
                      'errors': len(result.errors), 'successful': result.wasSuccessful()},
            'engine_games': 0, 'game_seeds': [], 'witnesses': WITNESSES,
            'failure_details': [{'test': str(t), 'traceback': msg} for t, msg in result.failures],
            'error_details': [{'test': str(t), 'traceback': msg} for t, msg in result.errors],
        }, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
