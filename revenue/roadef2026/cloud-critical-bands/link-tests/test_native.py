#!/usr/bin/env python3
"""Independent ASTRA-LINK binary/checker contracts for TRACE critical bands.

Inputs are constructed, not official development instances. All raw process
outputs stay in --output. Runtime budgets are upper bounds, not timing claims.
"""
from __future__ import annotations
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import time
import unittest
from witness import write_fixture

CONFIG = None

def vector(report):
    parsed=json.loads(report.read_text(),parse_float=Decimal)
    if parsed['valid'] is not True:
        raise AssertionError('Checker did not validate output')
    return sorted((Decimal(str(x['sat'])) for x in parsed['saturations']),reverse=True)

class NativeTests(unittest.TestCase):
    def setUp(self):
        self.root=CONFIG.output/self._testMethodName
        self.root.mkdir(parents=True,exist_ok=True)
    def run_solver(self,label,*,base=False,enabled=True,high=33,rank_limit=128,rounds=1024,
                   seconds=10,slots=1,budget=4,segments=2,noncontiguous=False,maintenance=False,
                   resume=None,output=None):
        inputs=write_fixture(self.root/(label+'-input'),high,slots=slots,budget=budget,
                             max_segments=segments,noncontiguous=noncontiguous,maintenance=maintenance)
        output=output or self.root/(label+'.solution.json')
        stats=self.root/(label+'.stats.json')
        env={k:v for k,v in os.environ.items() if not k.startswith(('SEDGE_','FLEET_','LINK_','CLOUD_INITIAL_'))}
        env.update(SEDGE_SECONDS=str(seconds),SEDGE_MAX_ROUNDS=str(rounds),SEDGE_STATS=str(stats),
                   FLEET_JOINT='0',FLEET_CRITICAL_BANDS=str(int(enabled)),FLEET_CRITICAL_MAX_RANK=str(rank_limit),
                   FLEET_BAND_STATS=str(self.root/(label+'.bands.json')))
        if resume is not None: env['CLOUD_INITIAL_SOLUTION']=str(resume)
        binary=CONFIG.baseline if base else CONFIG.candidate
        command=[str(binary),*map(str,inputs),str(output)]
        began=time.monotonic()
        run=subprocess.run(command,env=env,capture_output=True,timeout=seconds+10)
        (self.root/(label+'.stdout')).write_bytes(run.stdout)
        (self.root/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr.decode(errors='replace'))
        measures=json.loads(stats.read_text())
        band_path=self.root/(label+'.bands.json')
        telemetry=[json.loads(band_path.read_text())] if band_path.exists() else []
        reports=[]
        for decimals in (6,12):
            target=self.root/f'{label}.checker{decimals}.json'
            cmd=[str(CONFIG.checker),'--net',str(inputs[0]),'--tm',str(inputs[1]),'--scenario',str(inputs[2]),
                 '--srpaths',str(output),'--max-decimal-places',str(decimals)]
            check=subprocess.run(cmd,capture_output=True,timeout=15)
            target.write_bytes(check.stdout);target.with_suffix('.stderr').write_bytes(check.stderr)
            self.assertEqual(check.returncode,0,check.stderr.decode(errors='replace'))
            reports.append(vector(target))
        (self.root/(label+'.receipt.json')).write_text(json.dumps({'command':command,
            'returncode':run.returncode,'wall_with_checks_seconds':time.monotonic()-began,
            'source_binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
            'environment':{k:v for k,v in env.items() if k.startswith(('SEDGE_','FLEET_','LINK_','CLOUD_INITIAL_'))},
            'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest()},indent=2)+'\n')
        return output,measures,telemetry[0] if telemetry else None,reports[0]
    def test_original_and_disabled_correspond(self):
        a=self.run_solver('old',base=True)
        b=self.run_solver('disabled',enabled=False)
        self.assertEqual(a[0].read_bytes(),b[0].read_bytes())
        self.assertEqual({k:v for k,v in a[1].items() if k!='seconds'},{k:v for k,v in b[1].items() if k!='seconds'})
        self.assertEqual(b[2]['rounds'],64);self.assertEqual(b[2]['largest_critical_rank_visited'],32)
    def test_rank34_improves_without_peak_change(self):
        a=self.run_solver('old',base=True);b=self.run_solver('expanded')
        self.assertLess(b[3],a[3]);self.assertEqual(a[3][0],b[3][0])
        self.assertEqual(next(i+1 for i,(x,y) in enumerate(zip(a[3],b[3])) if x!=y),34)
        self.assertEqual(a[3][33],Decimal('5'));self.assertEqual(b[3][33],Decimal('0.5'))
        self.assertEqual(b[2]['bands'][1]['accepts'],1)
    def test_rank_limit32_preserves_plateau(self):
        a=self.run_solver('limited',rank_limit=32)
        self.assertEqual(a[1]['accepted'],0);self.assertEqual(a[2]['largest_critical_rank_visited'],32)
    def test_rank66_requires_third_band(self):
        a=self.run_solver('limited',high=65,rank_limit=64)
        b=self.run_solver('expanded',high=65,rank_limit=128)
        self.assertEqual(a[1]['accepted'],0);self.assertLess(b[3],a[3])
        self.assertEqual(b[2]['bands'][2]['accepts'],1)
    def test_rank130_requires_larger_limit(self):
        a=self.run_solver('limited',high=129,rank_limit=128)
        b=self.run_solver('expanded',high=129,rank_limit=256,rounds=2048)
        self.assertEqual(a[1]['accepted'],0);self.assertLess(b[3],a[3])
        self.assertEqual(b[2]['bands'][3]['accepts'],1)
    def test_segment_limit_preserved(self):
        a=self.run_solver('segment1',segments=1)
        self.assertEqual(a[1]['accepted'],0)
    def test_maintenance_and_budget(self):
        a=self.run_solver('budget0',high=17,slots=2,maintenance=True,budget=0)
        b=self.run_solver('budget3',high=17,slots=2,maintenance=True,budget=3)
        self.assertEqual(a[1]['accepted'],0)
        self.assertLess(b[3],a[3]);self.assertEqual(b[1]['budget_used'],[0,3])
    def test_noncontiguous_identifiers(self):
        a=self.run_solver('old',base=True,noncontiguous=True)
        b=self.run_solver('expanded',noncontiguous=True)
        self.assertLess(b[3],a[3])
    def test_repeat_fixed_work(self):
        a=self.run_solver('first');b=self.run_solver('repeat')
        self.assertEqual(a[0].read_bytes(),b[0].read_bytes());self.assertEqual(a[2],b[2])
        self.assertEqual(a[3],b[3])
    def test_in_place_resume_zero_rounds(self):
        first=self.run_solver('first');before=first[0].read_bytes()
        second=self.run_solver('resume',rounds=0,resume=first[0],output=first[0])
        self.assertEqual(second[0].read_bytes(),before)
        self.assertTrue(second[1]['resumed']);self.assertEqual(second[2]['rounds'],0)
    def test_round_limit_does_not_expand_early(self):
        a=self.run_solver('limited',rounds=64)
        self.assertEqual(a[1]['accepted'],0);self.assertEqual(a[2]['rounds'],64)
        self.assertEqual(a[2]['exit_reason'],'round_limit')
    def test_zero_deadline_keeps_valid_checkpoint(self):
        a=self.run_solver('zero',seconds=0)
        self.assertEqual(a[2]['exit_reason'],'deadline');self.assertEqual(a[2]['rounds'],0)
    def test_small_graph_disabled_and_enabled_match(self):
        a=self.run_solver('old',base=True,high=3)
        b=self.run_solver('expanded',high=3)
        self.assertEqual(a[0].read_bytes(),b[0].read_bytes());self.assertEqual(a[3],b[3])
    @unittest.skipUnless(os.name=='posix','POSIX process signal contract')
    def test_actual_sigterm_checkpoint(self):
        inputs=write_fixture(self.root/'input',129,slots=4)
        output=self.root/'signal.solution.json'
        env={k:v for k,v in os.environ.items() if not k.startswith(('SEDGE_','FLEET_','LINK_','CLOUD_INITIAL_'))}
        env.update(SEDGE_SECONDS='30',SEDGE_MAX_ROUNDS='1000000',FLEET_CRITICAL_BANDS='1',FLEET_CRITICAL_MAX_RANK='2048',FLEET_BAND_STATS=str(self.root/'signal.bands.json'),FLEET_JOINT='1')
        command=[str(CONFIG.candidate),*map(str,inputs),str(output)]
        p=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            ready=select.select([p.stderr],[],[],8)[0];self.assertTrue(ready)
            first=p.stderr.readline();self.assertTrue(first.startswith(b'Loaded '),first)
            p.send_signal(signal.SIGTERM);out,err=p.communicate(timeout=5)
        finally:
            if p.poll() is None:p.kill();p.wait()
        (self.root/'signal.stdout').write_bytes(out);(self.root/'signal.stderr').write_bytes(first+err)
        self.assertEqual(p.returncode,0)
        telemetry=json.loads((self.root/'signal.bands.json').read_text())
        self.assertEqual(telemetry['exit_reason'],'signal')
        checked=subprocess.run([str(CONFIG.checker),'--net',str(inputs[0]),'--tm',str(inputs[1]),
            '--scenario',str(inputs[2]),'--srpaths',str(output),'--max-decimal-places','6'],capture_output=True,timeout=15)
        (self.root/'signal.checker.json').write_bytes(checked.stdout)
        (self.root/'signal.checker.stderr').write_bytes(checked.stderr)
        self.assertEqual(checked.returncode,0,checked.stderr)
        self.assertTrue(json.loads(checked.stdout)['valid'])

def main():
    global CONFIG
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--checker',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    CONFIG=parser.parse_args()
    CONFIG.output.mkdir(parents=True,exist_ok=False)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeTests))
    (CONFIG.output/'RESULT.json').write_text(json.dumps({'methods':result.testsRun,'failures':len(result.failures),
        'errors':len(result.errors),'skipped':len(result.skipped),'success':result.wasSuccessful()},indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())

if __name__=='__main__':main()
