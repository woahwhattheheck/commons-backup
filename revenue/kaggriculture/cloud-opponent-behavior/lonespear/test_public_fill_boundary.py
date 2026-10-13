"""Public fill boundary regression. No policy calls, engine calls, or new games."""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
TARGET = HERE / 'behavior.py'


def load(path):
    spec = importlib.util.spec_from_file_location('fill_boundary_target', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FillBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load(TARGET)

    def pair(self, actor=1, fills=1, day=4):
        base = {'money': 1000.0, 'hands': [], 'hires_today': 0}
        before = {'step': 100, 'day': day,
                  'farms': [copy.deepcopy(base), copy.deepcopy(base)]}
        after = copy.deepcopy(before)
        after['step'] += 1
        after['farms'][actor].update(money=998.0, hires_today=fills,
                                     hands=[[4,4] for _ in range(fills)])
        return before, after

    def assert_unknown(self, before, after, actor=1):
        saved = copy.deepcopy((before, after))
        report = self.module.observed_fill(before, after, actor=actor)
        self.assertEqual(report['status'], 'unknown')
        self.assertIsNone(report['fills'])
        self.assertNotIn('public_cash_delta', report)
        self.assertIn('reason', report)
        self.assertEqual((before, after), saved)

    def test_short_or_missing_farm_arrays_are_unknown(self):
        for actor in (0,1):
            for which in (0,1):
                for farms in (None, [], [{}], [None], {}, 'farms'):
                    pair=self.pair(actor); pair[which]['farms']=farms
                    with self.subTest(actor=actor,which=which,farms=repr(farms)):
                        self.assert_unknown(*pair,actor)

    def test_extra_farms_return_unknown(self):
        for which in (0,1):
            pair=self.pair(); pair[which]['farms'].append(copy.deepcopy(pair[which]['farms'][0]))
            with self.subTest(which=which): self.assert_unknown(*pair)

    def test_nonmapping_actor_farms_are_unknown(self):
        for actor in (0,1):
            for which in (0,1):
                for bad in (None, [], 'farm', 10):
                    pair=self.pair(actor); pair[which]['farms'][actor]=bad
                    with self.subTest(actor=actor,which=which,bad=repr(bad)):
                        self.assert_unknown(*pair,actor)

    def test_nonmapping_observations_are_unknown(self):
        for which in (0,1):
            for bad in (None, [], 1, 'frame'):
                pair=list(self.pair()); pair[which]=bad
                with self.subTest(which=which,bad=repr(bad)): self.assert_unknown(*pair)

    def test_nonfinite_and_out_of_range_cash_stay_unknown(self):
        # Huge integers can raise OverflowError in math.isfinite.
        for cash in (10**1000, float('inf'), float('-inf'), -1, True, '1000'):
            before, after=self.pair(); after['farms'][1]['money']=cash
            with self.subTest(cash_type=type(cash).__name__): self.assert_unknown(before,after)

    def test_valid_tuple_arrays_and_mapping_subclasses_remain_supported(self):
        class Farm(dict): pass
        before,after=self.pair()
        before['farms']=tuple(Farm(f) for f in before['farms'])
        after['farms']=tuple(Farm(f) for f in after['farms'])
        after['farms'][1]['hands']=tuple(after['farms'][1]['hands'])
        report=self.module.observed_fill(before,after,actor=1)
        self.assertEqual((report['status'],report['fills'],report['public_cash_delta']),('known',1,-2.0))

    def test_valid_both_seat_zero_and_positive_fills_preserve_schema(self):
        for actor in (0,1):
            for fills in (0,1,6):
                pair=self.pair(actor,fills); saved=copy.deepcopy(pair)
                report=self.module.observed_fill(*pair,actor=actor)
                with self.subTest(actor=actor,fills=fills):
                    self.assertEqual(report, {'status':'known','fills':fills,
                        'public_cash_delta':-2.0,
                        'interpretation':'cash delta includes all other market orders; not hire-only spending'})
                    self.assertEqual(pair,saved)

    def test_reset_gap_and_count_disagreement_remain_unknown(self):
        for mode in ('day_reset','gap','repeat','count'):
            before,after=self.pair()
            if mode=='day_reset': after['day']+=1
            elif mode=='gap': after['step']+=1
            elif mode=='repeat': after['step']=before['step']
            else: after['farms'][1]['hires_today']+=1
            with self.subTest(mode=mode): self.assert_unknown(before,after)

    def test_invalid_actor_remains_unknown(self):
        for actor in (-1,2,True,None,'1'):
            with self.subTest(actor=actor): self.assert_unknown(*self.pair(),actor=actor)

    def test_private_and_action_payloads_are_not_read(self):
        class Unreadable(dict):
            def __getitem__(self,k): raise AssertionError('private/action payload read')
            def get(self,k,*a): raise AssertionError('private/action payload read')
        before,after=self.pair()
        for frame in (before,after):
            frame['private']=Unreadable(); frame['actions']=Unreadable()
        self.assertEqual(self.module.observed_fill(before,after,actor=1)['fills'],1)

    def test_unread_target_peer_record_does_not_affect_public_delta(self):
        # This consumer only needs the named actor's farm, not rival private data
        # or the other farm's fields. Do not broaden its validation to those.
        for actor in (0,1):
            before,after=self.pair(actor)
            before['farms'][1-actor]=None;after['farms'][1-actor]=None
            with self.subTest(actor=actor):
                self.assertEqual(self.module.observed_fill(before,after,actor=actor)['fills'],1)

    def test_invalid_step_values_return_unknown(self):
        for which in (0,1):
            for step in (None, -1, True, 100.0, '100'):
                pair=self.pair();pair[which]['step']=step
                with self.subTest(which=which,step=repr(step)):
                    self.assert_unknown(*pair)

    def test_current_peer_public_clock_paths_are_preserved(self):
        for actor in (0,1):
            for period in (10,24):
                for mode in ('explicit','mixed','sparse','null'):
                    before,after=self.pair(actor)
                    before.update(day=4,hour=1,step=4*period+1)
                    after.update(day=4,hour=2,step=4*period+2)
                    if mode=='mixed': before.pop('step')
                    elif mode=='sparse': before.pop('step');after.pop('step')
                    elif mode=='null': before['step']=None;after['step']=None
                    saved=copy.deepcopy((before,after))
                    report=self.module.observed_fill(before,after,actor=actor,
                        configuration={'turnsPerDay':period})
                    with self.subTest(actor=actor,period=period,mode=mode):
                        self.assertEqual(report['status'],'known')
                        self.assertEqual(report['fills'],1)
                        self.assertEqual(report['public_cash_delta'],-2.0)
                        self.assertEqual((before,after),saved)

    def test_cancellation_propagates(self):
        class Cancelled(BaseException): pass
        class CancellingFrame(dict):
            def get(self,*a): raise Cancelled()
        with self.assertRaises(Cancelled):
            self.module.observed_fill(CancellingFrame(),self.pair()[1],actor=1)


def main():
    global TARGET
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=TARGET)
    parser.add_argument('--json-output',type=Path)
    args=parser.parse_args(); TARGET=args.source.resolve(strict=True)
    if args.json_output:
        for incoming in (TARGET, Path(__file__)):
            if args.json_output.resolve() == incoming.resolve() or (args.json_output.exists() and args.json_output.samefile(incoming)):
                parser.error('Use a JSON result destination distinct from source files')
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(FillBoundaryTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'skipped':len(result.skipped),'passed':result.wasSuccessful(),
        'source_sha256':hashlib.sha256(TARGET.read_bytes()).hexdigest(),
        'failure_ids':[t.id() for t,_ in result.failures],
        'error_ids':[t.id() for t,_ in result.errors],
        'new_games':0,'policy_calls':0,'engine_calls':0}
    if args.json_output:
        args.json_output.parent.mkdir(parents=True,exist_ok=True)
        args.json_output.write_text(json.dumps(report,indent=2)+'\n')
    return not result.wasSuccessful()


if __name__=='__main__': sys.exit(main())
