"""Independent business-rule checks against the unchanged, pinned LACSD module.

Synthetic data only. These tests measure contract behavior, not OCR accuracy,
Oracle integration, buyer eligibility, source authenticity, or live performance.
Run with LACSD_SOURCE_DIR pointing at the retained original source directory.
"""
from __future__ import annotations
import copy
import importlib.util
import itertools
import json
import os
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
import unittest

SOURCE = Path(os.environ.get('LACSD_SOURCE_DIR', str(Path(__file__).resolve().parents[1] / 'lacsd-15865'))).resolve()
spec = importlib.util.spec_from_file_location('lacsd_pinned', SOURCE / 'lacsd_04252.py')
if spec is None or spec.loader is None:
    raise RuntimeError('source module could not be resolved')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
AS_OF = '2026-09-18T02:00:00Z'
MANIFEST = json.loads((SOURCE / 'fixtures/manifest.json').read_text())
MATRIX = json.loads((SOURCE / 'fixtures/ap_cases.json').read_text())
BASE = MATRIX['cases'][0]['case']


def case(**changes):
    out = copy.deepcopy(BASE)
    out.update(changes)
    return out


class IndependentLACSDTests(unittest.TestCase):
    def test_all_2048_simultaneous_gate_combinations(self):
        # Independent ordered specification: test simultaneous failures, not only
        # the author's one-failure-at-a-time examples.
        codes = (
            'REJECT_DUPLICATE', 'HOLD_EXTRACTION_ACCURACY', 'HOLD_MISSING_PO',
            'HOLD_VENDOR_MISMATCH', 'HOLD_AMOUNT_VARIANCE', 'HOLD_APPROVAL',
            'HOLD_CYCLE_TIME', 'HOLD_ORACLE_SYNC', 'HOLD_AUDIT_TRAIL',
            'HOLD_DASHBOARD_FRESHNESS',
        )
        for bits in itertools.product((False, True), repeat=11):
            bad = bits[:10]
            r = case(
                duplicate=bad[0], extraction_fields_correct=98 if bad[1] else 99,
                po_present=not bad[2], vendor_match=not bad[3],
                invoice_total_cents=10051 if bad[4] else 10000,
                routing_signoff_present=not bad[5],
                ready_at_utc='2026-09-18T12:00:00Z' if bad[6] else '2026-09-17T12:00:00Z',
                oracle_sync_evidenced=not bad[7], audit_trail_complete=not bad[8],
                dashboard_fresh=not bad[9], po_required=bits[10],
            )
            active = list(bad)
            active[2] = active[2] and bits[10]
            active[4] = active[4] and bits[10]
            expected = next((c for c, b in zip(codes, active) if b), 'ACCEPT_EVIDENCE_READY')
            actual = m.evaluate_case(r)
            self.assertEqual(actual['decision'], expected, msg=str(bits))
            for field in m.AUTHORITY_FALSE:
                self.assertIs(actual[field], False)

    def test_accuracy_threshold_for_all_supported_denominators(self):
        # Fractions supply an independent mathematical threshold oracle.
        for total in range(1, 10001):
            minimum = (99 * total + 99) // 100
            for correct in {max(0, minimum - 1), minimum}:
                actual = m.evaluate_case(case(extraction_fields_total=total, extraction_fields_correct=correct))
                expect = 'ACCEPT_EVIDENCE_READY' if Fraction(correct, total) >= Fraction(99, 100) else 'HOLD_EXTRACTION_ACCURACY'
                self.assertEqual(actual['decision'], expect, msg=f'{correct}/{total}')

    def test_subsecond_time_boundary(self):
        start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
        for micros in (172799000000, 172799999999, 172800000000, 172800000001):
            ready = (start + timedelta(microseconds=micros)).isoformat().replace('+00:00', 'Z')
            actual = m.evaluate_case(case(ready_at_utc=ready))
            expected = 'ACCEPT_EVIDENCE_READY' if micros < 172800000000 else 'HOLD_CYCLE_TIME'
            self.assertEqual(actual['decision'], expected)

    def test_po_tolerance_boundary_large_exact_integers(self):
        for po in (0, 1, 10000, 10**15 - 1):
            for tol in (0, 1):
                for delta in (-2, -1, 0, 1, 2):
                    invoice = po + delta
                    if not 0 <= invoice <= 10**15:
                        continue
                    result = m.evaluate_case(case(po_total_cents=po, invoice_total_cents=invoice, tolerance_cents=tol))
                    expected = 'ACCEPT_EVIDENCE_READY' if abs(delta) <= tol else 'HOLD_AMOUNT_VARIANCE'
                    self.assertEqual(result['decision'], expected)
                    self.assertEqual(result['variance_cents'], abs(delta))

    def test_all_boolean_fields_reject_nonbooleans(self):
        fields = [name for name, value in BASE.items() if type(value) is bool]
        for field in fields:
            for value in (0, 1, 'true', 'false', None, [], {}):
                with self.subTest(field=field, value=value), self.assertRaises(m.ContractError):
                    m.evaluate_case(case(**{field: value}))

    def test_all_integer_fields_reject_type_and_range_aliases(self):
        fields = [name for name, value in BASE.items() if type(value) is int]
        for field in fields:
            for value in (True, False, 1.0, '1', None, -1, 10**16):
                with self.subTest(field=field, value=value), self.assertRaises(m.ContractError):
                    m.evaluate_case(case(**{field: value}))

    def test_every_authority_field_cannot_be_promoted(self):
        for field in m.AUTHORITY_FALSE:
            changed = copy.deepcopy(MANIFEST)
            changed['authority'][field] = True
            with self.subTest(field=field), self.assertRaises(m.ContractError):
                m.compile_evidence(changed, MATRIX, AS_OF)

    def test_all_three_source_generations_cannot_be_future(self):
        for source in ('detail', 'current_list', 'submission_rules'):
            changed = copy.deepcopy(MANIFEST)
            changed['sources'][source]['captured_at_utc'] = '2026-09-18T02:00:01Z'
            with self.subTest(source=source), self.assertRaises(m.ContractError):
                m.compile_evidence(changed, MATRIX, AS_OF)

    def test_all_three_source_urls_are_bound(self):
        for source in ('detail', 'current_list', 'submission_rules'):
            changed = copy.deepcopy(MANIFEST)
            changed['sources'][source]['url'] += '?different_generation=1'
            with self.subTest(source=source), self.assertRaises(m.ContractError):
                m.compile_evidence(changed, MATRIX, AS_OF)

    def test_deadline_instant_changes_teaming_but_never_submission(self):
        for when, state in (
            ('2026-10-15T17:59:59Z', 'READY_FOR_PAID_TEAMING_REVIEW'),
            ('2026-10-15T18:00:00Z', 'HOLD_RESPONSE_WINDOW'),
            ('2026-10-15T18:00:01Z', 'HOLD_RESPONSE_WINDOW'),
        ):
            bundle = m.compile_evidence(MANIFEST, MATRIX, when)
            self.assertEqual(bundle['teaming_review_verdict'], state)
            self.assertEqual(bundle['submission_verdict'], 'HOLD_QUESTCDN_PACKET_AND_PLANHOLDER')
            for field in m.AUTHORITY_FALSE:
                self.assertIs(bundle[field], False)

    def test_every_top_level_bundle_field_tamper_is_rejected(self):
        base = m.compile_evidence(MANIFEST, MATRIX, AS_OF)
        for field in base:
            changed = copy.deepcopy(base)
            changed[field] = 'NOT_THE_COMPILED_VALUE'
            with self.subTest(field=field):
                self.assertFalse(m.verify_evidence(changed, MANIFEST, MATRIX, AS_OF))
        changed = copy.deepcopy(base)
        changed['new_authority'] = True
        self.assertFalse(m.verify_evidence(changed, MANIFEST, MATRIX, AS_OF))

    def test_nested_result_and_receipt_tamper_rejected(self):
        base = m.compile_evidence(MANIFEST, MATRIX, AS_OF)
        for path in (
            ('pursuit', 'bid_due_utc'), ('pursuit', 'receipt_sha256'),
            ('acceptance_matrix', 'receipt_sha256'),
            ('acceptance_matrix', 'case_count'),
        ):
            changed = copy.deepcopy(base)
            changed[path[0]][path[1]] = 'NOT_THE_COMPILED_VALUE'
            self.assertFalse(m.verify_evidence(changed, MANIFEST, MATRIX, AS_OF))
        changed = copy.deepcopy(base)
        changed['acceptance_matrix']['results'][0]['payment_authorized'] = True
        self.assertFalse(m.verify_evidence(changed, MANIFEST, MATRIX, AS_OF))

    def test_new_compilation_after_deadline_invalidates_earlier_bundle(self):
        base = m.compile_evidence(MANIFEST, MATRIX, AS_OF)
        self.assertFalse(m.verify_evidence(base, MANIFEST, MATRIX, '2026-10-15T18:00:00Z'))

    def test_json_duplicate_and_nonfinite_input_rejected(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{"a":{"x":1,"x":2}}'):
            with self.subTest(text=text), self.assertRaises(m.ContractError):
                m.strict_loads(text)

    def test_semantic_receipt_is_not_raw_input_authentication(self):
        # Document the declared semantic boundary rather than inventing a raw
        # evidence-integrity guarantee. Same variance/ratio/time may project alike.
        one = case(invoice_total_cents=10000, po_total_cents=10000)
        two = case(invoice_total_cents=20000, po_total_cents=20000)
        self.assertEqual(m.evaluate_case(one), m.evaluate_case(two))
        original = m.compile_evidence(MANIFEST, MATRIX, AS_OF)
        changed = copy.deepcopy(MANIFEST)
        changed['commercial_offer']['acceptance'] = 'Different internal acceptance wording; not an executed contract.'
        self.assertTrue(m.verify_evidence(original, changed, MATRIX, AS_OF))
        # This observation must be disclosed; semantic parity is not source parity.


if __name__ == '__main__':
    unittest.main()
