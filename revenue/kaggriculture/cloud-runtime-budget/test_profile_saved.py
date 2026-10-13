# SPDX-License-Identifier: Apache-2.0
"""Exercise the real process supervisor and observation-only profiling contract."""
import copy
import gzip
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import profile_saved as p

TIMING = Path(os.environ.get('TITAN_TIMING_SOURCE', str(
    Path(__file__).resolve().parent.parent / 'cloud-combination-analysis/execution_timing.py')))


def workload():
    return {'schema': 'titan.profile.observations.v1',
            'configuration': {'seed': 900, 'turnsPerDay': 24},
            'provenance': {'kind': 'synthetic-contract-fixture'},
            'records': [{'observation': {'step': k, 'player': 0, 'private': {'own': 42},
                         'farms': [{'money': 100}, {'money': 200}], 'market': {}}}
                        for k in range(3)]}


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.replay = self.root / 'work.json'
        self.replay.write_text(json.dumps(workload()))
        self.target_dir = self.root / 'target'
        self.target_dir.mkdir()
        self.target = self.target_dir / 'main.py'
        self.args = SimpleNamespace(entrypoint=self.target, factory='make_agent', method='act',
             timing_source=TIMING, replay=self.replay, seat=0, max_decisions=3,
             classification='synthetic-contract-fixture', process_timeout=10., output=self.root/'result.json')

    def tearDown(self):
        self.tmp.cleanup()

    def source(self, text):
        self.target.write_text(text)

    def run_report(self):
        code = p.supervise(self.args)
        return code, json.loads(self.args.output.read_text())

    def test_one_and_two_argument_binding(self):
        self.assertEqual(p.bind_action(lambda obs: obs)(1, {}), 1)
        self.assertEqual(p.bind_action(lambda obs,cfg: obs+cfg)(1,2), 3)

    def test_body_typeerror_no_retry(self):
        calls=[]
        def broken(obs,cfg=None):
            calls.append(1)
            raise TypeError('body')
        with self.assertRaisesRegex(TypeError,'body'):
            p.bind_action(broken)({}, {})
        self.assertEqual(calls,[1])

    def test_unsupported_signature_rejected_before_call(self):
        def broken(a,b,c):
            self.fail('should not call')
        with self.assertRaises(TypeError):
            p.bind_action(broken)

    def test_seed_removed_and_input_unchanged(self):
        raw = self.replay.read_bytes()
        cfg,rows,receipt = p.load_workload(self.replay,0,3)
        self.assertNotIn('seed',cfg)
        self.assertEqual(len(rows),3)
        self.assertEqual(self.replay.read_bytes(),raw)
        self.assertEqual(receipt['transport_sha256'],p.digest(raw))

    def test_prefix_gap_rejected(self):
        data=workload(); data['records'][1]['observation']['step']=8
        self.replay.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'uninterrupted prefix'):
            p.load_workload(self.replay,0,3)

    def test_summary_not_observation(self):
        self.replay.write_text(json.dumps({'records':[{'step':0,'elapsed_s':.2}]}))
        with self.assertRaisesRegex(ValueError,'complete observations'):
            p.load_workload(self.replay,0,3)

    def test_no_private_borrow(self):
        data={'steps': [[{'observation': {'step':0,'private':{'secret':99},'market':{},'farms':[{},{}]}},
                         {'observation': {'player':1}}], [{},{}]]}
        self.replay.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'full own observation'):
            p.load_workload(self.replay,1,3)

    def test_shared_fields_only(self):
        data={'steps': [[{'observation': {'step':0,'private':{'secret':99},'market':{},'farms':[{},{}]}},
                         {'observation': {'player':1,'private':{'own':42}}}], [{},{}]]}
        self.replay.write_text(json.dumps(data))
        _, rows, _ = p.load_workload(self.replay,1,3)
        self.assertEqual(rows[0]['observation']['private'],{'own':42})
        self.assertEqual(rows[0]['observation']['player'],1)

    def test_wrong_seat_rejected(self):
        with self.assertRaisesRegex(ValueError,'selected seat'):
            p.load_workload(self.replay,1,3)

    def test_gzip_input(self):
        self.replay.write_bytes(gzip.compress(self.replay.read_bytes(),mtime=0))
        self.assertEqual(len(p.load_workload(self.replay,0,3)[1]),3)

    def test_two_process_parity_actual_observer(self):
        self.source('''class Agent:
    def __init__(self): self.n=0
    def act(self,obs,cfg=None):
        self.n+=1
        assert 'seed' not in cfg
        assert obs['private']=={'own':42}
        return {'farmer':['PASS'],'hands':[],'market':[], 'counter':self.n}
def make_agent(): return Agent()
''')
        original=self.target.read_bytes()
        code,r=self.run_report()
        self.assertEqual(code,0)
        self.assertTrue(r['instrumentation_action_parity'])
        a,b=r['ordinary'],r['instrumented']
        self.assertNotEqual(a['process_id'],b['process_id'])
        self.assertEqual(len(a['calls']),3)
        self.assertEqual(a['timings']['calls'],3)
        self.assertGreaterEqual(a['target_load_through_first_attempt_wall_s'],a['timings']['first_action_s'])
        self.assertEqual(self.target.read_bytes(),original)
        self.assertTrue(any(x['function']=='act' for x in b['hot_functions']))

    def test_original_action_failure_preserved(self):
        self.source('''class Agent:
    def act(self,obs,cfg=None): raise TypeError('exact body failure')
def make_agent(): return Agent()
''')
        code,r=self.run_report()
        self.assertEqual(code,2)
        for arm in ('ordinary','instrumented'):
            a=r[arm]
            self.assertEqual(a['error'],{'type':'TypeError','message':'exact body failure'})
            self.assertEqual(a['timings']['calls'],1)
            self.assertEqual(a['timings']['failures'],1)
            self.assertEqual(len(a['calls']),1)
        self.assertFalse(r['instrumentation_action_parity'])

    def test_factory_failure_receipt(self):
        self.source("def make_agent(): raise RuntimeError('factory failure')\n")
        code,r=self.run_report()
        self.assertEqual(code,2)
        for arm in ('ordinary','instrumented'):
            self.assertEqual(r[arm]['error']['message'],'factory failure')
            self.assertTrue(r[arm]['timings']['initialization_failed'])
            self.assertEqual(r[arm]['calls'],[])

    def test_process_timeout_retained(self):
        self.source('import time\ndef make_agent(): time.sleep(10)\n')
        self.args.process_timeout=.3
        code,r=self.run_report()
        self.assertEqual(code,2)
        for arm in ('ordinary','instrumented'):
            self.assertEqual(r[arm]['status'],'process_timeout')
            self.assertIsNone(r[arm]['process_exit_code'])

    def test_stale_output_not_consumed_or_overwritten(self):
        old=self.root/'result.ordinary.json'
        old.write_text('{"status":"complete"}')
        with self.assertRaises(FileExistsError):
            self.run_report()
        self.assertEqual(old.read_text(),'{"status":"complete"}')
        self.assertFalse(self.args.output.exists())

    def test_expected_action_mismatch_not_hidden(self):
        data=workload()
        for row in data['records']: row['expected_action']={'different':True}
        self.replay.write_text(json.dumps(data))
        self.source('class Agent:\n    def act(self,obs): return {}\ndef make_agent(): return Agent()\n')
        code,r=self.run_report()
        self.assertEqual(code,0)
        self.assertEqual(r['ordinary']['expected_actions'],{'present':3,'mismatches':3,'first_mismatch':0})


if __name__=='__main__':
    unittest.main(verbosity=2)
