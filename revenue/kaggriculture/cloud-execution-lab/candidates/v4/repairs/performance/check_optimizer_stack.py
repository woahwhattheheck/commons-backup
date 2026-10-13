# SPDX-License-Identifier: Apache-2.0
"""Executable cross-component contracts for the single native optimizer stack.

CANOPY owns the complementary interruption/lifetime checker. This suite covers
complete plans/diagnostics/callback order, receipt/score interactions, source
preservation and actual CLI refusal. All assertions survive python -O.
"""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import itertools
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from compose_optimizer_stack import COMPONENTS, SOURCE_GIT, compose, git_blob, load_components

OUTPUT_GIT = '16dde00627effa5d0ae4d73a8e05a295e9534e1f'
RUNTIME = None
PARTS = None
COUNTS = {'optimizer_pairs': 0, 'score_pairs': 0, 'receipt_pairs': 0,
          'cli_rejections': 0, 'dependency_rejections': 0}


def module(raw, name):
    obj = types.ModuleType(name)
    obj.__file__ = str(RUNTIME / 'selected_sell_core.py')
    exec(compile(raw, obj.__file__, 'exec'), obj.__dict__)
    return obj


def cases():
    rng = random.Random(9182026)
    goods = ('WHEAT','CARROT','TOMATO','STRAWBERRY','MELON','EGG','MILK','WOOL','FERTILIZER')
    for index in range(324):
        now = rng.choice([0,23,241,696,710])
        horizon = rng.choice([1,3,8,18])
        end = min(718, now + horizon)
        quantity = rng.choice([0,1,3,8,17])
        config = {'sellAcceptanceRule': ('strict','expected_downside','minimax_regret')[index % 3],
                  'sellDownsideBound': 100,
                  'townShopSellInterval': rng.choice([3,4,7]),
                  'townCenterSellInterval': rng.choice([12,24]),
                  'sellScenarioWeights': {'no_rival': 3, 'observed_paired': 2,
                                         'observed_later_order': 1}}
        yield {'item': goods[index % len(goods)], 'quantity': quantity,
               'inventory': rng.choice([-10,1,6000,10000,20000,100000]),
               'params': None, 'shops': rng.choice([[], ['YARN_STORE'],
                         ['SMOOTHIE_SHOP','SMOOTHIE_SHOP','FARMERS_MARKET','YARN_STORE']]),
               'config': config, 'now': now,
               'dates': sorted(set([now, min(end,now+1), end])),
               'reference': ((now,quantity),), 'rival_quantity': rng.choice([0,1,8,20]),
               'minimum_now': rng.choice([0,quantity]), 'last': 718}, index


class StackContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(RUNTIME))
        cls.raw = (RUNTIME / 'selected_sell_core.py').read_bytes()
        cls.output, cls.trace = compose(cls.raw, PARTS)
        cls.old = module(cls.raw, '_weave_old')
        cls.new = module(cls.output, '_weave_new')
        cls.parts = load_components(PARTS)

    def test_01_exact_complete_stack(self):
        self.assertEqual(git_blob(self.raw), SOURCE_GIT)
        self.assertEqual(git_blob(self.output), OUTPUT_GIT)
        self.assertEqual([row['component'] for row in self.trace['stages']],
                         ['SIEVE','MEADOW','EVENTPATH','CACHELIFE'])
        again, trace = compose(self.raw, PARTS)
        self.assertEqual((again,trace), (self.output,self.trace))

    def test_02_source_and_reapplication_rejected(self):
        for source in [self.raw+b'\n', self.output, self.raw.replace(b'MarketPath', b'ChangedPath', 1)]:
            with self.assertRaises(ValueError):
                compose(source, PARTS)

    def test_03_every_component_missing_rejected(self):
        for _,relative,_ in COMPONENTS:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / 'parts'; shutil.copytree(PARTS, root)
                (root / relative).unlink()
                with self.assertRaises(OSError):
                    compose(self.raw, root)
                COUNTS['dependency_rejections'] += 1

    def test_04_every_component_drift_rejected(self):
        for _,relative,_ in COMPONENTS:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / 'parts'; shutil.copytree(PARTS, root)
                path = root / relative; path.write_bytes(path.read_bytes()+b'\n# drift\n')
                with self.assertRaises(ValueError):
                    compose(self.raw, root)
                COUNTS['dependency_rejections'] += 1

    def test_05_sieve_requires_first_position(self):
        for data in [self.parts['MEADOW'].transform(self.raw.decode()).encode(),
                     self.parts['EVENTPATH'].compose(self.raw.decode()).encode()]:
            with self.assertRaises(ValueError):
                self.parts['SIEVE'].transform(data)

    def test_06_disjoint_receipt_and_score_edits_commute(self):
        first = self.parts['SIEVE'].transform(self.raw).decode()
        m,e = self.parts['MEADOW'], self.parts['EVENTPATH']
        a = e.compose(m.transform(first)); b = m.transform(e.compose(first))
        self.assertEqual(a,b)
        self.assertEqual(self.trace['stages'][2]['output_git'],git_blob(a.encode()))
        self.assertEqual(m.transform(a),a)
        self.assertEqual(e.compose(a),a)

    def test_07_unrelated_top_level_source_preserved(self):
        def untouched(raw):
            tree = ast.parse(raw)
            lines = raw.decode().splitlines(keepends=True)
            return {node.name: ''.join(lines[node.lineno-1:node.end_lineno])
                    for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))
                    and node.name not in ['MarketPath','optimize_lot']}
        self.assertEqual(untouched(self.raw), untouched(self.output))
        def unaffected_methods(raw):
            tree = ast.parse(raw)
            owner = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MarketPath')
            lines=raw.decode().splitlines(keepends=True)
            return {n.name: ''.join(lines[n.lineno-1:n.end_lineno]) for n in owner.body
                    if isinstance(n,ast.FunctionDef) and n.name not in
                    ['score','_single','_joint','_receipt_series','_score_eventpath_reference']}
        self.assertEqual(unaffected_methods(self.raw),unaffected_methods(self.output))

    def test_08_complete_optimizer_and_physical_callback_order(self):
        for kwargs,index in cases():
            logs=[[],[]]; results=[]
            for which,core in enumerate([self.old,self.new]):
                def capacity(plan):
                    frozen=tuple(plan); logs[which].append(frozen)
                    # Distinct nonmonotone capacity worlds include forced rescue.
                    return index % 4 == 0 or sum((t%7+1)*q for t,q in plan) % (index%3+2) != 1
                results.append(core.optimize_lot(**copy.deepcopy(kwargs),capacity_ok=capacity))
            with self.subTest(index=index,item=kwargs['item'],rule=kwargs['config']['sellAcceptanceRule']):
                self.assertEqual(results[0],results[1])
                self.assertEqual(logs[0],logs[1])
            COUNTS['optimizer_pairs'] += 1

    def test_09_sparse_score_and_receipt_interaction(self):
        rng=random.Random(74179)
        for index in range(1600):
            item=('WOOL','STRAWBERRY','FERTILIZER','WHEAT')[index%4]
            now=rng.choice([0,23,241,695]);end=now+rng.choice([1,3,8,23])
            quantity=rng.choice([0,1,13,50,100]);inv=rng.choice([-17,0,10000,15000,100000])
            config={};shops=['YARN_STORE','YARN_STORE','FARMERS_MARKET','SMOOTHIE_SHOP']
            args=(item,inv,None,shops,config,now,end)
            old=self.old.MarketPath(*args);new=self.new.MarketPath(*args)
            plan=((now,quantity//2),(end,quantity-quantity//2))
            rival=((now+1, index%20),(end-1,3)) if index%2 else index%35
            alignment=('paired','before','after')[index%3]
            self.assertEqual(old.score(plan,quantity,rival,alignment,index%5==0),
                             new.score(plan,quantity,rival,alignment,index%5==0))
            COUNTS['score_pairs'] += 1

    def test_10_receipt_series_bounds_and_fallbacks(self):
        for item in ('WHEAT','WOOL','STRAWBERRY','FERTILIZER'):
            args=(item,10000,None,[],{},0,8)
            old=self.old.MarketPath(*args);new=self.new.MarketPath(*args)
            for inv in [-1,0,10000,100000,2**53]:
                for own in [0,1,7,13,100,101]:
                    self.assertEqual(old.single(inv,own),new.single(inv,own))
                    COUNTS['receipt_pairs']+=1
                    for rival in [0,1,13,100,101]:
                        for alignment in ['paired','before','after']:
                            self.assertEqual(old.joint(inv,own,rival,alignment),
                                             new.joint(inv,own,rival,alignment))
                            COUNTS['receipt_pairs']+=1
            self.assertLessEqual(len(getattr(new,'_receipt_prefixes',{})),64)
            self.assertTrue(all(len(rows)<=101 for rows in new._receipt_prefixes.values()))

    def test_11_score_context_changes_preserve_outputs(self):
        args=('WOOL',10000,None,[],{},23,31)
        old=self.old.MarketPath(*args);new=self.new.MarketPath(*args)
        for shops,interval in [([],4),(['YARN_STORE','YARN_STORE'],4),(['YARN_STORE'],3),([],4)]:
            for m in [old,new]:
                m.shops=shops;m.config['townShopSellInterval']=interval
            self.assertEqual(old.score((),13,0,'paired'),new.score((),13,0,'paired'))
            COUNTS['score_pairs']+=1

    def test_12_cli_emits_exact_stack_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'candidate.py'
            command=[sys.executable,*(['-O'] if sys.flags.optimize else []),
                     str(Path(__file__).with_name('compose_optimizer_stack.py')),
                     str(RUNTIME/'selected_sell_core.py'),str(output),'--components-root',str(PARTS)]
            process=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertEqual(output.read_bytes(),self.output)
            self.assertEqual(json.loads(process.stdout),self.trace)
            process=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(process.returncode,0)
            self.assertEqual(output.read_bytes(),self.output)
            COUNTS['cli_rejections']+=1

    def test_13_cli_source_and_dependency_failures_create_no_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'parts';shutil.copytree(PARTS,root)
            source=Path(temp)/'source.py';source.write_bytes(self.raw)
            output=Path(temp)/'out.py'
            base=[sys.executable,*(['-O'] if sys.flags.optimize else []),
                  str(Path(__file__).with_name('compose_optimizer_stack.py'))]
            for _,relative,_ in COMPONENTS:
                path=root/relative;data=path.read_bytes();path.write_bytes(data+b'\n')
                process=subprocess.run(base+[str(source),str(output),'--components-root',str(root)],capture_output=True)
                self.assertNotEqual(process.returncode,0);self.assertFalse(output.exists())
                path.write_bytes(data);COUNTS['cli_rejections']+=1
            source.write_bytes(self.raw+b'\n')
            process=subprocess.run(base+[str(source),str(output),'--components-root',str(root)],capture_output=True)
            self.assertNotEqual(process.returncode,0);self.assertFalse(output.exists())
            COUNTS['cli_rejections']+=1
            process=subprocess.run(base+[str(source),str(source),'--components-root',str(root)],capture_output=True)
            self.assertNotEqual(process.returncode,0);self.assertEqual(source.read_bytes(),self.raw+b'\n')
            COUNTS['cli_rejections']+=1


def main():
    global RUNTIME,PARTS
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root',type=Path,required=True)
    parser.add_argument('--components-root',type=Path,default=Path(__file__).parent)
    parser.add_argument('--json',type=Path)
    args=parser.parse_args();RUNTIME=args.runtime_root.resolve();PARTS=args.components_root.resolve()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(StackContracts))
    report={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'skipped':len(result.skipped),'counts':COUNTS,'optimized':sys.flags.optimize,
            'output_git':OUTPUT_GIT}
    if args.json:
        with args.json.open('x') as output:json.dump(report,output,indent=2,sort_keys=True);output.write('\n')
    print(json.dumps(report,sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__=='__main__':main()
