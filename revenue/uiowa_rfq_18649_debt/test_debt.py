"""Executable acceptance and regression suite; all data is synthetic."""
from __future__ import annotations
import copy
import csv
import hashlib
import io
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from .model import InputError, MAX_BYTES, analyze, canonical, load_register, validate
from .cli import render_csv, render_markdown

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[1]

def item(key='A', cost=(2, 3), weekly=(2, 3), reduction=(50, 80), deps=(), pool=None):
    return {'id':key,'service':'Fictional service','category':'RECURRING_SUPPORT',
        'summary':'Synthetic support remediation','service_impact':'MODERATE',
        'service_consequence':'Fictional repeat work','owner_role':'Service owner',
        'evidence_refs':['SYN-001'],'estimate_basis':'ESTIMATED',
        'effort_hours':dict(zip(('low','high'),cost)) if cost is not None else None,
        'weekly_support_hours':dict(zip(('low','high'),weekly)),
        'reduction_pct':dict(zip(('low','high'),reduction)),
        'benefit_delay_weeks':0,'benefit_pool':pool or key,'alternative_group':None,
        'dependencies':list(deps),'revisit_trigger':'Review a representative fictional sample.'}

def register(*items):
    return {'schema':'tjlabs.technical-debt-register/v1','evidence_class':'SYNTHETIC', 'items':list(items or (item(),))}

def oracle(data, budget, horizon, required=()):
    """Independent flat combinations, set closure and explicit tuple objective."""
    rows=sorted(data['items'],key=lambda r:r['id'])
    candidates=[]
    for count in range(len(rows)+1):
        for chosen in itertools.combinations(rows,count):
            ids={r['id'] for r in chosen}
            if not set(required)<=ids: continue
            if any(not set(r['dependencies'])<=ids for r in chosen): continue
            if any(any(r[k] is None for k in ('effort_hours','weekly_support_hours','reduction_pct')) for r in chosen): continue
            invalid=False
            for field in ('benefit_pool','alternative_group'):
                values=[r[field] for r in chosen if r[field] is not None]
                invalid |= len(set(values)) != len(values)
            if invalid: continue
            cost=sum(r['effort_hours']['high'] for r in chosen)
            if cost>budget:continue
            lo=hi=0
            for r in chosen:
                w=max(0,horizon-r['benefit_delay_weeks'])
                lo+=w*r['weekly_support_hours']['low']*r['reduction_pct']['low']-100*r['effort_hours']['high']
                hi+=w*r['weekly_support_hours']['high']*r['reduction_pct']['high']-100*r['effort_hours']['low']
            candidates.append((tuple(sorted(ids)),cost,lo,hi))
    result=[]
    for endpoint in (2,3):
        best=min(candidates,key=lambda p:(-p[endpoint],-p[5-endpoint],p[1],p[0]),default=None)
        result.append(best)
    return result,len(candidates)

class DebtTests(unittest.TestCase):
    def test_worked_portfolios(self):
        data=load_register((PACKAGE/'examples/synthetic-register.json').read_bytes())
        report=analyze(data,50,12)
        low,high=report['portfolios'].values()
        self.assertEqual(low['ids'],['BASE','RETRY','SYNC'])
        self.assertEqual((low['net_hours_low'],low['net_hours_high']),('42.00','120.00'))
        self.assertEqual(high['ids'],['AUTOMATE','BASE','RETRY'])
        self.assertEqual((high['net_hours_low'],high['net_hours_high']),('4.00','140.00'))
        rows={r['id']:r for r in report['items']}
        self.assertEqual(rows['UNKNOWN']['disposition'],'NEEDS_ESTIMATE')
        self.assertIsNone(rows['UNKNOWN']['modeled'])
        self.assertEqual(rows['POLISH']['disposition'],'NO_POSITIVE_MODELED_PAYBACK')
        q=next(q for q in report['investigations'] if q['id']=='OBSOLETE')
        self.assertEqual(q['priority'],2)
        self.assertIn('avoided risk',q['question'])

    def test_justified_deferral_with_capacity(self):
        r=analyze(register(item(cost=(20,25),weekly=(0,1),reduction=(10,20))),100,4)
        self.assertEqual(r['portfolios']['conservative']['ids'],[])
        self.assertEqual(r['items'][0]['disposition'],'NO_POSITIVE_MODELED_PAYBACK')

    def test_prerequisite_cost_once(self):
        a=item('BASE',cost=(5,5),weekly=(0,0),reduction=(0,0))
        b=item('B',cost=(2,2),deps=['BASE'])
        c=item('C',cost=(2,2),deps=['BASE'])
        result=analyze(register(a,b,c),9,12)['portfolios']['conservative']
        self.assertEqual(result['ids'],['B','BASE','C'])
        self.assertEqual(result['effort_hours_high'],9)

    def test_negative_enabler_not_greedily_discarded(self):
        a=item('A',cost=(5,5),weekly=(0,0),reduction=(0,0))
        b=item('B',cost=(1,1),weekly=(4,4),reduction=(100,100),deps=['A'])
        r=analyze(register(a,b),6,2)
        self.assertEqual(r['portfolios']['conservative']['ids'],['A','B'])
        self.assertEqual(r['portfolios']['conservative']['net_hours_low'],'2.00')

    def test_overlap_and_alternative_exclusion(self):
        for field in ('benefit_pool','alternative_group'):
            a,b=item('A'),item('B')
            a[field]=b[field]='same'
            r=analyze(register(a,b),100,12)
            self.assertEqual(r['portfolios']['conservative']['ids'],['A'])

    def test_unknown_dependency_blocks_benefit(self):
        a,b=item('A',cost=None),item('B',deps=['A'])
        r=analyze(register(a,b),100,12)
        self.assertEqual(r['portfolios']['conservative']['ids'],[])
        self.assertTrue(all(x['disposition']=='NEEDS_ESTIMATE' for x in r['items']))

    def test_required_unknown_is_infeasible_not_empty_success(self):
        r=analyze(register(item(cost=None)),100,12,['A'])
        self.assertEqual(r['decision_status'],'NO_FEASIBLE_PORTFOLIO')
        self.assertEqual(r['portfolios'],{'conservative':None,'optimistic':None})

    def test_required_negative_item_is_visible_scenario(self):
        r=analyze(register(item(cost=(5,5),weekly=(0,0))),10,12,['A'])
        self.assertEqual(r['portfolios']['conservative']['ids'],['A'])
        self.assertEqual(r['portfolios']['conservative']['net_hours_low'],'-5.00')
        self.assertIn('NOT_APPROVAL',r['truth_boundary'])

    def test_dependency_exceeds_capacity(self):
        r=analyze(register(item('A',cost=(10,10)),item('B',cost=(1,1),deps=['A'])),5,10)
        self.assertTrue(all(row['disposition']=='DEPENDENCY_CLOSURE_EXCEEDS_CAPACITY' for row in r['items']))

    def test_conflicting_dependency_closure(self):
        a,b=item('A',pool='same'),item('B',deps=['A'],pool='same')
        r=analyze(register(a,b),100,10)
        self.assertEqual(r['items'][1]['disposition'],'INCOMPATIBLE_DEPENDENCY_CLOSURE')
        r=analyze(register(a,b),100,10,['B'])
        self.assertEqual(r['decision_status'],'NO_FEASIBLE_PORTFOLIO')

    def test_benefit_delay_and_fractional_hours(self):
        a=item(weekly=(1,1),cost=(0,0),reduction=(33,33))
        a['benefit_delay_weeks']=1
        r=analyze(register(a),0,2)
        self.assertEqual(r['items'][0]['modeled']['saved_hours_low'],'0.33')
        a['benefit_delay_weeks']=3
        self.assertEqual(analyze(register(a),0,2)['items'][0]['modeled']['saved_hours_low'],'0.00')

    def test_zero_budget_all_deferred(self):
        self.assertEqual(analyze(register(item()),0,12)['portfolios']['conservative']['ids'],[])

    def test_stable_sort_and_receipt(self):
        data=register(item('Z'),item('A'))
        data['items'][0]['evidence_refs']=['SYN-002','SYN-001']
        a=analyze(data,10,12)
        data['items'].reverse()
        data['items'][1]['evidence_refs'].reverse()
        b=analyze(data,10,12)
        self.assertEqual(a,b)
        digest=a.pop('report_sha256')
        self.assertEqual(hashlib.sha256(canonical(a)).hexdigest(),digest)

    def test_detached_input(self):
        source=register(item())
        result=validate(source)
        source['items'][0]['effort_hours']['low']=99
        self.assertEqual(result['items'][0]['effort_hours']['low'],2)

    def test_randomized_exact_oracle(self):
        rng=random.Random(4916096)
        for case in range(120):
            rows=[]
            n=rng.randint(1,8)
            for i in range(n):
                lo=rng.randint(0,5); hi=lo+rng.randint(0,6)
                a=item(str(i),cost=(lo,hi),weekly=(rng.randint(0,2),rng.randint(2,8)),
                       reduction=(20,80),deps=[str(j) for j in range(i) if rng.random()<.15])
                a['benefit_delay_weeks']=rng.randint(0,5)
                if rng.random()<.15:a['effort_hours']=None
                if rng.random()<.3:a['benefit_pool']='shared'
                if rng.random()<.2:a['alternative_group']='exclusive'
                rows.append(a)
            data=register(*rows);budget=rng.randint(0,30); horizon=rng.randint(1,12)
            required=(str(rng.randrange(n)),) if rng.random()<.2 else ()
            expected,count=oracle(data,budget,horizon,required)
            actual=analyze(data,budget,horizon,required)
            self.assertEqual(actual['search']['feasible_portfolios'],count,case)
            for name,best in zip(('conservative','optimistic'),expected):
                got=actual['portfolios'][name]
                if best is None:self.assertIsNone(got)
                else:
                    self.assertEqual(got['ids'],list(best[0]),case)
                    self.assertEqual(got['effort_hours_high'],best[1],case)
                    self.assertEqual(round(float(got['net_hours_low'])*100),best[2],case)
                    self.assertEqual(round(float(got['net_hours_high'])*100),best[3],case)

    def test_duplicate_ids_fields(self):
        with self.assertRaises(InputError):validate(register(item(),item()))
        with self.assertRaises(InputError):load_register(b'{"schema":"one","schema":"two"}')

    def test_rejects_floats_nonfinite_huge_tokens(self):
        for raw in (b'{"x":1.0}',b'{"x":NaN}',b'{"x":Infinity}',b'{"x":'+b'9'*5000+b'}'):
            with self.subTest(raw=raw[:30]),self.assertRaises(InputError):load_register(raw)

    def test_rejects_malformed_utf8_size_and_deep_json(self):
        for raw in (b'\xff',b'x'*(MAX_BYTES+1),b'['*2000+b']'*2000):
            with self.assertRaises(InputError):load_register(raw)

    def test_bool_ranges_and_bad_intervals(self):
        for field,value in (('effort_hours',{'low':True,'high':3}),
                            ('reduction_pct',{'low':0,'high':101}),
                            ('weekly_support_hours',{'low':-1,'high':2}),
                            ('effort_hours',{'low':9,'high':3})):
            a=item();a[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(InputError):validate(register(a))
        for budget,horizon in ((True,12),(10,False),(-1,12),(10,0),(10,521)):
            with self.assertRaises(InputError):analyze(register(item()),budget,horizon)

    def test_missing_extra_fields(self):
        for target,key in (('root','unexpected'),('row','unexpected')):
            data=register(item()); (data if target=='root' else data['items'][0])[key]=1
            with self.assertRaises(InputError):validate(data)
        data=register(item());del data['items'][0]['service_consequence']
        with self.assertRaises(InputError):validate(data)

    def test_missing_cycle_and_repeated_dependencies(self):
        for rows in ((item(deps=['missing']),), (item('A',deps=['B']),item('B',deps=['A'])),
                     (item('A',deps=['A']),), (item('A'),item('B',deps=['A','A']))):
            with self.assertRaises(InputError):validate(register(*rows))

    def test_exact_container_types(self):
        class Foreign(dict):pass
        with self.assertRaises(InputError):validate(Foreign(register(item())))
        a=item();a['effort_hours']=Foreign(a['effort_hours'])
        with self.assertRaises(InputError):validate(register(a))

    def test_cohort_bound_and_empty(self):
        data=register(*[item(str(i)) for i in range(19)])
        with self.assertRaises(InputError):validate(data)
        data['items']=[]
        with self.assertRaises(InputError):validate(data)

    def test_labels_references_and_pool(self):
        for field,value in (('estimate_basis','bad'),('category','bad'),('service_impact','bad'),('benefit_pool',None)):
            a=item();a[field]=value
            with self.assertRaises(InputError):validate(register(a))
        a=item();a['estimate_basis']='OBSERVED';a['evidence_refs']=[]
        with self.assertRaises(InputError):validate(register(a))
        a=item();a['estimate_basis']='UNKNOWN'
        with self.assertRaises(InputError):validate(register(a))

    def test_bad_text_and_required_ids(self):
        for value in ('','x\n','\ud800'):
            a=item();a['service']=value
            with self.assertRaises(InputError):validate(register(a))
        for required in (['missing'],['A','A'],'A'):
            with self.assertRaises(InputError):analyze(register(item()),10,12,required)

    def test_csv_and_markdown_escaping(self):
        a=item();a['service']='=HYPERLINK("fictional")';a['service_consequence']='<b>|fictional'
        r=analyze(register(a),10,12)
        record=next(csv.DictReader(io.StringIO(render_csv(r))))
        self.assertTrue(record['service'].startswith("'="))
        md=render_markdown(r)
        self.assertIn('&lt;b&gt;\\|fictional',md)
        self.assertNotIn('<b>',md)

    def cli(self,input_path,out,*extra):
        return subprocess.run([sys.executable,'-m','revenue.uiowa_rfq_18649_debt',str(input_path),
            '--budget-hours','50','--horizon-weeks','12','--output-dir',str(out),*extra],
            cwd=ROOT,text=True,capture_output=True,timeout=15)

    def test_cli_outputs_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'output'
            src=PACKAGE/'examples/synthetic-register.json'
            result=self.cli(src,out)
            self.assertEqual(result.returncode,0,result.stderr)
            r=json.loads((out/'analysis.json').read_text())
            expected=analyze(load_register(src.read_bytes()),50,12)
            self.assertEqual(r,expected)
            self.assertEqual(len(list(csv.DictReader(io.StringIO((out/'priorities.csv').read_text())))),8)
            self.assertIn('42.00..120.00',(out/'analysis.md').read_text())
            before=(out/'analysis.json').read_bytes()
            result=self.cli(src,out)
            self.assertEqual(result.returncode,2)
            self.assertEqual((out/'analysis.json').read_bytes(),before)

    def test_cli_invalid_no_output(self):
        with tempfile.TemporaryDirectory() as folder:
            src=Path(folder)/'bad.json';src.write_text('{"x":NaN}')
            out=Path(folder)/'out'
            result=self.cli(src,out)
            self.assertEqual(result.returncode,2)
            self.assertFalse(out.exists())

    def test_cli_infeasible_reports_and_exit3(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'out'
            result=self.cli(PACKAGE/'examples/synthetic-register.json',out,'--require','UNKNOWN')
            self.assertEqual(result.returncode,3,result.stderr)
            self.assertIn('NO_FEASIBLE_PORTFOLIO',(out/'analysis.md').read_text())

    def test_full_18_item_bound_is_complete(self):
        r=analyze(register(*[item(f'N{i:02}',cost=(0,0),weekly=(0,0),reduction=(0,0)) for i in range(18)]),0,1)
        self.assertEqual(r['search']['feasible_portfolios'],2**18)
        self.assertEqual(r['portfolios']['conservative']['ids'],[])

if __name__=='__main__':unittest.main()
