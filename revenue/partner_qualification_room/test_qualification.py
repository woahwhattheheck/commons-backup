import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from qualification import (
    QualificationError,
    cli_main,
    evaluate_partner,
    evaluate_room,
    export_human_review_markdown,
    export_room_markdown,
)


BASE_OPPORTUNITY = {
    "id": "RFP-2026-001",
    "requirements": [
        {"id": "cap", "category": "capability", "must_have": True, "description": "Can deliver the required service"},
        {"id": "geo", "category": "geography", "must_have": True, "description": "Can serve the required geography"},
        {"id": "ins", "category": "insurance", "must_have": True, "description": "Required insurance is in force"},
        {"id": "nice", "category": "experience", "must_have": False, "description": "Prior public-sector experience"},
    ],
}

BASE_PARTNER = {
    "id": "partner-1",
    "evidence": [
        {"id": "e-cap", "requirement_id": "cap", "state": "confirmed", "source": {"ref": "src:capability-page"}, "observed_on": "2026-09-12"},
        {"id": "e-geo", "requirement_id": "geo", "state": "confirmed", "source": {"ref": "src:service-area"}, "observed_on": "2026-09-12"},
        {"id": "e-ins", "requirement_id": "ins", "state": "confirmed", "source": {"ref": "src:coi"}, "observed_on": "2026-09-12", "expires_on": "2026-12-31"},
    ],
}


class QualificationTests(unittest.TestCase):
    def test_all_must_haves_ready_for_review(self):
        packet = evaluate_partner(BASE_OPPORTUNITY, BASE_PARTNER, as_of="2026-09-13")
        self.assertEqual(packet["status"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(packet["counts"]["satisfied_must_have"], 3)
        self.assertEqual(packet["counts"]["gaps"], 1)
        self.assertTrue(all(value is False for value in packet["authority"].values()))

    def test_missing_required_evidence_is_gap(self):
        partner = copy.deepcopy(BASE_PARTNER)
        partner["evidence"] = [e for e in partner["evidence"] if e["requirement_id"] != "geo"]
        packet = evaluate_partner(BASE_OPPORTUNITY, partner, as_of="2026-09-13")
        self.assertEqual(packet["status"], "QUALIFICATION_GAPS")
        geo = next(x for x in packet["requirements"] if x["requirement_id"] == "geo")
        self.assertEqual(geo["status"], "GAP")

    def test_claimed_is_not_confirmed(self):
        partner = copy.deepcopy(BASE_PARTNER)
        partner["evidence"][0]["state"] = "claimed"
        packet = evaluate_partner(BASE_OPPORTUNITY, partner, as_of="2026-09-13")
        self.assertEqual(packet["status"], "QUALIFICATION_GAPS")
        cap = next(x for x in packet["requirements"] if x["requirement_id"] == "cap")
        self.assertEqual(cap["status"], "UNVERIFIED")

    def test_contradiction_blocks_required_requirement(self):
        partner = copy.deepcopy(BASE_PARTNER)
        partner["evidence"].append({"id": "e-geo-no", "requirement_id": "geo", "state": "contradicted", "source": {"ref": "src:territory-exclusion"}, "observed_on": "2026-09-13"})
        packet = evaluate_partner(BASE_OPPORTUNITY, partner, as_of="2026-09-13")
        self.assertEqual(packet["status"], "DISQUALIFYING_CONTRADICTION")
        self.assertEqual(packet["counts"]["contradictions"], 1)

    def test_expired_evidence_is_stale(self):
        partner = copy.deepcopy(BASE_PARTNER)
        partner["evidence"][2]["expires_on"] = "2026-09-12"
        packet = evaluate_partner(BASE_OPPORTUNITY, partner, as_of="2026-09-13")
        ins = next(x for x in packet["requirements"] if x["requirement_id"] == "ins")
        self.assertEqual(ins["status"], "STALE")
        self.assertEqual(packet["status"], "QUALIFICATION_GAPS")

    def test_expiry_on_as_of_date_is_usable(self):
        partner = copy.deepcopy(BASE_PARTNER)
        partner["evidence"][2]["expires_on"] = "2026-09-13"
        packet = evaluate_partner(BASE_OPPORTUNITY, partner, as_of="2026-09-13")
        self.assertEqual(packet["status"], "READY_FOR_HUMAN_REVIEW")

    def test_future_observation_does_not_satisfy(self):
        partner = copy.deepcopy(BASE_PARTNER)
        partner["evidence"][1]["observed_on"] = "2026-09-14"
        packet = evaluate_partner(BASE_OPPORTUNITY, partner, as_of="2026-09-13")
        geo = next(x for x in packet["requirements"] if x["requirement_id"] == "geo")
        self.assertEqual(geo["status"], "UNVERIFIED")

    def test_optional_contradiction_does_not_disqualify(self):
        partner = copy.deepcopy(BASE_PARTNER)
        partner["evidence"].append({"id": "e-nice-no", "requirement_id": "nice", "state": "contradicted", "source": {"ref": "src:experience"}, "observed_on": "2026-09-13"})
        packet = evaluate_partner(BASE_OPPORTUNITY, partner, as_of="2026-09-13")
        self.assertEqual(packet["status"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(packet["counts"]["contradictions"], 1)

    def test_unknown_requirement_link_fails_closed(self):
        partner = copy.deepcopy(BASE_PARTNER)
        partner["evidence"].append({"id": "e-x", "requirement_id": "nope", "state": "confirmed", "source": {"ref": "src:x"}, "observed_on": "2026-09-13"})
        with self.assertRaisesRegex(QualificationError, "unknown requirement"):
            evaluate_partner(BASE_OPPORTUNITY, partner, as_of="2026-09-13")

    def test_duplicate_requirement_id_rejected(self):
        opportunity = copy.deepcopy(BASE_OPPORTUNITY)
        opportunity["requirements"].append(copy.deepcopy(opportunity["requirements"][0]))
        with self.assertRaisesRegex(QualificationError, "duplicate requirements id"):
            evaluate_partner(opportunity, BASE_PARTNER, as_of="2026-09-13")

    def test_duplicate_evidence_id_rejected(self):
        partner = copy.deepcopy(BASE_PARTNER)
        partner["evidence"].append(copy.deepcopy(partner["evidence"][0]))
        with self.assertRaisesRegex(QualificationError, "duplicate evidence id"):
            evaluate_partner(BASE_OPPORTUNITY, partner, as_of="2026-09-13")

    def test_source_ref_required(self):
        partner = copy.deepcopy(BASE_PARTNER)
        partner["evidence"][0]["source"] = {}
        with self.assertRaisesRegex(QualificationError, "source.ref"):
            evaluate_partner(BASE_OPPORTUNITY, partner, as_of="2026-09-13")

    def test_malformed_date_rejected(self):
        partner = copy.deepcopy(BASE_PARTNER)
        partner["evidence"][0]["observed_on"] = "09/13/2026"
        with self.assertRaisesRegex(QualificationError, "ISO date"):
            evaluate_partner(BASE_OPPORTUNITY, partner, as_of="2026-09-13")

    def test_unknown_category_rejected(self):
        opportunity = copy.deepcopy(BASE_OPPORTUNITY)
        opportunity["requirements"][0]["category"] = "vibes"
        with self.assertRaisesRegex(QualificationError, "category must be one of"):
            evaluate_partner(opportunity, BASE_PARTNER, as_of="2026-09-13")

    def test_packet_is_fully_deterministic(self):
        first = evaluate_partner(BASE_OPPORTUNITY, BASE_PARTNER, as_of="2026-09-13")
        second = evaluate_partner(BASE_OPPORTUNITY, BASE_PARTNER, as_of="2026-09-13")
        self.assertEqual(first, second)

    def test_input_order_does_not_change_packet(self):
        opportunity = copy.deepcopy(BASE_OPPORTUNITY)
        partner = copy.deepcopy(BASE_PARTNER)
        opportunity["requirements"].reverse()
        partner["evidence"].reverse()
        first = evaluate_partner(BASE_OPPORTUNITY, BASE_PARTNER, as_of="2026-09-13")
        second = evaluate_partner(opportunity, partner, as_of="2026-09-13")
        self.assertEqual(first, second)

    def test_source_refs_are_sorted_and_deduped(self):
        partner = copy.deepcopy(BASE_PARTNER)
        partner["evidence"].append({"id": "e-cap-2", "requirement_id": "cap", "state": "confirmed", "source": {"ref": "src:capability-page"}, "observed_on": "2026-09-11"})
        packet = evaluate_partner(BASE_OPPORTUNITY, partner, as_of="2026-09-13")
        self.assertEqual(packet["source_refs"], sorted(set(packet["source_refs"])))
        self.assertEqual(packet["source_refs"].count("src:capability-page"), 1)

    def test_markdown_preserves_non_authority_and_evidence_ledger(self):
        packet = evaluate_partner(BASE_OPPORTUNITY, BASE_PARTNER, as_of="2026-09-13")
        rendered = export_human_review_markdown(packet)
        self.assertIn("Human review only", rendered)
        self.assertIn("outreach_authorized=false", rendered)
        self.assertIn("## Evidence ledger", rendered)
        self.assertIn("src:coi", rendered)
        self.assertIn("READY_FOR_HUMAN_REVIEW", rendered)

    def test_markdown_escapes_pipe_and_newline(self):
        partner = copy.deepcopy(BASE_PARTNER)
        partner["evidence"][0]["note"] = "left|right\nnext"
        packet = evaluate_partner(BASE_OPPORTUNITY, partner, as_of="2026-09-13")
        rendered = export_human_review_markdown(packet)
        self.assertIn("left\\|right next", rendered)

    def test_empty_requirements_rejected(self):
        opportunity = {"id": "x", "requirements": []}
        with self.assertRaisesRegex(QualificationError, "non-empty list"):
            evaluate_partner(opportunity, {"id": "p", "evidence": []}, as_of="2026-09-13")

    def test_non_boolean_must_have_rejected(self):
        opportunity = copy.deepcopy(BASE_OPPORTUNITY)
        opportunity["requirements"][0]["must_have"] = "yes"
        with self.assertRaisesRegex(QualificationError, "must_have must be boolean"):
            evaluate_partner(opportunity, BASE_PARTNER, as_of="2026-09-13")

    def test_room_evaluates_without_ranking(self):
        second = copy.deepcopy(BASE_PARTNER)
        second["id"] = "partner-2"
        second["evidence"] = [e for e in second["evidence"] if e["requirement_id"] != "geo"]
        room = evaluate_room(BASE_OPPORTUNITY, [second, BASE_PARTNER], as_of="2026-09-13")
        self.assertEqual([p["partner_id"] for p in room["partners"]], ["partner-1", "partner-2"])
        self.assertEqual(room["status_counts"]["READY_FOR_HUMAN_REVIEW"], 1)
        self.assertEqual(room["status_counts"]["QUALIFICATION_GAPS"], 1)
        self.assertNotIn("winner", room)
        self.assertTrue(all(value is False for value in room["authority"].values()))

    def test_room_digest_is_order_independent(self):
        second = copy.deepcopy(BASE_PARTNER)
        second["id"] = "partner-2"
        first_room = evaluate_room(BASE_OPPORTUNITY, [BASE_PARTNER, second], as_of="2026-09-13")
        second_room = evaluate_room(BASE_OPPORTUNITY, [second, BASE_PARTNER], as_of="2026-09-13")
        self.assertEqual(first_room, second_room)

    def test_room_duplicate_partner_id_rejected(self):
        with self.assertRaisesRegex(QualificationError, "duplicate partners id"):
            evaluate_room(BASE_OPPORTUNITY, [BASE_PARTNER, copy.deepcopy(BASE_PARTNER)], as_of="2026-09-13")

    def test_room_markdown_contains_each_partner(self):
        second = copy.deepcopy(BASE_PARTNER)
        second["id"] = "partner-2"
        room = evaluate_room(BASE_OPPORTUNITY, [BASE_PARTNER, second], as_of="2026-09-13")
        rendered = export_room_markdown(room)
        self.assertIn("`partner-1`", rendered)
        self.assertIn("`partner-2`", rendered)
        self.assertIn("\n\n---\n\n", rendered)

    def test_cli_json_single_partner(self):
        doc = {"as_of": "2026-09-13", "opportunity": BASE_OPPORTUNITY, "partner": BASE_PARTNER}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli_main([str(path)]), 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "READY_FOR_HUMAN_REVIEW")

    def test_cli_markdown_room(self):
        second = copy.deepcopy(BASE_PARTNER)
        second["id"] = "partner-2"
        doc = {"as_of": "2026-09-13", "opportunity": BASE_OPPORTUNITY, "partners": [BASE_PARTNER, second]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli_main([str(path), "--format", "markdown"]), 0)
            rendered = out.getvalue()
            self.assertIn("partner-1", rendered)
            self.assertIn("partner-2", rendered)


if __name__ == "__main__":
    unittest.main()
