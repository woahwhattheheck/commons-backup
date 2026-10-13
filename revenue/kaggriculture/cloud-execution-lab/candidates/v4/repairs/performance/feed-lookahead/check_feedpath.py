# SPDX-License-Identifier: Apache-2.0
"""Independent differential contracts for the emitted FEEDPATH consumers.
Set TITAN_NATIVE to the authenticated complete native fixture directory.
Set FEEDPATH_CANDIDATE only for deliberately broken-source controls.
"""
from __future__ import annotations
import ast
from copy import deepcopy
import os
from pathlib import Path
import random
import sys
import types
import unittest
from compose_feedpath import compose, fragments, INLINE, digest

ROOT = Path(os.environ['TITAN_NATIVE']).resolve()
sys.path[:0] = [str(ROOT), str(ROOT/'checks')]
SOURCE = (ROOT/'operating_stock.py').read_text()
if digest(SOURCE.encode()) != 'aade61ed3bcaca175998ab2871b97042dde0036950f038aef6326482e0fdd21c':
    raise RuntimeError('contract baseline must be the authenticated original native source')
CANDIDATE = (Path(os.environ['FEEDPATH_CANDIDATE']).read_text()
             if os.environ.get('FEEDPATH_CANDIDATE') else compose(SOURCE))

def module(source):
    result = types.ModuleType('feedpath_contract')
    exec(compile(source, '<feedpath-contract>', 'exec'), result.__dict__)
    return result

BASE, CAND = module(SOURCE), module(CANDIDATE)
import mechanics as MECHANICS
from test_feed_stock import FeedStockTests
from test_operating_stock import OperatingStockTests


def lookup(source, reference):
    # Extract the actual emitted actor-lookup prefix, not a duplicate candidate.
    body = fragments(source)['_feed_window'][2]
    start = body.index('                ', body.index('for actor, pos in enumerate(positions):')+1)
    stop = body.index('                if not isinstance(action, list)', start)
    prefix = body[start:stop]
    text = ('def loop(row, positions):\n    out = []\n'
            '    for actor, pos in enumerate(positions):\n' +
            ''.join(line[8:]+'\n' for line in prefix.splitlines()) +
            '        out.append(action)\n    return out\n')
    env = {'_action': reference._action}
    exec(compile(text, '<actual-emitted-prefix>', 'exec'), env)
    return env['loop']

OLD_LOOP, NEW_LOOP = lookup(SOURCE, BASE), lookup(CANDIDATE, CAND)

def outcome(function, *args):
    try:
        return ('ok', function(*args))
    except Exception as error:
        return ('error', type(error).__name__, str(error))


def fixture(kind, hands=1, carried=0, seat=0):
    f = (FeedStockTests if kind == 'feed' else OperatingStockTests)()
    f.setUp()
    for _ in range(hands-1):
        f.farm['hands'].append([0, 0]); f.private['inventories'].append({})
        f.selected['hands'].append(['PASS'])
        for row in f.route:
            row['hands'].append(['PASS'])
    product = 'WHEAT' if kind == 'feed' else 'FERTILIZER'
    f.private['inventories'][1][product] = carried
    f.obs['player'] = seat
    return f


def arguments(f):
    return (MECHANICS, f.obs, {}, f.selected, f.farm, f.private, f.route, ())


class FeedpathContracts(unittest.TestCase):
    def test_compose_idempotent(self):
        self.assertEqual(compose(compose(SOURCE)), compose(SOURCE))

    def test_exact_dependency_drift_rejected(self):
        for needle, replacement in (("return [row.get('farmer')", "return  [row.get('farmer')"), ('units = _units(row)', 'units = list(_units(row))')):
            with self.subTest(needle=needle), self.assertRaises(ValueError):
                compose(SOURCE.replace(needle, replacement, 1))

    def test_unrelated_source_preserved(self):
        changed = SOURCE.replace("reservation_basis='distinct_productive_obligations_and_market_slots'",
                                 "reservation_basis='external-correctness-edit'")
        self.assertIn("reservation_basis='external-correctness-edit'", compose(changed))
        original_funcs, next_funcs = fragments(SOURCE), fragments(compose(SOURCE))
        for name in original_funcs.keys()-{'_feed_window','_bonus_water_service','protect_operating_stock'}:
            self.assertEqual(original_funcs[name][2], next_funcs[name][2])

    def test_changed_loop_header_rejected(self):
        with self.assertRaises(ValueError):
            compose(SOURCE.replace('enumerate(positions)', 'enumerate(positions, 1)', 1))

    def test_partial_composition_rejected(self):
        before, after = fragments(SOURCE), fragments(compose(SOURCE))
        partial = SOURCE.replace(before['_feed_window'][2], after['_feed_window'][2], 1)
        with self.assertRaises(ValueError):
            compose(partial)

    def test_reserved_name_collision_rejected(self):
        with self.assertRaises(ValueError):
            compose(SOURCE.replace('    now = _whole(observation', '    _fp_hands = 0\n    now = _whole(observation', 1))

    def test_duplicate_helper_rejected(self):
        with self.assertRaises(ValueError):
            compose(SOURCE+'\n'+fragments(SOURCE)['_units'][2])

    def test_crlf_rejected(self):
        with self.assertRaises(ValueError):
            compose(SOURCE.replace('\n', '\r\n'))

    def test_schema_matrix_and_missing_actors(self):
        for farmer in (None, [], ['PASS'], ['CARE'], 'x', 0, False):
            for hands in (None, [], [['FEED']], [[],None,['WEST']], ('x',[]), 'xy', 3, False):
                for count in (0,1,2,4,12):
                    with self.subTest(farmer=farmer,hands=hands,count=count):
                        row={'farmer':farmer,'hands':hands}
                        self.assertEqual(outcome(OLD_LOOP,row,range(count)), outcome(NEW_LOOP,row,range(count)))
        self.assertEqual(OLD_LOOP({},range(4)), NEW_LOOP({},range(4)))

    def test_alias_and_fresh_pass(self):
        a=['FEED'];b=['CARE'];row={'farmer':a,'hands':[b,b,[]]}
        result=NEW_LOOP(row,range(7))
        self.assertIs(result[0],a);self.assertIs(result[1],b);self.assertIs(result[2],b)
        self.assertIsNot(result[3],result[4]);self.assertIsNot(result[4],result[5])
        result[1].append('sentinel');self.assertEqual(b,['CARE','sentinel'])

    def test_reads_after_in_place_and_whole_row_mutation(self):
        row={'farmer':['PASS'],'hands':[['WEST']]}
        self.assertEqual(NEW_LOOP(row,range(2)),OLD_LOOP(row,range(2)))
        row['hands'][0]=['EAST']
        self.assertEqual(NEW_LOOP(row,range(2)),OLD_LOOP(row,range(2)))
        row['hands']=[['FEED'],['CARE']]
        self.assertEqual(NEW_LOOP(row,range(3)),OLD_LOOP(row,range(3)))

    def test_mapping_get_order_and_generator_consumption(self):
        class Row(dict):
            def get(self,key,default=None):
                self.log.append(key);return super().get(key,default)
        for make_hands in (lambda:iter([['FEED'],['CARE']]),lambda:[['FEED']]):
            results=[]
            for fn in (OLD_LOOP,NEW_LOOP):
                row=Row(farmer=['PASS'],hands=make_hands());row.log=[]
                results.append((outcome(fn,row,range(4)),row.log))
            self.assertEqual(*results)

    def test_list_subclass_iteration_is_not_bypassed(self):
        class Hands(list):
            def __iter__(self):
                return iter([['CARE']])
        row={'farmer':['PASS'],'hands':Hands([['FEED']])}
        self.assertEqual(OLD_LOOP(row,range(3)),NEW_LOOP(row,range(3)))

    def test_action_truth_can_replace_hands_between_actors(self):
        def execute(fn):
            row={'farmer':['PASS']}
            class Mutator:
                def __bool__(self):
                    row['hands']=[['WEST'],['EAST']];return True
            action=Mutator();row['hands']=[action,['FEED']]
            out=fn(row,range(3))
            return out[0],out[1] is action,out[2]
        self.assertEqual(execute(OLD_LOOP),execute(NEW_LOOP))
        self.assertEqual(execute(NEW_LOOP),(['PASS'],True,['EAST']))

    def test_random_lookup_values(self):
        rng=random.Random(91241)
        values=[[],None,['PASS'],['FEED'],['PICKUP','WHEAT',3],['PLACE','COW'],False]
        for _ in range(2000):
            row={'farmer':deepcopy(rng.choice(values)),
                 'hands':[deepcopy(rng.choice(values)) for _ in range(rng.randrange(40))]}
            before=deepcopy(row);n=rng.randrange(48)
            self.assertEqual(OLD_LOOP(row,range(n)),NEW_LOOP(row,range(n)))
            self.assertEqual(row,before)

    def test_consumer_cross_product(self):
        self.engaged=0
        for kind in ('feed','fert'):
            key='protect_feed_stock' if kind=='feed' else 'protect_operating_stock'
            for hands in (1,4,8,16,32):
                for carried in (0,1,2):
                    for seat in (0,1):
                        f=fixture(kind,hands,carried,seat);args=arguments(f)
                        before=deepcopy(args[1:]);a=outcome(getattr(BASE,key),*args);b=outcome(getattr(CAND,key),*args)
                        with self.subTest(kind=kind,hands=hands,carried=carried,seat=seat):
                            self.assertEqual(a,b);self.assertEqual(args[1:],before)
                            self.assertEqual(a[1][0] is f.selected,b[1][0] is f.selected)
                            self.engaged+=int(b[0]=='ok' and b[1][1]['changed'])
        self.assertGreater(self.engaged,0)

    def test_adverse_route_and_reset_controls(self):
        cases=[(461,['DROP']),(461,['PICKUP','WHEAT',0]),(462,[]),(463,['DIG']),
               (464,['PLACE','WHEAT',2]),(465,['FEED']),(462,None),(461,['PLANT','CARROT'])]
        for kind in ('feed','fert'):
            key='protect_feed_stock' if kind=='feed' else 'protect_operating_stock'
            for step,action in cases:
                f=fixture(kind,4);f.route[step]['hands'][0]=deepcopy(action)
                self.assertEqual(outcome(getattr(BASE,key),*arguments(f)),outcome(getattr(CAND,key),*arguments(f)))
            for now in (455,460,463,479,480,694,695,718):
                f=fixture(kind,4);f.obs['step']=now;f.obs['day']=now//24
                self.assertEqual(outcome(getattr(BASE,key),*arguments(f)),outcome(getattr(CAND,key),*arguments(f)))


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(FeedpathContracts)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() and result.testsRun==17 and not result.skipped else 1)
