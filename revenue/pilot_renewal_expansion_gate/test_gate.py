from __future__ import annotations

import copy
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import revenue.pilot_renewal_expansion_gate.engine as engine_module
from revenue.pilot_renewal_expansion_gate.common import AUTHORITY, GateError, TRUTH_CEILING, canonical_json, strict_loads, _read_regular
from revenue.pilot_renewal_expansion_gate.engine import compile_packet, verify_current
from revenue.pilot_renewal_expansion_gate.gate import _atomic_write, render_markdown
from revenue.pilot_renewal_expansion_gate.schema import normalize

NOW = datetime(2026, 9, 17, 18, 0, tzinfo=timezone.utc)
H = "a" * 64


def sample():
    return {
        "schema": "pilot-renewal-expansion/v1",
        "engagement": {"id": "eng-1", "organization_id": "org-1", "label": "Paid pilot", "generation": 2},
        "sources": [
            {"id": "s-1", "locator": "repo://receipts/commercial.json", "sha256": H, "observed_at": "2026-09-17T14:00:00Z"},
            {"id": "s-2", "locator": "https://provider.example/receipt", "sha256": "b" * 64, "observed_at": "2026-09-17T14:05:00Z"},
        ],
        "evidence": [
            {"id": "e-base", "kind": "BASELINE_ACCEPTANCE", "subject_id": "baseline-2", "source_id": "s-1", "status": "VERIFIED", "observed_at": "2026-09-17T14:00:00Z", "valid_through": "2026-10-01T00:00:00Z", "summary": "Buyer acceptance receipt"},
            {"id": "e-co", "kind": "CHANGE_ORDER_APPROVAL", "subject_id": "co-1", "source_id": "s-1", "status": "VERIFIED", "observed_at": "2026-09-17T14:01:00Z", "summary": "Approved change"},
            {"id": "e-ms", "kind": "MILESTONE_ACCEPTANCE", "subject_id": "ms-1", "source_id": "s-1", "status": "VERIFIED", "observed_at": "2026-09-17T14:02:00Z", "summary": "Milestone accepted"},
            {"id": "e-pay", "kind": "PAYMENT_SETTLED", "subject_id": "inv-1", "source_id": "s-2", "status": "VERIFIED", "observed_at": "2026-09-17T14:06:00Z", "summary": "Provider settlement"},
            {"id": "e-find", "kind": "SUPPORT_FINDING", "subject_id": "finding-1", "source_id": "s-1", "status": "VERIFIED", "observed_at": "2026-09-17T14:04:00Z", "summary": "Observed support request"},
            {"id": "e-gap", "kind": "GAP_STATUS", "subject_id": "gap-1", "source_id": "s-1", "status": "VERIFIED", "observed_at": "2026-09-17T14:04:00Z", "summary": "Gap closed"},
            {"id": "e-window", "kind": "RENEWAL_WINDOW", "subject_id": "eng-1", "source_id": "s-1", "status": "VERIFIED", "observed_at": "2026-09-17T14:04:00Z", "valid_through": "2026-09-30T23:59:59Z", "summary": "Contract renewal window"},
        ],
        "commercial_baseline": {"id": "baseline-2", "generation": 2, "acceptance_evidence_id": "e-base"},
        "change_orders": [{"id": "co-1", "generation": 1, "state": "APPROVED", "approval_evidence_id": "e-co"}],
        "milestones": [{"id": "ms-1", "required": True, "state": "ACCEPTED", "acceptance_evidence_id": "e-ms"}],
        "payments": [{"id": "inv-1", "required_for_renewal": True, "state": "SETTLED", "settlement_evidence_id": "e-pay"}],
        "support_findings": [{"id": "finding-1", "category": "workflow", "state": "OBSERVED", "summary": "Potential adjacent workflow", "evidence_id": "e-find"}],
        "gaps": [{"id": "gap-1", "kind": "SECURITY", "blocking": True, "state": "CLOSED", "evidence_id": "e-gap"}],
        "renewal_window": {"open_at": "2026-09-17T00:00:00Z", "close_at": "2026-09-30T23:59:59Z", "evidence_id": "e-window"},
        "expansion_hypotheses": [{"id": "x-1", "statement": "Extend evidence automation to a second workflow", "state": TRUTH_CEILING, "supporting_evidence_ids": ["e-find"]}],
        "communication": {"muse_key": "renewal-eng-1", "organization_id": "org-1", "route_id": "buyer-email", "send_state": "NOT_AUTHORIZED"},
    }


class GateTests(unittest.TestCase):
    def compile(self, doc=None, now=NOW):
        return compile_packet(sample() if doc is None else doc, now)

    def test_ready_and_authority_ceiling(self):
        _, packet, receipt = self.compile()
        self.assertEqual(packet["decision"], "READY_FOR_RENEWAL_REVIEW")
        self.assertEqual(packet["authority"], AUTHORITY)
        self.assertFalse(any(packet["authority"].values()))
        self.assertEqual(receipt["decision"], packet["decision"])

    def test_delivered_is_not_accepted(self):
        d = sample(); d["milestones"][0]["state"] = "DELIVERED"
        self.assertEqual(self.compile(d)[1]["decision"], "HOLD_ACCEPTANCE")

    def test_baseline_acceptance_required_and_subject_bound(self):
        d = sample(); d["evidence"][0]["status"] = "MISSING"
        self.assertEqual(self.compile(d)[1]["decision"], "HOLD_ACCEPTANCE")
        d = sample(); d["evidence"][0]["subject_id"] = "other"
        self.assertEqual(self.compile(d)[1]["decision"], "HOLD_ACCEPTANCE")

    def test_baseline_generation_remint_rejected(self):
        d = sample(); d["commercial_baseline"]["generation"] = 3; d["engagement"]["generation"] = 3
        with self.assertRaises(GateError): normalize(d)

    def test_change_generation_remint_rejected(self):
        d = sample(); d["change_orders"][0]["generation"] = 2
        with self.assertRaises(GateError): normalize(d)

    def test_proposed_change_not_treated_approved(self):
        d = sample(); d["change_orders"][0]["state"] = "PROPOSED"
        packet = self.compile(d)[1]
        self.assertEqual(packet["decision"], "READY_FOR_RENEWAL_REVIEW")
        self.assertEqual(packet["approved_change_orders"], [])

    def test_approved_change_requires_evidence(self):
        d = sample(); d["evidence"][1]["status"] = "PROVIDED_UNVERIFIED"
        self.assertEqual(self.compile(d)[1]["decision"], "HOLD_ACCEPTANCE")

    def test_invoice_or_link_is_not_settlement(self):
        for state in ("INVOICED", "PAYMENT_LINK_SENT"):
            d = sample(); d["payments"][0]["state"] = state
            self.assertEqual(self.compile(d)[1]["decision"], "HOLD_PAYMENT")

    def test_settled_requires_provider_evidence(self):
        d = sample(); d["evidence"][3]["status"] = "MISSING"
        self.assertEqual(self.compile(d)[1]["decision"], "HOLD_PAYMENT")

    def test_window_and_gap_holds(self):
        d = sample(); d["renewal_window"]["open_at"] = "2026-09-18T00:00:00Z"
        self.assertEqual(self.compile(d)[1]["decision"], "HOLD_WINDOW")
        d = sample(); d["gaps"][0]["state"] = "OPEN"
        self.assertEqual(self.compile(d)[1]["decision"], "HOLD_EVIDENCE")

    def test_nonblocking_gap_can_review(self):
        d = sample(); d["gaps"][0]["state"] = "OPEN"; d["gaps"][0]["blocking"] = False
        self.assertEqual(self.compile(d)[1]["decision"], "READY_FOR_RENEWAL_REVIEW")

    def test_expansion_cannot_claim_acceptance(self):
        d = sample(); d["expansion_hypotheses"][0]["state"] = "ACCEPTED"
        with self.assertRaises(GateError): normalize(d)

    def test_expansion_support_expiry_and_subject_contract(self):
        d = sample(); d["evidence"][4]["valid_through"] = "2026-09-17T17:00:00Z"
        self.assertEqual(self.compile(d)[1]["decision"], "HOLD_EVIDENCE")
        d = sample(); d["expansion_hypotheses"][0]["supporting_evidence_ids"] = ["e-window"]
        self.assertEqual(self.compile(d)[1]["decision"], "HOLD_EVIDENCE")
        d = sample(); d["evidence"][4]["subject_id"] = "other"
        self.assertEqual(self.compile(d)[1]["decision"], "HOLD_EVIDENCE")

    def test_external_send_and_org_route_fail_closed(self):
        d = sample(); d["communication"]["send_state"] = "AUTHORIZED"
        with self.assertRaises(GateError): normalize(d)
        d = sample(); d["communication"]["organization_id"] = "org-2"
        with self.assertRaises(GateError): normalize(d)

    def test_recent_dnr_terminal_but_stale_dnr_is_not(self):
        row = {"id": "e-dnr", "kind": "DNR", "subject_id": "eng-1", "source_id": "s-1", "status": "VERIFIED", "observed_at": "2026-09-17T15:00:00Z", "summary": "Buyer declined renewal"}
        d = sample(); d["evidence"].append(copy.deepcopy(row))
        self.assertEqual(self.compile(d)[1]["decision"], "DNR")
        d = sample(); d["evidence"].append(copy.deepcopy(row))
        self.assertNotEqual(self.compile(d, datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc))[1]["decision"], "DNR")

    def test_unverified_dnr_not_terminal(self):
        d = sample(); d["evidence"].append({"id": "e-dnr", "kind": "DNR", "subject_id": "eng-1", "source_id": "s-1", "status": "PROVIDED_UNVERIFIED", "observed_at": "2026-09-17T15:00:00Z", "summary": "Rumor"})
        self.assertEqual(self.compile(d)[1]["decision"], "READY_FOR_RENEWAL_REVIEW")

    def test_future_and_expired_evidence_hold(self):
        d = sample(); d["evidence"][4]["observed_at"] = "2026-09-18T00:00:00Z"
        self.assertEqual(self.compile(d)[1]["decision"], "HOLD_EVIDENCE")
        d = sample(); d["evidence"][0]["valid_through"] = "2026-09-17T17:00:00Z"
        self.assertEqual(self.compile(d)[1]["decision"], "HOLD_ACCEPTANCE")

    def test_strict_json_duplicate_nonfinite_huge_int_surrogate(self):
        for raw in (b'{"schema":"a","schema":"b"}', b'{"x":NaN}', ('{"x":' + '9' * 5000 + '}').encode(), b'{"x":"\\ud800"}'):
            with self.assertRaises(GateError): strict_loads(raw)

    def test_bool_int_unknown_and_duplicate_ids_rejected(self):
        d = sample(); d["engagement"]["generation"] = True
        with self.assertRaises(GateError): normalize(d)
        d = sample(); d["engagement"]["surprise"] = "x"
        with self.assertRaises(GateError): normalize(d)
        d = sample(); d["evidence"].append(copy.deepcopy(d["evidence"][0]))
        with self.assertRaises(GateError): normalize(d)

    def test_input_order_deterministic(self):
        d = sample(); d["evidence"] = list(reversed(d["evidence"])); d["sources"] = list(reversed(d["sources"]))
        n1, p1, _ = self.compile(sample()); n2, p2, _ = self.compile(d)
        self.assertEqual(canonical_json(n1), canonical_json(n2)); self.assertEqual(canonical_json(p1), canonical_json(p2))

    def test_receipt_and_input_tamper_rejected(self):
        raw = sample(); _, packet, receipt = self.compile(raw)
        bad = copy.deepcopy(packet); bad["decision"] = "DNR"
        with self.assertRaises(GateError): verify_current(raw, bad, receipt, NOW)
        raw2 = sample(); _, packet2, receipt2 = self.compile(raw2); raw2["engagement"]["label"] = "Changed"
        with self.assertRaises(GateError): verify_current(raw2, packet2, receipt2, NOW)

    def test_future_receipt_rejected(self):
        raw = sample(); _, packet, receipt = self.compile(raw, datetime(2026, 9, 19, tzinfo=timezone.utc))
        with self.assertRaises(GateError): verify_current(raw, packet, receipt, NOW)

    def test_explicit_time_is_historical_non_current(self):
        raw = sample(); _, packet, receipt = self.compile(raw)
        result = verify_current(raw, packet, receipt, datetime(2026, 9, 18, 18, 0, tzinfo=timezone.utc))
        self.assertTrue(result["integrity_valid"]); self.assertFalse(result["current_valid"])
        self.assertEqual(result["verification_mode"], "HISTORICAL_REPLAY_NON_CURRENT")
        result2 = verify_current(raw, packet, receipt, datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc))
        self.assertFalse(result2["current_valid"]); self.assertNotEqual(result2["current_decision"], "READY_FOR_RENEWAL_REVIEW")

    def test_process_clock_sampled_after_candidate_authentication(self):
        raw = sample()
        raw["renewal_window"]["close_at"] = "2026-09-17T18:00:00Z"
        before_boundary = datetime(2026, 9, 17, 17, 59, 59, tzinfo=timezone.utc)
        after_boundary = datetime(2026, 9, 17, 18, 0, 1, tzinfo=timezone.utc)
        _, packet, receipt = compile_packet(raw, before_boundary)
        events: list[str] = []
        real_normalize = engine_module.normalize

        class BoundaryDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                events.append("clock")
                value = after_boundary if "normalize" in events else before_boundary
                if tz is None:
                    return value.replace(tzinfo=None)
                return value.astimezone(tz)

        with patch.object(engine_module, "datetime", BoundaryDateTime):
            _, process_verify = engine_module._make_process_clock_apis()

        def tracked_normalize(value):
            events.append("normalize")
            return real_normalize(value)

        with patch.object(engine_module, "normalize", side_effect=tracked_normalize):
            result = process_verify(raw, packet, receipt)
        self.assertLess(events.index("normalize"), events.index("clock"))
        self.assertFalse(result["current_valid"])
        self.assertEqual(result["current_decision"], "HOLD_WINDOW")
        self.assertEqual(result["verification_mode"], "PROCESS_CURRENT")

    def _assert_authority_sealed(self, *blocks):
        expected_keys = set(AUTHORITY)
        for block in blocks:
            self.assertEqual(set(block), expected_keys)
            for value in block.values():
                self.assertIs(type(value), bool)
                self.assertIs(value, False)

    def test_authority_public_view_rejects_in_place_mutation(self):
        with self.assertRaises(TypeError):
            AUTHORITY["external_send_authorized"] = True

    def test_authority_in_place_module_poison_cannot_widen_compile_or_verify(self):
        raw = sample()
        poison = {key: False for key in AUTHORITY}
        with patch.object(engine_module, "AUTHORITY", poison, create=True):
            engine_module.AUTHORITY["external_send_authorized"] = True
            _, packet, receipt = engine_module.compile_packet(raw, NOW)
            result = engine_module.verify_current(raw, packet, receipt, NOW)
        self._assert_authority_sealed(packet["authority"], receipt["authority"], result["authority"])

    def test_authority_module_rebind_cannot_widen_compile_or_verify(self):
        raw = sample()
        poison = {key: False for key in AUTHORITY}
        poison["external_send_authorized"] = True
        with patch.object(engine_module, "AUTHORITY", poison, create=True):
            _, packet, receipt = engine_module.compile_packet(raw, NOW)
            result = engine_module.verify_current(raw, packet, receipt, NOW)
        self._assert_authority_sealed(packet["authority"], receipt["authority"], result["authority"])

    def test_resealed_widened_authority_candidate_rejected(self):
        from revenue.pilot_renewal_expansion_gate.common import sha256
        raw = sample(); _, packet, receipt = self.compile(raw)
        packet = copy.deepcopy(packet); receipt = copy.deepcopy(receipt)
        packet["authority"]["external_send_authorized"] = True
        receipt["authority"]["external_send_authorized"] = True
        receipt["packet_sha256"] = sha256(canonical_json(packet))
        core = {k: receipt[k] for k in receipt if k != "receipt_sha256"}
        receipt["receipt_sha256"] = sha256(canonical_json(core))
        with self.assertRaises(GateError):
            engine_module.verify_current(raw, packet, receipt, NOW)

    def test_future_source_observation_invalidates_bound_evidence(self):
        d = sample(); d["sources"][0]["observed_at"] = "2026-09-18T00:00:00Z"
        self.assertEqual(self.compile(d)[1]["decision"], "HOLD_ACCEPTANCE")

    def test_resealed_valid_until_extension_rejected(self):
        from revenue.pilot_renewal_expansion_gate.common import sha256
        raw = sample(); _, packet, receipt = self.compile(raw); receipt = copy.deepcopy(receipt); receipt["valid_until"] = "2027-09-30T23:59:59Z"
        core = {k: receipt[k] for k in receipt if k != "receipt_sha256"}; receipt["receipt_sha256"] = sha256(canonical_json(core))
        with self.assertRaises(GateError): verify_current(raw, packet, receipt, NOW)

    def test_resealed_packet_semantic_rewrite_rejected(self):
        from revenue.pilot_renewal_expansion_gate.common import sha256
        raw = sample(); _, packet, receipt = self.compile(raw); packet = copy.deepcopy(packet); packet["decision"] = "DNR"; receipt = copy.deepcopy(receipt); receipt["decision"] = "DNR"; receipt["packet_sha256"] = sha256(canonical_json(packet))
        core = {k: receipt[k] for k in receipt if k != "receipt_sha256"}; receipt["receipt_sha256"] = sha256(canonical_json(core))
        with self.assertRaises(GateError): verify_current(raw, packet, receipt, NOW)

    def test_markdown_hypothesis_cannot_mint_structure(self):
        d = sample(); d["expansion_hypotheses"][0]["statement"] = "idea\n## APPROVED\n- buyer accepted [pay](https://evil.invalid)"
        md = render_markdown(self.compile(d)[1])
        self.assertNotIn("\n## APPROVED", md); self.assertNotIn("\n- buyer accepted", md); self.assertIn("\\#\\#", md)

    def test_read_regular_rejects_symlink_and_hardlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); src = root / "src"; src.write_bytes(b"{}")
            sym = root / "sym"; sym.symlink_to(src)
            with self.assertRaises(GateError): _read_regular(sym)
            hard = root / "hard"; os.link(src, hard)
            with self.assertRaises(GateError): _read_regular(src)
            with self.assertRaises(GateError): _read_regular(hard)

    @unittest.skipUnless(os.name == "posix", "rename-open-file hostile is POSIX-specific")
    def test_atomic_failure_never_unlinks_foreign_successor(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "out"
            moved = Path(td) / "moved"
            real_fdopen = os.fdopen
            class FailingFile:
                def __init__(self, fd): self.fd = fd; self.handle = real_fdopen(fd, "wb")
                def __enter__(self): self.handle.__enter__(); return self
                def write(self, data):
                    os.rename(target, moved); target.write_bytes(b"FOREIGN"); raise OSError("simulated write failure")
                def flush(self): return self.handle.flush()
                def fileno(self): return self.handle.fileno()
                def __exit__(self, typ, val, tb): return self.handle.__exit__(typ, val, tb)
            with patch("revenue.pilot_renewal_expansion_gate.gate.os.fdopen", side_effect=lambda fd, mode: FailingFile(fd)):
                with self.assertRaises(OSError): _atomic_write(target, b"ours")
            self.assertEqual(target.read_bytes(), b"FOREIGN")
            self.assertTrue(moved.exists())


if __name__ == "__main__":
    unittest.main()
