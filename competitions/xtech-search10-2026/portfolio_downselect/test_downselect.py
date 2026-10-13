from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from downselect import (
    MAX_FILE_BYTES,
    ContractError,
    compile_portfolio,
    parse_json_strict,
    read_regular_json,
)


SHA_A = "1" * 40
SHA_B = "2" * 40


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def claim(name: str, state: str = "EVIDENCED") -> dict:
    return {
        "claimId": name,
        "text": f"Evidence statement for {name}.",
        "state": state,
        "evidenceRef": None,
    }


def candidate(
    cid: str,
    sha: str,
    *,
    evidence: bool = True,
    traction: bool = True,
    overlap: str = "NONE",
    usamrdc: bool = False,
) -> dict:
    state = "EVIDENCED" if evidence else "PROPOSED"
    return {
        "candidateId": cid,
        "source": {
            "repo": "woahwhattheheck/example",
            "commit": sha,
            "path": f"products/{cid}",
        },
        "priorityArea": "ADAPTIVE_SUSTAINMENT",
        "sourceCurrentness": {"state": "CURRENT", "evidenceRef": None},
        "usamrdcExclusive": {
            "state": "EXCLUSIVE" if usamrdc else "NOT_EXCLUSIVE",
            "evidenceRef": None,
        },
        "federalSupportOverlap": {"state": overlap, "evidenceRef": None},
        "criteria": {
            "introduction": [claim(f"{cid}.intro", state)],
            "armyBenefits": [claim(f"{cid}.army", state)],
            "technicalApproach": [claim(f"{cid}.technical", state)],
            "commercialPotential": [claim(f"{cid}.commercial", state)],
            "proposalQuality": [claim(f"{cid}.quality", state)],
        },
        "demonstratedMetrics": [claim(f"{cid}.metric", state)],
        "transitionPath": [claim(f"{cid}.transition", state)],
        "traction": (
            [{"evidenceId": f"{cid}.contract", "kind": "CUSTOMER_CONTRACT", "evidenceRef": None}]
            if traction
            else []
        ),
    }


def gate(state: str = "CONFIRMED_TRUE") -> dict:
    return {"state": state, "evidenceRef": None}


GLOBAL_CLASSES = {
    "forProfitIndependentUsSmallBusiness": "OWNER",
    "ownershipControlEligible": "OWNER",
    "employeeCeilingMet": "OWNER",
    "sbirSmallBusinessRequirementsMet": "OWNER",
    "federalSupportCensus": "OWNER",
    "oneSubmissionSlot": "PROVIDER",
    "officialTemplate": "PROVIDER",
}


def bind_evidence(packet: dict) -> dict:
    """Build deterministic retained evidence records for the packet's declared states."""
    packet = copy.deepcopy(packet)
    records: list[dict] = []

    for name, row in packet["globalGates"].items():
        if row["state"] == "UNKNOWN":
            row["evidenceRef"] = None
            continue
        evidence_id = f"ev:global:{name}"
        row["evidenceRef"] = evidence_id
        records.append(
            {
                "evidenceId": evidence_id,
                "binding": f"global:{name}",
                "sourceClass": GLOBAL_CLASSES[name],
                "repo": None,
                "commit": None,
                "path": None,
                "locator": f"fixture:{name}",
                "sha256": digest("global:" + name + ":" + row["state"]),
            }
        )

    for cand in packet["candidates"]:
        source = cand["source"]
        for gate_name in (
            "sourceCurrentness",
            "usamrdcExclusive",
            "federalSupportOverlap",
        ):
            row = cand[gate_name]
            if row["state"] == "UNKNOWN":
                row["evidenceRef"] = None
                continue
            evidence_id = f"ev:{cand['candidateId']}:gate:{gate_name}"
            row["evidenceRef"] = evidence_id
            records.append(
                {
                    "evidenceId": evidence_id,
                    "binding": f"candidate:{cand['candidateId']}:{gate_name}",
                    "sourceClass": "OWNER",
                    "repo": None,
                    "commit": None,
                    "path": None,
                    "locator": f"fixture:gate:{cand['candidateId']}:{gate_name}",
                    "sha256": digest(
                        f"gate:{cand['candidateId']}:{gate_name}:{row['state']}"
                    ),
                }
            )
        claim_groups = list(cand["criteria"].values()) + [
            cand["demonstratedMetrics"],
            cand["transitionPath"],
        ]
        for claims in claim_groups:
            for row in claims:
                if row["state"] != "EVIDENCED":
                    row["evidenceRef"] = None
                    continue
                evidence_id = f"ev:{cand['candidateId']}:claim:{row['claimId']}"
                row["evidenceRef"] = evidence_id
                records.append(
                    {
                        "evidenceId": evidence_id,
                        "binding": f"candidate:{cand['candidateId']}:claim:{row['claimId']}",
                        "sourceClass": "REPO",
                        "repo": source["repo"],
                        "commit": source["commit"],
                        "path": source["path"],
                        "locator": None,
                        "sha256": None,
                    }
                )
        for row in cand["traction"]:
            if row["kind"] in {
                "CUSTOMER_PAYMENT",
                "CUSTOMER_CONTRACT",
                "CUSTOMER_PILOT",
                "CUSTOMER_DEPLOYMENT",
                "CUSTOMER_LOI",
                "EXTERNAL_ADOPTION",
            }:
                evidence_id = f"ev:{cand['candidateId']}:traction:{row['evidenceId']}"
                row["evidenceRef"] = evidence_id
                records.append(
                    {
                        "evidenceId": evidence_id,
                        "binding": f"candidate:{cand['candidateId']}:traction:{row['evidenceId']}",
                        "sourceClass": "EXTERNAL_COUNTERPARTY",
                        "repo": None,
                        "commit": None,
                        "path": None,
                        "locator": f"fixture:traction:{cand['candidateId']}:{row['evidenceId']}",
                        "sha256": digest(
                            f"traction:{cand['candidateId']}:{row['evidenceId']}"
                        ),
                    }
                )
            else:
                row["evidenceRef"] = None

    packet["evidenceRecords"] = sorted(records, key=lambda row: row["evidenceId"])
    return packet


def ready_packet() -> dict:
    return {
        "version": "xtech.search10.portfolio/v1",
        "entityId": "owner-entity",
        "globalGates": {
            "forProfitIndependentUsSmallBusiness": gate(),
            "ownershipControlEligible": gate(),
            "employeeCeilingMet": gate(),
            "sbirSmallBusinessRequirementsMet": gate(),
            "federalSupportCensus": {"state": "CLEAR", "evidenceRef": None},
            "oneSubmissionSlot": {"state": "AVAILABLE", "evidenceRef": None},
            "officialTemplate": {"state": "BOUND", "evidenceRef": None},
        },
        "evidenceRecords": [],
        "candidates": [
            candidate("alpha", SHA_A, evidence=True, traction=True),
            candidate("beta", SHA_B, evidence=False, traction=True),
        ],
    }


class DownselectTests(unittest.TestCase):
    def compile(self, packet: dict) -> dict:
        return compile_portfolio(bind_evidence(packet))

    def test_unique_fully_gated_leader_is_internal_selected_only(self) -> None:
        report = self.compile(ready_packet())
        self.assertEqual(report["state"], "SELECTED")
        self.assertEqual(report["selectedCandidateId"], "alpha")
        self.assertFalse(report["authority"]["submissionAuthorized"])
        self.assertFalse(report["authority"]["entitySlotConsumed"])

    def test_unknown_entity_facts_force_hold(self) -> None:
        packet = ready_packet()
        packet["globalGates"]["ownershipControlEligible"] = gate("UNKNOWN")
        report = self.compile(packet)
        self.assertEqual(report["state"], "HOLD")
        self.assertEqual(report["holdReason"], "GLOBAL_GATES")
        self.assertIsNone(report["selectedCandidateId"])

    def test_missing_template_forces_hold(self) -> None:
        packet = ready_packet()
        packet["globalGates"]["officialTemplate"] = {"state": "UNKNOWN", "evidenceRef": None}
        report = self.compile(packet)
        self.assertEqual(report["state"], "HOLD")
        self.assertTrue(any("officialTemplate" in row for row in report["globalBlockers"]))

    def test_consumed_entity_slot_forces_hold(self) -> None:
        packet = ready_packet()
        packet["globalGates"]["oneSubmissionSlot"] = {
            "state": "CONSUMED_OR_RESERVED",
            "evidenceRef": None,
        }
        self.assertEqual(self.compile(packet)["state"], "HOLD")

    def test_support_census_blocked_forces_hold(self) -> None:
        packet = ready_packet()
        packet["globalGates"]["federalSupportCensus"] = {
            "state": "BLOCKED",
            "evidenceRef": None,
        }
        self.assertEqual(self.compile(packet)["state"], "HOLD")

    def test_stale_source_generation_is_hard_blocker(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["sourceCurrentness"] = {
            "state": "STALE",
            "evidenceRef": None,
        }
        report = self.compile(packet)
        alpha = next(row for row in report["projections"] if row["candidateId"] == "alpha")
        self.assertIn("source_generation:STALE", alpha["hardBlockers"])
        self.assertEqual(report["state"], "HOLD")

    def test_unknown_source_generation_is_hard_blocker(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["sourceCurrentness"] = {
            "state": "UNKNOWN",
            "evidenceRef": None,
        }
        report = self.compile(packet)
        alpha = next(row for row in report["projections"] if row["candidateId"] == "alpha")
        self.assertIn("source_generation:UNKNOWN", alpha["hardBlockers"])

    def test_unknown_candidate_support_overlap_is_hard_blocker(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["federalSupportOverlap"] = {
            "state": "UNKNOWN",
            "evidenceRef": None,
        }
        report = self.compile(packet)
        alpha = next(row for row in report["projections"] if row["candidateId"] == "alpha")
        self.assertIn("federal_support_overlap:UNKNOWN", alpha["hardBlockers"])

    def test_unknown_usamrdc_scope_is_hard_blocker(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["usamrdcExclusive"] = {
            "state": "UNKNOWN",
            "evidenceRef": None,
        }
        report = self.compile(packet)
        alpha = next(row for row in report["projections"] if row["candidateId"] == "alpha")
        self.assertIn("scope:USAMRDC_EXCLUSIVE:UNKNOWN", alpha["hardBlockers"])

    def test_candidate_support_overlap_is_hard_blocker(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["federalSupportOverlap"] = {
            "state": "POTENTIALLY_SAME",
            "evidenceRef": None,
        }
        report = self.compile(packet)
        alpha = next(row for row in report["projections"] if row["candidateId"] == "alpha")
        self.assertIn("federal_support_overlap:POTENTIALLY_SAME", alpha["hardBlockers"])

    def test_proposed_transition_path_blocks_selection(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["transitionPath"][0]["state"] = "PROPOSED"
        report = self.compile(packet)
        alpha = next(row for row in report["projections"] if row["candidateId"] == "alpha")
        self.assertIn("claim:alpha.transition:PROPOSED", alpha["hardBlockers"])
        self.assertEqual(report["state"], "HOLD")

    def test_owner_required_metric_blocks_selection(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["demonstratedMetrics"][0]["state"] = "OWNER_REQUIRED"
        report = self.compile(packet)
        alpha = next(row for row in report["projections"] if row["candidateId"] == "alpha")
        self.assertIn("claim:alpha.metric:OWNER_REQUIRED", alpha["hardBlockers"])

    def test_pilot_or_loi_alone_does_not_clear_strong_traction_gate(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["traction"] = [
            {"evidenceId": "alpha.pilot", "kind": "CUSTOMER_PILOT", "evidenceRef": None}
        ]
        report = self.compile(packet)
        alpha = next(row for row in report["projections"] if row["candidateId"] == "alpha")
        self.assertEqual(alpha["externalTractionEvidenceCount"], 1)
        self.assertEqual(alpha["strongCommercialTractionEvidenceCount"], 0)
        self.assertIn(
            "commercial_traction:missing_strong_external_evidence",
            alpha["hardBlockers"],
        )
        self.assertEqual(report["state"], "HOLD")

    def test_no_external_traction_is_hard_blocker(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["traction"] = []
        report = self.compile(packet)
        alpha = next(row for row in report["projections"] if row["candidateId"] == "alpha")
        self.assertIn("commercial_traction:missing_external_evidence", alpha["hardBlockers"])

    def test_repo_activity_cannot_become_traction(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["traction"] = [
            {"evidenceId": "stars", "kind": "GITHUB_STARS", "evidenceRef": None}
        ]
        report = self.compile(packet)
        alpha = next(row for row in report["projections"] if row["candidateId"] == "alpha")
        self.assertIn("fake_traction:stars:GITHUB_STARS", alpha["hardBlockers"])
        self.assertEqual(alpha["externalTractionEvidenceCount"], 0)

    def test_proposed_claim_is_diagnostic_but_blocks_selection(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["criteria"]["armyBenefits"][0]["state"] = "PROPOSED"
        report = self.compile(packet)
        alpha = next(row for row in report["projections"] if row["candidateId"] == "alpha")
        self.assertIn("claim:alpha.army:PROPOSED", alpha["hardBlockers"])
        self.assertEqual(report["state"], "HOLD")

    def test_forbidden_claim_is_hard_blocker(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["criteria"]["technicalApproach"][0]["state"] = "FORBIDDEN"
        report = self.compile(packet)
        alpha = next(row for row in report["projections"] if row["candidateId"] == "alpha")
        self.assertIn("claim:alpha.technical:FORBIDDEN", alpha["hardBlockers"])

    def test_usamrdc_exclusive_candidate_is_hard_blocked(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["usamrdcExclusive"] = {
            "state": "EXCLUSIVE",
            "evidenceRef": None,
        }
        report = self.compile(packet)
        alpha = next(row for row in report["projections"] if row["candidateId"] == "alpha")
        self.assertIn("scope:USAMRDC_EXCLUSIVE:EXCLUSIVE", alpha["hardBlockers"])

    def test_equal_readiness_tie_holds_without_arbitrary_winner(self) -> None:
        packet = ready_packet()
        packet["candidates"][1] = candidate("beta", SHA_B, evidence=True, traction=True)
        report = self.compile(packet)
        self.assertEqual(report["state"], "HOLD")
        self.assertEqual(report["holdReason"], "TOP_READINESS_TIE")
        self.assertIsNone(report["selectedCandidateId"])

    def test_nonrepo_evidence_source_transplant_changes_receipt(self) -> None:
        packet = bind_evidence(ready_packet())
        for row in packet["evidenceRecords"]:
            if row["binding"].startswith("candidate:alpha:claim:") and row["sourceClass"] == "REPO":
                row["sourceClass"] = "OWNER"
                row["repo"] = None
                row["commit"] = None
                row["path"] = None
                row["locator"] = "fixture:owner:" + row["evidenceId"]
                row["sha256"] = digest("owner:" + row["evidenceId"])

        first = compile_portfolio(copy.deepcopy(packet))
        packet["candidates"][0]["source"]["commit"] = "3" * 40
        second = compile_portfolio(copy.deepcopy(packet))

        self.assertEqual(
            first["retainedEvidenceManifestSha256"],
            second["retainedEvidenceManifestSha256"],
        )
        self.assertNotEqual(
            first["projections"][0]["sourceIdentity"],
            second["projections"][0]["sourceIdentity"],
        )
        self.assertNotEqual(first["receiptSha256"], second["receiptSha256"])

    def test_semantic_packet_changes_always_change_packet_and_report_receipts(self) -> None:
        packet = bind_evidence(ready_packet())
        first = compile_portfolio(copy.deepcopy(packet))

        packet["candidates"][0]["priorityArea"] = "C2_COUNTER_C2_NETWORKS"
        packet["candidates"][0]["criteria"]["introduction"][0]["text"] = (
            "A different retained introduction statement."
        )
        second = compile_portfolio(copy.deepcopy(packet))

        self.assertEqual(first["state"], second["state"])
        self.assertEqual(
            first["projections"][0]["readinessBasisPoints"],
            second["projections"][0]["readinessBasisPoints"],
        )
        self.assertNotEqual(first["inputPacketSha256"], second["inputPacketSha256"])
        self.assertNotEqual(first["receiptSha256"], second["receiptSha256"])

    def test_mutating_prior_report_cannot_mutate_scoring_policy(self) -> None:
        packet = bind_evidence(ready_packet())
        first = compile_portfolio(copy.deepcopy(packet))
        original_receipt = first["receiptSha256"]
        policy_digest = first["officialConstraintPolicySha256"]

        first["officialConstraintSnapshot"]["weights"]["technicalApproach"] = 0
        first["officialConstraintSnapshot"]["priorityAreas"].append("MUTATED")

        second = compile_portfolio(copy.deepcopy(packet))
        self.assertEqual(
            second["officialConstraintSnapshot"]["weights"]["technicalApproach"],
            40,
        )
        self.assertNotIn("MUTATED", second["officialConstraintSnapshot"]["priorityAreas"])
        self.assertEqual(second["officialConstraintPolicySha256"], policy_digest)
        self.assertEqual(second["receiptSha256"], original_receipt)

    def test_clone_style_repo_alias_is_rejected(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["source"]["repo"] = "woahwhattheheck/example.git"
        with self.assertRaisesRegex(ContractError, "INVALID_SOURCE_REPO"):
            self.compile(packet)

    def test_dot_segment_repo_identity_is_rejected(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["source"]["repo"] = "../example"
        with self.assertRaisesRegex(ContractError, "INVALID_SOURCE_REPO"):
            self.compile(packet)

    def test_candidate_alias_cannot_replay_same_source_generation(self) -> None:
        packet = ready_packet()
        packet["candidates"][1]["source"] = copy.deepcopy(packet["candidates"][0]["source"])
        packet["candidates"][1]["source"]["repo"] = "WOAHWHATTHEHECK/EXAMPLE"
        with self.assertRaisesRegex(ContractError, "CANDIDATE_SOURCE_REPLAY"):
            self.compile(packet)

    def test_external_traction_artifact_cannot_be_replayed_across_candidates(self) -> None:
        packet = bind_evidence(ready_packet())
        alpha = next(
            row
            for row in packet["evidenceRecords"]
            if row["binding"] == "candidate:alpha:traction:alpha.contract"
        )
        beta = next(
            row
            for row in packet["evidenceRecords"]
            if row["binding"] == "candidate:beta:traction:beta.contract"
        )
        self.assertNotEqual(beta["locator"], alpha["locator"])
        beta["sha256"] = alpha["sha256"]
        with self.assertRaisesRegex(ContractError, "EXTERNAL_EVIDENCE_CANDIDATE_REPLAY"):
            compile_portfolio(packet)

    def test_duplicate_candidate_id_fails_before_evidence_use(self) -> None:
        packet = ready_packet()
        packet["candidates"][1]["candidateId"] = "alpha"
        with self.assertRaisesRegex(ContractError, "DUPLICATE_CANDIDATE_ID"):
            self.compile(packet)

    def test_duplicate_claim_id_across_criteria_is_rejected(self) -> None:
        packet = bind_evidence(ready_packet())
        packet["candidates"][0]["criteria"]["armyBenefits"][0]["claimId"] = "alpha.intro"
        with self.assertRaisesRegex(ContractError, "DUPLICATE_CLAIM_ID"):
            compile_portfolio(packet)

    def test_invalid_source_generation_fails_closed(self) -> None:
        packet = bind_evidence(ready_packet())
        packet["candidates"][0]["source"]["commit"] = "main"
        with self.assertRaisesRegex(ContractError, "INVALID_SOURCE_COMMIT"):
            compile_portfolio(packet)

    def test_repo_evidence_generation_transplant_is_rejected(self) -> None:
        packet = bind_evidence(ready_packet())
        target = next(
            row
            for row in packet["evidenceRecords"]
            if row["binding"] == "candidate:alpha:claim:alpha.intro"
        )
        target["commit"] = SHA_B
        with self.assertRaisesRegex(ContractError, "EVIDENCE_CANDIDATE_GENERATION_MISMATCH"):
            compile_portfolio(packet)

    def test_repo_path_dot_segment_alias_is_rejected(self) -> None:
        packet = ready_packet()
        packet["candidates"][0]["source"]["path"] = "products/alpha/../beta"
        with self.assertRaisesRegex(ContractError, "INVALID_REPO_PATH"):
            self.compile(packet)

    def test_evidence_path_dot_segment_alias_is_rejected(self) -> None:
        packet = bind_evidence(ready_packet())
        target = next(
            row
            for row in packet["evidenceRecords"]
            if row["binding"] == "candidate:alpha:claim:alpha.intro"
        )
        target["path"] = "products/alpha/../beta"
        with self.assertRaisesRegex(ContractError, "INVALID_REPO_PATH"):
            compile_portfolio(packet)

    def test_repo_evidence_path_transplant_is_rejected(self) -> None:
        packet = bind_evidence(ready_packet())
        target = next(
            row
            for row in packet["evidenceRecords"]
            if row["binding"] == "candidate:alpha:claim:alpha.intro"
        )
        target["path"] = "products/beta"
        with self.assertRaisesRegex(ContractError, "EVIDENCE_CANDIDATE_PATH_MISMATCH"):
            compile_portfolio(packet)

    def test_claim_binding_transplant_is_rejected(self) -> None:
        packet = bind_evidence(ready_packet())
        target = next(
            row
            for row in packet["evidenceRecords"]
            if row["binding"] == "candidate:alpha:claim:alpha.intro"
        )
        target["binding"] = "candidate:alpha:claim:alpha.army"
        with self.assertRaisesRegex(ContractError, "EVIDENCE_BINDING_MISMATCH"):
            compile_portfolio(packet)

    def test_one_evidence_record_cannot_satisfy_two_claims(self) -> None:
        packet = bind_evidence(ready_packet())
        intro_ref = packet["candidates"][0]["criteria"]["introduction"][0]["evidenceRef"]
        packet["candidates"][0]["criteria"]["armyBenefits"][0]["evidenceRef"] = intro_ref
        with self.assertRaisesRegex(ContractError, "EVIDENCE_RECORD_REUSED"):
            compile_portfolio(packet)

    def test_external_traction_requires_external_counterparty_class(self) -> None:
        packet = bind_evidence(ready_packet())
        target = next(
            row
            for row in packet["evidenceRecords"]
            if row["binding"] == "candidate:alpha:traction:alpha.contract"
        )
        target["sourceClass"] = "OWNER"
        with self.assertRaisesRegex(ContractError, "EVIDENCE_CLASS_MISMATCH"):
            compile_portfolio(packet)

    def test_template_requires_provider_class(self) -> None:
        packet = bind_evidence(ready_packet())
        target = next(
            row
            for row in packet["evidenceRecords"]
            if row["binding"] == "global:officialTemplate"
        )
        target["sourceClass"] = "OWNER"
        with self.assertRaisesRegex(ContractError, "EVIDENCE_CLASS_MISMATCH"):
            compile_portfolio(packet)

    def test_unused_evidence_record_fails_closed(self) -> None:
        packet = bind_evidence(ready_packet())
        packet["evidenceRecords"].append(
            {
                "evidenceId": "ev:unused",
                "binding": "unused:test",
                "sourceClass": "OWNER",
                "repo": None,
                "commit": None,
                "path": None,
                "locator": "fixture:unused",
                "sha256": digest("unused"),
            }
        )
        with self.assertRaisesRegex(ContractError, "UNUSED_EVIDENCE_RECORD"):
            compile_portfolio(packet)

    def test_artifact_evidence_requires_real_sha256_shape(self) -> None:
        packet = bind_evidence(ready_packet())
        target = next(
            row for row in packet["evidenceRecords"] if row["sourceClass"] != "REPO"
        )
        target["sha256"] = "not-a-digest"
        with self.assertRaisesRegex(ContractError, "INVALID_EVIDENCE_SHA256"):
            compile_portfolio(packet)

    def test_repo_evidence_cannot_smuggle_artifact_digest_variant(self) -> None:
        packet = bind_evidence(ready_packet())
        target = next(row for row in packet["evidenceRecords"] if row["sourceClass"] == "REPO")
        target["sha256"] = digest("wrong-variant")
        with self.assertRaisesRegex(ContractError, "REPO_EVIDENCE_VARIANT_MISMATCH"):
            compile_portfolio(packet)

    def test_single_candidate_packet_fails_closed(self) -> None:
        packet = ready_packet()
        packet["candidates"] = packet["candidates"][:1]
        with self.assertRaisesRegex(ContractError, "CANDIDATE_COUNT"):
            self.compile(packet)

    def test_extra_root_field_fails_closed(self) -> None:
        packet = ready_packet()
        packet["surprise"] = True
        with self.assertRaisesRegex(ContractError, "OBJECT_SHAPE"):
            self.compile(packet)

    def test_duplicate_json_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "JSON_DUPLICATE_KEY"):
            parse_json_strict('{"version":1,"version":2}')

    def test_float_is_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "JSON_FLOAT_FORBIDDEN"):
            parse_json_strict('{"score":1.5}')

    def test_receipt_and_evidence_manifest_are_deterministic(self) -> None:
        packet = bind_evidence(ready_packet())
        first = compile_portfolio(copy.deepcopy(packet))
        second = compile_portfolio(copy.deepcopy(packet))
        self.assertEqual(first["receiptSha256"], second["receiptSha256"])
        self.assertEqual(
            first["retainedEvidenceManifestSha256"],
            second["retainedEvidenceManifestSha256"],
        )
        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":")),
            json.dumps(second, sort_keys=True, separators=(",", ":")),
        )

    def test_readiness_metric_is_not_sponsor_score(self) -> None:
        report = self.compile(ready_packet())
        self.assertIn("not an Army score", report["readinessMetricMeaning"])
        self.assertNotIn("probability", report["projections"][0])

    def test_evidence_truth_boundary_is_explicit(self) -> None:
        report = self.compile(ready_packet())
        self.assertIn("does not independently authenticate", report["evidenceTrustBoundary"])
        self.assertFalse(report["authority"]["armyEligibilityDetermined"])

    def test_file_ingress_rejects_oversize_before_json_parse(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "packet.json"
            path.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
            with self.assertRaisesRegex(ContractError, "INPUT_TOO_LARGE"):
                read_regular_json(path)

    def test_file_ingress_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target.json"
            target.write_text("{}", encoding="utf-8")
            link = root / "link.json"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(ContractError, "INPUT_SYMLINK_FORBIDDEN"):
                read_regular_json(link)

    def test_file_ingress_rejects_invalid_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "packet.json"
            path.write_bytes(b"{\\xff}")
            with self.assertRaisesRegex(ContractError, "JSON_NOT_UTF8"):
                read_regular_json(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
