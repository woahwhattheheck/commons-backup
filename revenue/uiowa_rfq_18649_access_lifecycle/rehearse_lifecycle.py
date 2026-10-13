"""Replay fictional evidence arrivals using one captured source/fixture snapshot."""
from __future__ import annotations
import argparse
import copy
import hashlib
import itertools
import json
from pathlib import Path
import sys


def blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run():
    here=Path(__file__).resolve().parent
    source_path=here/'access_lifecycle.py'
    source=source_path.read_bytes()
    fixture=(here/'fixtures/lifecycle_cases.json').read_bytes()
    scope={'__name__':'uiowa053_captured_rehearsal','__file__':str(source_path)}
    exec(compile(source,str(source_path),'exec'),scope)
    original=json.loads(fixture)
    require(blob(fixture)=='d04aca2fae32fce4404b1eb3c60b77c4958fdd63','original fixture changed')
    def assess(packet):
        return scope['review_all'](scope['load_cases'](packet))
    def case(report, case_id):
        return next(c for c in report['cases'] if c['case_id']==case_id)
    snapshots=[]
    def save(label, data, target, expected):
        report=assess(data); selected=case(report,target)
        statuses=[r['status'] for r in selected['per_system']]
        require(statuses==expected,f'{label}: {statuses!r} != {expected!r}')
        snapshots.append({'step':label,'case_id':target,'statuses':statuses,
                          'case_status':selected['case_status'],
                          'unconfirmed':selected['systems_not_confirmed'],
                          'rows':selected['per_system']})
        return report
    contractor='CASE-SYN-LEAVER-01'
    save('1. Original contractor departure',original,contractor,
         ['CONFIRMED_IN_SYSTEM','ACTION_RECORDED','POLICY_ONLY'])
    follow=copy.deepcopy(original)
    entry=next(c for c in follow['cases'] if c['case_id']==contractor)
    entry['evidence'].append({'kind':'system_state_observation','system':'deployment pipeline',
        'statement':'Fictional follow-up: local pipeline account observed disabled',
        'observed_on':'2026-09-06','matches_intent':True,'locator':'SYN-follow-up-pipeline-1'})
    save('2. Pipeline evidence arrives; repository stays unverified',follow,contractor,
         ['CONFIRMED_IN_SYSTEM','ACTION_RECORDED','CONFIRMED_IN_SYSTEM'])
    entry['evidence'].append({'kind':'system_state_observation','system':'source repository',
        'statement':'Fictional follow-up: repository access observed absent',
        'observed_on':'2026-09-06','matches_intent':True,'locator':'SYN-follow-up-repository-1'})
    save('3. Repository evidence arrives; all three declared states evidenced',follow,contractor,
         ['CONFIRMED_IN_SYSTEM']*3)
    mover='CASE-SYN-MOVER-01'
    save('4. Original changed responsibilities',original,mover,
         ['CONFIRMED_IN_SYSTEM','REQUESTED_ONLY'])
    changed=copy.deepcopy(original)
    entry=next(c for c in changed['cases'] if c['case_id']==mover)
    entry['evidence'].append({'kind':'system_state_observation','system':'support console',
        'statement':'Fictional observation: old support role remains assigned',
        'observed_on':'2026-07-16','matches_intent':False,'locator':'SYN-old-role-observation'})
    save('5. Old role is still present',changed,mover,
         ['CONFIRMED_IN_SYSTEM','CONTRADICTED_IN_SYSTEM'])
    entry['evidence'].append({'kind':'approval_record','system':'support console',
        'statement':'Fictional late approval; not a new system observation','observed_on':'2026-07-17'})
    save('6. Extra approval does not erase the contradictory observation',changed,mover,
         ['CONFIRMED_IN_SYSTEM','CONTRADICTED_IN_SYSTEM'])
    emergency='CASE-SYN-EMERGENCY-01'
    save('7. Emergency elevation versus removal',original,emergency,
         ['CONFIRMED_IN_SYSTEM','ACTION_RECORDED'])
    changed=copy.deepcopy(original)
    entry=next(c for c in changed['cases'] if c['case_id']==emergency)
    entry['evidence'].append({'kind':'system_state_observation','system':'deployment pipeline',
        'intent':'revoke','statement':'Fictional observation: temporary role absent',
        'observed_on':'2026-08-14','matches_intent':True,'locator':'SYN-emergency-removal-1'})
    save('8. Removal observed; retrospective approval remains a separate question',changed,emergency,
         ['CONFIRMED_IN_SYSTEM']*2)
    variations=0
    for left,right in itertools.permutations(('role-A','role-B','role-C','role-D'),2):
        for qualifier,intent,reverse in itertools.product((None,left,right,'not-declared'),('grant','revoke'),(False,True)):
            changes=[{'system':'SYN-service','intent':intent,'entitlement':name,'effective_on':'2026-09-18'} for name in (left,right)]
            if reverse: changes.reverse()
            evidence={'kind':'system_state_observation','system':'SYN-service','intent':intent,
                      'statement':'Fictional scoped observation','observed_on':'2026-09-19','matches_intent':True}
            if qualifier is not None: evidence['entitlement']=qualifier
            value={'cases':[{'case_id':'SYN-grid','lifecycle_event':'mover','access_changes':changes,'evidence':[evidence]}]}
            rows=assess(value)['cases'][0]['per_system']
            for row in rows:
                expected='CONFIRMED_IN_SYSTEM' if qualifier==row['entitlement'] else 'NO_EVIDENCE'
                require(row['status']==expected,'evidence crossed a declared entitlement boundary')
            variations+=1
    require(variations==192,'finite audit did not execute all variants')
    return {'seat':'ZZ-KESTREL-P9N','model':'GPT-6 Astra Pro','content_class':'SYNTHETIC_NOT_A_UNIVERSITY_FINDING',
            'tested_source_blob':blob(source),'fixture_blob':blob(fixture),
            'python':sys.version.split()[0],'optimized':bool(sys.flags.optimize),
            'scope':'Captured source and fixture bytes; sparse-component local execution, not hosted CI or live account verification.',
            'snapshots':snapshots,'attribution_variations_checked':variations,
            'limits':['Only declared systems and supplied records are reviewed.',
                      'Confirmed state is not a complete approval or entitlement-review chain.',
                      'Dates have day precision; same-day records do not prove within-day ordering.',
                      'There is no as-of clock filter or authenticated source-locator verification.',
                      'The original conservative contradiction policy remains; later paper does not erase an observation.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    result=run()
    with args.out.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2,sort_keys=True);handle.write('\n')
    print(f"PASS snapshots={len(result['snapshots'])} attribution_variations={result['attribution_variations_checked']} source={result['tested_source_blob']}")


if __name__=='__main__':
    main()
