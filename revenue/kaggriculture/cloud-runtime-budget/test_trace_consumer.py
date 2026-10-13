# SPDX-License-Identifier: Apache-2.0
"""Native TRACE JSONL/receipt integration; no interpreter or reconstruction."""
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import profile_saved as p

TIMING = Path(os.environ.get('TITAN_TIMING_SOURCE', str(
    Path(__file__).resolve().parent.parent / 'cloud-combination-analysis/execution_timing.py')))


class TraceConsumerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.stream=self.root/'inputs.jsonl.gz'; self.receipt=self.root/'receipt.json'
        self.rows=[{'step':k,'seat':0,'observation':{'step':k,'player':0,'private':{},'farms':[{},{}],'market':{}},
                    'configuration':{'seed':9921001,'cost':k+10},'expected_action':{'value':k}} for k in range(3)]
        self.meta={'schema':'titan.recorded-actor-inputs.v1','candidate_seat':0,
                   'candidate_actor_rng_seed':20260907,'candidate_pythonhashseed':20260907,
                   'source_trace_sha256':'fixture-only','environment_seed_provenance_only':9921001}
        self.write()

    def tearDown(self): self.tmp.cleanup()

    def write(self, compressed=True):
        decoded=b''.join(p.canonical(row)+b'\n' for row in self.rows)
        data=gzip.compress(decoded,mtime=0) if compressed else decoded
        self.stream.write_bytes(data)
        self.meta.update(input_jsonl_sha256=p.digest(decoded),output_file_sha256=p.digest(data),observation_count=len(self.rows))
        self.receipt.write_text(json.dumps(self.meta))

    def test_native_plain_and_gzip(self):
        for compressed in (False,True):
            with self.subTest(compressed=compressed):
                self.write(compressed)
                original=self.stream.read_bytes()
                cfg,rows,receipt=p.load_workload(self.stream,0,3,self.receipt)
                self.assertNotIn('seed',cfg)
                self.assertEqual(rows,self.rows)
                self.assertEqual(receipt['provenance']['source_receipt'],self.meta)
                self.assertEqual(self.stream.read_bytes(),original)

    def test_compressed_and_decoded_hash_bindings(self):
        for key in ('input_jsonl_sha256','output_file_sha256'):
            with self.subTest(key=key):
                self.write(); bad=copy.deepcopy(self.meta);bad[key]='wrong'
                self.receipt.write_text(json.dumps(bad))
                with self.assertRaisesRegex(ValueError,'bytes differ'):
                    p.load_workload(self.stream,0,3,self.receipt)

    def test_whole_count_and_seat(self):
        for key,value in [('observation_count',4),('candidate_seat',1)]:
            with self.subTest(key=key):
                self.write();bad=copy.deepcopy(self.meta);bad[key]=value
                self.receipt.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):p.load_workload(self.stream,0,3,self.receipt)

    def test_row_clock_and_configuration(self):
        original=copy.deepcopy(self.rows)
        for alteration in ('clock','configuration','seat'):
            with self.subTest(alteration=alteration):
                self.rows=copy.deepcopy(original)
                if alteration=='clock':self.rows[1]['step']=7
                elif alteration=='configuration':self.rows[1].pop('configuration')
                else:self.rows[1]['seat']=1
                self.write()
                with self.assertRaises(ValueError):p.load_workload(self.stream,0,3,self.receipt)

    def test_seat_one_execution_metadata(self):
        for row in self.rows:row['seat']=row['observation']['player']=1
        self.meta.update(candidate_seat=1,candidate_actor_rng_seed=20260908,candidate_pythonhashseed=20260908)
        self.write()
        _,rows,receipt=p.load_workload(self.stream,1,3,self.receipt)
        self.assertEqual(rows[0]['observation']['player'],1)
        self.assertEqual(receipt['provenance']['source_receipt']['candidate_actor_rng_seed'],20260908)

    def test_missing_and_boolean_actor_seed(self):
        for field in ('candidate_actor_rng_seed','candidate_pythonhashseed'):
            for value in (None,True,'20260907'):
                with self.subTest(field=field,value=value):
                    bad=copy.deepcopy(self.meta);bad[field]=value
                    self.receipt.write_text(json.dumps(bad))
                    with self.assertRaisesRegex(ValueError,'actor seed'):
                        p.load_execution_receipt(self.receipt)

    def test_prefix_limit_retains_full_stream_identity(self):
        _,rows,receipt=p.load_workload(self.stream,0,1,self.receipt)
        self.assertEqual(len(rows),1)
        self.assertEqual(receipt['records'],1)
        self.assertEqual(receipt['provenance']['source_receipt']['observation_count'],3)

    def test_unselected_metadata_does_not_seed_legacy_actor(self):
        target=self.root/'target';target.mkdir(); source=target/'main.py'
        source.write_text("class Agent:\n    def act(self,obs,cfg): return {}\ndef make_agent(): return Agent()\n")
        legacy=self.root/'legacy.json'
        legacy.write_text(json.dumps({'schema':'titan.profile.observations.v1',
            'configuration':{},'records':[{'observation':r['observation']} for r in self.rows],
            'provenance':{'source_receipt':{'candidate_actor_rng_seed':20260907}}}))
        args=SimpleNamespace(entrypoint=source,factory='make_agent',method='act',timing_source=TIMING,
            replay=legacy,input_receipt=None,seat=0,max_decisions=3,
            classification='legacy-metadata-fixture',process_timeout=10,output=self.root/'out.json')
        self.assertEqual(p.supervise(args),0)
        result=json.loads(args.output.read_text())
        for name in ('ordinary','instrumented'):
            self.assertIsNone(result[name]['actor_rng_seed'])

    def test_exact_factory_keywords_and_sibling_source_attribution(self):
        for row in self.rows: row.pop('expected_action')
        self.write()
        root=self.root/'runtime';root.mkdir(); target=root/'entry';target.mkdir()
        sibling=root/'policy.py'
        sibling.write_text("class Agent:\n    def act(self,obs,cfg): return {'funded':False}\n")
        source=target/'main.py'
        source.write_text("from pathlib import Path\nimport sys\nsys.path.insert(0,str(Path(__file__).parent.parent))\nfrom policy import Agent\ndef make_agent(*,funded=True):\n    assert funded is False\n    return Agent()\n")
        args=SimpleNamespace(entrypoint=source,factory='make_agent',factory_kwargs={'funded':False},
            source_root=root,method='act',timing_source=TIMING,replay=self.stream,input_receipt=self.receipt,
            seat=0,max_decisions=3,classification='synthetic-factory-join',process_timeout=10,
            output=self.root/'out.json')
        self.assertEqual(p.supervise(args),0)
        result=json.loads(args.output.read_text())
        self.assertEqual(set(result['ordinary']['runtime_sources']),{'entry/main.py','policy.py'})
        self.assertEqual(result['ordinary']['factory_kwargs'],{'funded':False})
        self.assertTrue(any(row['file']=='policy.py' and row['function']=='act'
            for row in result['instrumented']['hot_functions']))
        self.assertEqual(result['ordinary']['timings']['calls'],3)

    def test_factory_keywords_typeerror_is_not_retried(self):
        target=self.root/'runtime';target.mkdir();source=target/'main.py'
        source.write_text("def make_agent(*,funded=True): raise TypeError('exact factory body')\n")
        args=SimpleNamespace(entrypoint=source,factory='make_agent',factory_kwargs={'funded':False},
            source_root=target,method='act',timing_source=TIMING,replay=self.stream,input_receipt=self.receipt,
            seat=0,max_decisions=3,classification='synthetic-factory-failure',process_timeout=10,
            output=self.root/'out.json')
        self.assertEqual(p.supervise(args),2)
        result=json.loads(args.output.read_text())
        for arm in ('ordinary','instrumented'):
            self.assertEqual(result[arm]['error'],{'type':'TypeError','message':'exact factory body'})
            self.assertTrue(result[arm]['timings']['initialization_failed'])
            self.assertEqual(result[arm]['calls'],[])

    def test_actual_fresh_process_seed_and_per_row_config(self):
        for row in self.rows:row.pop('expected_action')
        self.write()
        target=self.root/'target';target.mkdir(); source=target/'main.py'
        source.write_text('''import random, os
class Agent:
    def act(self,obs,cfg):
        assert 'seed' not in cfg
        assert cfg['cost']==obs['step']+10
        return {'sample':random.random(),'hash':hash('trace-consumer'),'env':os.environ.get('PYTHONHASHSEED')}
def make_agent(): return Agent()
''')
        args=SimpleNamespace(entrypoint=source,factory='make_agent',method='act',timing_source=TIMING,
            replay=self.stream,input_receipt=self.receipt,seat=0,max_decisions=3,
            classification='synthetic-trace-format-only',process_timeout=10,output=self.root/'out.json')
        self.assertEqual(p.supervise(args),0)
        result=json.loads(args.output.read_text())
        self.assertTrue(result['instrumentation_action_parity'])
        for name in ('ordinary','instrumented'):
            self.assertEqual(result[name]['actor_rng_seed'],20260907)
            self.assertEqual(result[name]['pythonhashseed'],'20260907')
            self.assertEqual(result[name]['input']['provenance']['source_receipt']['environment_seed_provenance_only'],9921001)
            self.assertEqual(result[name]['timings']['failures'],0)


if __name__=='__main__':unittest.main(verbosity=2)
