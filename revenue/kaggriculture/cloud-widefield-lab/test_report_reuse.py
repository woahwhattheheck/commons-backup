# SPDX-License-Identifier: Apache-2.0
"""Panel reuse/CLI with synthetic reports and an actual evaluator join; no official games."""
from __future__ import annotations
import argparse
import contextlib
import io
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

TARGET = Path(os.environ.get('TITAN_PANEL_PATH', Path(__file__).with_name('run_panel.py'))).resolve()
spec = importlib.util.spec_from_file_location('reuse_subject', TARGET)
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
WITNESSES = []


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ReportReuseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.evaluator = self.root/'cloud-eval/evaluate.py'; self.evaluator.parent.mkdir()
        self.evaluator.write_text(textwrap.dedent('''
            import json,sys
            from pathlib import Path
            root=Path(__file__).parent
            data=json.loads((root/'fixture.json').read_text())
            target=Path(sys.argv[sys.argv.index('--output')+1])
            target.write_text(json.dumps(data['report']))
            (root/'received-args.json').write_text(json.dumps(sys.argv[1:]))
            with (root/'launches.txt').open('a') as f:f.write('one\\n')
            if data.get('mutate'):
                Path(data['mutate']).write_text('changed during fixture subprocess\\n')
            print('fixture evaluator only; no policy or engine')
            raise SystemExit(data.get('exit',0))
        '''))
        self.loader = self.root/'20260907-offline-agent/evaluate.py'; self.loader.parent.mkdir()
        self.loader.write_text('# loader fixture, never imported\n')
        self.candidate = self.root/'candidate.py';self.candidate.write_text('# candidate fixture, never imported\n')
        self.opponent = self.root/'opponent.py';self.opponent.write_text('# opponent fixture, never imported\n')
        self.engine = self.root/'engine'; self.engine.mkdir()
        (self.engine/'kaggriculture.py').write_text('# engine fixture, never imported\n')
        (self.engine/'utils.py').write_text('# utility fixture, never imported\n')
        (self.engine/'kaggriculture.json').write_text(json.dumps({'configuration':{'episodeSteps':{'default':3}}}))
        self.job = {'arm':'candidate','candidate':str(self.candidate),'seeds':[12]}
        self.opponents = ['wanted='+str(self.opponent)]
        self.out=self.root/'out'; self.target=self.out/'raw/candidate/12-12.json'
        self.log=self.out/'logs/candidate/12-12.log'
        # Independent fixture in the unchanged evaluator's report schema.
        self.report={'schema_version':1,'seeds':[12], 'agent_rng_seed':20260907,
            'evaluator_sha256':sha(self.evaluator),'loader_sha256':sha(self.loader),
            'engine_sha256':{n:sha(self.engine/n) for n in ('kaggriculture.py','kaggriculture.json','utils.py')},
            'candidate':{'entry':self.candidate.name,'callable':'agent','sha256':sha(self.candidate)},
            'opponents':{'wanted':{'entry':self.opponent.name,'callable':'agent','sha256':sha(self.opponent)}},
            'limits':{'action_rpc_seconds':1.0,'startup_seconds':10.0,'game_seconds_between_steps':120.0,'remaining_overage_time':0},
            'progress':{'state':'complete'},
            'games':[{'seed':12,'candidate_seat':seat,'opponent':'wanted','status':'complete','scores':[10.0,9.0],
                      'failure':None,'episode_steps':3,'steps':2} for seat in (0,1)]}

    def save_report(self, value=None, raw=None):
        self.target.parent.mkdir(parents=True,exist_ok=True)
        self.target.write_bytes(raw if raw is not None else json.dumps(self.report if value is None else value).encode())
        self.log.parent.mkdir(parents=True,exist_ok=True);self.log.write_text('original log\n')

    def run_existing(self):
        before=self.target.read_bytes() if self.target.exists() else None
        before_log=self.log.read_bytes() if self.log.exists() else None
        with patch.object(P.subprocess,'run',side_effect=AssertionError('existing evidence was replayed')):
            result=P.run_job(self.job,self.evaluator,self.engine,self.opponents,self.out)
        if before is not None:self.assertEqual(self.target.read_bytes(),before)
        if before_log is not None:self.assertEqual(self.log.read_bytes(),before_log)
        return result

    def rejected(self):
        result=self.run_existing()
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result.get('reason'),'existing_evidence_not_reusable')
        self.assertTrue(result['validation']['problems'])
        return result

    def fixture(self, report=None, **extra):
        data={'report': self.report if report is None else report, **extra}
        (self.evaluator.parent/'fixture.json').write_text(json.dumps(data))

    def test_exact_report_reused_without_launch_or_writes(self):
        self.save_report();result=self.run_existing()
        self.assertEqual(result['status'],'reused-complete')
        self.assertEqual(result['sha256'],sha(self.target))
        self.assertEqual(result['source_binding']['candidate']['sha256'],sha(self.candidate))

    def test_scalar_episode_steps_report_reused_without_launch_or_writes(self):
        schema = self.engine/'kaggriculture.json'
        schema.write_text(json.dumps({'configuration': {'episodeSteps': 720}}))
        self.report['engine_sha256']['kaggriculture.json'] = sha(schema)
        for game in self.report['games']:
            game.update(episode_steps=720, steps=719)
        self.save_report()
        result = self.run_existing()
        self.assertEqual(result['status'], 'reused-complete')
        self.assertEqual(result['source_binding']['episode_steps'], 720)
        self.assertEqual(result['source_binding']['engine_sha256']['kaggriculture.json'], sha(schema))

    def test_episode_steps_accepts_scalar_and_default_integers(self):
        for value in (2, 720):
            for configured in (value, {'default': value}):
                with self.subTest(configured=configured):
                    (self.engine/'kaggriculture.json').write_text(json.dumps(
                        {'configuration': {'episodeSteps': configured}}))
                    binding = P.expected_binding(self.job, self.evaluator, self.engine, self.opponents)
                    self.assertEqual(binding['episode_steps'], value)

    def test_episode_steps_rejects_non_integer_and_short_values(self):
        for value in (None, True, False, -1, 0, 1, 2.0, 720.0, '720', []):
            for configured in (value, {'default': value}):
                with self.subTest(configured=configured):
                    (self.engine/'kaggriculture.json').write_text(json.dumps(
                        {'configuration': {'episodeSteps': configured}}))
                    with self.assertRaisesRegex(ValueError, 'integer >= 2'):
                        P.expected_binding(self.job, self.evaluator, self.engine, self.opponents)

    def test_changed_candidate_bytes_not_reused(self):
        self.save_report();self.candidate.write_text('# new revision\n')
        result=self.rejected();self.assertIn('candidate_source',result['validation']['problems'])

    def test_changed_callable_in_same_file_not_reused(self):
        self.save_report();self.job['candidate']+='::alternative'
        self.assertIn('candidate_source',self.rejected()['validation']['problems'])

    def test_changed_opponent_bytes_not_reused(self):
        self.save_report();self.opponent.write_text('# opponent changed\n')
        self.assertIn('opponent_source:wanted',self.rejected()['validation']['problems'])

    def test_changed_evaluator_not_reused(self):
        self.save_report();self.evaluator.write_text(self.evaluator.read_text()+'# changed\n')
        self.assertIn('evaluator_sha256',self.rejected()['validation']['problems'])

    def test_changed_engine_member_not_reused(self):
        for name in ('kaggriculture.py','utils.py','kaggriculture.json'):
            with self.subTest(name=name):
                file=self.engine/name;original=file.read_bytes();self.save_report()
                file.write_bytes(original+b'\n')
                self.assertIn('engine_sha256',self.rejected()['validation']['problems'])
                file.write_bytes(original)

    def test_changed_default_loader_not_reused(self):
        self.save_report();self.loader.write_text('# newer loader\n')
        self.assertIn('loader_sha256',self.rejected()['validation']['problems'])

    def test_same_count_wrong_seed_and_opponent_not_reused(self):
        data=deepcopy(self.report);data['seeds']=[99]
        for g in data['games']:g.update(seed=99,opponent='wrong')
        self.save_report(data);result=self.rejected()
        self.assertIn('seeds',result['validation']['problems'])
        self.assertIn('game_cells',result['validation']['problems'])
        WITNESSES.append({'case':'same_count_wrong_cells','result':result})

    def test_duplicate_cell_cannot_replace_missing_seat(self):
        data=deepcopy(self.report);data['games'][1]=deepcopy(data['games'][0]);self.save_report(data)
        self.assertIn('game_cells',self.rejected()['validation']['problems'])

    def test_different_opponent_registry_with_same_count_not_reused(self):
        data=deepcopy(self.report);data['opponents']={'other':data['opponents']['wanted']};self.save_report(data)
        self.assertIn('opponent_labels',self.rejected()['validation']['problems'])

    def test_bool_seat_is_not_integer_seat(self):
        data=deepcopy(self.report);data['games'][1]['candidate_seat']=True;self.save_report(data)
        self.assertIn('game_cell',self.rejected()['validation']['problems'])

    def test_other_rng_or_deadline_not_reused(self):
        for mutation in ('rng','timeout','bool-timeout'):
            with self.subTest(mutation=mutation):
                data=deepcopy(self.report)
                if mutation=='rng':data['agent_rng_seed']+=1
                else:data['limits']['action_rpc_seconds']=True if mutation=='bool-timeout' else 2.0
                self.save_report(data);self.rejected()

    def test_different_episode_length_not_reused(self):
        data=deepcopy(self.report);data['games'][0]['episode_steps']=100;self.save_report(data)
        self.assertIn('episode_steps',self.rejected()['validation']['problems'])

    def test_incomplete_report_and_log_preserved_without_whole_shard_replay(self):
        data=deepcopy(self.report);data['games'][1].update(status='failed',scores=None,failure={'kind':'timeout'})
        self.save_report(data);self.assertIn('game_incomplete',self.rejected()['validation']['problems'])

    def test_malformed_reports_retained_without_crashing(self):
        for raw in (b'{',b'[]',b'null',b'{"games":{}}',b'\xff'):
            with self.subTest(raw=raw):
                self.save_report(raw=raw);self.rejected()

    def test_invalid_terminal_scores_not_reused(self):
        for scores in ([True,1],[float('nan'),1],['1',2],[1],None):
            with self.subTest(scores=scores):
                data=deepcopy(self.report);data['games'][0]['scores']=scores;self.save_report(data)
                self.assertIn('game_scores',self.rejected()['validation']['problems'])

    def test_running_marker_is_not_completed_report(self):
        data=deepcopy(self.report);data['progress']['state']='running';self.save_report(data)
        self.assertIn('progress_incomplete',self.rejected()['validation']['problems'])

    def test_missing_source_preserves_report_without_launch(self):
        self.save_report();self.candidate.unlink();result=self.run_existing()
        self.assertEqual(result['status'],'failed');self.assertEqual(result.get('reason'),'binding_unavailable')

    def test_orphan_log_is_not_silently_overwritten(self):
        self.log.parent.mkdir(parents=True);self.log.write_text('interrupted original attempt\n')
        self.rejected();self.assertFalse(self.target.exists())

    def test_new_job_runs_existing_command_once_then_reuses(self):
        self.fixture();result=P.run_job(self.job,self.evaluator,self.engine,self.opponents,self.out)
        self.assertEqual(result['status'],'complete');self.assertEqual(result['returncode'],0)
        self.assertEqual(self.run_existing()['status'],'reused-complete')
        self.assertEqual((self.evaluator.parent/'launches.txt').read_text(),'one\n')
        WITNESSES.append({'case':'new_fixture_evaluator_then_reuse','result':result})

    def test_new_job_cannot_publish_wrong_cells_as_complete(self):
        data=deepcopy(self.report);data['games'][0]['seed']=99;self.fixture(data)
        result=P.run_job(self.job,self.evaluator,self.engine,self.opponents,self.out)
        self.assertEqual(result['returncode'],0);self.assertEqual(result['status'],'failed')
        self.assertIn('game_cells',result['validation']['problems'])
        self.assertEqual(json.loads(self.target.read_text()),data)

    def test_source_changed_during_child_is_explicit_failure(self):
        self.fixture(mutate=str(self.candidate))
        result=P.run_job(self.job,self.evaluator,self.engine,self.opponents,self.out)
        self.assertEqual(result['status'],'failed')
        self.assertIn('source_changed_during_job',result['validation']['problems'])
        self.assertTrue(self.target.exists())

    def test_nonzero_exit_stays_failed_with_complete_fixture_rows(self):
        self.fixture(exit=7);result=P.run_job(self.job,self.evaluator,self.engine,self.opponents,self.out)
        self.assertEqual(result['status'],'failed');self.assertEqual(result['returncode'],7)
        self.assertTrue(self.target.exists());self.assertTrue(self.log.exists())

    def test_existing_default_limits_are_explicit_in_child_argv(self):
        self.fixture();self.assertEqual(P.run_job(self.job,self.evaluator,self.engine,self.opponents,self.out)['status'],'complete')
        args=json.loads((self.evaluator.parent/'received-args.json').read_text())
        for flag,value in (('--rng-seed','20260907'),('--action-timeout','1.0'),('--startup-timeout','10.0'),('--game-timeout','120.0'),('--loader',str(self.loader))):
            self.assertIn(flag,args);self.assertEqual(args[args.index(flag)+1],value)

    def test_unknown_extra_report_annotations_do_not_invalidate_direct_binding(self):
        data=deepcopy(self.report);data['unrelated_note']='preserved';data['candidate']['dependency_note']='not a direct-source claim'
        self.save_report(data);self.assertEqual(self.run_existing()['status'],'reused-complete')

    def test_cli_reports_mismatch_as_failure_without_replacing_old_rows(self):
        self.fixture()
        cfg=self.root/'config.json';cfg.write_text(json.dumps({'evaluator':str(self.evaluator),'engine':str(self.engine),
            'seeds':{'first':12,'last':12,'shard_size':1},'arms':{'candidate':str(self.candidate)},'opponents':self.opponents}))
        command=[sys.executable,'-B',str(TARGET),'--config',str(cfg),'--output',str(self.out),'--jobs','1']
        first=subprocess.run(command,capture_output=True,text=True,timeout=10);self.assertEqual(first.returncode,0,first.stderr)
        before=self.target.read_bytes();self.candidate.write_text('# replaced candidate\n')
        second=subprocess.run(command,capture_output=True,text=True,timeout=10)
        self.assertEqual(second.returncode,1,second.stdout+second.stderr)
        self.assertEqual(self.target.read_bytes(),before)
        states=json.loads((self.out/'run-state.json').read_text());self.assertEqual(states[0]['status'],'failed')
        self.assertEqual((self.evaluator.parent/'launches.txt').read_text(),'one\n')

    def test_input_job_and_lists_not_mutated(self):
        self.save_report();job=deepcopy(self.job);opponents=list(self.opponents)
        self.run_existing();self.assertEqual(self.job,job);self.assertEqual(self.opponents,opponents)

    def test_legacy_two_argument_check_remains_shape_only(self):
        self.save_report();self.assertTrue(P.valid_report(self.target,2))
        self.assertFalse(P.valid_report(self.target,3))

    def test_actual_evaluator_report_contract_is_consumed(self):
        evaluator_source=Path(os.environ.get('TITAN_EVALUATOR_SOURCE', TARGET.parent.parent/'cloud-eval/evaluate.py'))
        self.evaluator.write_bytes(evaluator_source.read_bytes())
        self.candidate.write_text('def agent(obs,cfg):return {}\n')
        self.opponent.write_text('def agent(obs,cfg):return {}\n')
        spec=importlib.util.spec_from_file_location('reuse_join_actual_evaluator',self.evaluator)
        evaluator=importlib.util.module_from_spec(spec);sys.modules[spec.name]=evaluator;spec.loader.exec_module(evaluator)
        self.addCleanup(sys.modules.pop,spec.name,None)
        class FixtureEngine:
            specification={'configuration':{'episodeSteps':{'default':3},'turnsPerDay':{'default':24}}}
            @staticmethod
            def interpreter(state,env):
                env.configuration.seed=None
                if not state[0].observation:
                    for seat,st in enumerate(state):
                        st.observation.update(player=seat,farms=[{'money':10},{'money':9}],private={})
                else:
                    for seat,st in enumerate(state):st.status='DONE';st.reward=10-seat
        hashes={n:sha(self.engine/n) for n in ('kaggriculture.py','kaggriculture.json','utils.py')}
        launches=[]
        def invoke_existing_main(command, **kwargs):
            launches.append(list(command));captured=io.StringIO()
            # Only engine construction is a test fixture. Existing main, play,
            # report writer, Actor, worker, pipes and four fixture-agent calls run.
            with patch.object(sys,'argv',command[2:]),patch.object(evaluator,'get_engine',return_value=(FixtureEngine(),hashes)),contextlib.redirect_stdout(captured):
                rc=evaluator.main()
            return subprocess.CompletedProcess(command,rc,captured.getvalue())
        with patch.object(P.subprocess,'run',invoke_existing_main):
            result=P.run_job(self.job,self.evaluator,self.engine,self.opponents,self.out)
        self.assertEqual(result['status'],'complete',result)
        self.assertEqual(len(launches),1)
        self.assertEqual(self.run_existing()['status'],'reused-complete')
        report=json.loads(self.target.read_text())
        self.assertEqual(report['evaluator_sha256'],sha(self.evaluator))
        self.assertEqual(report['progress']['state'],'complete')
        self.assertEqual(len(report['games']),2)
        self.assertTrue(all(g['status']=='complete' for g in report['games']))
        WITNESSES.append({'case':'actual_evaluator_join','evaluator_sha256':sha(self.evaluator),
                          'fixture_agent_calls':4,'synthetic_engine_episodes':2,'report_sha256':sha(self.target),
                          'result':result})

    def test_duplicate_requested_seeds_do_not_start_compute(self):
        self.job['seeds']=[12,12]
        with patch.object(P.subprocess,'run',side_effect=AssertionError('launched')):
            result=P.run_job(self.job,self.evaluator,self.engine,self.opponents,self.out)
        self.assertEqual(result['status'],'failed');self.assertEqual(result.get('reason'),'binding_unavailable')

    def test_official_starter_identity_uses_engine_not_nonexistent_entry_file(self):
        self.job['candidate']='official_starter';self.report['candidate']={'entry':'official_starter','engine_ref':'fixture'}
        self.save_report();self.assertEqual(self.run_existing()['status'],'reused-complete')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path);args=ap.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReportReuseTests))
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps({'scope':'actual panel helper and CLI; synthetic report/file/process fixtures',
            'source_sha256':sha(TARGET),'test_sha256':sha(Path(__file__)), 'tests':{'run':result.testsRun,'failures':len(result.failures),
            'errors':len(result.errors),'successful':result.wasSuccessful()},'python':sys.version,'engine_games':0,'official_policy_calls':0,
            'synthetic_engine_episodes':2,'fixture_agent_calls':4,
            'registered_game_seeds':[],'witnesses':WITNESSES,'failures':[{'test':str(t),'traceback':msg} for t,msg in result.failures],
            'errors':[{'test':str(t),'traceback':msg} for t,msg in result.errors]},indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
