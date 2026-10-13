from __future__ import annotations

import unittest

import sara_partner_accession as sara


class FailOnSet(dict):
    def __setitem__(self, key, value):
        raise RuntimeError("injected job write failure")


class FailOnAppend(list):
    def append(self, value):
        raise RuntimeError("injected event append failure")


class SaraReplayAtomicityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.manifest = sara.load_fixture()

    def assert_empty_shadow(self, shadow, digest, authoritative):
        self.assertEqual(digest, shadow.state_digest())
        self.assertEqual(authoritative, shadow.authoritative_fingerprint)
        self.assertEqual({}, shadow.accessions)
        self.assertEqual({}, shadow.jobs)
        self.assertEqual({}, shadow.staged_reports)
        self.assertEqual({}, shadow.holds)
        self.assertEqual([], shadow.events)
        self.assertEqual(set(), shadow._seen)
        self.assertEqual(set(), shadow._external)

    def assert_full_retry(self, shadow):
        first = shadow.replay(self.records, self.manifest)
        self.assertEqual(192, first.ready)
        self.assertEqual(48, first.hold)
        self.assertEqual({code: 8 for code in sara.HOLD_CODES}, first.hold_counts)
        self.assertEqual((192, 192, 192, 48, 240), (
            first.accessions_added,
            first.jobs_added,
            first.reports_added,
            first.holds_added,
            first.events_added,
        ))
        self.assertEqual(240, len(shadow.events))
        self.assertEqual(240, len(shadow._seen))

        digest = first.state_digest
        second = shadow.replay(self.records, self.manifest)
        self.assertEqual(240, second.replayed)
        self.assertEqual((0, 0, 0, 0, 0), (
            second.accessions_added,
            second.jobs_added,
            second.reports_added,
            second.holds_added,
            second.events_added,
        ))
        self.assertEqual(digest, second.state_digest)

    def test_mid_record_job_write_failure_rolls_back_exactly_and_retry_recovers(self):
        shadow = sara.SaraPartnerAccessionShadow({
            "adapter_mode": "read-only",
            "production_writes": 0,
        })
        before = shadow.state_digest()
        authoritative = shadow.authoritative_fingerprint
        shadow.jobs = FailOnSet()

        with self.assertRaisesRegex(RuntimeError, "injected job write failure"):
            shadow.replay(self.records, self.manifest)

        self.assert_empty_shadow(shadow, before, authoritative)
        self.assert_full_retry(shadow)

    def test_final_event_append_failure_rolls_back_all_record_state_and_retry_recovers(self):
        shadow = sara.SaraPartnerAccessionShadow({
            "adapter_mode": "read-only",
            "production_writes": 0,
        })
        before = shadow.state_digest()
        authoritative = shadow.authoritative_fingerprint
        shadow.events = FailOnAppend()

        with self.assertRaisesRegex(RuntimeError, "injected event append failure"):
            shadow.replay(self.records, self.manifest)

        self.assert_empty_shadow(shadow, before, authoritative)
        self.assert_full_retry(shadow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
