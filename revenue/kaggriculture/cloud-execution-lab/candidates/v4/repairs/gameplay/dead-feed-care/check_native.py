# SPDX-License-Identifier: Apache-2.0
"""Executed W2 native wiring tests, not a duplicate service-policy oracle.

Engaged fixtures replace ONLY production.act's one returned action to reach the
service seam. The selected consumer, post-unit model, market/stock/finalization,
main entrypoint, real deadline and entire official interpreter remain native.
Natural unmodified production is measured separately by run_native_census.py.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import compose_native as composer
from native_support import authenticate, load_engine, load_native, new_world, sha, HELPER_SHA

ARGS = None
COUNTS = {'fixture_native_calls': 0, 'official_transition_pairs': 0, 'cancelled_calls': 0}


def prepare(species='COW', seat=0, *, ordered=False, step=250, cared=False, wheat=1,
            extra_care=False):
    state, env = new_world(ENGINE, STRUCT, step=step)
    farm = state[seat].observation.farms[seat]
    farm['farmer'] = [1,1]
    farm['hands'] = [[1,1]] if ordered else [[2,1]]
    tile = ENGINE._new_animal(species, 0)
    tile['fed_today'] = not ordered
    tile['cared_today'] = cared
    tile['fertilizer_available'] = True
    farm['tiles'][1][1] = tile
    private = state[seat].observation.private
    private['inventories'] = [{'WHEAT': wheat}, {}]
    private['shed'] = {'WHEAT': 8}
    private['seeds'] = {}
    parent = {'farmer': ['FEED'], 'hands': [['FEED']] if ordered else [['PASS']],
              'market': [['SELL','WHEAT',1]]}
    if extra_care:
        farm['hands'].append([1,1]);private['inventories'].append({})
        parent['hands'].append(['CARE'])
    return state, env, parent


def instance(parent, *, enabled=True, consumer='frozen'):
    data = json.loads((ARGS.package/'TITAN-CONFIG.json').read_text())
    data['r04_dead_feed_care'] = enabled
    if consumer != 'frozen':
        data.update(consumer=consumer, redundant_hire=False, crop_release=False,
                    idle_fertilizer=False, operating_stock=False)
    inst = MAIN._new_instance(ARGS.package, data)
    inst._initialize()
    inst.production = type('AuthoredFixture', (), {'act': lambda self, obs: deepcopy(parent)})()
    MAIN._INSTANCE = inst
    return inst


def invoke(inst, observation, cfg):
    COUNTS['fixture_native_calls'] += 1
    return MAIN.agent(deepcopy(observation), cfg)


class ComposerContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = (ARGS.baseline/'titan_runtime.py').read_text()

    def test_two_seams_only_and_idempotence(self):
        after = composer.compose_runtime(self.before)
        self.assertEqual(composer.compose_runtime(after), after)
        restored = after.replace(composer.SELECT_AFTER, composer.SELECT_BEFORE, 1).replace(
            composer.FEATURE_AFTER, composer.FEATURE_BEFORE, 1)
        self.assertEqual(restored, self.before)

    def test_unrelated_peer_edits_preserved(self):
        edited = self.before.replace('def _finish_production(self, obs, returned, cfg=None):',
                                    'def _finish_production(self, obs, returned, cfg=None):\n        # peer finalizer boundary')
        after = composer.compose_runtime(edited)
        self.assertIn('# peer finalizer boundary', after)
        self.assertEqual(after.replace(composer.SELECT_AFTER, composer.SELECT_BEFORE, 1).replace(
            composer.FEATURE_AFTER, composer.FEATURE_BEFORE, 1), edited)

    def test_unknown_seam_and_partial_install_fail(self):
        variants = [self.before.replace('selected = self.production.act(obs)',
                                        'selected = self.production.act(obs, cfg)'),
                    self.before.replace(composer.FEATURE_BEFORE, composer.FEATURE_AFTER),
                    composer.compose_runtime(self.before).replace("stage = 'dead_feed_care'", "stage = 'drift'"),
                    self.before.replace('class TitanAgent:', 'class OtherAgent:')]
        for text in variants:
            with self.subTest(digest=hash(text)), self.assertRaises(ValueError):
                composer.compose_runtime(text)

    def test_default_off_field_not_configuration(self):
        self.assertIs(RUNTIME.Features().r04_dead_feed_care, False)
        self.assertNotIn('r04_dead_feed_care', json.loads((ARGS.baseline/'TITAN-CONFIG.json').read_text()))

    def test_cli_wrong_helper_and_runtime_never_create_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            for runtime_sha, helper_sha in [('0'*64, HELPER_SHA),
                                           (sha(ARGS.baseline/'titan_runtime.py'), '0'*64)]:
                out=Path(tmp)/'candidate'
                with self.assertRaises(ValueError):
                    composer.materialize(ARGS.baseline, ARGS.package/'r04_dead_feed_care.py', out,
                                         runtime_sha, helper_sha)
                self.assertFalse(out.exists())


class NativeWire(unittest.TestCase):
    def test_observed_and_ordered_feed_reach_consumer_snapshot_and_engine(self):
        for species in ('GOOSE','COW','SHEEP'):
            for seat in (0,1):
                for ordered in (False,True):
                    with self.subTest(species=species,seat=seat,ordered=ordered):
                        state,env,parent=prepare(species,seat,ordered=ordered)
                        obs=deepcopy(state[seat].observation)
                        inst=instance(parent)
                        before=deepcopy(parent)
                        out=invoke(inst,obs,env.configuration)
                        self.assertEqual(inst.diagnostics['status'],'completed')
                        actor=1 if ordered else 0
                        self.assertEqual([out['farmer'],*out['hands']][actor],['CARE'])
                        self.assertEqual([inst.selected['farmer'],*inst.selected['hands']][actor],['CARE'])
                        self.assertEqual(inst.diagnostics['parent_calls'],1)
                        self.assertEqual(parent,before)
                        post=inst._selected_snapshot(obs,out)
                        self.assertIsNotNone(post, 'completed units lost their authentic snapshot')
                        self.assertTrue(post['farms'][seat]['tiles'][1][1]['cared_today'])
                        self.assertTrue(post['farms'][seat]['tiles'][1][1]['fed_today'])
                        self.assertEqual(inst.consumer.selected_post_units_binding,
                                         (obs['step'],seat,out['farmer'],out['hands']))
                        left,right=deepcopy(state),deepcopy(state)
                        left[seat].action=deepcopy(out)
                        right[seat].action=deepcopy(out)
                        right[seat].action['farmer']=parent['farmer'][:]
                        right[seat].action['hands']=deepcopy(parent['hands'])
                        if actor==0:right[seat].action['farmer']=['CARE']
                        else:right[seat].action['hands'][actor-1]=['CARE']
                        e1,e2=deepcopy(env),deepcopy(env)
                        ENGINE.interpreter(left,e1);ENGINE.interpreter(right,e2)
                        COUNTS['official_transition_pairs']+=1
                        self.assertEqual(left,right)
                        self.assertEqual(e1,e2)
                        self.assertTrue(left[seat].observation.farms[seat]['tiles'][1][1]['cared_today'])

    def test_disabled_does_not_load_or_call_helper(self):
        state,env,parent=prepare(ordered=True)
        inst=instance(parent,enabled=False)
        with patch.object(HELPER,'apply_dead_feed_care',side_effect=AssertionError('disabled helper called')):
            out=invoke(inst,state[0].observation,env.configuration)
        self.assertEqual(out['farmer'],parent['farmer'])
        self.assertEqual(out['hands'],parent['hands'])
        self.assertFalse(inst._selected_snapshot(state[0].observation,out)['farms'][0]['tiles'][1][1]['cared_today'])

    def test_failed_first_feed_late_day_and_later_care_unchanged(self):
        cases=[{'ordered':True,'wheat':0},{'ordered':True,'extra_care':True},
               {'step':680},{'cared':True}]
        for kw in cases:
            with self.subTest(case=kw):
                state,env,parent=prepare(**kw)
                inst=instance(parent)
                out=invoke(inst,state[0].observation,env.configuration)
                self.assertEqual(out['farmer'],parent['farmer'])
                self.assertEqual(out['hands'],parent['hands'])

    def test_helper_cancellation_preserves_completed_parent_not_stale_prior_turn(self):
        for seat in (0,1):
            state,env,parent=prepare(seat=seat,ordered=True)
            inst=instance(parent)
            inst.selected={'farmer':['DROP'],'hands':[],'market':[['SELL','MILK',99]]}
            original_timer=RUNTIME.deadline._DeadlineTimer
            timers=[]
            def factory(seconds):
                timer=original_timer(seconds);timers.append(timer);return timer
            def interrupt(*args,**kwargs):
                raise timers[-1].expired
            with patch.object(RUNTIME.deadline,'_DeadlineTimer',side_effect=factory), \
                 patch.object(HELPER,'apply_dead_feed_care',side_effect=interrupt):
                out=invoke(inst,state[seat].observation,env.configuration)
            COUNTS['cancelled_calls']+=1
            self.assertEqual(out['farmer'],parent['farmer'])
            self.assertEqual(out['hands'],parent['hands'])
            self.assertEqual(inst.selected,parent)
            self.assertEqual(inst.diagnostics.get('fallback_stage'),'dead_feed_care')
            self.assertIsNone(inst.consumer.selected_post_units)
            self.assertIsNone(inst._selected_snapshot(state[seat].observation,out))
            self.assertFalse(inst.ready)

    def test_every_executed_helper_line_can_cancel_to_parent(self):
        state,env,parent=prepare(ordered=True)
        inst=instance(parent)
        helper_path=str((ARGS.package/'r04_dead_feed_care.py').resolve())
        executed=set()
        def collect(frame,event,arg):
            if event=='line' and frame.f_code.co_filename==helper_path:
                executed.add(frame.f_lineno)
            return collect
        prior=sys.gettrace()
        try:
            sys.settrace(collect)
            out=invoke(inst,state[0].observation,env.configuration)
        finally:
            sys.settrace(prior)
        self.assertEqual(out['hands'][0],['CARE'])
        self.assertGreater(len(executed),20)
        for cut in sorted(executed):
            with self.subTest(helper_line=cut):
                state,env,parent=prepare(ordered=True)
                inst=instance(parent)
                original_timer=RUNTIME.deadline._DeadlineTimer
                timers=[]
                def factory(seconds):
                    timer=original_timer(seconds);timers.append(timer);return timer
                def stop(frame,event,arg):
                    if (event=='line' and frame.f_code.co_filename==helper_path
                            and frame.f_lineno==cut):
                        raise timers[-1].expired
                    return stop
                try:
                    with patch.object(RUNTIME.deadline,'_DeadlineTimer',side_effect=factory):
                        sys.settrace(stop)
                        out=invoke(inst,state[0].observation,env.configuration)
                finally:
                    sys.settrace(prior)
                COUNTS['cancelled_calls']+=1
                self.assertEqual(out['farmer'],parent['farmer'])
                self.assertEqual(out['hands'],parent['hands'])
                self.assertEqual(inst.selected,parent)
                self.assertEqual(inst.diagnostics.get('fallback_stage'),'dead_feed_care')
                self.assertIsNone(inst.consumer.selected_post_units)

    def test_helper_result_detached_from_completed_checkpoint(self):
        state,env,parent=prepare(ordered=True)
        inst=instance(parent)
        result_box=[];original=HELPER.apply_dead_feed_care
        def capture(*args,**kwargs):
            result=original(*args,**kwargs);result_box.append(result);return result
        with patch.object(HELPER,'apply_dead_feed_care',side_effect=capture):
            out=invoke(inst,state[0].observation,env.configuration)
        self.assertEqual(len(result_box),1, 'native hook did not call the exact helper')
        result_box[0]['hands'][0][0]='DROP'
        self.assertEqual(inst.selected['hands'][0],['CARE'])
        self.assertEqual(out['hands'][0],['CARE'])
        out['hands'][0][0]='PASS'
        self.assertEqual(inst.selected['hands'][0],['CARE'])

    def test_nonfrozen_consumers_receive_same_rewrite(self):
        for consumer in ('ordered','parent'):
            state,env,parent=prepare(ordered=True)
            inst=instance(parent,consumer=consumer)
            out=invoke(inst,state[0].observation,env.configuration)
            self.assertEqual(out['hands'][0],['CARE'])
            self.assertEqual(inst.selected['hands'][0],['CARE'])
            self.assertEqual(inst.diagnostics['parent_calls'],1)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--runtime-sha256',required=True)
    p.add_argument('--output',type=Path,required=True)
    ARGS=p.parse_args()
    AUTH=authenticate(ARGS.package,ARGS.manifest,runtime_sha=ARGS.runtime_sha256,enabled=True,composed=True)
    authenticate(ARGS.baseline,ARGS.manifest)
    ENGINE,STRUCT,HASHES=load_engine(ARGS.package)
    MAIN=load_native(ARGS.package)
    import titan_runtime as RUNTIME
    HELPER=RUNTIME.load('_titan_dead_feed_care',ARGS.package/'r04_dead_feed_care.py',cache=True)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    report={'auth':AUTH,'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'skips':len(result.skipped),'optimized':not __debug__,'counts':COUNTS,
            'limits':['Engaged source fixtures substitute production.act only.',
                      'No natural activation or economic promotion follows from these controls.']}
    ARGS.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    sys.exit(0 if result.wasSuccessful() and not result.skipped else 1)
