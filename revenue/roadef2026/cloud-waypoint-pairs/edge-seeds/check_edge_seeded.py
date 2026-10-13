#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native, fixed-work controls for the opt-in edge-seeded pair frontier.

Constructed legal networks only. Uses existing exact parent and checker binaries;
never downloads sources, runs public instance panels, or changes a submission.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from decimal import Decimal
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('edge_builder', HERE/'build_edge_seeded.py')
BUILD = importlib.util.module_from_spec(spec); spec.loader.exec_module(BUILD)
ARGS = FIXTURE = None
RECORDS = []


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p, value): Path(p).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def fixture(name, *, middle=2, maintenance=False, budget=4, segments=3,
            volume=1, capacity=10, reorder=False, remap=False, prefix_tie=False, suffix_tie=False):
    folder, paths, _ = FIXTURE.fixture(ARGS.output, name, volume=volume, capacity=capacity,
        maintenance=maintenance, budget=budget, segments=segments)
    net = json.loads(paths[0].read_text());net['links'][2]['metric'] = middle
    for node in range(4, 40):
        net['nodes'].append({'id':node, 'name':f'n{node}'})
        for source,target in ((0,node),(node,0)):
            net['links'].append({'id':len(net['links']), 'from':source, 'to':target,
                                'metric':100, 'capacity':1000})
    if prefix_tie:
        net['links'].extend([{'id':len(net['links']), 'from':3,'to':1,'metric':2,'capacity':10},
                            {'id':len(net['links'])+1,'from':1,'to':3,'metric':1000,'capacity':10}])
    if suffix_tie:
        net['links'].extend([{'id':len(net['links']), 'from':2,'to':0,'metric':2,'capacity':10},
                            {'id':len(net['links'])+1,'from':0,'to':2,'metric':1000,'capacity':10}])
    if reorder:
        random.Random(84721).shuffle(net['links'])
    if remap:
        mapping={i:1007+i*17 for i in range(40)}
        for node in net['nodes']:node['id']=mapping[node['id']]
        for edge in net['links']:
            edge['from']=mapping[edge['from']];edge['to']=mapping[edge['to']]
        traffic=json.loads(paths[1].read_text())
        for demand in traffic['demands']:demand['s']=mapping[demand['s']];demand['t']=mapping[demand['t']]
        write(paths[1],traffic)
    write(paths[0],net)
    return folder, paths


def execute(folder, paths, label, binary, *, seeds=None, arc_limit=2048, trials=4096, seconds=10,
            pair_enabled=True):
    output=folder/(label+'.solution.json');stats=folder/(label+'.stats.json')
    env={k:v for k,v in os.environ.items() if not k.startswith(('SEDGE_', 'FLEET_', 'CEDAR_', 'CLOUD_INITIAL_'))}
    env.update(SEDGE_MAX_ROUNDS='100',SEDGE_SECONDS=str(seconds),SEDGE_STATS=str(stats),
        CEDAR_PAIR_WIDTH='16',CEDAR_PAIR_TRIALS=str(trials),CEDAR_PAIRS=str(int(pair_enabled)),
        CEDAR_SEED_ARCS=str(arc_limit))
    if seeds is not None:env['CEDAR_EDGE_SEEDS']=str(int(seeds))
    start=time.perf_counter()
    completed=subprocess.run([str(binary),*map(str,paths),str(output)],capture_output=True,env=env,timeout=15)
    elapsed=time.perf_counter()-start
    (folder/(label+'.stdout')).write_bytes(completed.stdout)
    (folder/(label+'.stderr')).write_bytes(completed.stderr)
    if completed.returncode:raise AssertionError((label,completed.returncode,completed.stderr.decode(errors='replace')))
    checked=subprocess.run([str(ARGS.checker),'--net',str(paths[0]),'--tm',str(paths[1]),
        '--scenario',str(paths[2]),'--srpaths',str(output),'--max-decimal-places','6'],
        capture_output=True,timeout=15)
    (folder/(label+'.checker.json')).write_bytes(checked.stdout)
    (folder/(label+'.checker.stderr')).write_bytes(checked.stderr)
    if checked.returncode:raise AssertionError((label,checked.returncode,checked.stderr.decode(errors='replace')))
    report=json.loads(checked.stdout,parse_float=Decimal)
    if report.get('valid') is not True:raise AssertionError((label,report))
    stat=json.loads(stats.read_text())
    native={(row['t'],row['from'],row['to']):Decimal(str(row['sat'])) for row in stat['loads']}
    for row in report['saturations']:
        expected=native[row['t'],row['from'],row['to']]
        if abs(expected-Decimal(str(row['sat'])))>Decimal('0.0000011'):
            raise AssertionError((label,row,expected))
    ranked=tuple(sorted((Decimal(str(row['sat'])) for row in report['saturations']),reverse=True))
    record={'case':folder.name,'label':label,'solution_sha256':sha(output),'checker_sha256':sha(folder/(label+'.checker.json')),
        'vector':[str(x) for x in ranked],'total_cost':report['total_cost'],'stats':{k:v for k,v in stat.items() if k!='loads'},
        'wall_seconds':elapsed,'seed_setting':seeds,'arc_limit':arc_limit,'pair_trials_per_call':trials,
        'binary_sha256':sha(binary)}
    RECORDS.append(record)
    return record, ranked, stat


def compare(folder, paths, **kw):
    parent=execute(folder,paths,'parent',ARGS.parent_binary,**{k:v for k,v in kw.items() if k in ('seconds','trials','pair_enabled')})
    default=execute(folder,paths,'default',ARGS.candidate_binary,**{k:v for k,v in kw.items() if k in ('seconds','trials','pair_enabled')})
    active=execute(folder,paths,'active',ARGS.candidate_binary,seeds=True,**kw)
    assert parent[0]['solution_sha256']==default[0]['solution_sha256']
    assert parent[1]==default[1]
    # The new fields are diagnostic-only when off; all inherited work matches.
    stripped={k:v for k,v in default[2].items() if k not in ('seconds',) and not k.startswith('cedar_seed_')}
    original={k:v for k,v in parent[2].items() if k!='seconds'}
    assert stripped==original
    assert all(v==0 for k,v in default[2].items() if k.startswith('cedar_seed_'))
    return parent, default, active


class EdgeSeedTests(unittest.TestCase):
    def test_01_generated_source_is_additive_and_deterministic(self):
        raw=ARGS.parent_source.read_bytes();generated=BUILD.generate(raw,HERE)
        self.assertEqual(generated, BUILD.generate(raw,HERE))
        opcodes=difflib.SequenceMatcher(None,raw.splitlines(keepends=True),generated.splitlines(keepends=True),autojunk=False).get_opcodes()
        self.assertFalse(any(tag in ('delete','replace') for tag,*_ in opcodes))
        with self.assertRaises(ValueError):BUILD.generate(raw+b'\n',HERE)

    def test_02_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'exists.cpp';p.write_text('existing output\n')
            out=subprocess.run([sys.executable,str(HERE/'build_edge_seeded.py'),'--parent',str(ARGS.parent_source),
                '--output',str(p)],capture_output=True,timeout=10)
            self.assertNotEqual(out.returncode,0);self.assertEqual(p.read_text(),'existing output\n')

    def test_03_default_width_miss_becomes_native_gain(self):
        f,p=fixture('default-width')
        parent,default,active=compare(f,p)
        self.assertEqual(parent[1][0],Decimal('1'))
        self.assertEqual(active[1][0],Decimal('0.1'))
        self.assertLess(active[1],parent[1]);self.assertGreater(active[2]['cedar_seed_accepted'],0)
        again=execute(f,p,'repeat',ARGS.candidate_binary,seeds=True)
        self.assertEqual(active[0]['solution_sha256'],again[0]['solution_sha256'])
        disabled=execute(f,p,'explicit-off',ARGS.candidate_binary,seeds=False)
        self.assertEqual(parent[0]['solution_sha256'],disabled[0]['solution_sha256'])

    def test_04_arc_order_does_not_invent_node_ids(self):
        f,p=fixture('reordered-remapped',reorder=True,remap=True)
        parent,_,active=compare(f,p)
        self.assertLess(active[1],parent[1]);self.assertEqual(active[1][0],Decimal('0.1'))

    def test_05_scaled_flow(self):
        f,p=fixture('scaled',volume=3,capacity=11)
        parent,_,active=compare(f,p)
        self.assertLess(active[1],parent[1]);self.assertLess(abs(active[1][0]-Decimal(3)/11),Decimal('0.0000011'))

    def test_06_arc_frontier_limit_stays_visible(self):
        f,p=fixture('arc-cap')
        parent,_,short=compare(f,p,arc_limit=2)
        self.assertEqual(short[1],parent[1]);self.assertEqual(short[2]['cedar_seed_candidates'],0)
        full=execute(f,p,'first-useful-arc',ARGS.candidate_binary,seeds=True,arc_limit=3)
        self.assertLess(full[1],parent[1]);self.assertGreater(full[2]['cedar_seed_accepted'],0)
        zero=execute(f,p,'zero-arcs',ARGS.candidate_binary,seeds=True,arc_limit=0)
        self.assertEqual(zero[0]['solution_sha256'],parent[0]['solution_sha256'])
        self.assertTrue(all(v==0 for k,v in zero[2].items() if k.startswith('cedar_seed_')))

    def test_07_seeded_proposals_share_existing_trial_limit(self):
        f,p=fixture('one-trial')
        parent,_,active=compare(f,p,trials=1)
        self.assertLess(active[1],parent[1]);self.assertGreater(active[2]['cedar_seed_accepted'],0)
        self.assertLessEqual(active[2]['cedar_seed_trials'],active[2]['cedar_pair_checks'])

    def test_08_input_arc_is_not_forced_shortest_path(self):
        f,p=fixture('middle-detour',middle=9)
        parent,_,active=compare(f,p)
        self.assertEqual(active[1],parent[1]);self.assertEqual(active[2]['cedar_seed_candidates'],0)

    def test_09_middle_ecmp_exposure_is_not_rounded_to_zero(self):
        f,p=fixture('middle-ecmp',middle=3)
        parent,_,active=compare(f,p)
        self.assertEqual(active[1],parent[1]);self.assertEqual(active[2]['cedar_seed_candidates'],0)

    def test_10_prefix_ecmp_exposure_is_not_ignored(self):
        f,p=fixture('prefix-ecmp',prefix_tie=True)
        parent,_,active=compare(f,p)
        self.assertEqual(active[1],parent[1]);self.assertEqual(active[2]['cedar_seed_candidates'],0)

    def test_11_suffix_ecmp_exposure_is_not_ignored(self):
        f,p=fixture('suffix-ecmp',suffix_tie=True)
        parent,_,active=compare(f,p)
        self.assertEqual(active[1],parent[1]);self.assertEqual(active[2]['cedar_seed_candidates'],0)

    def test_12_segment_limit_preserved(self):
        f,p=fixture('segment-two',segments=2)
        parent,_,active=compare(f,p)
        self.assertEqual(active[0]['solution_sha256'],parent[0]['solution_sha256'])
        self.assertEqual(active[2]['cedar_seed_scans'],0)

    def test_13_transition_budgets_remain_per_boundary(self):
        for budget in (0,3,4):
            with self.subTest(budget=budget):
                f,p=fixture('maintenance-'+str(budget),maintenance=True,budget=budget)
                parent,_,active=compare(f,p)
                self.assertEqual(active[1][0],Decimal('100'))
                if budget<4:
                    self.assertEqual(active[1],parent[1]);self.assertEqual(active[2]['cedar_seed_accepted'],0)
                else:
                    self.assertLess(active[1],parent[1]);self.assertEqual(active[0]['total_cost'],8)
                self.assertTrue(all(cost<=budget for cost in active[2]['budget_used'][1:]))

    def test_14_existing_zero_allowance_prevents_new_work(self):
        f,p=fixture('deadline-zero')
        parent,_,active=compare(f,p,seconds=0)
        self.assertEqual(active[0]['solution_sha256'],parent[0]['solution_sha256'])
        self.assertEqual(active[2]['cedar_seed_scans'],0)

    def test_15_pair_ablation_also_disables_seeds(self):
        f,p=fixture('paired-off')
        parent,_,active=compare(f,p,pair_enabled=False)
        self.assertEqual(active[0]['solution_sha256'],parent[0]['solution_sha256'])
        self.assertEqual(active[2]['cedar_seed_scans'],0)


def main():
    global ARGS, FIXTURE
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent-source',type=Path,required=True)
    p.add_argument('--parent-binary',type=Path,required=True)
    p.add_argument('--candidate-binary',type=Path,required=True)
    p.add_argument('--checker',type=Path,required=True)
    p.add_argument('--pair-component',type=Path,default=HERE.parent)
    p.add_argument('--output',type=Path,required=True)
    ARGS=p.parse_args()
    ARGS.output.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('original_pairs_fixture',ARGS.pair_component/'check_native.py')
    FIXTURE=importlib.util.module_from_spec(spec);spec.loader.exec_module(FIXTURE)
    start=time.perf_counter()
    with (ARGS.output/'tests.log').open('w') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EdgeSeedTests))
    summary={'methods':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),
        'passed':result.wasSuccessful(),'official_checker_calls':len(RECORDS),'full_solver_invocations':len(RECORDS),
        'public_instances':0,'wall_seconds':time.perf_counter()-start,
        'parent_source_sha256':sha(ARGS.parent_source),'generated_source_sha256':hashlib.sha256(BUILD.generate(ARGS.parent_source.read_bytes(),HERE)).hexdigest(),
        'binaries':{n:sha(getattr(ARGS,n)) for n in ('parent_binary','candidate_binary','checker')},
        'sources':{n:sha(HERE/n) for n in ('edge_seed_moves.inc','build_edge_seeded.py','check_edge_seeded.py')},
        'scope':'Constructed same-host fixed-work mechanism and fallback checks; no competition-performance or hard-deadline claim.',
        'records':RECORDS}
    write(ARGS.output/'summary.json',summary)
    print((ARGS.output/'tests.log').read_text())
    print(json.dumps({k:v for k,v in summary.items() if k!='records'},indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__=='__main__':main()
