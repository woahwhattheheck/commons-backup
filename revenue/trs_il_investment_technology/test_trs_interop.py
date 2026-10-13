import copy
import hashlib
import json
import unittest

import trs_interop
from trs_interop import ContractError, compile_packet, loads_strict, verify_packet

def base():
    from pathlib import Path
    return loads_strict((Path(__file__).parent / "example_input.json").read_text())

def promote_all_to_first_party(data):
    for source in data["sources"]:
        source["authority"] = "BUYER_FIRST_PARTY"
        source["content_state"] = "RETAINED_BYTES"
    packet_source = data["sources"][0]
    data["controlling_packet"] = {"status":"RETAINED_CURRENT","source_id":packet_source["source_id"]}
    return packet_source["sha256"]

class TestTRSInterop(unittest.TestCase):
    def test_discovery_fixture_holds_packet(self):
        report = compile_packet(base())
        self.assertEqual(report["state"], "HOLD_CONTROLLING_PACKET")
        self.assertFalse(report["packet_gate"]["clear"])
        self.assertTrue(all(v is False for v in report["authority_ceiling"].values()))

    def test_payload_cannot_self_promote_without_out_of_band_hash(self):
        data = base()
        sha = promote_all_to_first_party(data)
        report = compile_packet(data)
        self.assertEqual(report["state"], "HOLD_CONTROLLING_PACKET")
        self.assertIn("out-of-band", report["packet_gate"]["reason"])
        self.assertEqual(sha, data["sources"][0]["sha256"])

    def test_wrong_out_of_band_hash_holds(self):
        data = base()
        promote_all_to_first_party(data)
        report = compile_packet(data, trusted_packet_sha256="0"*64)
        self.assertEqual(report["state"], "HOLD_CONTROLLING_PACKET")
        self.assertIn("mismatch", report["packet_gate"]["reason"])

    def test_third_party_packet_never_clears(self):
        data = base()
        packet = data["sources"][0]
        packet["content_state"] = "RETAINED_BYTES"
        data["controlling_packet"] = {"status":"RETAINED_CURRENT","source_id":packet["source_id"]}
        report = compile_packet(data, trusted_packet_sha256=packet["sha256"])
        self.assertEqual(report["state"], "HOLD_CONTROLLING_PACKET")
        self.assertIn("not BUYER_FIRST_PARTY", report["packet_gate"]["reason"])


    def test_first_party_metadata_only_packet_still_holds(self):
        data = base()
        packet = data["sources"][1]
        data["controlling_packet"] = {"status":"RETAINED_CURRENT","source_id":packet["source_id"]}
        report = compile_packet(data, trusted_packet_sha256=packet["sha256"])
        self.assertEqual(report["state"], "HOLD_CONTROLLING_PACKET")
        self.assertIn("does not bind retained bytes", report["packet_gate"]["reason"])

    def test_packet_clear_but_discovery_systems_hold_source_authority(self):
        data = base()
        # use buyer-first-party vendor page as controlling packet, while all stack facts remain discovery
        packet = data["sources"][1]
        packet["content_state"] = "RETAINED_BYTES"
        data["controlling_packet"] = {"status":"RETAINED_CURRENT","source_id":packet["source_id"]}
        report = compile_packet(data, trusted_packet_sha256=packet["sha256"])
        self.assertEqual(report["state"], "HOLD_SOURCE_AUTHORITY")
        self.assertTrue(report["packet_gate"]["clear"])
        self.assertGreater(len(report["source_authority_holds"]["systems"]), 0)

    def test_all_first_party_can_only_reach_partner_qualification(self):
        data = base()
        sha = promote_all_to_first_party(data)
        report = compile_packet(data, trusted_packet_sha256=sha)
        self.assertEqual(report["state"], "READY_FOR_PARTNER_QUALIFICATION")
        self.assertNotIn("BID", report["state"])
        self.assertFalse(report["authority_ceiling"]["bid_submission"])

    def test_market_data_overlap_is_visible(self):
        report = compile_packet(base())
        row = next(x for x in report["domain_authority"] if x["domain"] == "MARKET_DATA")
        self.assertEqual(row["systems"], ["BLOOMBERG","FACTSET"])
        self.assertEqual(row["review_state"], "MULTI_SYSTEM_AUTHORITY_REVIEW")

    def test_deterministic_under_collection_reorder(self):
        data = base()
        a = compile_packet(data)
        data["sources"].reverse()
        data["systems"].reverse()
        data["objectives"].reverse()
        data["proposed_controls"].reverse()
        b = compile_packet(data)
        self.assertEqual(a, b)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ContractError):
            loads_strict('{"schema":"x","schema":"y"}')

    def test_float_rejected(self):
        with self.assertRaises(ContractError):
            loads_strict('{"x":1.25}')

    def test_duplicate_source_rejected(self):
        data = base()
        data["sources"].append(copy.deepcopy(data["sources"][0]))
        with self.assertRaises(ContractError):
            compile_packet(data)

    def test_unknown_system_evidence_rejected(self):
        data = base()
        data["systems"][0]["evidence_source_id"] = "NOPE"
        with self.assertRaises(ContractError):
            compile_packet(data)

    def test_unknown_control_system_rejected(self):
        data = base()
        data["proposed_controls"][0]["systems"].append("NOPE")
        with self.assertRaises(ContractError):
            compile_packet(data)

    def test_unknown_control_source_rejected(self):
        data = base()
        data["proposed_controls"][0]["evidence_source_ids"].append("NOPE")
        with self.assertRaises(ContractError):
            compile_packet(data)

    def test_duplicate_system_role_rejected(self):
        data = base()
        data["systems"][0]["roles"].append(data["systems"][0]["roles"][0])
        with self.assertRaises(ContractError):
            compile_packet(data)

    def test_commercial_acceptance_self_claim_rejected(self):
        data = base()
        data["commercial"]["state"] = "ACCEPTED"
        with self.assertRaises(ContractError):
            compile_packet(data)

    def test_post_import_authority_global_mutation_cannot_widen_report(self):
        original_obj = trs_interop.AUTHORITY_CEILING
        original_value = dict(original_obj)
        try:
            original_obj["bid_submission"] = True
            original_obj["recognized_revenue"] = True
            mutated = compile_packet(base())
            self.assertTrue(all(v is False for v in mutated["authority_ceiling"].values()))
            trs_interop.AUTHORITY_CEILING = {"bid_submission": True, "recognized_revenue": True}
            rebound = compile_packet(base())
            self.assertTrue(all(v is False for v in rebound["authority_ceiling"].values()))
            self.assertEqual(mutated["authority_ceiling"], rebound["authority_ceiling"])
        finally:
            original_obj.clear()
            original_obj.update(original_value)
            trs_interop.AUTHORITY_CEILING = original_obj

    def test_post_import_commercial_state_rebind_cannot_self_promote(self):
        original = trs_interop.COMMERCIAL_STATE
        try:
            trs_interop.COMMERCIAL_STATE = "ACCEPTED"
            promoted = base()
            promoted["commercial"]["state"] = "ACCEPTED"
            with self.assertRaises(ContractError):
                compile_packet(promoted)
            report = compile_packet(base())
            self.assertEqual(report["commercial"]["state"], "PROPOSED_NOT_ACCEPTED")
        finally:
            trs_interop.COMMERCIAL_STATE = original

    def test_bool_money_rejected(self):
        data = base()
        data["commercial"]["proposed_fee_minor"] = True
        with self.assertRaises(ContractError):
            compile_packet(data)

    def test_report_tamper_fails_verify(self):
        data = base()
        report = compile_packet(data)
        report["state"] = "READY_FOR_PARTNER_QUALIFICATION"
        self.assertFalse(verify_packet(data, report))

    def test_receipt_binds_report_core(self):
        data = base()
        report = compile_packet(data)
        core = {k:v for k,v in report.items() if k != "receipt"}
        actual = hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(actual, report["receipt"]["report_core_sha256"])

    def test_controlling_packet_unknown_source_rejected(self):
        data = base()
        data["controlling_packet"] = {"status":"RETAINED_CURRENT","source_id":"NOPE"}
        with self.assertRaises(ContractError):
            compile_packet(data)

    def test_missing_packet_requires_null_source(self):
        data = base()
        data["controlling_packet"] = {"status":"MISSING","source_id":"TRS_VENDOR_PAGE_20260917"}
        with self.assertRaises(ContractError):
            compile_packet(data)

    def test_bad_trusted_hash_syntax_rejected_only_when_needed(self):
        data = base()
        sha = promote_all_to_first_party(data)
        with self.assertRaises(ContractError):
            compile_packet(data, trusted_packet_sha256="ABC")
        self.assertEqual(len(sha), 64)

if __name__ == "__main__":
    unittest.main()
