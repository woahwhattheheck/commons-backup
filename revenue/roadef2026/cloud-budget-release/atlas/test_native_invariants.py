#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Independent compiled consumer of DATE's operator and the pinned fleet kernel.

Constructed graph fixtures only. No contest instances, solver selection, network,
submission, timeout-budget changes, or new runtime implementation.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import heapq
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
FLEET_SHA = '322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1'
HEADER_BLOB = '5ce70d722c6d4e2f7c053990697387d9f46514fc'
ARGS = None
RECEIPTS = []


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def rational_loads(net, tm, scenario, paths):
    """Small-fixture reference: exact rational per-forwarder ECMP, no fleet code."""
    nodes = [v['id'] for v in net['nodes']]
    links = net['links']
    down = {row['t']: set(row['links']) for row in scenario['interventions']}
    routes = {(r['d'], r['t']): r['w'] for r in paths['srpaths']}
    values = []
    for t in range(tm['num_time_slots']):
        loads = [Fraction(0) for _ in links]
        for d, demand in enumerate(tm['demands']):
            route = [demand['s'], *routes.get((d, t), []), demand['t']]
            for source, target in zip(route, route[1:]):
                dist = {v: float('inf') for v in nodes}
                dist[target] = 0
                todo = [(0, target)]
                while todo:
                    value, v = heapq.heappop(todo)
                    if value != dist[v]: continue
                    for edge in links:
                        if edge['to'] == v and edge['id'] not in down.get(t, set()):
                            new = value + edge['metric']
                            if new < dist[edge['from']]:
                                dist[edge['from']] = new
                                heapq.heappush(todo, (new, edge['from']))
                if dist[source] == float('inf'): raise ValueError('unreachable fixture')
                flow = {v: Fraction(0) for v in nodes}
                flow[source] = Fraction(demand['v'][t])
                for v in sorted(nodes, key=lambda v: dist[v], reverse=True):
                    if v == target or not flow[v]: continue
                    outgoing = [(i, e) for i, e in enumerate(links)
                                if e['from'] == v and e['id'] not in down.get(t, set())
                                and dist[v] == e['metric'] + dist[e['to']]]
                    if not outgoing: raise ValueError('broken fixture DAG')
                    share = flow[v] / len(outgoing)
                    for i, edge in outgoing:
                        loads[i] += share / edge['capacity']
                        flow[edge['to']] += share
        values.extend(loads)
    return values


def budget_usage(tm, paths):
    routes = {(r['d'], r['t']): r['w'] for r in paths['srpaths']}
    result = [0] * tm['num_time_slots']
    def segments(d, t):
        demand = tm['demands'][d]
        p = [demand['s'], *routes.get((d, t), []), demand['t']]
        return set(zip(p, p[1:]))
    for t in range(1, len(result)):
        result[t] = sum(len(segments(d, t-1) ^ segments(d, t))
                        for d in range(len(tm['demands'])))
    return result


def fixture(schedules, *, diamond=False, maintenance=False, zero=False):
    ids = [101, 205, 309, 413] + [1001 + 113*d for d in range(1, len(schedules))]
    # Distinct sources preserve a shared forwarding core while satisfying the
    # official traffic-matrix requirement that each (source, target) is unique.
    origins = [0] + list(range(4, len(ids)))
    cheap = {(0,1), (1,2), (2,3)} if not diamond else {(0,1),(0,2),(1,3),(2,3)}
    cheap.update((origin, 0) for origin in origins[1:])
    links = [dict(id=i, **{'from':ids[u], 'to':ids[v]},
                  metric=1 if (u,v) in cheap else 100, capacity=100)
             for i, (u,v) in enumerate((u,v) for u in range(len(ids)) for v in range(len(ids)) if u!=v)]
    net = dict(directed=True, multigraph=False,
               nodes=[dict(id=v, name=f'n{v}') for v in ids], links=links)
    h = len(schedules[0])
    tm = dict(num_time_slots=h, demands=[dict(s=ids[origins[d]], t=ids[3],
              v=[0 if zero else 7+d+t for t in range(h)]) for d in range(len(schedules))])
    paths = {'srpaths':[dict(d=d,t=t,w=[ids[w] for w in route])
              for d, schedule in enumerate(schedules) for t, route in enumerate(schedule) if route]}
    used = budget_usage(tm, paths)
    scenario = dict(max_segments=8, budget=[dict(t=t,value=used[t]) for t in range(1,h)],
                    interventions=[])
    if maintenance:
        edge = next(e['id'] for e in links if e['from']==ids[0] and e['to']==ids[1])
        scenario['interventions'] = [dict(t=h-1, links=[edge])]
    return net,tm,scenario,paths


class NativeInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if ARGS is None:
            raise unittest.SkipTest("Use the native CLI with explicit pinned source/header/vendor inputs")
        cls.scratch = tempfile.TemporaryDirectory(prefix='atlas-budget-native-')
        cls.root = Path(cls.scratch.name)
        cls.case_number = 0
        source = ARGS.fleet_source.read_bytes()
        header = ARGS.header.read_bytes()
        if sha(source) != FLEET_SHA or blob(header) != ARGS.expected_header_blob:
            raise ValueError('exact fleet/header input identities differ from this test revision')
        text = source.decode()
        if text.count('class Solver {')!=1 or text.count('int main(int argc, char** argv) {')!=1:
            raise ValueError('test-only access anchors differ')
        text=text.replace('class Solver {','class Solver {\npublic:',1)
        text=text.replace('int main(int argc, char** argv) {','int fleet_original_main(int argc, char** argv) {',1)
        (cls.root/'fleet_exposed.cpp').write_text(text)
        (cls.root/'budget_release.hpp').write_bytes(header)
        shutil.copyfile(HERE/'inspect_release.cpp',cls.root/'inspect_release.cpp')
        cls.binary=cls.root/'inspect_release'
        run=subprocess.run([ARGS.cxx,'-std=c++17','-O2','-Wall','-Wextra','-pedantic',
                            '-Wno-deprecated-declarations','-I',str(ARGS.vendor.resolve()),
                            str(cls.root/'inspect_release.cpp'),'-o',str(cls.binary)],
                           capture_output=True,timeout=60)
        if run.returncode: raise RuntimeError(run.stderr.decode(errors='replace'))
        cls.compile_log=run.stdout+run.stderr
        cls.compiler=subprocess.check_output([ARGS.cxx,'--version'],text=True).splitlines()[0]

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def execute(self, model, *, mode='normal', limit=4096):
        directory=self.root/f'case-{NativeInvariants.case_number:04d}'
        NativeInvariants.case_number += 1
        directory.mkdir()
        names=['net','tm','scenario','incumbent']
        paths=[]
        for name,value in zip(names,model):
            p=directory/(name+'.json');p.write_text(json.dumps(value));paths.append(p)
        before=[p.read_bytes() for p in paths]
        output=directory/'output.json';stats=directory/'stats.json'
        env={k:v for k,v in os.environ.items() if not k.startswith(('SEDGE_','FLEET_','CLOUD_'))}
        env.update(SEDGE_SECONDS='30',SEDGE_MAX_ROUNDS='0',SEDGE_STATS=str(stats))
        run=subprocess.run([str(self.binary),*map(str,paths),str(output),mode,str(limit)],
                           env=env,capture_output=True,timeout=35)
        self.assertEqual(run.returncode,0,run.stderr.decode(errors='replace'))
        result=json.loads(run.stdout); final=json.loads(output.read_bytes())
        self.assertEqual([p.read_bytes() for p in paths],before)
        self.assertEqual(rational_loads(*model[:3],model[3]), rational_loads(*model[:3],final))
        old=budget_usage(model[1],model[3]); new=budget_usage(model[1],final)
        self.assertTrue(all(b<=a for a,b in zip(old,new)))
        self.assertEqual(sum(old)-sum(new),result['released'])
        self.assertEqual(json.loads(stats.read_bytes())['budget_used'],new)
        RECEIPTS.append(dict(test=self._testMethodName,mode=mode,result=result,
            input_sha256=[sha(b) for b in before],output_sha256=sha(output.read_bytes()),
            stats_sha256=sha(stats.read_bytes()),budget_before=old,budget_after=new,
            rational_vector_sha256=sha(str(rational_loads(*model[:3],final)).encode())))
        if ARGS.evidence_dir:
            dest=ARGS.evidence_dir/directory.name;shutil.copytree(directory,dest)
            (dest/'stdout.log').write_bytes(run.stdout);(dest/'stderr.log').write_bytes(run.stderr)
        return result,final

    def test_repeated_releases_preserve_other_demands_and_complete_load_bytes(self):
        result,_=self.execute(fixture([[[],[1],[1],[]],[[1,2],[1,2],[],[]]]))
        self.assertGreaterEqual(result['committed'],2);self.assertGreater(result['released'],0)

    def test_componentwise_boundary_dominance_not_total_cost_only(self):
        result,_=self.execute(fixture([[[1],[1,2],[2]]]))
        self.assertEqual(result['committed'],0)

    def test_all_slots_checked_across_a_maintenance_boundary(self):
        result,_=self.execute(fixture([[[],[1],[1]]],maintenance=True))
        self.assertEqual(result['committed'],0)

    def test_equal_cost_path_is_not_ecmp_flow_equivalence(self):
        result,_=self.execute(fixture([[[],[1]]],diamond=True))
        self.assertEqual(result['committed'],0)

    def test_zero_volume_does_not_bypass_unit_flow_equality(self):
        result,_=self.execute(fixture([[[],[1]]],diamond=True,zero=True))
        self.assertEqual(result['committed'],0)

    def test_no_strict_budget_gain_does_not_change_route(self):
        result,_=self.execute(fixture([[[1],[1],[1]]]))
        self.assertEqual(result['committed'],0)

    def test_stopped_before_search_leaves_state_unchanged(self):
        result,_=self.execute(fixture([[[],[1]]]),mode='pre_stop')
        self.assertEqual(result['flow_callbacks'],0)

    def test_stop_after_real_flow_callback_cannot_return_a_proposal(self):
        result,_=self.execute(fixture([[[],[1]]]),mode='post_callback_stop')
        self.assertEqual(result['flow_callbacks'],1)

    def test_callback_exception_preserves_arrays_and_diagnostic(self):
        result,_=self.execute(fixture([[[],[1]]]),mode='callback_exception')
        self.assertTrue(result['exception_seen'])

    def test_inexact_sparse_coefficient_is_rejected(self):
        result,_=self.execute(fixture([[[],[1]]]),mode='near_flow')
        self.assertEqual(result['committed'],0)

    def test_unreachable_callback_and_zero_proposal_budget(self):
        for mode,limit in [('unreachable',4096),('normal',0)]:
            result,_=self.execute(fixture([[[],[1]]]),mode=mode,limit=limit)
            self.assertEqual(result['committed'],0)

    def test_generated_multi_demand_schedules(self):
        rng=random.Random(20260908)
        menu=[[],[1],[2],[1,2]]
        for i in range(64):
            h=rng.randrange(2,8);count=rng.randrange(1,5)
            model=fixture([[rng.choice(menu) for _ in range(h)] for _ in range(count)])
            with self.subTest(i=i):self.execute(model)


def main():
    global ARGS
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fleet-source',type=Path,required=True)
    parser.add_argument('--header',type=Path,default=HERE.parent/'budget_release.hpp')
    parser.add_argument('--vendor',type=Path,required=True)
    parser.add_argument('--cxx',default='g++')
    parser.add_argument('--expected-header-blob',default=HEADER_BLOB,
                        help='Explicit source identity for a separately labeled operator revision or mutation')
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--evidence-dir',type=Path)
    ARGS=parser.parse_args()
    if ARGS.evidence_dir:ARGS.evidence_dir.mkdir(parents=True,exist_ok=False)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(NativeInvariants)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report=dict(schema='roadef.atlas-date-native-invariants.v1',successful=result.wasSuccessful(),
        tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        compiled_cases=len(RECEIPTS),compiler=getattr(NativeInvariants,'compiler',None),
        header_blob=blob(ARGS.header.read_bytes()),expected_header_blob=ARGS.expected_header_blob,
        header_sha256=sha(ARGS.header.read_bytes()),
        fleet_sha256=sha(ARGS.fleet_source.read_bytes()),
        driver_sha256=sha((HERE/'inspect_release.cpp').read_bytes()),
        test_sha256=sha(Path(__file__).read_bytes()),cases=RECEIPTS,
        scope='constructed native graph fixtures, exact rational independent flow and segment-set reference; not official checker or contest performance',
        public_instances=0,submission=False)
    ARGS.report.parent.mkdir(parents=True,exist_ok=True)
    ARGS.report.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
