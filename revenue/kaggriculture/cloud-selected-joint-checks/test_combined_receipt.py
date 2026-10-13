# SPDX-License-Identifier: Apache-2.0
"""Read-side checks for the ATLAS v2 aggregate; no producer/test/game execution."""
import hashlib
import json
import unittest
import test_funded_receipt as fixtures
funded_members = fixtures.funded_members
import check_joint_receipt as reader


def with_combined(members):
    spec = dict(reader.SUITES)
    row = reader.SUPPLEMENTS['joined_wrapper']
    spec['joined_wrapper'] = (*row[:3], row[3][0])
    spec['funded_join'] = reader.OPTIONAL_SUITES['funded_join']
    snap = members['SOURCE-SNAPSHOT.json']
    combined = dict(schema='titan.selected-projection.combined.v2', checkout=snap['checkout'],
                    run_id=snap['run_id'], attempt=snap['attempt'], complete=True,
                    successful=True, problems=[], full_games=0)
    combined['suites'] = {key: dict(tests=row[2], successful=True, log=row[0],
                                     test_source_sha256=snap['files'][row[3]]['sha256'])
                          for key,row in spec.items()}
    combined['suite_count'] = len(spec)
    combined['total_tests'] = combined['observed_tests'] = sum(row[2] for row in spec.values())
    combined['input_sha256'] = {name: hashlib.sha256(
        (json.dumps(value) if isinstance(value,dict) else value).encode()).hexdigest()
        for name,value in members.items()}
    members['COMBINED-RESULTS.json'] = combined
    return members


class CombinedReceiptTests(unittest.TestCase):
    # Reuse fixture mechanics, not the inherited funded test methods.
    setUp = fixtures.FundedReceiptTests.setUp
    write = fixtures.FundedReceiptTests.write
    inspect = fixtures.FundedReceiptTests.inspect

    def test_bound_v2_summary(self):
        self.members = with_combined(funded_members())
        out = self.inspect()
        self.assertEqual((out['status'],out['reported_test_methods']),('COMPLETE_PASS',73))
        self.assertTrue(out['aggregate_summary']['declarations_checked'])
        self.assertTrue(out['aggregate_summary']['total_matches_recognized'])

    def test_v2_totals_and_counts_are_typed_and_consistent(self):
        for field in ('suite_count','total_tests','observed_tests'):
            for value in (None, True, 999):
                with self.subTest(field=field,value=value):
                    self.members = with_combined(funded_members())
                    self.members['COMBINED-RESULTS.json'][field] = value
                    self.assertEqual(self.inspect()['status'],'FAIL')

    def test_v2_suite_log_source_and_result_must_agree(self):
        for field,value in (('log','other-tests.log'),('tests',19),('successful',False),
                            ('test_source_sha256','0'*64)):
            with self.subTest(field=field):
                self.members = with_combined(funded_members())
                self.members['COMBINED-RESULTS.json']['suites']['funded_join'][field] = value
                self.assertEqual(self.inspect()['status'],'FAIL')

    def test_v2_input_digest_checks_original_bytes(self):
        for value in ('0'*64,None):
            with self.subTest(value=value):
                self.members = with_combined(funded_members())
                self.members['COMBINED-RESULTS.json']['input_sha256']['funded-join-results.json'] = value
                self.assertEqual(self.inspect()['status'],'FAIL')
        self.members = with_combined(funded_members())
        del self.members['COMBINED-RESULTS.json']['input_sha256']['SOURCE-SNAPSHOT.json']
        self.assertEqual(self.inspect()['status'],'FAIL')

    def test_v2_wrong_run_and_false_completion_fail(self):
        for field,value in (('run_id','456'),('attempt','2'),('complete',False),
                            ('successful',False),('problems',['bad source']),('full_games',True)):
            with self.subTest(field=field):
                self.members = with_combined(funded_members())
                self.members['COMBINED-RESULTS.json'][field] = value
                self.assertEqual(self.inspect()['status'],'FAIL')

    def test_v2_undeclared_observed_suite_remains_explicit(self):
        self.members = with_combined(funded_members())
        doc = self.members['COMBINED-RESULTS.json']
        del doc['suites']['funded_join']
        doc['suite_count'] = 4
        doc['observed_tests'] = doc['total_tests'] = 57
        out = self.inspect()
        self.assertEqual(out['status'],'INCOMPLETE')
        self.assertTrue(any('undeclared: funded_join' in p['detail'] for p in out['problems']))

    def test_v2_malformed_nested_objects(self):
        for field in ('suites','input_sha256'):
            with self.subTest(field=field):
                self.members = with_combined(funded_members())
                self.members['COMBINED-RESULTS.json'][field] = []
                self.assertEqual(self.inspect()['status'],'FAIL')

    def test_reporter_log_is_optional_but_source_bound(self):
        self.members = funded_members()
        name = reader.PROJECTION + 'test_combined_report.py'
        self.members['SOURCE-SNAPSHOT.json']['files'][name] = {'sha256':'c'*64}
        self.members['reporter-tests.log'] = 'Ran 22 tests in 0.1s\n\nOK\n'
        out = self.inspect()
        self.assertEqual((out['status'],out['reported_test_methods']),('COMPLETE_PASS',95))
        del self.members['SOURCE-SNAPSHOT.json']['files'][name]
        self.assertEqual(self.inspect()['status'],'INCOMPLETE')


if __name__ == '__main__':
    unittest.main()
