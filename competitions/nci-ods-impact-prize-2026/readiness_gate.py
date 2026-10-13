#!/usr/bin/env python3
import argparse,json
from pathlib import Path
SCHEMA='nci-ods-impact-readiness/v1';GATES=('official_rules_rechecked','eligibility_confirmed','human_substantive_review','submission_fields_reconciled','account_registration_complete','external_submission_authorized')
def main(argv=None):
 ap=argparse.ArgumentParser();ap.add_argument('--state',type=Path,default=Path(__file__).with_name('READINESS.json'));a=ap.parse_args(argv)
 try:v=json.loads(a.state.read_text())
 except Exception as e:print('BLOCKED: unreadable state',e);return 2
 if type(v) is not dict or v.get('schema')!=SCHEMA or type(v.get('gates')) is not dict or set(v['gates'])!=set(GATES):print('BLOCKED: malformed readiness schema');return 2
 if any(type(v['gates'][g]) is not bool for g in GATES):print('BLOCKED: gates must be booleans');return 2
 blocked=[g for g in GATES if not v['gates'][g]]
 if blocked:print('BLOCKED: '+', '.join(blocked));return 2
 print('READY: all explicit human/account/rule gates are true');return 0
if __name__=='__main__':raise SystemExit(main())
