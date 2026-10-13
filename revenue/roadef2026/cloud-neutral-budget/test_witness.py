# SPDX-License-Identifier: MIT
"""Native tests require the exact witness binary; no synthetic replacement kernel."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from check_witness import HERE,native,run

BINARY = os.environ.get('OSPREY_NEUTRAL_WITNESS')
CHECKER = os.environ.get('OSPREY_ROADEF_CHECKER')

@unittest.skipUnless(BINARY, 'Set OSPREY_NEUTRAL_WITNESS to the built exact-source harness')
class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.fixture=self.root/'fixture';self.fixture.mkdir()
        for p in (HERE/'fixtures').glob('*.json'):
            (self.fixture/p.name).write_bytes(p.read_bytes())
    def edit(self,name,fn):
        p=self.fixture/name;value=json.loads(p.read_bytes());fn(value)
        p.write_text(json.dumps(value)+'\n')
    def execute(self,mode,label=None):
        return native(Path(BINARY),self.fixture,self.root/(label or mode),mode)
    def test_original_search_stalls_with_occupied_budget(self):
        row=self.execute('original');self.assertEqual(row['accepted'],0)
        self.assertEqual((row['final_mlu'],row['budget_used']),(1.6,[0,3]))
    def test_neutral_only_changes_budget_not_loads(self):
        old=self.execute('original');new=self.execute('release-only')
        self.assertEqual(old['loads'],new['loads']);self.assertEqual(new['budget_used'],[0,0])
        self.assertEqual(new['accepted'],0)
    def test_existing_search_uses_freed_budget(self):
        row=self.execute('release');self.assertEqual(row['final_mlu'],1)
        self.assertEqual(row['budget_used'],[0,3]);self.assertEqual(row['accepted'],1)
    def test_exact_solution_reproducible(self):
        a=self.execute('release','a');b=self.execute('release','b')
        a.pop('seconds');b.pop('seconds');self.assertEqual(a,b)
        self.assertEqual((self.root/'a/solution.json').read_bytes(),(self.root/'b/solution.json').read_bytes())
    def test_no_neutral_cycle_after_release(self):
        self.execute('release-only')
        (self.fixture/'incumbent.json').write_bytes((self.root/'release-only/solution.json').read_bytes())
        self.execute('no-release')
    def test_equal_cost_constant_route_is_not_a_release(self):
        self.edit('incumbent.json',lambda x:x['srpaths'].append({'d':0,'t':0,'w':[1]}))
        row=self.execute('no-release');self.assertEqual(row['budget_used'],[0,0])
    def test_ecmp_branch_destroys_equivalence(self):
        self.edit('network.json',lambda x:x['links'][2].update(metric=2))
        row=self.execute('no-release');self.assertEqual(row['budget_used'],[0,3])
    def test_all_slots_must_be_equivalent(self):
        self.edit('network.json',lambda x:x['links'][2].update(metric=2))
        def traffic(x):
            x['num_time_slots']=3
            for d in x['demands']: d['v'].append(d['v'][-1])
        self.edit('traffic.json',traffic)
        self.edit('incumbent.json',lambda x:x['srpaths'].append({'d':0,'t':2,'w':[1]}))
        self.edit('scenario.json',lambda x:x['interventions'].append({'t':1,'links':[2,11]}))
        row=self.execute('no-release');self.assertEqual(row['budget_used'],[0,3,0])
    def test_no_reconfiguration_boundary(self):
        def traffic(x):
            x['num_time_slots']=1
            for d in x['demands']:d['v']=d['v'][:1]
        self.edit('traffic.json',traffic)
        self.edit('incumbent.json',lambda x:x['srpaths'][0].update(t=0))
        self.edit('scenario.json',lambda x:x.update(budget=[]))
        row=self.execute('no-release');self.assertEqual(row['budget_used'],[0])
    def test_zero_proposal_work_keeps_incumbent(self): self.execute('zero-work')
    def test_cancel_before_callback_keeps_incumbent(self): self.execute('cancel')
    def test_late_callback_keeps_incumbent(self): self.execute('late-cancel')
    def test_no_overwrite_of_evidence(self):
        self.execute('original')
        with self.assertRaises(FileExistsError):self.execute('original')
    @unittest.skipUnless(CHECKER,'Set OSPREY_ROADEF_CHECKER for official differential')
    def test_official_checker_all_three_stages(self):
        report=run(Path(BINARY),Path(CHECKER),self.root/'official',self.fixture)
        self.assertEqual(report['checker_invocations'],6)
        self.assertEqual(report['native_checker_load_comparisons_12'],108)
        self.assertTrue(report['neutral_link_loads_identical'])

if __name__=='__main__':unittest.main()
