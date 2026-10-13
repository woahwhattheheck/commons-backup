"""Regression contract for supplied-record assessment, with no provider calls."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('uiowa_review_practice_r73d', ROOT / 'review_practice.py')
rp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rp)


class ReviewPracticeTests(unittest.TestCase):
    def setUp(self):
        self.packet = rp.loads((ROOT / 'synthetic_reviews.json').read_text())

    def change(self, cid):
        return next(c for c in self.packet['changes'] if c['id'] == cid)

    def row(self, cid):
        return next(c for c in rp.assess(self.packet)['changes'] if c['id'] == cid)

    def invalid(self):
        with self.assertRaises(rp.InputError):
            rp.assess(self.packet)

    def test_fixture_expected_counts_and_waits(self):
        s = rp.assess(self.packet)['summary']
        self.assertEqual((s['sampled_changes'], s['merged_changes']), (11, 10))
        self.assertEqual(s['substantive_signal_among_assessable_merged'], rp.ratio(3, 8))
        self.assertEqual(s['assessable_merged_coverage'], rp.ratio(8, 10))
        self.assertEqual(s['observed_substantive_among_all_merged'], rp.ratio(3, 10))
        self.assertEqual(s['latency']['observed_pairs'], 3)
        self.assertEqual(s['latency']['median'], 30)
        self.assertEqual(s['latency']['p90_nearest_rank'], 45)

    def test_approval_click_is_not_substantive(self):
        row = self.row('ESS-102')
        self.assertEqual(row['review_signal'], 'approval_only_recorded')
        self.assertFalse(row['substantive_before_cutoff'])
        self.assertIsNone(row['first_substantive_feedback_wait_minutes'])

    def test_stale_revision_is_not_final_head(self):
        row = self.row('RIS-201')
        self.assertEqual(row['review_signal'], 'older_head_evidence_only')
        self.assertEqual(row['older_head_review_count'], 1)

    def test_partial_export_remains_unknown(self):
        row = self.row('RIS-202')
        self.assertEqual(row['review_signal'], 'unknown_incomplete_export')
        self.assertFalse(row['export_complete_through_cutoff'])

    def test_self_review_not_counted_as_peer(self):
        row = self.row('IAM-303')
        self.assertEqual(row['self_review_count'], 1)
        self.assertFalse(row['substantive_before_cutoff'])

    def test_open_changes_are_not_merged_denominator_or_zero_latency(self):
        row = self.row('RIS-203')
        self.assertFalse(row['merged'])
        self.assertEqual(row['no_observed_feedback_window_minutes'], 175)
        self.assertIsNone(row['first_substantive_feedback_wait_minutes'])

    def test_post_merge_resolution_does_not_rewrite_cutoff(self):
        self.assertEqual(self.row('RIS-204')['feedback_unresolved_at_cutoff'], 1)
        self.assertEqual(self.row('ESS-101')['feedback_unresolved_at_cutoff'], 0)

    def test_missing_resolution_reference_is_unknown(self):
        self.change('ESS-101')['reviews'][0]['feedback'][0]['resolution_ref'] = None
        self.assertEqual(self.row('ESS-101')['feedback_unresolved_at_cutoff'], 1)

    def test_post_merge_review_not_pre_merge_coverage(self):
        self.assertFalse(self.row('IAM-301')['substantive_before_cutoff'])
        self.assertEqual(self.row('IAM-301')['emergency_followup'], 'completed_on_time')

    def test_emergency_complete_export_without_followup_overdue(self):
        self.assertEqual(self.row('IAM-302')['emergency_followup'], 'overdue')

    def test_later_completed_review_cannot_mask_open_point(self):
        c = self.change('IAM-301')
        r = deepcopy(c['reviews'][0])
        r['id'] = 'R2'
        r['source_ref'] = 'synthetic://reviews/R2'
        r['feedback'][0].update(id='F2', disposition='open', resolved_at=None, resolution_ref=None)
        c['reviews'].append(r)
        self.assertEqual(self.row('IAM-301')['emergency_followup'], 'overdue')

    def test_emergency_late_uses_last_resolution_across_reviews(self):
        c = self.change('IAM-301')
        r = deepcopy(c['reviews'][0])
        r['id'] = 'R2'
        r['feedback'][0].update(id='F2', resolved_at='2026-09-10T11:05:00Z')
        c['reviews'].append(r)
        self.assertEqual(self.row('IAM-301')['emergency_followup'], 'completed_late')

    def test_partial_export_cannot_establish_emergency_completion(self):
        self.change('IAM-301')['export']['complete'] = False
        self.assertEqual(self.row('IAM-301')['emergency_followup'], 'unknown_incomplete_export')

    def test_emergency_completion_without_context_remains_open(self):
        self.change('IAM-301')['reviews'][0]['context_ref'] = None
        self.assertEqual(self.row('IAM-301')['emergency_followup'], 'overdue')

    def test_emergency_due_unknown_is_not_on_time(self):
        self.change('IAM-301')['emergency']['followup_due_at'] = None
        self.assertEqual(self.row('IAM-301')['emergency_followup'], 'completed_due_unknown')

    def test_emergency_future_due_is_pending(self):
        self.change('IAM-302')['emergency']['followup_due_at'] = '2026-09-11T12:00:00Z'
        self.assertEqual(self.row('IAM-302')['emergency_followup'], 'pending')

    def test_undated_evidence_not_silently_negative(self):
        row = self.row('ESS-104')
        self.assertEqual(row['review_signal'], 'unknown_review_timing')
        self.assertEqual(row['unknown_time_review_count'], 1)

    def test_undated_review_plus_approval_excluded_from_negative_denominator(self):
        c = self.change('ESS-104')
        r = deepcopy(self.change('ESS-102')['reviews'][0])
        r['id'] = 'R2'
        c['reviews'].append(r)
        s = rp.assess(self.packet)['summary']
        self.assertEqual(s['assessable_merged_coverage'], rp.ratio(8, 10))

    def test_partial_positive_included_but_first_latency_not_inferred(self):
        self.change('ESS-101')['export']['complete'] = False
        row = self.row('ESS-101')
        self.assertTrue(row['substantive_before_cutoff'])
        self.assertIsNone(row['first_substantive_feedback_wait_minutes'])
        self.assertEqual(rp.assess(self.packet)['summary']['assessable_merged_coverage'], rp.ratio(8, 10))

    def test_unknown_timing_prevents_first_feedback_inference(self):
        c = self.change('ESS-101')
        r = deepcopy(self.change('ESS-104')['reviews'][0])
        r['id'] = 'R2'
        r['feedback'][0]['id'] = 'F2'
        c['reviews'].append(r)
        self.assertIsNone(self.row('ESS-101')['first_substantive_feedback_wait_minutes'])

    def test_dismissed_record_not_current_but_reference_retained(self):
        self.change('ESS-101')['reviews'][0]['state'] = 'dismissed'
        row = self.row('ESS-101')
        self.assertFalse(row['substantive_before_cutoff'])
        self.assertIn('synthetic://reviews/R1', row['source_refs'])

    def test_missing_context_generates_specific_question(self):
        self.change('ESS-101')['reviews'][0]['context_ref'] = None
        self.assertIn('reviewer_context_unknown', {f['code'] for f in self.row('ESS-101')['followups']})

    def test_rerequest_after_feedback_not_zero_wait(self):
        self.change('ESS-101')['review_requested_at'] = '2026-09-10T09:35:00Z'
        row = self.row('ESS-101')
        self.assertIsNone(row['first_substantive_feedback_wait_minutes'])
        self.assertIn('request_after_recorded_feedback', {f['code'] for f in row['followups']})

    def test_missing_request_not_imputed(self):
        self.change('ESS-101')['review_requested_at'] = None
        self.assertIsNone(self.row('ESS-101')['first_substantive_feedback_wait_minutes'])

    def test_export_before_merge_is_incomplete_through_cutoff(self):
        self.change('ESS-102')['export']['captured_at'] = '2026-09-10T09:45:00Z'
        self.assertFalse(self.row('ESS-102')['export_complete_through_cutoff'])

    def test_timezone_offsets_normalize(self):
        self.change('ESS-101')['reviews'][0]['submitted_at'] = '2026-09-10T05:30:00-04:00'
        self.assertEqual(self.row('ESS-101')['first_substantive_feedback_wait_minutes'], 30)

    def test_duplicate_feedback_across_reviews_rejected(self):
        c = self.change('ESS-101')
        r = deepcopy(c['reviews'][0]); r['id'] = 'R2'; c['reviews'].append(r)
        self.invalid()

    def test_duplicate_review_rejected(self):
        c = self.change('ESS-101'); c['reviews'].append(deepcopy(c['reviews'][0])); self.invalid()

    def test_duplicate_change_rejected(self):
        self.packet['changes'].append(deepcopy(self.packet['changes'][0])); self.invalid()

    def test_duplicate_json_keys_and_nonfinite_rejected(self):
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}', '{'):
            with self.subTest(raw=raw), self.assertRaises(rp.InputError):
                rp.loads(raw)

    def test_unknown_schema_fields_rejected(self):
        self.packet['maturity'] = 5; self.invalid()

    def test_not_a_packet_rejected(self):
        with self.assertRaises(rp.InputError): rp.assess([])

    def test_boolean_must_not_be_integer(self):
        self.packet['synthetic'] = 1; self.invalid()

    def test_naive_timestamp_rejected(self):
        self.packet['as_of'] = '2026-09-10T12:00:00'; self.invalid()

    def test_future_review_rejected(self):
        self.change('ESS-101')['reviews'][0]['submitted_at'] = '2026-09-11T10:00:00Z'; self.invalid()

    def test_resolution_before_review_rejected(self):
        self.change('ESS-101')['reviews'][0]['feedback'][0]['resolved_at'] = '2026-09-10T09:15:00Z'; self.invalid()

    def test_review_after_export_rejected(self):
        self.change('ESS-101')['export']['captured_at'] = '2026-09-10T09:20:00Z'; self.invalid()

    def test_complete_export_needs_reference(self):
        self.change('ESS-101')['export']['reference'] = None; self.invalid()

    def test_false_emergency_with_due_rejected(self):
        self.change('ESS-101')['emergency']['followup_due_at'] = '2026-09-10T11:00:00Z'; self.invalid()

    def test_unknown_disposition_cannot_have_resolution_proof(self):
        self.change('ESS-101')['reviews'][0]['feedback'][0]['disposition'] = 'unknown'; self.invalid()

    def test_empty_collection_denominators_are_null(self):
        self.packet['changes'] = []
        r = rp.assess(self.packet)
        self.assertIsNone(r['summary']['substantive_signal_among_assessable_merged']['fraction'])
        self.assertIsNone(r['summary']['latency']['median'])

    def test_deterministic_output_does_not_mutate_input(self):
        before = deepcopy(self.packet)
        self.assertEqual(rp.assess(self.packet), rp.assess(self.packet))
        self.assertEqual(self.packet, before)

    def test_changed_input_changes_receipt(self):
        original = rp.assess(self.packet)['input_sha256']
        self.packet['sampling_note'] += ' Changed context.'
        self.assertNotEqual(rp.assess(self.packet)['input_sha256'], original)

    def test_markdown_contains_limitations_and_escaped_cells(self):
        self.change('ESS-101')['service'] = 'A | B\n<script>'
        rendered = rp.render(rp.assess(self.packet))
        self.assertIn('SYNTHETIC REHEARSAL', rendered)
        self.assertIn('not verified source authenticity', rendered)
        self.assertIn('A \\| B &lt;script&gt;', rendered)
        self.assertIn('feedback_not_resolved_by_cutoff', rendered)

    def test_cli_json_and_markdown_and_bad_input(self):
        script = str(ROOT / 'review_practice.py')
        fixture = str(ROOT / 'synthetic_reviews.json')
        good = subprocess.run([sys.executable, script, fixture], capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout), rp.assess(self.packet))
        markdown = subprocess.run([sys.executable, script, fixture, '--format', 'markdown'], capture_output=True, text=True)
        self.assertEqual(markdown.returncode, 0)
        self.assertTrue(markdown.stdout.startswith('# Review practice'))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'bad.json'; path.write_text('{"schema":0}')
            bad = subprocess.run([sys.executable, script, str(path)], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(bad.stdout, '')
            self.assertIn('review-practice:', bad.stderr)


if __name__ == '__main__':
    unittest.main()
