# SPDX-License-Identifier: MIT
"""Targeted contracts and relocatable package checks; no new full games."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

from controller import Titan, load
from sell_adapter import CapSell, SelectedAction
from build import build

HERE=Path(__file__).resolve().parent
FIXTURES=json.loads((HERE/'test-observations.json').read_text())

class Contracts(unittest.TestCase):
    def test_frozen_vendor_bytes(self):
        expected={'vendor/base/arlene.py':'1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4',
                  'vendor/sell/scheduler.py':'32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9',
                  'vendor/flora/candidate.py':'87aed426f965e8ac542c32b748b7d58847ced19b2681c862c10820b698c46ee7'}
        for name,digest in expected.items():
            self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(),digest)

    def test_selected_action_is_consumed_once(self):
        base=Titan().base
        proxy=SelectedAction(base)
        proxy.action={'farmer':['PASS'],'hands':[],'market':[]}
        self.assertEqual(proxy.act({}),proxy.action)
        with self.assertRaises(RuntimeError):proxy.act({})
        self.assertIs(proxy.R,base.R)

    def test_one_authoritative_pass(self):
        for carrot,cap in ((False,False),(True,False),(False,True),(True,True)):
            policy=Titan(carrot,cap)
            counter=[];original=policy.base.act
            def counted(obs):
                counter.append(1)
                return original(obs)
            policy.base.act=counted
            for f in FIXTURES:
                policy.act(copy.deepcopy(f['observation']),f['configuration'])
            self.assertEqual(len(counter),len(FIXTURES))

    def test_sell_stage_preserves_selected_units_and_expense_positions(self):
        policy=CapSell()
        calls=[];original=policy.production.act
        def selected(obs,cfg):
            out=original(obs,cfg);calls.append(copy.deepcopy(out));return out
        policy.production.act=selected
        for f in FIXTURES:
            out=policy.act(copy.deepcopy(f['observation']),f['configuration'])
            base=calls[-1]
            self.assertEqual(out['farmer'],base['farmer'])
            self.assertEqual(out['hands'],base['hands'])
            for i,order in enumerate(base['market']):
                if order and order[0]!='SELL':self.assertEqual(out['market'][i],order)
        self.assertEqual(len(calls),len(FIXTURES))

    def test_archive_has_no_checkout_dependency(self):
        for arm in ('carrot_cap','carrot_sell','carrot_cap_sell_safe',
                    'carrot_cap_sell_dated','carrot_cap_sell_conserved','flora'):
            with tempfile.TemporaryDirectory(prefix='t08-archive-') as td:
                root=Path(td);archive=root/'agent.tar.gz'
                build(arm,archive)
                with tarfile.open(archive) as t:t.extractall(root,filter='data')
                fixture=root/'obs.json';fixture.write_text(json.dumps(FIXTURES[0]))
                code="import json,sys;sys.path.insert(0,sys.argv[1]);import main;f=json.load(open(sys.argv[2]));print(json.dumps(main.agent(f['observation']) if sys.argv[3]=='flora' else main.agent(f['observation'],f['configuration'])))"
                result=subprocess.run([sys.executable,'-I','-c',code,str(root),str(fixture),arm],
                                      cwd=root,capture_output=True,text=True,timeout=10,check=True)
                actual=json.loads(result.stdout)
                expected=load(HERE/'arms'/f'{arm}.py','fixture_'+arm)
                wanted=expected.agent(FIXTURES[0]['observation']) if arm=='flora' else expected.agent(FIXTURES[0]['observation'],FIXTURES[0]['configuration'])
                self.assertEqual(actual,wanted)

    def test_deposit_phase_and_conservation(self):
        from conserved_sell_adapter import possible_extra_deposits,unbanked
        farm={'farmer':[0,0],'hands':[], 'tiles':[[{} for _ in range(10)] for _ in range(10)]}
        farm['tiles'][0][2]={'animal':'GOOSE','yield_units':3}
        private={'inventories':[{'EGG':2}],'shed':{'EGG':9}}
        events=possible_extra_deposits(farm,private,20,23)
        self.assertTrue(events)
        self.assertTrue(all(e[0]==23 and e[1]=='after' for e in events))
        self.assertEqual(unbanked(farm,private),{'EGG':5})
        farm['tiles'][0][2]['yield_units']=0
        private['inventories'][0]={};private['shed']['EGG']+=5
        self.assertEqual(unbanked(farm,private).get('EGG',0),0)

if __name__=='__main__':unittest.main()
