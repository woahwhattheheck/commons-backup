# SPDX-License-Identifier: Apache-2.0
"""Completion ordering for the one receipt reader; synthetic evidence only."""
import unittest

import check_joint_receipt as reader
import test_funded_receipt as fixtures


class FooterOrderTests(unittest.TestCase):
    setUp = fixtures.FundedReceiptTests.setUp
    write = fixtures.FundedReceiptTests.write
    inspect = fixtures.FundedReceiptTests.inspect

    def test_funded_success_before_count_is_incomplete(self):
        self.members['funded-join-tests.log'] = 'OK\n\nRan 16 tests in 0.1s\n'
        result = self.inspect()
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertFalse(result['suites']['funded_join']['reported_pass'])
        self.assertTrue(result['provider_digest_matched'])

    def test_core_success_before_count_is_incomplete(self):
        for label, (log, _, count, _) in reader.SUITES.items():
            with self.subTest(suite=label):
                self.members = fixtures.funded_members()
                self.members[log] = f'OK\n\nRan {count} tests in 0.1s\n'
                result = self.inspect()
                self.assertEqual(result['status'], 'INCOMPLETE')
                self.assertEqual(result['core_receipt']['status'], 'INCOMPLETE')
                self.assertFalse(result['suites'][label]['reported_pass'])

    def test_valid_order_preserves_optional_json_trailer(self):
        self.members['funded-join-tests.log'] = (
            'test_example ... ok\nRan 16 tests in 0.1s\n\nOK\n'
            '{"test_methods": 16, "successful": true}\n')
        result = self.inspect()
        self.assertEqual(result['status'], 'COMPLETE_PASS')
        self.assertEqual(result['reported_test_methods'], 73)
        self.assertEqual(result['tests_rerun'], 0)
        self.assertEqual(result['game_panels'], 0)
        self.assertEqual(result['seeds_consumed'], [])


if __name__ == '__main__':
    unittest.main()
