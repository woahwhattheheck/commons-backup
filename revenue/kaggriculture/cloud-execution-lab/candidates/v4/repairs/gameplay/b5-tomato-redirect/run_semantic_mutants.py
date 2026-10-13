# SPDX-License-Identifier: Apache-2.0
"""Require green controls, then assertion failures (not import errors) for faults."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
HELPER_MUTANTS=[
 ('spend_retained_fertilizer','if sum(shed.values()) < 100:','if sum(shed.values()) < 99:'),
 ('water_not_required',"or tile.get('watered_today') is not True","or False"),
 ('covered_day_fertilized_again','or coverage >= day','or coverage > day'),
 ('premature_production','not 8 <= day + 1 - planted <= 11','not 7 <= day + 1 - planted <= 11'),
 ('expired_production','not 8 <= day + 1 - planted <= 11','not 8 <= day + 1 - planted <= 12'),
 ('ignore_yield_cap','or held > 2','or held > 3'),
 ('sell_frees_room_ignored',"for order in market[:cap]:","for order in []:"),
 ('live_pickup_ignored','for command in live_commands:\n','for command in live_commands:\n        if command[0] == "PICKUP": continue\n'),
 ('truncate_ghost_plant_demand','out = deepcopy(action)\n','out = deepcopy(action)\n    out["hands"] = out.get("hands", [])[:len(inventories)-1]\n'),
 ('mutate_parent','out = deepcopy(action)','out = action'),
 ('ignore_enabled','if enabled is not True:','if False:'),
 ('invent_fill',"'observed_fill': False","'observed_fill': True"),
]
COMPOSER_MUTANTS=[
 ('dead_config_key','if not self.features.tomato_discard_salvage:', 'if True:'),
 ('optional_on_fallback',"if self.diagnostics.get('status') != 'completed':",'if False:'),
 ('miss_pending_plan',"if pending and (not isinstance(pending, dict)","if False and (not isinstance(pending, dict)"),
 ('stale_snapshot',"'            self.consumer.selected_post_units = None\\n'", "'            self.consumer.selected_post_units = self.consumer.selected_post_units\\n'"),
 ('stale_returned_action',"'            self.selected = deepcopy(returned)\\n'", "'            pass  # deliberately leave old selected bytes\\n'"),
 ('before_last_market_guard',"anchor = '        returned = self._early_capital_selected(obs, cfg or {}, returned)\\n'", "anchor = '        returned = self._feed_stock_selected(obs, cfg or {}, returned)\\n'"),
]


def invoke(test, report, *, optimized, env):
    command=[sys.executable]+(['-O'] if optimized else [])+[str(HERE/test),'--report',str(report)]
    result=subprocess.run(command,capture_output=True,text=True,env=env,timeout=30)
    if not report.exists():raise RuntimeError('test report missing: '+result.stderr[-1600:])
    return result.returncode,json.loads(report.read_text())


def run():
    rows=[];controls=[]
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        for optimized in (False,True):
            for family,test,source,mutants,key in (
                ('helper','test_discarded_fertilizer.py','discarded_fertilizer_tomato.py',HELPER_MUTANTS,'TOMATO_HELPER'),
                ('native','test_native_binding.py','compose_native.py',COMPOSER_MUTANTS,'TOMATO_COMPOSER')):
                env=dict(os.environ);env.pop('TOMATO_HELPER',None);env.pop('TOMATO_COMPOSER',None)
                code,report=invoke(test,root/f'control-{family}-{optimized}.json',optimized=optimized,env=env)
                if code or report['failures'] or report['errors'] or report['skips']:
                    raise RuntimeError('green control failed before mutation: '+str(report))
                controls.append({'family':family,'optimized':optimized,'tests':report['tests']})
                text=(HERE/source).read_text()
                for name,old,new in mutants:
                    if text.count(old)!=1:raise ValueError('nonunique mutant anchor: '+name)
                    mutant=root/f'{family}-{name}.py';mutant.write_text(text.replace(old,new,1))
                    # Native composer reads the helper beside itself, so preserve
                    # its same pinned source rather than accepting setup failure.
                    if family=='native':
                        (root/'discarded_fertilizer_tomato.py').write_bytes((HERE/'discarded_fertilizer_tomato.py').read_bytes())
                    env[key]=str(mutant)
                    code,result=invoke(test,root/f'{name}-{optimized}.json',optimized=optimized,env=env)
                    rejected=(code!=0 and result['failures']>0 and result['errors']==0 and result['skips']==0)
                    row={'family':family,'name':name,'optimized':optimized,'assertion_rejected':rejected,
                         'failures':result['failures'],'errors':result['errors'],'skips':result['skips'],
                         'mutant_sha256':hashlib.sha256(mutant.read_bytes()).hexdigest()}
                    rows.append(row)
                    if not rejected:raise RuntimeError('fault not assertion-rejected: '+str(row))
    return {'controls':controls,'mutants':rows,'mutants_per_mode':len(HELPER_MUTANTS)+len(COMPOSER_MUTANTS),
            'scope':'deliberately broken candidate/composer copies; no field games'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    result=run();a.report.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,sort_keys=True))
