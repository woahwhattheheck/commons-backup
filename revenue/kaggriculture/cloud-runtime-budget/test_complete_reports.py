# SPDX-License-Identifier: Apache-2.0
"""Missing or inconsistent saved-profile identity is not successful parity.

All reports are controlled fixtures unless a test explicitly starts the actual
profiler CLI. No engine, game, remote service, or dependency installation is used.
Set PROFILER_SOURCE to an exact profile_saved.py to test another revision.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import base64, contextlib, copy, hashlib, importlib.util, io, json, os
import subprocess, sys, tempfile, unittest

SOURCE=Path(os.environ.get('PROFILER_SOURCE',Path(__file__).with_name('profile_saved.py'))).resolve()
spec=importlib.util.spec_from_file_location('complete_report_subject',SOURCE)
p=importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
def sha(text): return hashlib.sha256(text.encode()).hexdigest()
def good(mode='ordinary'):
    return {
        'schema':'titan.saved-runtime-pass.v1','mode':mode,'status':'complete',
        'calls':[{'step':n,'wall_s':.001,'cpu_s':.001,'action_sha256':sha('action'+str(n))} for n in range(2)],
        'action_sequence_sha256':sha('constructed-sequence'),
        'profiler_sha256':sha('profiler'),'timing_source_sha256':sha('timing'),
        'runtime_sources':{'actor.py':sha('actor')},
        'loaded_sources':{'finch_existing_timing':{'path':'/fixture/timing.py','sha256':sha('timing')},'finch_profile_target':{'path':'/fixture/actor.py','sha256':sha('actor')}},
        'input':{'records':2,'transport_sha256':sha('input'),'decoded_sha256':sha('input'),'provenance':{'kind':'constructed'}},
        'loaded_sources_unchanged':True,'sources_unchanged':True,
        'expected_actions':{'present':2,'mismatches':0,'first_mismatch':None},
    }

class CompleteReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.counter=0
    def tearDown(self): self.tmp.cleanup()
    def read(self, value, mode='ordinary'):
        self.counter+=1; path=self.root/f'report{self.counter}.json'
        raw=json.dumps(value,sort_keys=True).encode();path.write_bytes(raw)
        return p.read_child_report(path,mode),raw
    def invalid(self,value,mode='ordinary'):
        out,raw=self.read(value,mode)
        self.assertEqual(out['status'],'process_error')
        self.assertEqual(out['error']['type'],'InvalidChildReport')
        retained=out['invalid_report']
        self.assertEqual(Path(retained['path']).read_bytes(),raw)
        self.assertEqual(retained['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(retained['bytes'],len(raw))
    def supervise(self, payloads, code=0):
        self.counter+=1; output=self.root/f'parent{self.counter}.json'
        args=SimpleNamespace(output=output,entrypoint=self.root/'unused_actor.py',factory='make_agent',method='act',timing_source=self.root/'unused_timing.py',replay=self.root/'unused_input.json',seat=0,max_decisions=2,classification='constructed-report-data',process_timeout=5,profile_slowest=1)
        original=subprocess.run;seen=[]
        def child(command,**kwargs):
            mode=command[command.index('--worker-mode')+1];seen.append(mode)
            target=command[command.index('--output')+1]
            raw=json.dumps(payloads[mode],sort_keys=True).encode()
            script='import pathlib,base64,sys;pathlib.Path(sys.argv[1]).write_bytes(base64.b64decode(sys.argv[2]));print("retained child log");sys.exit(int(sys.argv[3]))'
            return original([sys.executable,'-c',script,target,base64.b64encode(raw).decode(),str(code)],**kwargs)
        with mock.patch.object(p.subprocess,'run',side_effect=child),contextlib.redirect_stdout(io.StringIO()):
            result_code=p.supervise(args)
        self.assertEqual(seen,['ordinary','profile'])
        for mode in seen:
            self.assertIn('retained child log',output.with_name(output.stem+'.'+mode+'.log').read_text())
        return result_code,json.loads(output.read_text())
    def test_complete_record_preserves_original_fields(self):
        source=good();original=copy.deepcopy(source);out,_=self.read(source)
        self.assertEqual(out,original);self.assertEqual(source,original)
    def test_missing_schema_is_not_complete(self):
        x=good();x.pop('schema');self.invalid(x)
    def test_wrong_mode_is_not_the_requested_pass(self):
        self.invalid(good('profile'),'ordinary')
    def test_missing_digest_fields_are_not_complete(self):
        for name in ('action_sequence_sha256','profiler_sha256','timing_source_sha256'):
            with self.subTest(field=name):
                x=good();x.pop(name);self.invalid(x)
    def test_malformed_digest_is_not_an_identity(self):
        for value in (None,'','fixture','a'*63,'g'*64,'a'*64+'\n',True,3,[],{}):
            with self.subTest(value=value):
                x=good();x['action_sequence_sha256']=value;self.invalid(x)
    def test_missing_input_identity_is_not_complete(self):
        for value in (None,[],{}):
            with self.subTest(value=value):
                x=good();x['input']=value;self.invalid(x)
    def test_input_count_must_equal_completed_calls(self):
        for count in (0,1,3,True,2.0,'2'):
            with self.subTest(count=count):
                x=good();x['input']['records']=count;self.invalid(x)
    def test_input_transport_hashes_are_required(self):
        for field in ('transport_sha256','decoded_sha256'):
            with self.subTest(field=field):
                x=good();x['input'].pop(field);self.invalid(x)
    def test_missing_or_invalid_runtime_map_is_not_complete(self):
        for value in (None,[],{'actor.py':'fixture'},{'':sha('actor')}):
            with self.subTest(value=value):
                x=good();x['runtime_sources']=value;self.invalid(x)
    def test_loaded_entrypoint_and_timing_identities_are_required(self):
        for name in ('finch_existing_timing','finch_profile_target'):
            for field in ('path','sha256'):
                with self.subTest(name=name,field=field):
                    x=good();x['loaded_sources'][name].pop(field);self.invalid(x)
        for value in (None,[],{}):
            with self.subTest(value=value):
                x=good();x['loaded_sources']=value;self.invalid(x)
    def test_timing_identity_must_agree_with_loaded_bytes(self):
        x=good();x['timing_source_sha256']=sha('different timing');self.invalid(x)
    def test_call_steps_are_an_uninterrupted_prefix(self):
        for steps in ((1,2),(0,0),(0,2),(1,0)):
            with self.subTest(steps=steps):
                x=good()
                for row,step in zip(x['calls'],steps): row['step']=step
                self.invalid(x)
    def test_completed_call_has_an_action_identity(self):
        x=good();x['calls'][1].pop('action_sha256');self.invalid(x)
    def test_complete_report_cannot_also_claim_error(self):
        x=good();x['error']={'type':'RuntimeError'};self.invalid(x)
    def test_original_failure_remains_original(self):
        x={'status':'error','calls':[],'error':{'type':'TypeError','message':'original error'}}
        out,_=self.read(x);self.assertEqual(out,x)
    def test_unknown_metadata_is_preserved(self):
        x=good();x['future_annotation']={'some':'data'};out,_=self.read(x);self.assertEqual(out,x)
    def test_expected_action_mismatch_is_valid_off_policy_evidence(self):
        x=good();x['expected_actions']={'present':2,'mismatches':2,'first_mismatch':0}
        out,_=self.read(x);self.assertEqual(out,x)
    def test_source_change_remains_recorded_without_false_parity(self):
        a,b=good('ordinary'),good('profile');a['sources_unchanged']=False
        code,result=self.supervise({'ordinary':a,'profile':b})
        self.assertEqual(code,2);self.assertFalse(result['instrumentation_action_parity'])
        self.assertEqual(result['ordinary']['status'],'complete')
    def test_two_incomplete_real_children_do_not_report_parity(self):
        x={'status':'complete','calls':[{'step':0,'wall_s':.001}],'loaded_sources_unchanged':True,'sources_unchanged':True}
        code,result=self.supervise({'ordinary':x,'profile':x})
        self.assertEqual(code,2);self.assertFalse(result['instrumentation_action_parity'])
        for name in ('ordinary','instrumented'):
            self.assertEqual(result[name]['error']['type'],'InvalidChildReport')
            self.assertEqual(Path(result[name]['invalid_report']['path']).read_bytes(),json.dumps(x,sort_keys=True).encode())
    def test_call_hash_difference_overrides_equal_aggregate(self):
        a,b=good('ordinary'),good('profile');b['calls'][1]['action_sha256']=sha('different action')
        code,result=self.supervise({'ordinary':a,'profile':b})
        self.assertEqual(code,2);self.assertFalse(result['instrumentation_action_parity'])
    def test_matching_well_formed_child_reports_keep_success(self):
        code,result=self.supervise({mode:good(mode) for mode in ('ordinary','profile')})
        self.assertEqual(code,0);self.assertTrue(result['instrumentation_action_parity'])
    def actual_cli(self, corrupt=False, mismatched=False):
        actor_dir=self.root/'runtime';actor_dir.mkdir()
        actor=actor_dir/'actor.py'
        tail=''
        if corrupt:
            tail='''
import atexit,json,pathlib,sys
def truncate_identity():
    destination=pathlib.Path(sys.argv[sys.argv.index('--output')+1])
    report=json.loads(destination.read_text())
    report.pop('action_sequence_sha256')
    destination.write_text(json.dumps(report))
atexit.register(truncate_identity)
'''
        actor.write_text('class Actor:\n    def act(self, obs, cfg):\n        return {"value": obs["step"]}\ndef make_agent():\n    return Actor()\n'+tail)
        timing=self.root/'timing.py'
        timing.write_text('''class TimedFactory:
    def __init__(self,factory): self.factory=factory
    def __call__(self): return self.factory()
    def timings(self): return {'initialization_plus_first_action_s': None}
''')
        rows=[{'observation':{'farms':[],'private':{},'market':{},'step':n,'player':0},'expected_action':{'value':99 if mismatched else n}} for n in range(3)]
        inputs=self.root/'inputs.json';inputs.write_text(json.dumps({'schema':'titan.profile.observations.v1','configuration':{},'records':rows}))
        output=self.root/'actual.json'
        run=subprocess.run([sys.executable,'-B',str(SOURCE),'--entrypoint',str(actor),'--timing-source',str(timing),'--replay',str(inputs),'--output',str(output),'--max-decisions','3','--process-timeout','10'],capture_output=True,text=True,timeout=20)
        self.assertTrue(output.exists(),run.stderr)
        return run,json.loads(output.read_text())
    def test_actual_profiler_worker_complete_reports_still_pass(self):
        run,result=self.actual_cli()
        self.assertEqual(run.returncode,0,run.stderr);self.assertTrue(result['instrumentation_action_parity'])
        for name in ('ordinary','instrumented'):
            self.assertEqual(len(result[name]['calls']),3)
            self.assertEqual(result[name]['expected_actions']['mismatches'],0)
    def test_actual_worker_shutdown_loss_of_identity_is_detected(self):
        run,result=self.actual_cli(corrupt=True)
        self.assertEqual(run.returncode,2,run.stderr);self.assertFalse(result['instrumentation_action_parity'])
        for name in ('ordinary','instrumented'):
            retained=result[name]['invalid_report'];raw=Path(retained['path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),retained['sha256'])
            self.assertNotIn('action_sequence_sha256',json.loads(raw))
            self.assertEqual(result[name]['process_exit_code'],0)
    def test_actual_off_policy_correspondence_remains_separate_from_parity(self):
        run,result=self.actual_cli(mismatched=True)
        self.assertEqual(run.returncode,0,run.stderr);self.assertTrue(result['instrumentation_action_parity'])
        self.assertEqual(result['ordinary']['expected_actions']['mismatches'],3)

if __name__=='__main__': unittest.main(verbosity=2)
