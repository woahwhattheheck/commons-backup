#!/usr/bin/env python3
"""Run the existing fictional interview through a declared disagreement change.

The three scenarios are fictional variants, not adjudicated University findings.
Outputs go to a new private directory; no input or prior report is overwritten.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import interview_adapter as ia


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf-8')


def run(output):
    root=Path(__file__).parent
    session=ia.load_json(root/'data/session.json')
    register_path=root/'data/source_register.json'
    missing=copy.deepcopy(session)
    missing['notes'][2]['disagrees_with']='N12'
    supplied=copy.deepcopy(missing)
    supplied['notes'].append({
        'note_id':'N12','participant_id':'P1','question_id':'Q2',
        'stated_practice':'The nightly suite was disabled for the most recent fictional integration window.',
        'concrete_example':'The fictional scheduler change CH-SYN-12 paused that window.',
        'corroborating_artifact':None,'disagrees_with':None,
        'follow_up':'Request the scheduler export for the same window before deciding between the accounts.'})
    output=Path(output)
    ia._empty_output(output)
    output.mkdir(parents=True,exist_ok=False)
    rows=[]
    for name,payload in [('baseline',session),('counterpart_missing',missing),('counterpart_supplied',supplied)]:
        case=output/name;case.mkdir()
        source=case/'session.json';source.write_bytes(canonical(payload))
        records,diagnostics,_=ia.build(source,register_path,case/'imported')
        counts={status:sum(r['status']==status for r in records)
                for status in (ia.CORROBORATED,ia.DISPUTED,ia.ILLUSTRATED,ia.STATED)}
        row=next(r for r in records if r['record_id'].endswith('-N3'))
        rows.append({'scenario':name,'records':len(records),'counts':counts,
            'errors':sum(d['severity']==ia.ERROR for d in diagnostics),
            'changed_note':row,'session_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'review_sha256':hashlib.sha256((case/'imported/capture_review.json').read_bytes()).hexdigest()})
    summary={'fiction_notice':session['fiction_notice'],'finding_verified':False,'scenarios':rows}
    (output/'rehearsal.json').write_bytes(canonical(summary))
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:
        print(canonical(run(args.out)).decode('utf-8'),end='')
        return 0
    except (ValueError,OSError) as exc:
        parser.exit(2,f'REFUSED: {exc}\n')


if __name__=='__main__':raise SystemExit(main())
