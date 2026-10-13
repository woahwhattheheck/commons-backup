import copy
import json
import tempfile
import unittest
from pathlib import Path

from reconcile import LedgerError, main, reconcile, verify_receipt

H = "a" * 64


def _project(project_id: str, partner_id: str):
    metric_id = f"{project_id}-served"
    obs_id = f"{project_id}-obs-1"
    return {
        "project_id": project_id,
        "partner_id": partner_id,
        "milestones": [{"milestone_id": f"{project_id}-close", "status": "complete", "evidence_sha256": H}],
        "metric_definitions": [{
            "metric_id": metric_id,
            "revision": 1,
            "unit": "count",
            "scale": 1,
            "effective_from": "2026-01-01",
            "effective_to": "2026-12-31",
            "donor_safe": True,
            "causal_claim": False,
        }],
        "outcome_observations": [{
            "event_id": obs_id,
            "metric_id": metric_id,
            "definition_revision": 1,
            "period_start": "2026-01-01",
            "period_end": "2026-06-30",
            "observed_at": "2026-07-05",
            "value_scaled": 10,
            "evidence_sha256": H,
            "corrects_event_id": None,
        }],
        "attestations": [{
            "event_id": f"{project_id}-att-1",
            "subject_event_id": obs_id,
            "partner_id": partner_id,
            "status": "confirmed",
            "observed_at": "2026-07-06",
            "evidence_sha256": H,
        }],
        "corrections": [],
    }


def synthetic_payload():
    # 14 synthetic partner awards / 17 synthetic projects.
    # Award distribution mirrors the public FY2026 portfolio arithmetic:
    # 3 x $30k, 1 x $10k, 10 x $15k = $250k.
    awards_spec = [30_000_00, 30_000_00, 30_000_00, 10_000_00] + [15_000_00] * 10
    projects = []
    awards = []
    project_counter = 1
    restricted_ids = []
    for i, cents in enumerate(awards_spec, start=1):
        partner_id = f"SYNTH-PARTNER-{i:02d}"
        project_count = 2 if i <= 3 else 1
        splits = [cents // project_count] * project_count
        splits[-1] += cents - sum(splits)
        allocations = []
        for split in splits:
            project_id = f"SYNTH-PROJECT-{project_counter:02d}"
            projects.append(_project(project_id, partner_id))
            fund_id = "restricted-youth" if project_counter in {1, 2, 3, 4} else "general"
            if fund_id == "restricted-youth":
                restricted_ids.append(project_id)
            allocations.append({
                "allocation_id": f"alloc-{project_counter:02d}",
                "project_id": project_id,
                "fund_id": fund_id,
                "amount_cents": split,
            })
            project_counter += 1
        awards.append({
            "award_id": f"SYNTH-AWARD-{i:02d}",
            "partner_id": partner_id,
            "award_cents": cents,
            "project_allocations": allocations,
            "disbursements": [{
                "event_id": f"disb-{i:02d}",
                "amount_cents": cents,
                "status": "paid",
                "evidence_sha256": H,
            }],
        })
    restricted_total = sum(
        alloc["amount_cents"]
        for award in awards
        for alloc in award["project_allocations"]
        if alloc["fund_id"] == "restricted-youth"
    )
    return {
        "schema_version": 1,
        "portfolio_id": "uwa-fy2026-united-fund-synthetic",
        "expected_portfolio_award_cents": 25_000_000,
        "require_full_disbursement": True,
        "funds": [
            {
                "fund_id": "general",
                "authorized_cents": 25_000_000 - restricted_total,
                "restriction": {"kind": "unrestricted"},
            },
            {
                "fund_id": "restricted-youth",
                "authorized_cents": restricted_total,
                "restriction": {"kind": "project_ids", "allowed_project_ids": restricted_ids},
            },
        ],
        "awards": awards,
        "projects": projects,
    }


class ReconcileTests(unittest.TestCase):
    def test_public_portfolio_shape_passes(self):
        out = reconcile(synthetic_payload())
        self.assertEqual(out["summary"]["status"], "PASS")
        self.assertEqual(out["summary"]["award_count"], 14)
        self.assertEqual(out["summary"]["project_count"], 17)
        self.assertEqual(out["summary"]["portfolio_award_cents"], 25_000_000)
        self.assertEqual(out["summary"]["paid_disbursement_cents"], 25_000_000)
        self.assertEqual(out["summary"]["publishable_outcome_count"], 17)
        self.assertTrue(verify_receipt(out))

    def test_order_invariant_receipt(self):
        a = synthetic_payload()
        b = copy.deepcopy(a)
        b["funds"].reverse()
        b["awards"].reverse()
        b["projects"].reverse()
        for award in b["awards"]:
            award["project_allocations"].reverse()
        self.assertEqual(reconcile(a), reconcile(b))

    def test_portfolio_total_mismatch_holds(self):
        p = synthetic_payload()
        p["expected_portfolio_award_cents"] += 1
        out = reconcile(p)
        self.assertIn("PORTFOLIO_AWARD_TOTAL_MISMATCH", out["summary"]["holds"])

    def test_restriction_violation_holds(self):
        p = synthetic_payload()
        p["awards"][-1]["project_allocations"][0]["fund_id"] = "restricted-youth"
        out = reconcile(p)
        self.assertIn("FUND_RESTRICTION_VIOLATION", out["summary"]["holds"])

    def test_award_allocation_mismatch_holds(self):
        p = synthetic_payload()
        p["awards"][0]["project_allocations"][0]["amount_cents"] -= 1
        out = reconcile(p)
        self.assertIn("AWARD_ALLOCATION_MISMATCH", out["summary"]["holds"])

    def test_overdisbursement_holds(self):
        p = synthetic_payload()
        p["awards"][0]["disbursements"][0]["amount_cents"] += 1
        out = reconcile(p)
        self.assertIn("DISBURSEMENT_EXCEEDS_AWARD", out["summary"]["holds"])

    def test_fully_paid_award_with_pending_commitment_holds(self):
        p = synthetic_payload()
        award = p["awards"][0]
        award["disbursements"].append({
            "event_id": "pending-over-fully-paid",
            "amount_cents": 1,
            "status": "pending",
            "evidence_sha256": H,
        })
        out = reconcile(p)
        result_award = next(a for a in out["awards"] if a["award_id"] == award["award_id"])
        self.assertIn("COMMITTED_DISBURSEMENT_EXCEEDS_AWARD", result_award["holds"])
        self.assertNotIn("DISBURSEMENT_EXCEEDS_AWARD", result_award["holds"])
        self.assertEqual(result_award["status"], "HOLD")
        self.assertEqual(out["summary"]["status"], "HOLD")

    def test_partial_paid_plus_pending_over_award_holds(self):
        p = synthetic_payload()
        award = p["awards"][0]
        award["disbursements"][0]["amount_cents"] = award["award_cents"] - 1
        award["disbursements"].append({
            "event_id": "pending-over-partial-paid",
            "amount_cents": 2,
            "status": "pending",
            "evidence_sha256": H,
        })
        out = reconcile(p)
        result_award = next(a for a in out["awards"] if a["award_id"] == award["award_id"])
        self.assertIn("COMMITTED_DISBURSEMENT_EXCEEDS_AWARD", result_award["holds"])
        self.assertIn("AWARD_NOT_FULLY_DISBURSED", result_award["holds"])
        self.assertNotIn("DISBURSEMENT_EXCEEDS_AWARD", result_award["holds"])

    def test_paid_plus_pending_exact_award_boundary_passes(self):
        p = synthetic_payload()
        p["require_full_disbursement"] = False
        award = p["awards"][0]
        award["disbursements"][0]["amount_cents"] = award["award_cents"] - 1
        award["disbursements"].append({
            "event_id": "pending-exact-boundary",
            "amount_cents": 1,
            "status": "pending",
            "evidence_sha256": H,
        })
        out = reconcile(p)
        result_award = next(a for a in out["awards"] if a["award_id"] == award["award_id"])
        self.assertNotIn("COMMITTED_DISBURSEMENT_EXCEEDS_AWARD", result_award["holds"])
        self.assertEqual(result_award["status"], "PASS")
        self.assertEqual(out["summary"]["status"], "PASS")

    def test_full_disbursement_shortfall_holds(self):
        p = synthetic_payload()
        p["awards"][0]["disbursements"][0]["amount_cents"] -= 1
        out = reconcile(p)
        self.assertIn("AWARD_NOT_FULLY_DISBURSED", out["summary"]["holds"])

    def test_pending_milestone_holds(self):
        p = synthetic_payload()
        p["projects"][0]["milestones"][0]["status"] = "pending"
        out = reconcile(p)
        self.assertIn("MILESTONE_PENDING", out["summary"]["holds"])

    def test_stale_definition_holds_and_excludes_outcome(self):
        p = synthetic_payload()
        p["projects"][0]["metric_definitions"][0]["effective_to"] = "2026-05-31"
        out = reconcile(p)
        project = next(x for x in out["projects"] if x["project_id"] == "SYNTH-PROJECT-01")
        self.assertIn("STALE_OR_INAPPLICABLE_METRIC_DEFINITION", project["holds"])
        self.assertEqual(project["publishable_outcomes"], [])

    def test_unknown_definition_fails_closed(self):
        p = synthetic_payload()
        p["projects"][0]["outcome_observations"][0]["definition_revision"] = 99
        with self.assertRaisesRegex(LedgerError, "unknown metric definition"):
            reconcile(p)

    def test_overlapping_definition_windows_fail_closed(self):
        p = synthetic_payload()
        d = copy.deepcopy(p["projects"][0]["metric_definitions"][0])
        d["revision"] = 2
        d["effective_from"] = "2026-06-01"
        d["effective_to"] = "2026-12-31"
        p["projects"][0]["metric_definitions"].append(d)
        with self.assertRaisesRegex(LedgerError, "overlapping effective windows"):
            reconcile(p)

    def test_missing_attestation_holds(self):
        p = synthetic_payload()
        p["projects"][0]["attestations"] = []
        out = reconcile(p)
        self.assertIn("OUTCOME_ATTESTATION_MISSING", out["summary"]["holds"])

    def test_withdrawn_latest_attestation_holds(self):
        p = synthetic_payload()
        project = p["projects"][0]
        project["attestations"].append({
            "event_id": "att-withdraw",
            "subject_event_id": project["outcome_observations"][0]["event_id"],
            "partner_id": project["partner_id"],
            "status": "withdrawn",
            "observed_at": "2026-07-07",
            "evidence_sha256": H,
        })
        out = reconcile(p)
        self.assertIn("OUTCOME_ATTESTATION_WITHDRAWN", out["summary"]["holds"])

    def test_conflicting_latest_attestation_states_fail_closed(self):
        p = synthetic_payload()
        project = p["projects"][0]
        project["attestations"].extend([
            {"event_id": "att-a", "subject_event_id": project["outcome_observations"][0]["event_id"], "partner_id": project["partner_id"], "status": "confirmed", "observed_at": "2026-07-07", "evidence_sha256": H},
            {"event_id": "att-b", "subject_event_id": project["outcome_observations"][0]["event_id"], "partner_id": project["partner_id"], "status": "withdrawn", "observed_at": "2026-07-07", "evidence_sha256": H},
        ])
        with self.assertRaisesRegex(LedgerError, "conflicting latest attestation states"):
            reconcile(p)

    def test_correction_lineage_passes_when_old_withdrawn(self):
        p = synthetic_payload()
        project = p["projects"][0]
        old = project["outcome_observations"][0]
        old_id = old["event_id"]
        project["corrections"].append({"event_id": "corr-1", "target_event_id": old_id, "action": "withdraw", "observed_at": "2026-07-07", "evidence_sha256": H})
        new = copy.deepcopy(old)
        new["event_id"] = "obs-corrected"
        new["corrects_event_id"] = old_id
        new["observed_at"] = "2026-07-08"
        new["value_scaled"] = 11
        project["outcome_observations"].append(new)
        project["attestations"].append({"event_id": "att-corrected", "subject_event_id": "obs-corrected", "partner_id": project["partner_id"], "status": "confirmed", "observed_at": "2026-07-09", "evidence_sha256": H})
        out = reconcile(p)
        result_project = next(x for x in out["projects"] if x["project_id"] == project["project_id"])
        ids = [x["event_id"] for x in result_project["publishable_outcomes"]]
        self.assertIn("obs-corrected", ids)
        self.assertNotIn(old_id, ids)
        self.assertNotIn("CORRECTION_WITHOUT_WITHDRAWAL", result_project["holds"])

    def test_correction_without_withdrawal_holds(self):
        p = synthetic_payload()
        project = p["projects"][0]
        old = project["outcome_observations"][0]
        new = copy.deepcopy(old)
        new["event_id"] = "obs-corrected"
        new["corrects_event_id"] = old["event_id"]
        new["observed_at"] = "2026-07-08"
        project["outcome_observations"].append(new)
        project["attestations"].append({"event_id": "att-corrected", "subject_event_id": "obs-corrected", "partner_id": project["partner_id"], "status": "confirmed", "observed_at": "2026-07-09", "evidence_sha256": H})
        out = reconcile(p)
        self.assertIn("CORRECTION_WITHOUT_WITHDRAWAL", out["summary"]["holds"])

    def test_unknown_correction_target_fails_closed(self):
        p = synthetic_payload()
        project = p["projects"][0]
        project["corrections"].append({"event_id": "corr-1", "target_event_id": "missing", "action": "withdraw", "observed_at": "2026-07-07", "evidence_sha256": H})
        with self.assertRaisesRegex(LedgerError, "unknown target_event_id"):
            reconcile(p)

    def test_pii_key_rejected_before_processing(self):
        p = synthetic_payload()
        p["projects"][0]["beneficiary_email"] = "person@example.com"
        with self.assertRaisesRegex(LedgerError, "PII field is forbidden"):
            reconcile(p)

    def test_duplicate_event_id_across_projects_fails_closed(self):
        p = synthetic_payload()
        p["projects"][1]["outcome_observations"][0]["event_id"] = p["projects"][0]["outcome_observations"][0]["event_id"]
        with self.assertRaisesRegex(LedgerError, "duplicate event_id"):
            reconcile(p)

    def test_causal_claim_definition_holds(self):
        p = synthetic_payload()
        p["projects"][0]["metric_definitions"][0]["causal_claim"] = True
        out = reconcile(p)
        self.assertIn("CAUSAL_IMPACT_CLAIM_NOT_ALLOWED", out["summary"]["holds"])

    def test_non_donor_safe_definition_holds(self):
        p = synthetic_payload()
        p["projects"][0]["metric_definitions"][0]["donor_safe"] = False
        out = reconcile(p)
        self.assertIn("OUTCOME_NOT_DONOR_SAFE", out["summary"]["holds"])

    def test_observed_before_period_end_fails_closed(self):
        p = synthetic_payload()
        p["projects"][0]["outcome_observations"][0]["observed_at"] = "2026-06-01"
        with self.assertRaisesRegex(LedgerError, "observed_at precedes period_end"):
            reconcile(p)

    def test_receipt_tamper_detection(self):
        out = reconcile(synthetic_payload())
        tampered = copy.deepcopy(out)
        tampered["summary"]["portfolio_award_cents"] += 1
        self.assertFalse(verify_receipt(tampered))

    def test_cli_require_pass_and_verify(self):
        p = synthetic_payload()
        p["projects"][0]["milestones"][0]["status"] = "pending"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "in.json"
            out = root / "out.json"
            inp.write_text(json.dumps(p), encoding="utf-8")
            self.assertEqual(main([str(inp), "--output", str(out), "--require-pass"]), 3)
            self.assertTrue(out.exists())
            self.assertEqual(main(["--verify", str(out)]), 0)


if __name__ == "__main__":
    unittest.main()
