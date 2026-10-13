"""Microsecond ingress and durable-state regressions (stdlib only).

Run from this directory: python -m unittest -v test_timestamp_precision
Repeat with python -O. All checks use unittest, never removable assert.

This suite preserves the #15973 whole-second/ISO-parser hostiles while adapting
the contract for #15965: wall-clock fractions through six digits are accepted
and canonicalized exactly; excess nonzero precision and fractional UTC offsets
fail closed.
"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rights_model import RightsError, SCHEMA, norm_time, parse_time
from rights_store import (evaluate, import_manifest, queues, record_placement,
                          revoke_grant, snapshot)

START = '2026-09-18T12:00:00Z'
END = '2026-09-18T13:00:00Z'
CLOCK = '2026-09-18T11:00:00Z'


def manifest():
    return {'schema': SCHEMA, 'assets': [
        {'asset_id': 'asset-a', 'sha256': 'a' * 64, 'parent_asset_id': None}],
        'grants': [{'grant_id': 'grant-a', 'asset_id': 'asset-a',
                    'authority_ref': 'owner-supplied-fixture',
                    'valid_from': START, 'valid_until': END,
                    'channels': ['web'], 'territories': ['US']}]}


def intent(**changes):
    value = {'asset_id': 'asset-a', 'channel': 'web', 'territory': 'US',
             'starts_at': START, 'ends_at': END}
    value.update(changes)
    return value


class TimestampParsingTests(unittest.TestCase):
    def test_zero_fraction_and_offset_equivalence(self):
        for value in (START, '2026-09-18T12:00:00.0Z',
                      '2026-09-18T12:00:00,000000000000Z',
                      '2026-09-18T14:00:00+02:00',
                      '2026-09-18T12:00:01+00:00:01',
                      '2026-09-18T12:00:00+00:00:00.000000000',
                      '20260918T120000Z', '2026-W38-5T12:00:00Z'):
            with self.subTest(value=value):
                self.assertEqual(norm_time(value, 'test'), START)
                self.assertEqual(parse_time(value, 'test').microsecond, 0)

    def test_date_time_decimal_separator_is_not_a_fraction(self):
        for value in ('2026-09-18.123456Z', '2026-09-18,12:34:56Z',
                      '20260918.123456Z', '2026-W38-5.123456Z'):
            with self.subTest(value=value):
                self.assertEqual(norm_time(value, 'test'), '2026-09-18T12:34:56Z')

    def test_week_date_time_digits_do_not_mask_excess_fraction(self):
        for value in ('2026W38112.0000001Z', '2026W38112,0000001Z'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RightsError, 'at most 6'):
                    norm_time(value, 'test')
                with self.assertRaisesRegex(RightsError, 'at most 6'):
                    parse_time(value, 'test')

    def test_representable_second_fractions_are_preserved(self):
        cases = {
            '.1': '2026-09-18T12:00:00.100000Z',
            '.100000': '2026-09-18T12:00:00.100000Z',
            ',9': '2026-09-18T12:00:00.900000Z',
            '.000001': '2026-09-18T12:00:00.000001Z',
        }
        for suffix, expected in cases.items():
            value = START[:-1] + suffix + 'Z'
            with self.subTest(value=value):
                self.assertEqual(norm_time(value, 'intent.starts_at'), expected)

    def test_excess_nonzero_fraction_rejected_without_rounding(self):
        for suffix in ('.0000001', '.1234567',
                       '.000000000000000000000000000001'):
            value = START[:-1] + suffix + 'Z'
            with self.subTest(value=value):
                with self.assertRaisesRegex(RightsError, 'at most 6'):
                    norm_time(value, 'intent.starts_at')
                with self.assertRaisesRegex(RightsError, 'at most 6'):
                    parse_time(value, 'as_of')

    def test_nonzero_offset_fractions_rejected(self):
        for offset in ('+00:00:00.1', '-00:00:00.1', '+00:00.1',
                       '+01:00:00.1', '-01:00:00.1', '+00:00:00.0000001',
                       '+01:00:00.0000001', '+00:00:00,0000000001'):
            with self.subTest(offset=offset):
                with self.assertRaises(RightsError):
                    norm_time(START[:-1] + offset, 'test')

    def test_fractional_time_and_offset_do_not_cancel_into_acceptance(self):
        with self.assertRaisesRegex(RightsError, 'fractional UTC offsets'):
            norm_time('2026-09-18T12:00:00.5+01:00:00.5', 'test')

    def test_utc_overflow_is_domain_error(self):
        for value in ('0001-01-01T00:00:00+00:01',
                      '9999-12-31T23:59:59-00:01'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RightsError, 'UTC range'):
                    norm_time(value, 'test')

    def test_valid_utc_range_boundaries(self):
        for value in ('0001-01-01T00:00:00Z', '9999-12-31T23:59:59Z'):
            with self.subTest(value=value):
                self.assertEqual(norm_time(value, 'test'), value)

    def test_invalid_and_naive_values_are_domain_errors(self):
        for value in (None, 0, True, [], {}, '', 'nonsense',
                      '2026-09-18', '2026-09-18T12:00:00',
                      '2026-09-18T12:00:60Z'):
            with self.subTest(value=value):
                with self.assertRaises(RightsError):
                    norm_time(value, 'test')


class TimestampStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'rights.db'
        import_manifest(self.db, manifest(), CLOCK)

    def assert_rejected_without_mutation(self, action):
        before = snapshot(self.db)
        with self.assertRaises(RightsError):
            action()
        self.assertEqual(snapshot(self.db), before)

    def test_unrepresentable_grant_and_import_clock_do_not_create_database(self):
        for field in ('valid_from', 'valid_until', 'imported_at'):
            suffix = '.0000001Z'
            with self.subTest(field=field):
                doc = manifest()
                at = CLOCK
                if field == 'imported_at':
                    at = CLOCK[:-1] + suffix
                else:
                    doc['grants'][0][field] = doc['grants'][0][field][:-1] + suffix
                db = Path(self.temp.name) / 'absent' / (field + '.db')
                with self.assertRaises(RightsError):
                    import_manifest(db, doc, at)
                self.assertFalse(db.parent.exists())

    def test_microsecond_grant_and_import_clock_are_persisted_exactly(self):
        doc = manifest()
        doc['grants'][0]['valid_from'] = START[:-1] + '.000001Z'
        db = Path(self.temp.name) / 'micro.db'
        import_manifest(db, doc, CLOCK[:-1] + '.123456Z')
        snap = snapshot(db)
        self.assertEqual(snap['grants'][0]['valid_from'],
                         '2026-09-18T12:00:00.000001Z')
        self.assertEqual(snap['audit'][0]['at'],
                         '2026-09-18T11:00:00.123456Z')

    def test_fractional_placement_overrun_holds_without_record(self):
        candidate = intent(request_id='request-a', ends_at=END[:-1] + '.8Z')
        before = snapshot(self.db)
        out = record_placement(self.db, candidate, CLOCK)
        self.assertEqual(out['status'], 'HOLD')
        self.assertEqual(out['reasons'], ['WINDOW_NOT_AUTHORIZED'])
        self.assertEqual(snapshot(self.db), before)

    def test_fractional_intent_start_is_not_truncated(self):
        candidate = intent(starts_at=START[:-1] + '.9Z')
        out = evaluate(self.db, candidate)
        self.assertEqual(out['status'], 'READY_ON_SUPPLIED_AUTHORITY')
        self.assertEqual(
            norm_time(candidate['starts_at'], 'test'),
            '2026-09-18T12:00:00.900000Z',
        )

    def test_fractional_replay_cannot_match_different_whole_second_identity(self):
        record_placement(self.db, intent(request_id='request-a'), CLOCK)
        for field in ('starts_at', 'ends_at'):
            for suffix in ('.1Z', '.9Z', '.0000001Z'):
                candidate = intent(request_id='request-a')
                candidate[field] = candidate[field][:-1] + suffix
                with self.subTest(field=field, suffix=suffix):
                    self.assert_rejected_without_mutation(
                        lambda: record_placement(self.db, candidate, CLOCK))

    def test_equivalent_fractional_replay_preserves_identity(self):
        candidate = intent(request_id='request-a',
                           starts_at=START[:-1] + '.1Z',
                           ends_at='2026-09-18T12:59:59.1Z')
        first = record_placement(self.db, candidate, CLOCK[:-1] + '.5Z')
        again = record_placement(
            self.db,
            intent(request_id='request-a',
                   starts_at=START[:-1] + '.100000Z',
                   ends_at='2026-09-18T12:59:59.100000Z'),
            CLOCK[:-1] + '.6Z',
        )
        self.assertEqual(first['status'], 'RECORDED')
        self.assertEqual(again['status'], 'IDEMPOTENT_REPLAY')
        self.assertEqual(first['intent_sha256'], again['intent_sha256'])
        self.assertEqual(again['recorded_at'], '2026-09-18T11:00:00.500000Z')

    def test_fractional_recorded_clock_is_exact_in_ledger_and_audit(self):
        result = record_placement(
            self.db, intent(request_id='request-a'), CLOCK[:-1] + '.5Z')
        self.assertEqual(result['recorded_at'],
                         '2026-09-18T11:00:00.500000Z')
        snap = snapshot(self.db)
        self.assertEqual(snap['placements'][0]['recorded_at'],
                         '2026-09-18T11:00:00.500000Z')
        self.assertEqual(snap['audit'][-1]['at'],
                         '2026-09-18T11:00:00.500000Z')

    def test_fractional_revocation_is_exact_and_replayable(self):
        first = revoke_grant(self.db, 'grant-a', START[:-1] + '.5Z')
        again = revoke_grant(self.db, 'grant-a', START[:-1] + '.500000Z')
        self.assertEqual(first['revoked_at'],
                         '2026-09-18T12:00:00.500000Z')
        self.assertEqual(again['status'], 'IDEMPOTENT_REPLAY')
        self.assertEqual(snapshot(self.db)['grants'][0]['revoked_at'],
                         '2026-09-18T12:00:00.500000Z')

    def test_fractional_revocation_replay_cannot_match_whole_second(self):
        revoke_grant(self.db, 'grant-a', START)
        for suffix in ('.1Z', '.9Z', '.0000001Z'):
            with self.subTest(suffix=suffix):
                self.assert_rejected_without_mutation(lambda: revoke_grant(
                    self.db, 'grant-a', START[:-1] + suffix))

    def test_fractional_queue_clock_is_supported_to_microseconds(self):
        out = queues(self.db, START[:-1] + '.123456Z')
        self.assertEqual(out['as_of'], '2026-09-18T12:00:00.123456Z')
        self.assert_rejected_without_mutation(lambda: queues(
            self.db, START[:-1] + '.1234567Z'))

    def test_utc_overflow_before_new_database_creation(self):
        db = Path(self.temp.name) / 'not-created' / 'state.db'
        with self.assertRaises(RightsError):
            import_manifest(db, manifest(), '0001-01-01T00:00:00+00:01')
        self.assertFalse(db.parent.exists())

    def test_utc_overflow_does_not_mutate_placement_or_revocation(self):
        bad = '9999-12-31T23:59:59-00:01'
        self.assert_rejected_without_mutation(lambda: record_placement(
            self.db, intent(request_id='request-a'), bad))
        self.assert_rejected_without_mutation(lambda: revoke_grant(self.db, 'grant-a', bad))

    def test_whole_second_edges_and_one_second_outside(self):
        self.assertEqual(evaluate(self.db, intent())['status'], 'READY_ON_SUPPLIED_AUTHORITY')
        for change in ({'starts_at': '2026-09-18T11:59:59Z'},
                       {'ends_at': '2026-09-18T13:00:01Z'}):
            with self.subTest(change=change):
                result = evaluate(self.db, intent(**change))
                self.assertEqual(result['status'], 'HOLD')
                self.assertEqual(result['reasons'], ['WINDOW_NOT_AUTHORIZED'])

    def test_zero_fraction_placement_replay_preserves_hash_and_audit(self):
        first = record_placement(self.db, intent(request_id='request-a'), CLOCK)
        before = snapshot(self.db)
        again = record_placement(self.db, intent(request_id='request-a',
            starts_at='2026-09-18T14:00:00.000000000+02:00',
            ends_at='2026-09-18T15:00:00,000+02:00'), CLOCK)
        self.assertEqual(again['status'], 'IDEMPOTENT_REPLAY')
        self.assertEqual(again['intent_sha256'], first['intent_sha256'])
        self.assertEqual(snapshot(self.db), before)

    def test_whole_second_changed_request_still_rejected(self):
        record_placement(self.db, intent(request_id='request-a'), CLOCK)
        self.assert_rejected_without_mutation(lambda: record_placement(self.db,
            intent(request_id='request-a', starts_at='2026-09-18T12:00:01Z'), CLOCK))

    def test_zero_fraction_revocation_replay_preserves_audit(self):
        revoke_grant(self.db, 'grant-a', START)
        before = snapshot(self.db)
        result = revoke_grant(self.db, 'grant-a', '2026-09-18T14:00:00.000+02:00')
        self.assertEqual(result['status'], 'IDEMPOTENT_REPLAY')
        self.assertEqual(snapshot(self.db), before)

    def test_whole_second_workflow_and_snapshot_compatibility(self):
        result = record_placement(self.db, intent(request_id='request-a'), CLOCK)
        self.assertEqual(result['status'], 'RECORDED')
        self.assertEqual(queues(self.db, CLOCK, 1)['renewal_review'][0]['state'], 'EXPIRING')
        revoke_grant(self.db, 'grant-a', '2026-09-18T12:30:00Z')
        self.assertEqual(queues(self.db, END, 0)['retraction_review'][0]['request_id'], 'request-a')
        self.assertEqual(evaluate(self.db, intent())['reasons'], ['REVOKED_GRANT'])
        self.assertEqual(snapshot(self.db)['snapshot_sha256'],
                         'ab5b6c418059575b5b5b1a06adf7f27ac254087085202d53145cd70f63972dce')


if __name__ == '__main__':
    unittest.main()
