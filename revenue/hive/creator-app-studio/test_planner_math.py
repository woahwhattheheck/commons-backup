#!/usr/bin/env python3
"""Run the shipped JavaScript arithmetic with Node; this is not a browser test."""
import json
import random
import re
import shutil
import subprocess
import unittest
from decimal import Decimal, ROUND_CEILING, localcontext
from pathlib import Path

HERE=Path(__file__).resolve().parent
HTML=(HERE/'planner.html').read_text(encoding='utf-8')
PURE=HTML[HTML.index('const SCALE='):HTML.index('const storageKey=')]


@unittest.skipUnless(shutil.which('node'), 'Node is required for the real JavaScript arithmetic tests')
class PlannerMathTests(unittest.TestCase):
    def js(self, expression, data=None):
        code=PURE+'\nconst input=JSON.parse(require("fs").readFileSync(0,"utf8"));\nconsole.log(JSON.stringify('+expression+'));'
        result=subprocess.run(['node','-e',code],input=json.dumps(data),text=True,capture_output=True,check=True,timeout=10)
        return json.loads(result.stdout)

    @staticmethod
    def plan(per='0.1',pack='0.3',reserve='0',attendees=3):
        return {'name':'Arithmetic test','attendees':attendees,'materials':[
            {'name':'Supply','unit':'units','per_attendee':per,'pack_size':pack,'buffer_percent':reserve}]}

    def test_exact_fraction_pack_boundary(self):
        row=self.js('calculate(input)',self.plan())[0]
        self.assertEqual((row['required'],row['packs'],row['purchase']),('0.3','1','0.3'))

    def test_reference_case(self):
        row=self.js('calculate(input)',self.plan('2','10','10',12))[0]
        self.assertEqual((row['required'],row['packs'],row['purchase']),('26.4','3','30'))

    def test_zero_and_smallest_supported_quantities(self):
        inputs=[self.plan('0','1','100',1000000),self.plan('0.000001','0.000001','0.000001',1)]
        rows=self.js('input.map(p=>calculate(p)[0])',inputs)
        self.assertEqual(rows[0]['packs'],'0')
        self.assertEqual(rows[1]['required'],'0.00000100000001')
        self.assertEqual(rows[1]['packs'],'2')

    def test_500_real_javascript_cases_match_decimal(self):
        rng=random.Random(16092026)
        inputs=[self.plan(str(Decimal(rng.randrange(0,100000000))/1000000),
                          str(Decimal(rng.randrange(1,100000000))/1000000),
                          str(Decimal(rng.randrange(0,100000001))/1000000),
                          rng.randrange(1,1000001)) for _ in range(500)]
        outputs=self.js('input.map(p=>calculate(p)[0])',inputs)
        with localcontext() as ctx:
            ctx.prec=60
            for plan,result in zip(inputs,outputs):
                row=plan['materials'][0]
                required=Decimal(row['per_attendee'])*plan['attendees']*(1+Decimal(row['buffer_percent'])/100)
                packs=(required/Decimal(row['pack_size'])).to_integral_value(rounding=ROUND_CEILING)
                self.assertEqual(Decimal(result['required']),required)
                self.assertEqual(Decimal(result['packs']),packs)
                self.assertEqual(Decimal(result['purchase']),packs*Decimal(row['pack_size']))

    def test_invalid_inputs_rejected_by_shipped_javascript(self):
        invalid=[]
        for n in [0,True,1.5,1000001,None,'3']:
            p=self.plan();p['attendees']=n;invalid.append(p)
        for n in ['0','-1','NaN','Infinity','1.0000001',None,True]:
            p=self.plan();p['materials'][0]['pack_size']=n;invalid.append(p)
        self.assertTrue(all(self.js('input.map(p=>{try{calculate(p);return false;}catch(e){return true;}})',invalid)))

    def test_csv_neutralizes_formulas_and_preserves_quotes(self):
        result=self.js('input.map(csvCell)',['=1+1','\t+2','@formula','-supply','ordinary','a,"b"'])
        self.assertEqual(result,['"\'=1+1"','"\'\t+2"','"\'@formula"','"\'-supply"','"ordinary"','"a,""b"""'])

    def test_all_browser_scripts_parse(self):
        for html_name in ['planner.html','studio.html']:
            html=(HERE/html_name).read_text(encoding='utf-8')
            scripts=re.findall(r'<script>(.*?)</script>',html,re.S)
            self.assertTrue(scripts)
            for script in scripts:
                subprocess.run(['node','--check'],input=script,text=True,capture_output=True,check=True,timeout=10)


if __name__=='__main__':
    unittest.main(verbosity=2)
