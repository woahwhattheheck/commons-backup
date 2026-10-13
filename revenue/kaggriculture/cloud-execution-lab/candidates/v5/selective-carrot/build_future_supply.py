# SPDX-License-Identifier: Apache-2.0
"""Reproduce optional own-future-supply sale valuation over exact production v3."""
import argparse
import json
from pathlib import Path

from build_delivery import archive_bytes, digest, members

BASELINE_SHA = '20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239'
CANDIDATE_SHA = 'ca8ca6f5d1ffb5ad828db5d924ed27d4d3c2f35b3a54ebd1f4cb311d7cdea9e1'
HELPER_SHA = 'fa668fe23f3e94ad3b77b0ae1a1c2f3b8727a18447a68939f66c4a3f693fe738'


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Expected one source seam: ' + old[:80])
    return text.replace(old, new)


def compose(baseline, helper):
    if digest(helper) != HELPER_SHA:
        raise ValueError('Unexpected projection helper')
    files = dict(baseline)
    text = files['selected_sell_core.py'].decode().replace('\r\n','\n')
    text = replace_once(text,
        'def __init__(self, item, inventory, params, shops, config, now, end):',
        'def __init__(self, item, inventory, params, shops, config, now, end, own_future=()):')
    text = replace_once(text, '        self.item,self.inventory,self.params=item,inventory,params',
        '        self.own_future = dict(own_future)\n        self.item,self.inventory,self.params=item,inventory,params')
    text = replace_once(text, '            a,b,inv=self.joint(inv,q,r,alignment)',
        '            a,b,inv=self.joint(inv,q+self.own_future.get(step,0),r,alignment)')
    text = replace_once(text, 'reference,rival_quantity,minimum_now=0,capacity_ok=None,last=718):',
        'reference,rival_quantity,minimum_now=0,capacity_ok=None,last=718,own_future=()):')
    text = replace_once(text, 'model=MarketPath(item,inventory,params,shops,config,now,end)',
        'model=MarketPath(item,inventory,params,shops,config,now,end,own_future)')
    text = replace_once(text, "'reference':list(reference),'plan':list(best_plan),'minimum_now':minimum_now,",
        "'reference':list(reference),'plan':list(best_plan),'minimum_now':minimum_now,\n        'future_own_sales':list(own_future),")
    files['selected_sell_core.py'] = text.encode()
    text = files['frozen_selected.py'].decode().replace('\r\n','\n')
    needle = '            plan,info=optimize_lot(item=item,quantity=quantity'
    text = replace_once(text, needle,
        '            from future_own_supply import projected_sales\n'
        '            own_future=projected_sales(obs,config,base,farm,private,route,item_end,item)\n' + needle)
    text = replace_once(text, 'capacity_ok=feasible,last=last)', 'capacity_ok=feasible,last=last,own_future=own_future)')
    files['frozen_selected.py'] = text.encode()
    files['future_own_supply.py'] = helper
    if digest(archive_bytes(files)) != CANDIDATE_SHA:
        raise ValueError('Composition differs from the tested candidate')
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--tar',type=Path,required=True)
    args = parser.parse_args()
    receipt = args.out.parent/(args.out.name+'-manifest.json')
    if any(p.exists() for p in (args.out,args.tar,receipt)):
        parser.error('Use new output paths')
    baseline = members(args.baseline,BASELINE_SHA)
    helper = Path(__file__).with_name('future_own_supply.py').read_bytes().replace(b'\r\n',b'\n')
    files = compose(baseline,helper)
    args.out.mkdir(parents=True)
    for name,body in files.items():
        path=args.out/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(body)
    args.tar.parent.mkdir(parents=True,exist_ok=True)
    with args.tar.open('xb') as stream:
        stream.write(archive_bytes(files))
    record={'schema':'titan-future-own-supply-build/v1','baseline_sha256':BASELINE_SHA,
        'candidate_sha256':CANDIDATE_SHA,'changed_members':['frozen_selected.py','selected_sell_core.py'],
        'new_members':['future_own_supply.py'],
        'files':{name:digest(body) for name,body in sorted(files.items())},
        'kaggle_submission_hold':True}
    receipt.write_bytes((json.dumps(record,indent=2)+'\n').encode())
    print(json.dumps({'sha256':CANDIDATE_SHA,'members':len(files)}))


if __name__=='__main__':
    main()
