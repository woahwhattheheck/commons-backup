"""R9C4 review regression: readable statuses must identify their target."""
from __future__ import annotations
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get('LIFECYCLE_SOURCE', HERE / 'access_lifecycle.py')).resolve()
SPEC = importlib.util.spec_from_file_location('uiowa053_readable_subject', SOURCE)
access = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(access)


def packet(field='entitlement', reverse=False, stale=False):
    change = {'system':'SYN-service', 'intent':'revoke', 'environment':'development',
              'entitlement':'old-admin', 'effective_on':'2026-09-18'}
    other = dict(change)
    other[field] = {'entitlement':'old-release', 'environment':'deployment',
                    'effective_on':'2026-09-17'}[field]
    observation = {'kind':'system_state_observation','system':'SYN-service','intent':'revoke',
                   'statement':'Fictional target-specific observation','locator':'SYN-reader-1',
                   'observed_on':'2026-09-16' if stale else '2026-09-19',
                   'matches_intent':True,field:change[field]}
    changes = [other,change] if reverse else [change,other]
    return {'cases':[{'case_id':'SYN-READER','lifecycle_event':'mover',
                     'event_on':'2026-09-18','access_changes':changes,'evidence':[observation]}]}


def report(value):
    return access.review_all(access.load_cases(value))


def identity(row):
    fields = '; '.join(name+'='+(json.dumps(row[name],ensure_ascii=False) if row[name] else 'UNKNOWN')
                       for name in ('entitlement','environment','effective_on'))
    return access._markdown_values(row['system']+' ['+fields+']')


class ReadableTargetIdentityTests(unittest.TestCase):
    def check_case(self, field, reverse=False):
        result = report(packet(field,reverse))
        before = copy.deepcopy(result)
        matrix, scenarios = access.render_matrix(result), access.render_scenarios(result)
        for row in result['cases'][0]['per_system']:
            label = identity(row)
            self.assertTrue(any(label in line and '**'+row['status']+'**' in line
                                for line in matrix.splitlines()), matrix)
            self.assertIn('| '+label+' | revoke | `'+row['status']+'` |',scenarios)
            if row['what_would_settle_it']:
                self.assertIn('- *'+label+'* — '+row['what_would_settle_it'],scenarios)
                self.assertIn('the weakest system is '+label+' at '+row['status'],scenarios)
        self.assertEqual(result,before)
        self.assertEqual([row['system'] for row in result['cases'][0]['per_system']],['SYN-service']*2)
        return result,matrix,scenarios

    def test_entitlements_identify_both_statuses_and_follow_up(self):
        self.check_case('entitlement')

    def test_environments_identify_both_statuses_and_follow_up(self):
        self.check_case('environment')

    def test_repeated_change_dates_identify_both_statuses_and_follow_up(self):
        self.check_case('effective_on')

    def test_target_reordering_does_not_rebind_identity_or_status(self):
        for field in ('entitlement','environment','effective_on'):
            with self.subTest(field=field):
                _,matrix_a,scenarios_a=self.check_case(field)
                _,matrix_b,scenarios_b=self.check_case(field,True)
                self.assertEqual(sorted(matrix_a.splitlines()),sorted(matrix_b.splitlines()))
                self.assertEqual(sorted(scenarios_a.splitlines()),sorted(scenarios_b.splitlines()))

    def test_excluded_observation_keeps_its_target_identity(self):
        for field in ('entitlement','environment','effective_on'):
            with self.subTest(field=field):
                result=report(packet(field,stale=True));matrix=access.render_matrix(result)
                target=next(row for row in result['cases'][0]['per_system'] if row['evidence_excluded_as_stale'])
                self.assertIn('| `SYN-READER` | '+identity(target)+' | 2026-09-16 |',matrix)
                self.assertIn('- *'+identity(target)+'* —',access.render_scenarios(result))

    def test_case_summary_names_only_the_unconfirmed_target(self):
        result=report(packet());matrix=access.render_matrix(result)
        unknown=next(row for row in result['cases'][0]['per_system'] if row['status']=='NO_EVIDENCE')
        confirmed=next(row for row in result['cases'][0]['per_system'] if row['status']=='CONFIRMED_IN_SYSTEM')
        summary=matrix.split('## Case summary\n',1)[1].split('## Limits',1)[0]
        self.assertIn(identity(unknown),summary)
        self.assertNotIn(identity(confirmed),summary)

    def test_empty_and_literal_unknown_entitlements_remain_distinct(self):
        value=packet();case=value['cases'][0]
        case['access_changes'][0]['entitlement']=''
        case['access_changes'][1]['entitlement']='UNKNOWN'
        case['evidence'][0]['entitlement']='UNKNOWN'
        result=report(value)
        for rendered in (access.render_matrix(result),access.render_scenarios(result)):
            self.assertIn('entitlement=UNKNOWN;',rendered)
            self.assertIn('entitlement="UNKNOWN";',rendered)

    def test_real_cli_readable_exports_preserve_target_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp);source=temp/'cases.json';source.write_text(json.dumps(packet()))
            matrix=temp/'matrix.md';scenarios=temp/'scenarios.md'
            run=subprocess.run([sys.executable,*(['-O'] if sys.flags.optimize else []),str(SOURCE),
                                '--cases',str(source),'--matrix-out',str(matrix),'--scenarios-out',str(scenarios)],
                               capture_output=True,text=True,timeout=20)
            self.assertEqual(run.returncode,0,run.stderr)
            for row in report(packet())['cases'][0]['per_system']:
                label=identity(row)
                self.assertTrue(any(label in line and row['status'] in line for line in matrix.read_text().splitlines()))
                self.assertTrue(any(label in line and row['status'] in line for line in scenarios.read_text().splitlines()))


if __name__=='__main__':
    unittest.main(verbosity=2)
