#!/usr/bin/env python3
"""Executable fixed-work, official-checker and source-preservation tests.

Set TRACE_CRITICAL_WORK to a build directory containing bin/original, bin/bands,
and bin/checker. No network access, provider calls or public-instance search.
"""
from __future__ import annotations
import copy, hashlib, importlib.util, json, os, pathlib, subprocess, tempfile, unittest
from decimal import Decimal

HERE = pathlib.Path(__file__).resolve().parent
WORK = pathlib.Path(os.environ.get('TRACE_CRITICAL_WORK', HERE.parent))

def fixture(slots=40, offset=0):
    links=[]
    for a,b,metric,capacity in [(0,1,1,1),(1,2,100,100),(2,3,1,1),(2,4,2,10),(4,3,2,10)]:
        for u,v in [(a,b),(b,a)]:
            links.append({'id':len(links),'from':u+offset,'to':v+offset,'metric':metric,'capacity':capacity})
    return ({'directed':True,'multigraph':False,'nodes':[{'id':n+offset,'name':f'n{n}'} for n in range(5)],'links':links},
            {'num_time_slots':slots,'demands':[{'s':0+offset,'t':1+offset,'v':[2]*slots},
                                                {'s':2+offset,'t':3+offset,'v':[1]*slots}]},
            {'max_segments':8,'interventions':[],'budget':[{'t':t,'value':0} for t in range(1,slots)]})

def run_case(root, name, *, enabled=None, cap=None, rounds=128, slots=40, offset=0,
             incumbent=None, seconds=30):
    case=root/name;case.mkdir()
    paths=[]
    for filename, value in zip(('network.json','traffic.json','scenario.json'),fixture(slots,offset)):
        p=case/filename;p.write_text(json.dumps(value));paths.append(p)
    stats=case/'stats.json';bands=case/'bands.json';output=case/'solution.json'
    env={k:v for k,v in os.environ.items() if not k.startswith(('SEDGE_','FLEET_','CLOUD_'))}
    env.update(SEDGE_SECONDS=str(seconds),SEDGE_MAX_ROUNDS=str(rounds),SEDGE_STATS=str(stats),FLEET_BAND_STATS=str(bands))
    if enabled is not None:env['FLEET_CRITICAL_BANDS']=str(enabled)
    if cap is not None:env['FLEET_CRITICAL_MAX_RANK']=str(cap)
    if incumbent is not None:env['CLOUD_INITIAL_SOLUTION']=str(incumbent)
    binary=WORK/'bin'/('original' if name.startswith('original') else 'bands')
    result=subprocess.run([str(binary),*(str(p) for p in paths),str(output)],env=env,capture_output=True,timeout=40)
    (case/'stdout').write_bytes(result.stdout);(case/'stderr').write_bytes(result.stderr)
    if result.returncode:raise AssertionError(f'{name}: {result.returncode}: {result.stderr!r}')
    return {'case':case,'output':output,'stats':json.loads(stats.read_text()),
            'bands':json.loads(bands.read_text()) if bands.exists() else None}

def non_time(stats):
    return {k:v for k,v in stats.items() if k!='seconds'}

class CriticalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='trace-critical-tests-')
        cls.root=pathlib.Path(cls.tmp.name)
        cls.original=run_case(cls.root,'original-cold')
        cls.disabled=run_case(cls.root,'disabled',enabled=0)
        cls.default=run_case(cls.root,'default')
        cls.enabled=run_case(cls.root,'enabled',enabled=1)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_disabled_exact_actions_loads_budgets_counters(self):
        self.assertEqual(self.original['output'].read_bytes(),self.disabled['output'].read_bytes())
        self.assertEqual(non_time(self.original['stats']),non_time(self.disabled['stats']))
    def test_default_exact(self):
        self.assertEqual(non_time(self.original['stats']),non_time(self.default['stats']))
        self.assertFalse(self.default['bands']['enabled'])
    def test_lower_rank_gain_without_peak_change(self):
        a=sorted((Decimal(str(x['sat'])) for x in self.original['stats']['loads']),reverse=True)
        b=sorted((Decimal(str(x['sat'])) for x in self.enabled['stats']['loads']),reverse=True)
        self.assertEqual(a[:40],b[:40]);self.assertLess(b,a)
        self.assertEqual(next(i+1 for i,(x,y) in enumerate(zip(a,b)) if x!=y),41)
        self.assertEqual(a[40],1);self.assertEqual(b[40],Decimal('.1'))
    def test_baseline_stop_is_original_stall(self):
        self.assertEqual(self.disabled['bands']['exit_reason'],'original_stall')
        self.assertEqual(self.disabled['bands']['rounds'],64)
        self.assertEqual(self.disabled['bands']['largest_critical_rank_visited'],32)
    def test_gain_at_lower_band(self):
        report=self.enabled['bands']
        self.assertGreaterEqual(report['largest_critical_rank_visited'],41)
        self.assertEqual(report['bands'][1]['accepts'],1)
        self.assertEqual(report['improvement_resets'],1)
    def test_all_transition_budgets_zero(self):
        self.assertEqual(self.enabled['stats']['budget_used'],[0]*40)
    def test_32_cap_keeps_baseline(self):
        cap=run_case(self.root,'cap32',enabled=1,cap=32)
        self.assertEqual(non_time(self.original['stats']),non_time(cap['stats']))
        self.assertEqual(cap['bands']['exit_reason'],'rank_bands_exhausted')
    def test_40_cap_cannot_reach_41(self):
        cap=run_case(self.root,'cap40',enabled=1,cap=40,rounds=256)
        self.assertEqual(self.original['output'].read_bytes(),cap['output'].read_bytes())
        self.assertEqual(cap['bands']['largest_critical_rank_visited'],40)
    def test_41_cap_reaches_gain(self):
        cap=run_case(self.root,'cap41',enabled=1,cap=41,rounds=256)
        self.assertEqual(self.enabled['output'].read_bytes(),cap['output'].read_bytes())
    def test_round_limit_retained(self):
        x=run_case(self.root,'round64',enabled=1,rounds=64)
        self.assertEqual(self.original['output'].read_bytes(),x['output'].read_bytes())
        self.assertEqual(x['bands']['exit_reason'],'round_limit')
    def test_improvement_resets_priority(self):
        x=run_case(self.root,'round74',enabled=1,rounds=74)
        self.assertEqual(x['bands']['bands'][0]['rounds'],65)
        self.assertEqual(x['bands']['bands'][1]['rounds'],9)
        self.assertEqual(x['bands']['improvement_resets'],1)
    def test_fixed_round_repeatability(self):
        x=run_case(self.root,'repeat',enabled=1)
        self.assertEqual(self.enabled['output'].read_bytes(),x['output'].read_bytes())
        self.assertEqual(non_time(self.enabled['stats']),non_time(x['stats']))
        self.assertEqual(self.enabled['bands'],x['bands'])
    def test_resume_same_incumbent(self):
        a=run_case(self.root,'original-resume',incumbent=self.original['output'])
        b=run_case(self.root,'resume',enabled=1,incumbent=self.original['output'])
        self.assertTrue(a['stats']['resumed']);self.assertTrue(b['stats']['resumed'])
        self.assertEqual(self.enabled['output'].read_bytes(),b['output'].read_bytes())
        self.assertEqual(self.original['output'].read_bytes(),a['output'].read_bytes())
    def test_noncontiguous_node_ids(self):
        x=run_case(self.root,'offset',enabled=1,offset=100)
        self.assertEqual([v['sat'] for v in x['stats']['loads']],[v['sat'] for v in self.enabled['stats']['loads']])
        self.assertEqual(x['stats']['budget_used'],[0]*40)
    def test_zero_rounds_keeps_initial_solution(self):
        a=run_case(self.root,'original-zero',rounds=0)
        b=run_case(self.root,'zero',enabled=1,rounds=0)
        self.assertEqual(a['output'].read_bytes(),b['output'].read_bytes())
        self.assertEqual(non_time(a['stats']),non_time(b['stats']))
        self.assertEqual(b['bands']['largest_critical_rank_visited'],0)
    def test_zero_seconds_keeps_initial_solution(self):
        a=run_case(self.root,'original-deadline',seconds=0)
        b=run_case(self.root,'deadline',enabled=1,seconds=0)
        self.assertEqual(a['output'].read_bytes(),b['output'].read_bytes())
        self.assertEqual(b['bands']['exit_reason'],'deadline')
    def test_builder_preserves_non_run_methods_and_input(self):
        import build_candidate
        base=(WORK/'base/fleet-candidate/main.cpp').read_text()
        actual=build_candidate.transform(base)
        restored=actual
        for before,after in reversed(build_candidate.PATCHES):restored=restored.replace(after,before,1)
        self.assertEqual(restored,base)
        before=base[base.index('    Dag& dag('):base.index('    void run()')]
        self.assertIn(before,actual)
        self.assertEqual(hashlib.sha256(base.encode()).hexdigest(),'322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1')
    def test_builder_rejects_reapplication_without_output(self):
        import build_candidate
        with self.assertRaises(ValueError):build_candidate.transform((WORK/'generated/main.cpp').read_text())

if __name__=='__main__':unittest.main(verbosity=2)
