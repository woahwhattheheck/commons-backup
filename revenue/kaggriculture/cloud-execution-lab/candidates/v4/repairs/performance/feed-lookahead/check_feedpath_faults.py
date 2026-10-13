# SPDX-License-Identifier: Apache-2.0
"""Require behavioral assertion failures from six deliberately broken consumers."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from compose_feedpath import compose, digest

MUTANTS={
 'omit_last_hand':('elif actor <= len(_fp_hands):','elif actor < len(_fp_hands):'),
 'wrong_hand_offset':('_fp_hands[actor - 1]','(_fp_hands[actor] if actor < len(_fp_hands) else None)'),
 'missing_pass':("action = action if action else ['PASS']",'action = action'),
 'bypass_list_subclass':('type(_fp_hands) is list','isinstance(_fp_hands, list)'),
 'discard_farmer':('action = _fp_farmer',"action = ['PASS']"),
 'copy_farmer_alias':('action = _fp_farmer','action = (_fp_farmer[:] if type(_fp_farmer) is list else _fp_farmer)'),
}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    env=dict(os.environ,TITAN_NATIVE=str(args.root.resolve()))
    env.pop('FEEDPATH_CANDIDATE',None)
    command=[sys.executable]+(['-O'] if sys.flags.optimize else [])+[str(Path(__file__).with_name('check_feedpath.py'))]
    control=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
    if control.returncode or 'Ran 17 tests' not in control.stderr or not control.stderr.rstrip().endswith('OK'):
        raise RuntimeError('unchanged control failed: '+control.stderr)
    source=compose((args.root/'operating_stock.py').read_text())
    rows=[]
    with tempfile.TemporaryDirectory(prefix='feedpath-faults-') as directory:
        for name,(before,after) in MUTANTS.items():
            if source.count(before)!=3:
                raise RuntimeError('fault anchor drift: '+name)
            mutated=source.replace(before,after)
            path=Path(directory)/(name+'.py');path.write_text(mutated)
            run=subprocess.run(command,env=dict(env,FEEDPATH_CANDIDATE=str(path)),capture_output=True,text=True,timeout=60)
            found=re.search(r'FAILED \(failures=(\d+)\)',run.stderr)
            if run.returncode!=1 or not found or int(found[1])<1 or 'ERROR:' in run.stderr:
                raise RuntimeError('not an assertion-only rejection: '+name+'\n'+run.stderr)
            rows.append({'name':name,'source_sha256':digest(mutated.encode()),
                         'assertion_failures':int(found[1]),'errors':0,'exit_code':run.returncode,
                         'log':run.stderr})
    result={'optimized':bool(sys.flags.optimize),'control_log':control.stderr,'mutants':rows,
            'candidate_sha256':digest(source.encode()),'count':len(rows)}
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'optimized':result['optimized'],'mutants_rejected':len(rows),
                      'assertion_failures':[r['assertion_failures'] for r in rows],'errors':0}))

if __name__=='__main__':main()
