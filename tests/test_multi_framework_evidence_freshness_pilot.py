from __future__ import annotations

import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from revenue.multi_framework_evidence_freshness import gate
from revenue.multi_framework_evidence_freshness_pilot import pilot
from revenue.multi_framework_evidence_freshness_pilot import strict_cli as cli

FIXED_NOW = dt.datetime(2026, 9, 16, 22, 30, 0, tzinfo=dt.timezone.utc)


def row(eid, *, owner="owner-1", collected="2026-09-15T00:00:00Z", start="2026-07-01T00:00:00Z", end="2026-07-10T00:00:00Z", checksum="a"*64, rule="fresh-30", source="src-1"):
    return {
        "evidence_id": eid,
        "owner_ref": owner,
        "collected_at": collected,
        "coverage_start": start,
        "coverage_end": end,
        "mappings": [{"framework": "SOC2", "control": "CC1.1"}],
        "checksum_sha256": checksum,
        "freshness_rule_id": rule,
        "source_ref": source,
    }


def evidence_input(rows=None):
    return {
        "schema": "commons.multi-framework-evidence-freshness/v1",
        "assessment": {
            "assessment_id": "assessment-1",
            "period_start": "2026-07-01T00:00:00Z",
            "period_end": "2026-07-10T00:00:00Z",
            "scope": [{"framework": "SOC2", "control": "CC1.1"}],
        },
        "freshness_policy": {"rule_id": "fresh-30", "max_age_days": 30},
        "evidence": rows if rows is not None else [
            row("reuse-1"),
            row("stale-1", collected="2026-07-11T00:00:00Z"),
            row("scope-1", start="2026-07-02T00:00:00Z"),
            row("owner-1", owner=""),
            row("incomplete-1", checksum=""),
        ],
    }


def request(rows=None):
    return {
        "schema": pilot.REQUEST_SCHEMA,
        "engagement_ref": "demo-engagement-1",
        "sanitized_export_attested": True,
        "evidence_input": evidence_input(rows),
    }


class PilotTests(unittest.TestCase):
    def compile(self, req=None):
        with mock.patch.object(gate, "_now_utc", return_value=FIXED_NOW):
            return pilot.compile_diagnostic(req or request())

    def verify(self, req, packet, diagnostic, report, now=FIXED_NOW):
        with mock.patch.object(gate, "_now_utc", return_value=now):
            return pilot.verify_diagnostic(req, packet, diagnostic, report)

    def test_clean_diagnostic_exact_counts(self):
        packet, diag, report = self.compile()
        self.assertEqual(diag["classification_counts"], {"REUSABLE":1,"STALE":1,"SCOPE_MISMATCH":1,"MISSING_OWNER":1,"INCOMPLETE":1})
        self.assertTrue(self.verify(request(), packet, diag, report))

    def test_offer_is_code_owned(self):
        _, diag, _ = self.compile()
        self.assertEqual(diag["offer"]["fixed_diagnostic_usd"], 3500)
        self.assertEqual(diag["offer"]["integration_sprint_usd"], 10000)
        self.assertFalse(diag["offer"]["free_custom_adapter"])
        self.assertEqual(diag["offer"]["commercial_state"], "PROPOSED_NOT_ACCEPTED")

    def test_reason_counts_are_aggregate_only(self):
        _, diag, report = self.compile()
        self.assertEqual(diag["non_reusable_reason_counts"]["FRESHNESS_WINDOW_EXCEEDED"], 1)
        self.assertNotIn("reuse-1", report)
        self.assertNotIn("stale-1", report)

    def test_authority_all_false(self):
        _, diag, _ = self.compile()
        self.assertFalse(any(diag["authority"].values()))

    def test_request_501_rejected_before_engine(self):
        rows=[row(f"e-{i}") for i in range(501)]
        with self.assertRaises(pilot.PilotError): pilot.validate_request(request(rows))

    def test_request_500_boundary_accepted(self):
        rows=[row(f"e-{i}") for i in range(500)]
        with mock.patch.object(gate, "_now_utc", return_value=FIXED_NOW):
            packet, diag, _ = pilot.compile_diagnostic(request(rows))
        self.assertEqual(diag["scope"]["evidence_object_count"], 500)
        self.assertEqual(sum(diag["classification_counts"].values()), 500)

    def test_empty_export_rejected(self):
        with self.assertRaises(pilot.PilotError): pilot.validate_request(request([]))

    def test_sanitized_attestation_true_required(self):
        req=request(); req["sanitized_export_attested"]=False
        with self.assertRaises(pilot.PilotError): pilot.validate_request(req)

    def test_bool_int_alias_rejected(self):
        req=request(); req["sanitized_export_attested"]=1
        with self.assertRaises(pilot.PilotError): pilot.validate_request(req)

    def test_unknown_request_price_override_rejected(self):
        req=request(); req["fixed_price_usd"]=1
        with self.assertRaises(pilot.PilotError): pilot.validate_request(req)

    def test_bad_engagement_ref_rejected(self):
        req=request(); req["engagement_ref"]="hello@example.com"
        with self.assertRaises(pilot.PilotError): pilot.validate_request(req)

    def test_packet_tamper_rejected(self):
        packet, diag, report=self.compile(); packet=copy.deepcopy(packet); packet["counts"]["REUSABLE"]+=1
        with self.assertRaises(pilot.PilotError): self.verify(request(), packet, diag, report)

    def test_request_packet_cross_pair_rejected(self):
        packet, diag, report=self.compile()
        req=request(); req["evidence_input"]["evidence"][0]["checksum_sha256"]="b"*64
        with self.assertRaises(pilot.PilotError): self.verify(req, packet, diag, report)

    def test_diagnostic_tamper_rejected(self):
        packet, diag, report=self.compile(); diag=copy.deepcopy(diag); diag["offer"]["fixed_diagnostic_usd"]=1
        with self.assertRaises(pilot.PilotError): self.verify(request(), packet, diag, report)

    def test_report_tamper_rejected(self):
        packet, diag, report=self.compile()
        with self.assertRaises(pilot.PilotError): self.verify(request(), packet, diag, report+"tamper")

    def test_engine_binding_matches_packet(self):
        packet, diag, _=self.compile(); b=diag["engine_binding"]
        self.assertEqual(b["normalized_input_sha256"], packet["input_sha256"])
        self.assertEqual(b["projection_sha256"], packet["projection_sha256"])
        self.assertEqual(b["engine_receipt_sha256"], packet["receipt_sha256"])
        self.assertEqual(b["packet_sha256"], pilot.sha256_obj(packet))

    def test_source_bindings_are_sha256(self):
        _, diag, _=self.compile()
        self.assertRegex(diag["engine_binding"]["engine_source_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(diag["compiler_source_sha256"], r"^[0-9a-f]{64}$")

    def test_receipt_is_self_consistent(self):
        _, diag, _=self.compile(); body=dict(diag); receipt=body.pop("receipt_sha256")
        self.assertEqual(receipt, pilot.sha256_obj(body))

    def test_fixed_time_repeat_is_byte_deterministic(self):
        p1,d1,r1=self.compile(); p2,d2,r2=self.compile()
        self.assertEqual(pilot.canonical(p1), pilot.canonical(p2))
        self.assertEqual(pilot.canonical(d1), pilot.canonical(d2))
        self.assertEqual(r1,r2)

    def test_stale_later_verification_fails_closed(self):
        packet, diag, report=self.compile(request([row("only-reuse")]))
        later=dt.datetime(2026,11,1,tzinfo=dt.timezone.utc)
        with self.assertRaises(pilot.PilotError): self.verify(request([row("only-reuse")]),packet,diag,report,now=later)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"x.json"; p.write_text('{"schema":"x","schema":"y"}')
            with self.assertRaises(pilot.PilotError): pilot.load_json(p)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"x.json"; p.write_text('{"x":NaN}')
            with self.assertRaises(pilot.PilotError): pilot.load_json(p)

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); real=root/"real"; real.write_text("{}")
            link=root/"link"; link.symlink_to(real)
            with self.assertRaises(pilot.PilotError): pilot.load_json(link)

    def test_create_exclusive_output(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"out"; pilot.write_exclusive(path,b"one")
            with self.assertRaises(pilot.PilotError): pilot.write_exclusive(path,b"two")
            self.assertEqual(path.read_bytes(),b"one")

    def test_symlink_output_parent_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); real=root/"real"; real.mkdir(); link=root/"link"; link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(pilot.PilotError): pilot.write_exclusive(link/"out",b"x")
            self.assertFalse((real/"out").exists())

    def test_cli_compile_verify(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); reqp=root/"request.json"; pp=root/"packet.json"; dp=root/"diagnostic.json"; mp=root/"buyer.md"
            reqp.write_bytes(pilot.canonical(request()))
            with mock.patch.object(gate,"_now_utc",return_value=FIXED_NOW):
                self.assertEqual(cli.main(["compile",str(reqp),str(pp),str(dp),str(mp)]),0)
                self.assertEqual(cli.main(["verify",str(reqp),str(pp),str(dp),str(mp)]),0)
            self.assertIn("$3,500",mp.read_text())

    def test_cli_duplicate_output_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); reqp=root/"request.json"; out=root/"out"; mp=root/"buyer.md"; reqp.write_bytes(pilot.canonical(request()))
            with mock.patch.object(gate,"_now_utc",return_value=FIXED_NOW):
                self.assertEqual(cli.main(["compile",str(reqp),str(out),str(out),str(mp)]),2)
            self.assertFalse(out.exists())

    def test_cli_late_output_collision_is_fail_visible_non_destructive(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); reqp=root/"request.json"; pp=root/"packet.json"; dp=root/"diagnostic.json"; mp=root/"buyer.md"
            reqp.write_bytes(pilot.canonical(request())); dp.write_text("foreign")
            with mock.patch.object(gate,"_now_utc",return_value=FIXED_NOW):
                self.assertEqual(cli.main(["compile",str(reqp),str(pp),str(dp),str(mp)]),2)
            self.assertTrue(pp.exists())
            self.assertEqual(dp.read_text(),"foreign")
            self.assertFalse(mp.exists())

    def test_buyer_report_is_bounded_summary(self):
        _,_,report=self.compile()
        self.assertLess(len(report.encode("utf-8")),10000)
        self.assertIn("PROPOSED_NOT_ACCEPTED",report)
        self.assertIn("not an audit or certification opinion",report)


if __name__ == "__main__":
    unittest.main()
