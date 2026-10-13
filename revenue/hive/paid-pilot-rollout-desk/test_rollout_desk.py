import json
import os
import tempfile
import unittest
from pathlib import Path

import rollout_desk as rd

H = "a" * 64
H2 = "b" * 64
H3 = "c" * 64


def spec(payment_state="PAID_EXTERNAL_EVIDENCE"):
    return {
        "schema_version": rd.SCHEMA_VERSION,
        "pilot_id": "pilot-001",
        "buyer_ref": "buyer-opaque-001",
        "currency": "USD",
        "pilot_price_cents": 250000,
        "scope_version": "scope-v1",
        "scope_sha256": H,
        "commercial_gate": {
            "pilot_payment_state": payment_state,
            "evidence_ref": "payment-receipt-opaque",
            "evidence_sha256": H2,
        },
        "included_scope": [
            {"scope_id": "diagnostic", "title": "Bounded diagnostic"},
            {"scope_id": "summary", "title": "Summary handoff"},
        ],
        "excluded_scope": [
            {"scope_id": "production-deploy", "title": "Production deployment"},
            {"scope_id": "provider-mutation", "title": "Provider mutation"},
        ],
        "acceptance_criteria": [
            {"criterion_id": "accuracy", "statement": "Agreed synthetic truth set matches."},
            {"criterion_id": "handoff", "statement": "Buyer receives deterministic handoff."},
        ],
        "phase2_template": {
            "title": "Bounded production rollout",
            "proposed_price_cents": 750000,
            "proposed_duration_days": 14,
            "acceptance_criteria": [
                {"criterion_id": "rollout-a", "statement": "Production adapter passes agreed fixture set."},
                {"criterion_id": "rollout-b", "statement": "Rollback drill completes without duplicate effects."},
            ],
            "dependencies": ["Named buyer owner", "Sanitized integration fixture"],
        },
    }


def evidence(cid, disposition="MET", sha=H3, ref=None, recorded_at="2026-09-13T12:00:00Z"):
    return {
        "criterion_id": cid,
        "disposition": disposition,
        "evidence_ref": ref or f"ev-{cid}",
        "evidence_sha256": sha,
        "recorded_at": recorded_at,
        "note": "",
    }


def ready_state():
    st = rd.new_state(spec())
    st = rd.record_evidence(st, evidence("accuracy"))
    st = rd.record_evidence(st, evidence("handoff"))
    return st


class DeskTests(unittest.TestCase):
    def test_new_state_is_sealed_and_authority_false(self):
        st = rd.new_state(spec())
        self.assertEqual(st["revision"], 0)
        rd.validate_state(st)
        self.assertTrue(all(v is False for v in st["authority"].values()))

    def test_missing_evidence_holds(self):
        out = rd.compile_rollout(rd.new_state(spec()))
        self.assertEqual(out["decision"], "HOLD_FOR_PILOT_EVIDENCE")
        self.assertEqual([r["disposition"] for r in out["pilot_criteria"]], ["MISSING", "MISSING"])

    def test_unverified_payment_holds_before_ready(self):
        st = rd.new_state(spec("UNVERIFIED"))
        st = rd.record_evidence(st, evidence("accuracy"))
        st = rd.record_evidence(st, evidence("handoff"))
        out = rd.compile_rollout(st)
        self.assertEqual(out["decision"], "HOLD_FOR_PAYMENT_EVIDENCE")
        self.assertFalse(out["commercial_gate"]["payment_verified_by_this_system"])

    def test_not_met_is_no_go(self):
        st = rd.new_state(spec())
        st = rd.record_evidence(st, evidence("accuracy", "NOT_MET"))
        st = rd.record_evidence(st, evidence("handoff"))
        self.assertEqual(rd.compile_rollout(st)["decision"], "NO_GO")

    def test_hold_evidence_holds(self):
        st = rd.new_state(spec())
        st = rd.record_evidence(st, evidence("accuracy", "HOLD"))
        st = rd.record_evidence(st, evidence("handoff"))
        self.assertEqual(rd.compile_rollout(st)["decision"], "HOLD_FOR_PILOT_EVIDENCE")

    def test_latest_evidence_wins_without_erasing_history(self):
        st = rd.new_state(spec())
        st = rd.record_evidence(st, evidence("accuracy", "HOLD", ref="ev-old", recorded_at="2026-09-13T12:00:00Z"))
        st = rd.record_evidence(st, evidence("accuracy", "MET", ref="ev-new", recorded_at="2026-09-13T12:00:01Z"))
        st = rd.record_evidence(st, evidence("handoff"))
        out = rd.compile_rollout(st)
        self.assertEqual(out["decision"], "READY_FOR_OWNER_ROLLOUT_REVIEW")
        row = [x for x in out["pilot_criteria"] if x["criterion_id"] == "accuracy"][0]
        self.assertEqual(row["evidence"]["evidence_ref"], "ev-new")
        self.assertEqual(len(st["evidence_history"]), 3)

    def test_same_time_contradictory_evidence_rejected(self):
        st = rd.new_state(spec())
        st = rd.record_evidence(st, evidence("accuracy", "NOT_MET", recorded_at="2026-09-13T12:00:10Z"))
        with self.assertRaises(rd.DeskError):
            rd.record_evidence(st, evidence("accuracy", "MET", recorded_at="2026-09-13T12:00:10Z"))

    def test_backdated_evidence_rejected(self):
        st = rd.new_state(spec())
        st = rd.record_evidence(st, evidence("accuracy", "NOT_MET", recorded_at="2026-09-13T12:00:10Z"))
        with self.assertRaises(rd.DeskError):
            rd.record_evidence(st, evidence("accuracy", "MET", recorded_at="2026-09-13T12:00:09Z"))

    def test_resealed_backdated_history_rejected(self):
        st = rd.new_state(spec())
        st = rd.record_evidence(st, evidence("accuracy", "NOT_MET", recorded_at="2026-09-13T12:00:10Z"))
        st = rd.record_evidence(st, evidence("accuracy", "MET", recorded_at="2026-09-13T12:00:11Z"))
        raw = rd._state_without_seal(st)
        raw["evidence_history"][1]["recorded_at"] = "2026-09-13T12:00:09Z"
        resealed = rd.seal_state(raw)
        with self.assertRaises(rd.DeskError):
            rd.validate_state(resealed)
        with self.assertRaises(rd.DeskError):
            rd.compile_rollout(resealed)

    def test_timestamp_aliases_and_invalid_dates_rejected(self):
        bad_values = [
            "2026-09-13T12:00:00+00:00",
            "2026-09-13 12:00:00Z",
            "2026-09-13T12:00:00z",
            "2026-02-30T12:00:00Z",
            "yesterday",
        ]
        for value in bad_values:
            with self.subTest(value=value):
                st = rd.new_state(spec())
                with self.assertRaises(rd.DeskError):
                    rd.record_evidence(st, evidence("accuracy", recorded_at=value))

    def test_fractional_utc_timestamp_is_supported(self):
        st = rd.new_state(spec())
        st = rd.record_evidence(st, evidence("accuracy", recorded_at="2026-09-13T12:00:00.123456Z"))
        self.assertEqual(st["evidence_history"][0]["recorded_at"], "2026-09-13T12:00:00.123456Z")

    def test_included_followon_is_not_change_order(self):
        st = ready_state()
        st = rd.add_followon_request(st, {
            "request_id": "req-1",
            "title": "Add another summary format",
            "scope_refs": ["summary"],
            "requested_at": "2026-09-13T12:01:00Z",
        })
        out = rd.compile_rollout(st)
        self.assertEqual(out["decision"], "READY_FOR_OWNER_ROLLOUT_REVIEW")
        self.assertEqual(out["followon_scope"][0]["classification"], "INCLUDED")
        self.assertTrue(out["followon_scope"][0]["free_extension_allowed"])

    def test_excluded_followon_stays_out_of_scope(self):
        st = ready_state()
        st = rd.add_followon_request(st, {
            "request_id": "req-2",
            "title": "Deploy to production",
            "scope_refs": ["production-deploy"],
            "requested_at": "2026-09-13T12:01:00Z",
        })
        out = rd.compile_rollout(st)
        self.assertEqual(out["decision"], "READY_FOR_OWNER_ROLLOUT_REVIEW")
        self.assertEqual(out["followon_scope"][0]["classification"], "OUT_OF_SCOPE")
        self.assertFalse(out["followon_scope"][0]["free_extension_allowed"])
        self.assertIn("req-2", out["rollout_candidate"]["excluded_request_ids"])

    def test_unknown_followon_without_terms_holds_commercial_scope(self):
        st = ready_state()
        st = rd.add_followon_request(st, {
            "request_id": "req-3",
            "title": "New provider adapter",
            "scope_refs": ["new-provider-adapter"],
            "requested_at": "2026-09-13T12:01:00Z",
        })
        out = rd.compile_rollout(st)
        self.assertEqual(out["decision"], "HOLD_FOR_COMMERCIAL_SCOPE")
        self.assertEqual(out["followon_scope"][0]["classification"], "CHANGE_ORDER_REQUIRED")
        self.assertTrue(out["followon_scope"][0]["requires_separate_buyer_agreement"])

    def test_unknown_followon_with_terms_becomes_change_order_candidate(self):
        st = ready_state()
        st = rd.add_followon_request(st, {
            "request_id": "req-4",
            "title": "New provider adapter",
            "scope_refs": ["new-provider-adapter"],
            "requested_at": "2026-09-13T12:01:00Z",
            "commercial_delta": {
                "proposed_price_cents": 300000,
                "proposed_duration_days": 5,
                "acceptance_criteria": [
                    {"criterion_id": "adapter-a", "statement": "Adapter passes bounded fixture."}
                ],
                "dependencies": ["Buyer-provided sanitized fixture"],
            },
        })
        out = rd.compile_rollout(st)
        self.assertEqual(out["decision"], "READY_FOR_OWNER_ROLLOUT_REVIEW")
        self.assertEqual(out["rollout_candidate"]["change_order_candidates"][0]["request_id"], "req-4")
        self.assertFalse(out["rollout_candidate"]["buyer_acceptance"])
        self.assertFalse(out["rollout_candidate"]["payment_received"])
        self.assertFalse(out["rollout_candidate"]["revenue_recognized"])

    def test_followon_chronology_regression_rejected(self):
        st = ready_state()
        st = rd.add_followon_request(st, {
            "request_id": "req-newer",
            "title": "First observed request",
            "scope_refs": ["summary"],
            "requested_at": "2026-09-13T12:02:00Z",
        })
        with self.assertRaises(rd.DeskError):
            rd.add_followon_request(st, {
                "request_id": "req-older",
                "title": "Backdated request",
                "scope_refs": ["summary"],
                "requested_at": "2026-09-13T12:01:59Z",
            })

    def test_resealed_followon_classification_rejected(self):
        st = ready_state()
        st = rd.add_followon_request(st, {
            "request_id": "req-class",
            "title": "Deploy to production",
            "scope_refs": ["production-deploy"],
            "requested_at": "2026-09-13T12:01:00Z",
        })
        raw = rd._state_without_seal(st)
        raw["followon_requests"][0]["classification"] = "INCLUDED"
        resealed = rd.seal_state(raw)
        with self.assertRaises(rd.DeskError):
            rd.validate_state(resealed)

    def test_resealed_followon_chronology_rejected(self):
        st = ready_state()
        st = rd.add_followon_request(st, {
            "request_id": "req-a",
            "title": "A",
            "scope_refs": ["summary"],
            "requested_at": "2026-09-13T12:01:00Z",
        })
        st = rd.add_followon_request(st, {
            "request_id": "req-b",
            "title": "B",
            "scope_refs": ["summary"],
            "requested_at": "2026-09-13T12:02:00Z",
        })
        raw = rd._state_without_seal(st)
        raw["followon_requests"][1]["requested_at"] = "2026-09-13T12:00:59Z"
        resealed = rd.seal_state(raw)
        with self.assertRaises(rd.DeskError):
            rd.validate_state(resealed)

    def test_duplicate_followon_id_rejected(self):
        st = ready_state()
        req = {
            "request_id": "req-x",
            "title": "Thing",
            "scope_refs": ["summary"],
            "requested_at": "2026-09-13T12:01:00Z",
        }
        st = rd.add_followon_request(st, req)
        with self.assertRaises(rd.DeskError):
            rd.add_followon_request(st, req)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(rd.DeskError):
            rd.loads_strict('{"a":1,"a":2}')

    def test_bool_price_rejected(self):
        bad = spec()
        bad["pilot_price_cents"] = True
        with self.assertRaises(rd.DeskError):
            rd.new_state(bad)

    def test_url_and_email_buyer_refs_rejected(self):
        for value in ("https://example.com", "a@b.com"):
            bad = spec()
            bad["buyer_ref"] = value
            with self.assertRaises(rd.DeskError):
                rd.new_state(bad)

    def test_scope_overlap_rejected(self):
        bad = spec()
        bad["excluded_scope"].append({"scope_id": "summary", "title": "Bad overlap"})
        with self.assertRaises(rd.DeskError):
            rd.new_state(bad)

    def test_tampered_state_rejected(self):
        st = ready_state()
        st["revision"] = 999
        with self.assertRaises(rd.DeskError):
            rd.validate_state(st)

    def test_resealed_revision_drift_rejected(self):
        st = ready_state()
        raw = rd._state_without_seal(st)
        raw["revision"] = 999
        with self.assertRaises(rd.DeskError):
            rd.validate_state(rd.seal_state(raw))

    def test_authority_escalation_rejected(self):
        st = ready_state()
        raw = rd._state_without_seal(st)
        raw["authority"]["charge_authorized"] = True
        tampered = rd.seal_state(raw)
        with self.assertRaises(rd.DeskError):
            rd.validate_state(tampered)

    def test_export_hash_binds_output(self):
        out = rd.compile_rollout(ready_state())
        digest = out["export_sha256"]
        core = {k: v for k, v in out.items() if k != "export_sha256"}
        self.assertEqual(digest, rd.sha256_value(core))

    def test_markdown_keeps_truth_boundary(self):
        md = rd.render_markdown(rd.compile_rollout(ready_state()))
        self.assertIn("Buyer acceptance: false", md)
        self.assertIn("Payment received: false", md)
        self.assertIn("Revenue recognized: false", md)
        self.assertIn("does not contact the buyer", md)

    def test_read_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real.json"
            real.write_text("{}")
            link = root / "link.json"
            try:
                link.symlink_to(real)
            except OSError:
                self.skipTest("symlink unavailable")
            with self.assertRaises(rd.DeskError):
                rd._read_regular_json(link)

    def test_write_exclusive_refuses_existing(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.txt"
            path.write_text("keep")
            with self.assertRaises(FileExistsError):
                rd._write_exclusive(path, "replace")
            self.assertEqual(path.read_text(), "keep")

    def test_compile_cli_is_create_exclusive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path = root / "state.json"
            rd._atomic_write_json(state_path, ready_state())
            out_json = root / "out.json"
            out_md = root / "out.md"
            args = type("A", (), {"state": str(state_path), "out_json": str(out_json), "out_md": str(out_md)})()
            rd.cmd_compile(args)
            self.assertTrue(out_json.exists())
            self.assertTrue(out_md.exists())
            with self.assertRaises(rd.DeskError):
                rd.cmd_compile(args)

    def test_state_reopen_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            st = ready_state()
            rd._atomic_write_json(path, st)
            reopened = rd.validate_state(rd._read_regular_json(path))
            self.assertEqual(reopened, st)
            self.assertEqual(rd.compile_rollout(reopened)["decision"], "READY_FOR_OWNER_ROLLOUT_REVIEW")


if __name__ == "__main__":
    unittest.main()
