import copy
import json
import unittest
from pathlib import Path

from engine import (
    COMPLETENESS_CONTRACT,
    CONTRACT,
    HOLD,
    NO_BID,
    PRIME_READY,
    TEAMING_READY,
    QualificationError,
    compile_qualification,
    digest,
    loads_strict,
    render_markdown,
    verify_receipt,
    verify_receipt_against_inputs,
)

AS_OF = "2026-09-13T10:00:00Z"
OFFICIAL_HASH = "1" * 64
CAP_HASH = "2" * 64
TEAM_HASH = "3" * 64

PACKET = {
    "contract": CONTRACT,
    "as_of": AS_OF,
    "opportunity": {
        "opportunity_id": "opp-demo-001",
        "buyer": "Example Public Buyer",
        "solicitation_id": "RFP-2026-001",
        "title": "AI workflow verification services",
        "controlling_source_id": "buyer-rfp",
        "proposal_deadline": "2026-10-01T17:00:00Z",
        "proposal_deadline_source_id": "buyer-rfp",
        "question_deadline": "2026-09-20T17:00:00Z",
        "question_deadline_source_id": "buyer-rfp",
        "teaming": "ALLOWED",
        "teaming_source_id": "buyer-rfp",
    },
    "sources": [
        {
            "source_id": "buyer-rfp",
            "scope": "BUYER",
            "source_class": "OFFICIAL",
            "url": "https://buyer.example.gov/rfp/2026-001",
            "captured_at": "2026-09-13T09:00:00Z",
            "sha256": OFFICIAL_HASH,
            "label": "Controlling RFP package",
        },
        {
            "source_id": "prime-cap",
            "scope": "CAPABILITY",
            "source_class": "OFFICIAL",
            "url": "https://github.com/example/repo/commit/1111111111111111111111111111111111111111",
            "captured_at": "2026-09-13T09:00:00Z",
            "sha256": CAP_HASH,
            "label": "Prime capability evidence",
        },
        {
            "source_id": "team-cap",
            "scope": "CAPABILITY",
            "source_class": "OFFICIAL",
            "url": "https://partner.example.com/public/evidence",
            "captured_at": "2026-09-13T09:00:00Z",
            "sha256": TEAM_HASH,
            "label": "Partner capability evidence",
        },
    ],
    "evidence": [
        {
            "evidence_id": "prime-technical",
            "subject": "PRIME",
            "category": "TECHNICAL",
            "source_id": "prime-cap",
            "captured_at": "2026-09-13T09:05:00Z",
            "sha256": "4" * 64,
            "statement": "Exact technical delivery evidence.",
        },
        {
            "evidence_id": "prime-registration",
            "subject": "PRIME",
            "category": "REGISTRATION",
            "source_id": "prime-cap",
            "captured_at": "2026-09-13T09:05:00Z",
            "sha256": "5" * 64,
            "statement": "Current organization registration evidence.",
            "valid_until": "2027-09-13T09:05:00Z",
        },
        {
            "evidence_id": "team-experience",
            "subject": "TEAM",
            "category": "EXPERIENCE",
            "source_id": "team-cap",
            "captured_at": "2026-09-13T09:05:00Z",
            "sha256": "6" * 64,
            "statement": "Partner experience evidence.",
        },
        {
            "evidence_id": "team-reference",
            "subject": "TEAM",
            "category": "REFERENCE",
            "source_id": "team-cap",
            "captured_at": "2026-09-13T09:05:00Z",
            "sha256": "7" * 64,
            "statement": "Partner reference evidence.",
        },
    ],
    "requirements": [
        {
            "gate_id": "technical-fit",
            "category": "TECHNICAL",
            "mandatory": True,
            "route": "PRIME",
            "cure": "NONE",
            "buyer_source_id": "buyer-rfp",
            "description": "Respondent must support deterministic workflow verification.",
            "prime_state": "PASS",
            "prime_evidence_ids": ["prime-technical"],
            "team_state": "MISSING",
            "team_evidence_ids": [],
        },
        {
            "gate_id": "registration",
            "category": "REGISTRATION",
            "mandatory": True,
            "route": "PRIME",
            "cure": "NONE",
            "buyer_source_id": "buyer-rfp",
            "description": "Prime organization registration must be current.",
            "prime_state": "PASS",
            "prime_evidence_ids": ["prime-registration"],
            "team_state": "MISSING",
            "team_evidence_ids": [],
        },
        {
            "gate_id": "experience",
            "category": "EXPERIENCE",
            "mandatory": False,
            "route": "PRIME",
            "cure": "PARTNER",
            "buyer_source_id": "buyer-rfp",
            "description": "Comparable public-sector experience is scoreable.",
            "prime_state": "MISSING",
            "prime_evidence_ids": [],
            "team_state": "PASS",
            "team_evidence_ids": ["team-experience"],
        },
    ],
}

_FIXTURE_DIR = Path(__file__).resolve().parent
TRUSTED_COMPLETENESS = loads_strict(
    (_FIXTURE_DIR / "completeness_fixture.json").read_text(encoding="utf-8")
)
TRUSTED_COMPLETENESS_SHA256 = (
    (_FIXTURE_DIR / "completeness_fixture.sha256").read_text(encoding="utf-8").split()[0]
)


def completeness_for(packet):
    """Test-only generator for tests that intentionally alter the package model."""
    sources = {source["source_id"]: source for source in packet["sources"]}
    gates = []
    for requirement in packet["requirements"]:
        source = sources[requirement["buyer_source_id"]]
        gates.append(
            {
                "gate_id": requirement["gate_id"],
                "category": requirement["category"],
                "mandatory": requirement["mandatory"],
                "route": requirement["route"],
                "cure": requirement["cure"],
                "buyer_source_id": requirement["buyer_source_id"],
                "buyer_source_sha256": source["sha256"],
                "description_sha256": digest(requirement["description"]),
            }
        )
    gates.sort(key=lambda gate: gate["gate_id"])
    controlling_id = packet["opportunity"]["controlling_source_id"]
    manifest = {
        "contract": COMPLETENESS_CONTRACT,
        "opportunity_id": packet["opportunity"]["opportunity_id"],
        "controlling_source_id": controlling_id,
        "controlling_source_sha256": sources[controlling_id]["sha256"],
        "extracted_at": "2026-09-13T09:30:00Z",
        "extraction_evidence_sha256": "e" * 64,
        "complete": True,
        "gate_count": len(gates),
        "gate_set_sha256": digest(gates),
        "gates": gates,
    }
    return manifest, digest(manifest)


class QualificationTests(unittest.TestCase):
    def compile(self, packet=None, as_of=AS_OF, trust="RETAINED"):
        packet = copy.deepcopy(PACKET if packet is None else packet)
        if trust == "RETAINED":
            completeness = copy.deepcopy(TRUSTED_COMPLETENESS)
            root = TRUSTED_COMPLETENESS_SHA256
        elif trust == "AUTO":
            completeness, root = completeness_for(packet)
        elif trust is None:
            completeness, root = None, None
        else:
            completeness, root = trust
        return compile_qualification(
            packet,
            trusted_as_of=as_of,
            trusted_completeness=copy.deepcopy(completeness),
            trusted_completeness_sha256=root,
        )

    def test_retained_fixture_root_matches_manifest(self):
        self.assertEqual(digest(TRUSTED_COMPLETENESS), TRUSTED_COMPLETENESS_SHA256)

    def test_prime_ready(self):
        receipt = self.compile()
        self.assertEqual(receipt["disposition"], PRIME_READY)
        self.assertTrue(receipt["prime"]["ready"])
        self.assertTrue(receipt["completeness"]["verified"])
        self.assertEqual(receipt["completeness"]["manifest_digest"], TRUSTED_COMPLETENESS_SHA256)
        self.assertTrue(verify_receipt(receipt))
        self.assertTrue(all(value is False for value in receipt["authority"].values()))

    def test_deterministic(self):
        self.assertEqual(self.compile(), self.compile())

    def test_order_invariant(self):
        packet = copy.deepcopy(PACKET)
        packet["sources"] = list(reversed(packet["sources"]))
        packet["evidence"] = list(reversed(packet["evidence"]))
        packet["requirements"] = list(reversed(packet["requirements"]))
        self.assertEqual(self.compile()["input_digest"], self.compile(packet)["input_digest"])
        self.assertEqual(self.compile()["receipt_digest"], self.compile(packet)["receipt_digest"])

    def test_team_ready_when_partner_cures_prime_gap(self):
        packet = copy.deepcopy(PACKET)
        gate = packet["requirements"][1]
        gate["cure"] = "PARTNER"
        gate["prime_state"] = "MISSING"
        gate["prime_evidence_ids"] = []
        gate["team_state"] = "PASS"
        gate["team_evidence_ids"] = ["team-reference"]
        gate["category"] = "REFERENCE"
        packet["evidence"][3]["category"] = "REFERENCE"
        receipt = self.compile(packet, trust="AUTO")
        self.assertEqual(receipt["disposition"], TEAMING_READY)
        self.assertFalse(receipt["prime"]["ready"])
        self.assertTrue(receipt["team"]["ready"])

    def test_missing_prime_gate_holds_if_team_cure_missing(self):
        packet = copy.deepcopy(PACKET)
        gate = packet["requirements"][1]
        gate["cure"] = "PARTNER"
        gate["prime_state"] = "MISSING"
        gate["prime_evidence_ids"] = []
        receipt = self.compile(packet, trust="AUTO")
        self.assertEqual(receipt["disposition"], HOLD)

    def test_noncurable_prime_failure_no_bid_when_team_cannot_cure(self):
        packet = copy.deepcopy(PACKET)
        gate = packet["requirements"][1]
        gate["prime_state"] = "FAIL"
        gate["prime_evidence_ids"] = ["prime-registration"]
        receipt = self.compile(packet)
        self.assertEqual(receipt["disposition"], NO_BID)

    def test_teaming_prohibited_blocks_partner_route(self):
        packet = copy.deepcopy(PACKET)
        packet["opportunity"]["teaming"] = "PROHIBITED"
        packet["opportunity"]["teaming_source_id"] = "buyer-rfp"
        gate = packet["requirements"][1]
        gate["cure"] = "PARTNER"
        gate["prime_state"] = "MISSING"
        gate["prime_evidence_ids"] = []
        gate["team_state"] = "PASS"
        gate["team_evidence_ids"] = ["team-reference"]
        gate["category"] = "REFERENCE"
        receipt = self.compile(packet, trust="AUTO")
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertIn("TEAMING_PROHIBITED", receipt["team"]["reasons"])

    def test_expired_deadline_no_bid(self):
        packet = copy.deepcopy(PACKET)
        packet["opportunity"]["proposal_deadline"] = "2026-09-12T17:00:00Z"
        receipt = self.compile(packet)
        self.assertEqual(receipt["disposition"], NO_BID)
        self.assertEqual(receipt["reasons"], ["PROPOSAL_DEADLINE_EXPIRED"])

    def test_official_extension_can_restore_open_deadline(self):
        packet = copy.deepcopy(PACKET)
        packet["sources"].append(
            {
                "source_id": "buyer-addendum",
                "scope": "BUYER",
                "source_class": "OFFICIAL",
                "url": "https://buyer.example.gov/rfp/2026-001/addendum-2",
                "captured_at": "2026-09-13T09:30:00Z",
                "sha256": "8" * 64,
                "label": "Official deadline extension",
            }
        )
        packet["opportunity"]["proposal_deadline"] = "2026-10-15T17:00:00Z"
        packet["opportunity"]["proposal_deadline_source_id"] = "buyer-addendum"
        receipt = self.compile(packet)
        self.assertEqual(receipt["disposition"], PRIME_READY)

    def test_secondary_controlling_source_holds(self):
        packet = copy.deepcopy(PACKET)
        packet["sources"][0]["source_class"] = "SECONDARY"
        receipt = self.compile(packet)
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertIn("CONTROLLING_PACKAGE_NOT_OFFICIALLY_EVIDENCED", receipt["reasons"])

    def test_secondary_mandatory_requirement_cannot_green(self):
        packet = copy.deepcopy(PACKET)
        packet["sources"].append(
            {
                "source_id": "buyer-mirror",
                "scope": "BUYER",
                "source_class": "SECONDARY",
                "url": "https://mirror.example.com/rfp/2026-001",
                "captured_at": "2026-09-13T09:00:00Z",
                "sha256": "9" * 64,
                "label": "Procurement mirror",
            }
        )
        packet["requirements"][0]["buyer_source_id"] = "buyer-mirror"
        receipt = self.compile(packet, trust="AUTO")
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertIn("technical-fit:MANDATORY_SOURCE_NOT_OFFICIAL", receipt["reasons"])

    def test_secondary_capability_source_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["sources"][1]["source_class"] = "SECONDARY"
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_future_source_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["sources"][0]["captured_at"] = "2026-09-14T09:00:00Z"
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_future_evidence_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["evidence"][0]["captured_at"] = "2026-09-14T09:00:00Z"
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_expired_capability_evidence_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["evidence"][1]["valid_until"] = "2026-09-12T09:05:00Z"
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_unknown_source_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["requirements"][0]["buyer_source_id"] = "missing-source"
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_evidence_subject_drift_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["requirements"][0]["prime_evidence_ids"] = ["team-experience"]
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_evidence_category_drift_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["requirements"][0]["prime_evidence_ids"] = ["prime-registration"]
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_missing_state_cannot_carry_evidence(self):
        packet = copy.deepcopy(PACKET)
        packet["requirements"][0]["prime_state"] = "MISSING"
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_pass_state_requires_evidence(self):
        packet = copy.deepcopy(PACKET)
        packet["requirements"][0]["prime_evidence_ids"] = []
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_duplicate_source_id_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["sources"].append(copy.deepcopy(packet["sources"][0]))
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_changed_duplicate_source_id_rejected(self):
        packet = copy.deepcopy(PACKET)
        changed = copy.deepcopy(packet["sources"][0])
        changed["label"] = "Changed"
        packet["sources"].append(changed)
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_duplicate_gate_id_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["requirements"].append(copy.deepcopy(packet["requirements"][0]))
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_unknown_root_field_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["send_now"] = True
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_unknown_requirement_field_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["requirements"][0]["confidence"] = 99
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_bool_is_not_text_or_integer_alias(self):
        packet = copy.deepcopy(PACKET)
        packet["requirements"][0]["mandatory"] = 1
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_float_rejected_anywhere(self):
        packet = copy.deepcopy(PACKET)
        packet["evidence"][0]["score"] = 0.9
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_bad_hash_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["sources"][0]["sha256"] = "ABC"
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_http_url_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["sources"][0]["url"] = "http://buyer.example.gov/rfp"
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_url_userinfo_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["sources"][0]["url"] = "https://user:pass@buyer.example.gov/rfp"
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_secret_shaped_label_rejected(self):
        packet = copy.deepcopy(PACKET)
        packet["sources"][0]["label"] = "Bearer abcdefghijklmnopqrstuvwxyz"
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_bad_as_of_rejected(self):
        with self.assertRaises(QualificationError):
            self.compile(as_of="2026-09-13 10:00:00")

    def test_packet_clock_must_match_trusted_clock(self):
        packet = copy.deepcopy(PACKET)
        packet["as_of"] = "2026-09-13T09:59:59Z"
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_unknown_teaming_requires_no_source(self):
        packet = copy.deepcopy(PACKET)
        packet["opportunity"]["teaming"] = "UNKNOWN"
        with self.assertRaises(QualificationError):
            self.compile(packet)

    def test_unknown_teaming_holds_if_prime_not_ready(self):
        packet = copy.deepcopy(PACKET)
        packet["opportunity"]["teaming"] = "UNKNOWN"
        packet["opportunity"]["teaming_source_id"] = None
        packet["requirements"][1]["prime_state"] = "MISSING"
        packet["requirements"][1]["prime_evidence_ids"] = []
        receipt = self.compile(packet)
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertIn("TEAMING_NOT_OFFICIALLY_EVIDENCED", receipt["team"]["reasons"])

    def test_both_route_requires_both_sides_for_team(self):
        packet = copy.deepcopy(PACKET)
        gate = packet["requirements"][1]
        gate["route"] = "BOTH"
        gate["team_state"] = "PASS"
        gate["team_evidence_ids"] = ["team-reference"]
        gate["category"] = "REFERENCE"
        packet["evidence"][1]["category"] = "REFERENCE"
        receipt = self.compile(packet, trust="AUTO")
        self.assertEqual(receipt["disposition"], PRIME_READY)
        self.assertTrue(receipt["team"]["ready"])

    def test_team_only_requirement_does_not_block_prime_route(self):
        packet = copy.deepcopy(PACKET)
        packet["requirements"].append(
            {
                "gate_id": "partner-staff",
                "category": "STAFFING",
                "mandatory": True,
                "route": "TEAM",
                "cure": "NONE",
                "buyer_source_id": "buyer-rfp",
                "description": "Team partner staffing requirement.",
                "prime_state": "MISSING",
                "prime_evidence_ids": [],
                "team_state": "MISSING",
                "team_evidence_ids": [],
            }
        )
        receipt = self.compile(packet, trust="AUTO")
        self.assertEqual(receipt["disposition"], PRIME_READY)

    def test_tampered_receipt_fails_verification(self):
        receipt = self.compile()
        receipt["disposition"] = NO_BID
        self.assertFalse(verify_receipt(receipt))

    def test_authority_tamper_fails_verification_even_with_old_digest(self):
        receipt = self.compile()
        receipt["authority"]["buyer_contact"] = True
        self.assertFalse(verify_receipt(receipt))

    def test_markdown_is_deterministic_and_bound(self):
        receipt = self.compile()
        first = render_markdown(receipt)
        second = render_markdown(receipt)
        self.assertEqual(first, second)
        self.assertIn(receipt["receipt_digest"], first)
        self.assertIn("PRIME_READY", first)

    def test_markdown_rejects_tampered_receipt(self):
        receipt = self.compile()
        receipt["counts"]["sources"] += 1
        with self.assertRaises(QualificationError):
            render_markdown(receipt)

    def test_strict_loader_duplicate_key(self):
        with self.assertRaises(QualificationError):
            loads_strict('{"contract":"a","contract":"b"}')

    def test_strict_loader_float(self):
        with self.assertRaises(QualificationError):
            loads_strict('{"value":1.5}')

    def test_strict_loader_nonfinite(self):
        with self.assertRaises(QualificationError):
            loads_strict('{"value":NaN}')

    def test_scoreable_gap_does_not_block_readiness(self):
        receipt = self.compile()
        self.assertEqual(receipt["disposition"], PRIME_READY)
        self.assertEqual([g["gate_id"] for g in receipt["scoreable_gaps"]], ["experience"])

    def test_missing_completeness_cannot_mint_ready(self):
        receipt = compile_qualification(copy.deepcopy(PACKET), trusted_as_of=AS_OF)
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertFalse(receipt["prime"]["ready"])
        self.assertTrue(receipt["prime"]["requirements_ready"])
        self.assertIn("PACKAGE_COMPLETENESS_NOT_PROVIDED", receipt["reasons"])

    def test_manifest_without_retained_root_cannot_mint_ready(self):
        receipt = compile_qualification(
            copy.deepcopy(PACKET),
            trusted_as_of=AS_OF,
            trusted_completeness=copy.deepcopy(TRUSTED_COMPLETENESS),
        )
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertIn("COMPLETENESS_TRUST_ROOT_NOT_PROVIDED", receipt["reasons"])

    def test_attacker_recomputed_manifest_cannot_replace_retained_root(self):
        packet = copy.deepcopy(PACKET)
        packet["requirements"] = [r for r in packet["requirements"] if r["gate_id"] != "registration"]
        attacker_manifest, _attacker_digest = completeness_for(packet)
        receipt = compile_qualification(
            packet,
            trusted_as_of=AS_OF,
            trusted_completeness=attacker_manifest,
            trusted_completeness_sha256=TRUSTED_COMPLETENESS_SHA256,
        )
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertIn("COMPLETENESS_TRUST_ROOT_MISMATCH", receipt["reasons"])

    def test_frozen_manifest_rejects_removed_mandatory_gate(self):
        packet = copy.deepcopy(PACKET)
        packet["requirements"] = [r for r in packet["requirements"] if r["gate_id"] != "registration"]
        receipt = self.compile(packet)
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertIn("PACKAGE_GATE_SET_MISMATCH", receipt["reasons"])
        self.assertFalse(receipt["prime"]["ready"])

    def test_frozen_manifest_rejects_removed_scoreable_category(self):
        packet = copy.deepcopy(PACKET)
        packet["requirements"] = [r for r in packet["requirements"] if r["category"] != "EXPERIENCE"]
        receipt = self.compile(packet)
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertIn("PACKAGE_GATE_SET_MISMATCH", receipt["reasons"])

    def test_frozen_manifest_rejects_required_addendum_gate_omission(self):
        packet = copy.deepcopy(PACKET)
        packet["sources"].append(
            {
                "source_id": "buyer-addendum",
                "scope": "BUYER",
                "source_class": "OFFICIAL",
                "url": "https://buyer.example.gov/rfp/2026-001/addendum-3",
                "captured_at": "2026-09-13T09:20:00Z",
                "sha256": "8" * 64,
                "label": "Mandatory submission addendum",
            }
        )
        packet["requirements"].append(
            {
                "gate_id": "addendum-certification",
                "category": "SUBMISSION",
                "mandatory": True,
                "route": "PRIME",
                "cure": "NONE",
                "buyer_source_id": "buyer-addendum",
                "description": "Respondent must include the addendum certification.",
                "prime_state": "PASS",
                "prime_evidence_ids": ["prime-registration"],
                "team_state": "MISSING",
                "team_evidence_ids": [],
            }
        )
        packet["evidence"][1]["category"] = "OTHER"
        manifest, root = completeness_for(packet)
        packet["requirements"] = [r for r in packet["requirements"] if r["gate_id"] != "addendum-certification"]
        receipt = self.compile(packet, trust=(manifest, root))
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertIn("PACKAGE_GATE_SET_MISMATCH", receipt["reasons"])

    def test_frozen_manifest_rejects_route_drift(self):
        packet = copy.deepcopy(PACKET)
        packet["requirements"][0]["route"] = "TEAM"
        packet["requirements"][0]["prime_state"] = "MISSING"
        packet["requirements"][0]["prime_evidence_ids"] = []
        packet["requirements"][0]["team_state"] = "PASS"
        packet["requirements"][0]["team_evidence_ids"] = ["team-experience"]
        packet["requirements"][0]["category"] = "EXPERIENCE"
        receipt = self.compile(packet)
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertIn("PACKAGE_GATE_SET_MISMATCH", receipt["completeness"]["reasons"])

    def test_controlling_source_digest_mismatch_holds(self):
        manifest = copy.deepcopy(TRUSTED_COMPLETENESS)
        manifest["controlling_source_sha256"] = "f" * 64
        receipt = self.compile(trust=(manifest, digest(manifest)))
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertIn("COMPLETENESS_CONTROLLING_SOURCE_MISMATCH", receipt["reasons"])

    def test_incomplete_extraction_holds(self):
        manifest = copy.deepcopy(TRUSTED_COMPLETENESS)
        manifest["complete"] = False
        receipt = self.compile(trust=(manifest, digest(manifest)))
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertIn("PACKAGE_EXTRACTION_INCOMPLETE", receipt["reasons"])

    def test_manifest_gate_digest_tamper_rejected(self):
        manifest = copy.deepcopy(TRUSTED_COMPLETENESS)
        manifest["gates"][0]["route"] = "TEAM"
        with self.assertRaises(QualificationError):
            self.compile(trust=(manifest, TRUSTED_COMPLETENESS_SHA256))

    def test_manifest_future_extraction_rejected(self):
        manifest = copy.deepcopy(TRUSTED_COMPLETENESS)
        manifest["extracted_at"] = "2026-09-14T09:30:00Z"
        with self.assertRaises(QualificationError):
            self.compile(trust=(manifest, digest(manifest)))

    def test_manifest_gate_count_bool_rejected(self):
        manifest = copy.deepcopy(TRUSTED_COMPLETENESS)
        manifest["gate_count"] = True
        with self.assertRaises(QualificationError):
            self.compile(trust=(manifest, digest(manifest)))

    def test_trust_root_shape_rejected(self):
        with self.assertRaises(QualificationError):
            self.compile(trust=(TRUSTED_COMPLETENESS, "ABC"))

    def test_gate_derived_no_bid_without_completeness_holds(self):
        packet = copy.deepcopy(PACKET)
        packet["requirements"][1]["prime_state"] = "FAIL"
        packet["requirements"][1]["prime_evidence_ids"] = ["prime-registration"]
        receipt = compile_qualification(copy.deepcopy(packet), trusted_as_of=AS_OF)
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertIn("PACKAGE_COMPLETENESS_NOT_PROVIDED", receipt["reasons"])

    def test_official_expired_deadline_can_stand_without_completeness(self):
        packet = copy.deepcopy(PACKET)
        packet["opportunity"]["proposal_deadline"] = "2026-09-12T17:00:00Z"
        receipt = compile_qualification(copy.deepcopy(packet), trusted_as_of=AS_OF)
        self.assertEqual(receipt["disposition"], NO_BID)
        self.assertEqual(receipt["reasons"], ["PROPOSAL_DEADLINE_EXPIRED"])

    def test_receipt_can_be_reverified_against_trust_inputs(self):
        receipt = self.compile()
        self.assertTrue(
            verify_receipt_against_inputs(
                receipt,
                copy.deepcopy(PACKET),
                trusted_as_of=AS_OF,
                trusted_completeness=copy.deepcopy(TRUSTED_COMPLETENESS),
                trusted_completeness_sha256=TRUSTED_COMPLETENESS_SHA256,
            )
        )
        self.assertFalse(
            verify_receipt_against_inputs(
                receipt,
                copy.deepcopy(PACKET),
                trusted_as_of=AS_OF,
                trusted_completeness=copy.deepcopy(TRUSTED_COMPLETENESS),
                trusted_completeness_sha256="f" * 64,
            )
        )


if __name__ == "__main__":
    unittest.main()
