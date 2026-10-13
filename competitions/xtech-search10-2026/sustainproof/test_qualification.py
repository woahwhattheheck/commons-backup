from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from qualification import (
    ContractError, EXPECTED_SOURCE_FACTSET_SHA256, INPUT_VERSION,
    compile_packet, parse_json_strict, read_regular_json, sha256_json,
)

AS_OF = datetime(2026, 9, 14, 4, 40, tzinfo=timezone.utc)


def confirmed(value=True, *, when="2026-09-14T04:30:00Z", ref="owner:retained-evidence"):
    return {"state": "CONFIRMED_TRUE" if value else "CONFIRMED_FALSE", "evidenceRef": ref, "observedAt": when}


def unknown():
    return {"state": "UNKNOWN", "evidenceRef": None, "observedAt": None}


def base_input():
    return {
        "version": INPUT_VERSION,
        "entityRef": "OWNER_ENTITY",
        "entityFacts": {
            "forProfitUSConcern": confirmed(),
            "independent": confirmed(),
            "sbirSmallBusinessRequirementsMet": confirmed(),
            "majorityQualifyingOwnershipControl": confirmed(),
            "employeeCountWithAffiliatesAtMost500": confirmed(),
            "oneSubmissionSlotAvailable": confirmed(),
        },
        "federalSupportCensus": confirmed(ref="owner:federal-support-census"),
        "federalSupport": [],
        "commercialEvidence": [],
    }


def sources():
    return json.loads((HERE / "official_sources.json").read_text())


class QualificationTests(unittest.TestCase):
    def test_pinned_official_factset_hash_matches_checked_in_source(self):
        self.assertEqual(sha256_json(sources()["facts"]), EXPECTED_SOURCE_FACTSET_SHA256)

    def test_all_owner_evidence_present_is_review_ready_not_army_eligible(self):
        out = compile_packet(base_input(), sources(), as_of=AS_OF)
        self.assertEqual(out["state"], "EVIDENCE_PACKET_COMPLETE_OWNER_REVIEW")
        self.assertFalse(any(out["authority"].values()))
        self.assertEqual(out["mode"], "HISTORICAL_INTEGRITY_ONLY")

    def test_unknown_entity_fact_blocks(self):
        d = base_input()
        d["entityFacts"]["majorityQualifyingOwnershipControl"] = unknown()
        out = compile_packet(d, sources(), as_of=AS_OF)
        self.assertEqual(out["state"], "BLOCKED_OWNER_ENTITY_FACTS")
        self.assertIn("ENTITY_FACT_UNPROVEN_OR_STALE:majorityQualifyingOwnershipControl", out["blockers"])

    def test_consumed_or_unproven_entity_submission_slot_blocks(self):
        d = base_input()
        d["entityFacts"]["oneSubmissionSlotAvailable"] = confirmed(False)
        out = compile_packet(d, sources(), as_of=AS_OF)
        self.assertIn("ENTITY_FACT_FALSE:oneSubmissionSlotAvailable", out["blockers"])

    def test_false_entity_fact_blocks(self):
        d = base_input()
        d["entityFacts"]["forProfitUSConcern"] = confirmed(False)
        out = compile_packet(d, sources(), as_of=AS_OF)
        self.assertIn("ENTITY_FACT_FALSE:forProfitUSConcern", out["blockers"])

    def test_stale_entity_fact_blocks(self):
        d = base_input()
        d["entityFacts"]["independent"] = confirmed(when="2026-01-01T00:00:00Z")
        out = compile_packet(d, sources(), as_of=AS_OF)
        self.assertIn("ENTITY_FACT_UNPROVEN_OR_STALE:independent", out["blockers"])

    def test_empty_support_rows_do_not_imply_complete_census(self):
        d = base_input()
        d["federalSupportCensus"] = unknown()
        out = compile_packet(d, sources(), as_of=AS_OF)
        self.assertEqual(out["state"], "BLOCKED_FEDERAL_SUPPORT_CENSUS")
        self.assertIn("FEDERAL_SUPPORT_CENSUS_UNPROVEN_OR_STALE", out["blockers"])

    def test_substantially_same_active_federal_support_blocks(self):
        d = base_input()
        d["federalSupport"] = [{
            "recordId": "fed-1", "agencyRef": "agency-a", "status": "CURRENT",
            "technologyOverlap": "SUBSTANTIALLY_SAME", "evidenceRef": "owner:fed-1",
            "observedAt": "2026-09-14T04:20:00Z",
        }]
        out = compile_packet(d, sources(), as_of=AS_OF)
        self.assertEqual(out["state"], "BLOCKED_FEDERAL_SUPPORT_COLLISION")

    def test_potential_overlap_requires_review(self):
        d = base_input()
        d["federalSupport"] = [{
            "recordId": "fed-1", "agencyRef": "agency-a", "status": "CLOSED_UNFUNDED",
            "technologyOverlap": "POTENTIALLY_SAME", "evidenceRef": "owner:fed-1",
            "observedAt": "2026-09-14T04:20:00Z",
        }]
        out = compile_packet(d, sources(), as_of=AS_OF)
        self.assertEqual(out["state"], "BLOCKED_FEDERAL_SUPPORT_REVIEW")

    def test_stale_support_evidence_requires_review(self):
        d = base_input()
        d["federalSupport"] = [{
            "recordId": "fed-1", "agencyRef": "agency-a", "status": "CLOSED_UNFUNDED",
            "technologyOverlap": "NONE", "evidenceRef": "owner:fed-1",
            "observedAt": "2026-01-01T00:00:00Z",
        }]
        out = compile_packet(d, sources(), as_of=AS_OF)
        self.assertEqual(out["state"], "BLOCKED_FEDERAL_SUPPORT_REVIEW")

    def test_inactive_substantially_same_closed_unfunded_does_not_trigger_collision(self):
        d = base_input()
        d["federalSupport"] = [{
            "recordId": "fed-1", "agencyRef": "agency-a", "status": "CLOSED_UNFUNDED",
            "technologyOverlap": "SUBSTANTIALLY_SAME", "evidenceRef": "owner:fed-1",
            "observedAt": "2026-09-14T04:20:00Z",
        }]
        out = compile_packet(d, sources(), as_of=AS_OF)
        self.assertEqual(out["state"], "EVIDENCE_PACKET_COMPLETE_OWNER_REVIEW")

    def test_source_fact_mutation_is_rejected(self):
        s = sources()
        s["facts"]["whitePaperPages"] = 4
        with self.assertRaisesRegex(ContractError, "SOURCE_FACT_MISMATCH"):
            compile_packet(base_input(), s, as_of=AS_OF)

    def test_source_generation_timestamp_cannot_be_resealed_by_caller(self):
        s = sources()
        s["retrievedAt"] = "2026-09-14T04:39:00Z"
        for row in s["sources"]:
            row["retrievedAt"] = "2026-09-14T04:39:00Z"
        with self.assertRaisesRegex(ContractError, "SOURCE_GENERATION_UNPINNED"):
            compile_packet(base_input(), s, as_of=AS_OF)

    def test_source_id_url_cannot_be_replaced(self):
        s = sources()
        s["sources"][0]["url"] = "https://example.invalid/fake"
        with self.assertRaisesRegex(ContractError, "SOURCE_ID_URL_UNPINNED"):
            compile_packet(base_input(), s, as_of=AS_OF)

    def test_pinned_source_generation_expires_without_code_refresh(self):
        with self.assertRaisesRegex(ContractError, "SOURCE_TOO_OLD"):
            compile_packet(base_input(), sources(), as_of=datetime(2026, 10, 20, 4, 40, tzinfo=timezone.utc))

    def test_support_and_commercial_row_order_do_not_change_receipt(self):
        d = base_input()
        d["federalSupport"] = [
            {"recordId":"fed-b","agencyRef":"b","status":"CLOSED_UNFUNDED","technologyOverlap":"NONE","evidenceRef":"owner:b","observedAt":"2026-09-14T04:20:00Z"},
            {"recordId":"fed-a","agencyRef":"a","status":"CLOSED_UNFUNDED","technologyOverlap":"NONE","evidenceRef":"owner:a","observedAt":"2026-09-14T04:20:00Z"},
        ]
        d["commercialEvidence"] = [
            {"evidenceId":"e-b","kind":"MARKET_RESEARCH","claim":"market b","evidenceRef":"owner:market-b","observedAt":"2026-09-14T04:20:00Z"},
            {"evidenceId":"e-a","kind":"PRODUCT_PROOF","claim":"prototype a","evidenceRef":"owner:prototype-a","observedAt":"2026-09-14T04:20:00Z"},
        ]
        a = compile_packet(d, sources(), as_of=AS_OF)
        d["federalSupport"].reverse()
        d["commercialEvidence"].reverse()
        b = compile_packet(d, sources(), as_of=AS_OF)
        self.assertEqual(a, b)

    def test_duplicate_support_record_rejected(self):
        d = base_input()
        row = {"recordId":"fed-a","agencyRef":"a","status":"CLOSED_UNFUNDED","technologyOverlap":"NONE","evidenceRef":"owner:a","observedAt":"2026-09-14T04:20:00Z"}
        d["federalSupport"] = [row, deepcopy(row)]
        with self.assertRaisesRegex(ContractError, "SUPPORT_RECORD_DUPLICATE"):
            compile_packet(d, sources(), as_of=AS_OF)

    def test_unknown_fact_cannot_carry_evidence(self):
        d = base_input()
        d["entityFacts"]["independent"] = {"state":"UNKNOWN","evidenceRef":"owner:x","observedAt":None}
        with self.assertRaisesRegex(ContractError, "UNKNOWN_FACT_HAS_EVIDENCE"):
            compile_packet(d, sources(), as_of=AS_OF)

    def test_strict_json_rejects_duplicate_keys(self):
        with self.assertRaisesRegex(ContractError, "JSON_DUPLICATE_KEY"):
            parse_json_strict('{"a":1,"a":2}')

    def test_regular_file_reader_refuses_symlink(self):
        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("O_NOFOLLOW unavailable")
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "target.json"
            link = Path(td) / "link.json"
            target.write_text('{"ok":true}')
            link.symlink_to(target)
            with self.assertRaisesRegex(ContractError, "INPUT_OPEN_FAILED"):
                read_regular_json(str(link))


if __name__ == "__main__":
    unittest.main()
