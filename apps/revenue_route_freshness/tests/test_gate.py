import copy
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from apps.revenue_route_freshness.gate import (
    DEAD_ROUTE,
    HARD_DNR,
    HOLD_COMPANY_PRIOR_TOUCH,
    HOLD_STALE_ROUTE,
    READY_FOR_MUSE_CENSUS,
    EvidenceError,
    compile_decision,
)


def base_payload():
    return {
        "schema": "revenue-route-evidence/v1",
        "as_of": "2026-09-17T05:30:00Z",
        "max_route_age_days": 30,
        "seat": "ZVH-0118",
        "buyer_scope": "example.com",
        "offer_key": "lims-workshare-25k",
        "purpose_key": "prime-teaming",
        "route": {
            "kind": "email",
            "value": "Sales@Example.com",
            "source_url": "https://example.com/contact",
            "source_class": "FIRST_PARTY",
            "observed_at": "2026-09-16T18:00:00Z",
        },
        "provider_events": [],
        "company_touches": [],
        "dnr": [],
        "muse_leases": [],
    }


class GateTests(unittest.TestCase):
    def test_ready_never_authorizes_send(self):
        out = compile_decision(base_payload())
        self.assertEqual(out["decision"], READY_FOR_MUSE_CENSUS)
        self.assertIs(out["send_authorized"], False)
        self.assertEqual(out["next_step"], "REQUEST_FRESH_MUSE_CENSUS")

    def test_stale_route_holds(self):
        p = base_payload(); p["route"]["observed_at"] = "2026-08-01T00:00:00Z"
        out = compile_decision(p)
        self.assertEqual(out["decision"], HOLD_STALE_ROUTE)
        self.assertIn("ROUTE_SOURCE_TOO_OLD", out["reason_codes"])

    def test_secondary_route_holds_even_recent(self):
        p = base_payload(); p["route"]["source_class"] = "SECONDARY"
        self.assertEqual(compile_decision(p)["decision"], HOLD_STALE_ROUTE)

    def test_unknown_source_holds(self):
        p = base_payload(); p["route"]["source_class"] = "UNKNOWN"
        self.assertEqual(compile_decision(p)["decision"], HOLD_STALE_ROUTE)

    def test_exact_hard_bounce_marks_dead(self):
        p = base_payload(); p["provider_events"] = [{
            "id":"gmail:b1","kind":"HARD_BOUNCE","route_kind":"email",
            "route_value":"sales@example.com","buyer_scope":"example.com",
            "observed_at":"2026-09-17T01:00:00Z"}]
        out = compile_decision(p)
        self.assertEqual(out["decision"], DEAD_ROUTE)
        self.assertEqual(out["evidence_ids"], ["gmail:b1"])

    def test_other_route_bounce_does_not_kill_current(self):
        p = base_payload(); p["provider_events"] = [{
            "id":"gmail:b2","kind":"HARD_BOUNCE","route_kind":"email",
            "route_value":"old@example.com","buyer_scope":"example.com",
            "observed_at":"2026-09-17T01:00:00Z"}]
        self.assertEqual(compile_decision(p)["decision"], READY_FOR_MUSE_CENSUS)

    def test_company_send_holds_even_route_changed(self):
        p = base_payload(); p["provider_events"] = [{
            "id":"gmail:s1","kind":"SENT","route_kind":"email",
            "route_value":"old@example.com","buyer_scope":"example.com",
            "observed_at":"2026-09-16T20:00:00Z"}]
        out = compile_decision(p)
        self.assertEqual(out["decision"], HOLD_COMPANY_PRIOR_TOUCH)
        self.assertIn("gmail:s1", out["evidence_ids"])

    def test_soft_delay_is_prior_touch_not_dead(self):
        p = base_payload(); p["provider_events"] = [{
            "id":"gmail:d1","kind":"SOFT_DELAY","route_kind":"email",
            "route_value":"sales@example.com","buyer_scope":"example.com",
            "observed_at":"2026-09-17T01:00:00Z"}]
        self.assertEqual(compile_decision(p)["decision"], HOLD_COMPANY_PRIOR_TOUCH)

    def test_auto_ack_never_releases_prior_touch(self):
        p = base_payload(); p["provider_events"] = [
            {"id":"gmail:s2","kind":"SENT","route_kind":"email","route_value":"sales@example.com","buyer_scope":"example.com","observed_at":"2026-09-16T20:00:00Z"},
            {"id":"gmail:a1","kind":"AUTO_ACK","route_kind":"email","route_value":"sales@example.com","buyer_scope":"example.com","observed_at":"2026-09-16T20:01:00Z"},
        ]
        self.assertEqual(compile_decision(p)["decision"], HOLD_COMPANY_PRIOR_TOUCH)

    def test_later_human_reply_releases_to_recensus(self):
        p = base_payload(); p["provider_events"] = [
            {"id":"gmail:s3","kind":"SENT","route_kind":"email","route_value":"sales@example.com","buyer_scope":"example.com","observed_at":"2026-09-16T20:00:00Z"},
            {"id":"gmail:h1","kind":"HUMAN_REPLY","route_kind":"email","route_value":"sales@example.com","buyer_scope":"example.com","observed_at":"2026-09-17T01:00:00Z"},
        ]
        out = compile_decision(p)
        self.assertEqual(out["decision"], READY_FOR_MUSE_CENSUS)
        self.assertIs(out["send_authorized"], False)

    def test_explicit_company_touch_holds(self):
        p = base_payload(); p["company_touches"] = [{
            "id":"slack:t1","kind":"OUTBOUND_SENT","buyer_scope":"example.com",
            "offer_key":"other","purpose_key":"other","observed_at":"2026-09-16T22:00:00Z"}]
        self.assertEqual(compile_decision(p)["decision"], HOLD_COMPANY_PRIOR_TOUCH)

    def test_company_dnr_terminal(self):
        p = base_payload(); p["dnr"] = [{
            "id":"slack:dnr-company","active":True,"scope":"COMPANY",
            "buyer_scope":"example.com","observed_at":"2026-09-16T23:00:00Z"}]
        out = compile_decision(p)
        self.assertEqual(out["decision"], HARD_DNR)
        self.assertEqual(out["next_step"], "STOP_DNR")

    def test_exact_route_dnr_only_same_route(self):
        p = base_payload(); p["dnr"] = [{
            "id":"slack:dnr-old","active":True,"scope":"EXACT_ROUTE",
            "buyer_scope":"example.com","route_kind":"email","route_value":"old@example.com",
            "observed_at":"2026-09-16T23:00:00Z"}]
        self.assertEqual(compile_decision(p)["decision"], READY_FOR_MUSE_CENSUS)

    def test_buyer_offer_purpose_dnr_matches_casefolded_key(self):
        p = base_payload(); p["dnr"] = [{
            "id":"slack:dnr-key","active":True,"scope":"BUYER_OFFER_PURPOSE",
            "buyer_scope":"EXAMPLE.COM","offer_key":"LIMS-WORKSHARE-25K",
            "purpose_key":"PRIME-TEAMING","observed_at":"2026-09-16T23:00:00Z"}]
        self.assertEqual(compile_decision(p)["decision"], HARD_DNR)

    def test_inactive_dnr_ignored(self):
        p = base_payload(); p["dnr"] = [{
            "id":"slack:released","active":False,"scope":"COMPANY",
            "buyer_scope":"example.com","observed_at":"2026-09-16T23:00:00Z"}]
        self.assertEqual(compile_decision(p)["decision"], READY_FOR_MUSE_CENSUS)

    def test_live_muse_lease_holds_even_same_seat(self):
        p = base_payload(); p["muse_leases"] = [{
            "id":"slack:muse","status":"CLEAR","seat":"ZVH-0118",
            "buyer_scope":"example.com","offer_key":"lims-workshare-25k","purpose_key":"prime-teaming",
            "route_kind":"email","route_value":"sales@example.com",
            "observed_at":"2026-09-17T05:00:00Z","expires_at":"2026-09-17T06:00:00Z"}]
        out = compile_decision(p)
        self.assertEqual(out["decision"], HOLD_COMPANY_PRIOR_TOUCH)
        self.assertIn("ACTIVE_MUSE_CLEAR", out["reason_codes"])
        self.assertIs(out["send_authorized"], False)

    def test_expired_muse_lease_ignored(self):
        p = base_payload(); p["muse_leases"] = [{
            "id":"slack:muse-old","status":"SELECT","seat":"OTHER",
            "buyer_scope":"example.com","offer_key":"lims-workshare-25k","purpose_key":"prime-teaming",
            "route_kind":"email","route_value":"sales@example.com",
            "observed_at":"2026-09-16T04:00:00Z","expires_at":"2026-09-16T06:00:00Z"}]
        self.assertEqual(compile_decision(p)["decision"], READY_FOR_MUSE_CENSUS)

    def test_dnr_precedes_dead_route(self):
        p = base_payload(); p["dnr"] = [{"id":"dnr:p","active":True,"scope":"COMPANY","buyer_scope":"example.com","observed_at":"2026-09-17T00:00:00Z"}]
        p["provider_events"] = [{"id":"bounce:p","kind":"HARD_BOUNCE","route_kind":"email","route_value":"sales@example.com","buyer_scope":"example.com","observed_at":"2026-09-17T01:00:00Z"}]
        self.assertEqual(compile_decision(p)["decision"], HARD_DNR)

    def test_bool_is_not_integer_age(self):
        p = base_payload(); p["max_route_age_days"] = True
        with self.assertRaises(EvidenceError): compile_decision(p)

    def test_naive_timestamp_rejected(self):
        p = base_payload(); p["route"]["observed_at"] = "2026-09-16T18:00:00"
        with self.assertRaises(EvidenceError): compile_decision(p)

    def test_future_evidence_rejected(self):
        p = base_payload(); p["route"]["observed_at"] = "2026-09-18T18:00:00Z"
        with self.assertRaises(EvidenceError): compile_decision(p)

    def test_duplicate_evidence_ids_rejected_cross_collection(self):
        p = base_payload(); p["provider_events"] = [{"id":"dup","kind":"AUTO_ACK","route_kind":"email","route_value":"sales@example.com","buyer_scope":"example.com","observed_at":"2026-09-17T01:00:00Z"}]
        p["dnr"] = [{"id":"dup","active":False,"scope":"COMPANY","buyer_scope":"example.com","observed_at":"2026-09-17T02:00:00Z"}]
        with self.assertRaises(EvidenceError): compile_decision(p)

    def test_email_canonicalization_drives_dedupe(self):
        p = base_payload(); p["provider_events"] = [{"id":"b:case","kind":"HARD_BOUNCE","route_kind":"email","route_value":"SALES@example.COM","buyer_scope":"example.com","observed_at":"2026-09-17T01:00:00Z"}]
        out = compile_decision(p)
        self.assertEqual(out["route_key"], "email:sales@example.com")
        self.assertEqual(out["decision"], DEAD_ROUTE)

    def test_url_credentials_rejected(self):
        p = base_payload(); p["route"] = {"kind":"url","value":"https://u:p@example.com/contact","source_url":"https://example.com/","source_class":"FIRST_PARTY","observed_at":"2026-09-17T01:00:00Z"}
        with self.assertRaises(EvidenceError): compile_decision(p)

    def test_schema_required_omits_speaker_fields(self):
        schema_path = pathlib.Path(__file__).resolve().parents[1] / "route_evidence.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(
            schema["required"],
            ["schema", "as_of", "buyer_scope", "offer_key", "purpose_key", "route"],
        )
        self.assertIn("seat", schema["properties"])

    def test_compile_rejects_blank_evidence_seat(self):
        missing = base_payload()
        del missing["seat"]
        with self.assertRaises(EvidenceError):
            compile_decision(missing)
        blank = base_payload()
        blank["seat"] = "   "
        with self.assertRaises(EvidenceError):
            compile_decision(blank)

    def test_deterministic_projection(self):
        p = base_payload()
        self.assertEqual(compile_decision(copy.deepcopy(p)), compile_decision(copy.deepcopy(p)))
        self.assertRegex(compile_decision(p)["input_digest_sha256"], r"^[0-9a-f]{64}$")

    def test_every_decision_keeps_send_authorized_false(self):
        cases = []
        cases.append(base_payload())
        p = base_payload(); p["route"]["source_class"] = "SECONDARY"; cases.append(p)
        p = base_payload(); p["company_touches"] = [{"id":"t:x","kind":"OUTBOUND_SENT","buyer_scope":"example.com","offer_key":"x","purpose_key":"y","observed_at":"2026-09-17T00:00:00Z"}]; cases.append(p)
        p = base_payload(); p["dnr"] = [{"id":"d:x","active":True,"scope":"COMPANY","buyer_scope":"example.com","observed_at":"2026-09-17T00:00:00Z"}]; cases.append(p)
        p = base_payload(); p["provider_events"] = [{"id":"b:x","kind":"HARD_BOUNCE","route_kind":"email","route_value":"sales@example.com","buyer_scope":"example.com","observed_at":"2026-09-17T00:00:00Z"}]; cases.append(p)
        self.assertEqual({compile_decision(x)["decision"] for x in cases}, {READY_FOR_MUSE_CENSUS,HOLD_STALE_ROUTE,HOLD_COMPANY_PRIOR_TOUCH,HARD_DNR,DEAD_ROUTE})
        for case in cases: self.assertIs(compile_decision(case)["send_authorized"], False)


class CliTests(unittest.TestCase):
    def test_invalid_input_exits_two_without_projection(self):
        p = base_payload(); p["max_route_age_days"] = False
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "bad.json"; path.write_text(json.dumps(p), encoding="utf-8")
            proc = subprocess.run([sys.executable, "-m", "apps.revenue_route_freshness.gate", str(path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("route-evidence-error:", proc.stderr)


if __name__ == "__main__": unittest.main()
