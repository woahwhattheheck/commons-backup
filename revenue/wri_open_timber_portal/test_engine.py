from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from revenue.wri_open_timber_portal import engine

UTC = timezone.utc
TEST_NOW = datetime(2026, 9, 14, 18, 0, 0, tzinfo=UTC)


def _packet() -> dict:
    _, binding = engine._load_repo_evidence_registry()
    baseline = deepcopy(binding["baseline"])
    return {
        "schema": engine.INPUT_SCHEMA,
        "opportunity": {
            "buyer_id": "wri",
            "opportunity_id": "open-timber-portal-frontend-developer-2026",
            "buyer_name": "World Resources Institute",
            "project_name": "Open Timber Portal",
            "target_role": "Front-End Developer (Ruby on Rails) for the Open Timber Portal Platform",
            "issued_date_hint": "2026-09-04",
            "proposal_due_date_hint": "2026-09-18",
            "vendor_decision_date_hint": "2026-09-21",
            "anticipated_start_date_hint": "2026-10-01",
            "deliverables_due_date_hint": "2027-03-31"
        },
        "sources": [
            {
                "source_id": "wri_procurement",
                "authority": "OFFICIAL_BUYER_PAGE",
                "url": "https://www.wri.org/about/procurement-opportunities",
                "access_state": "UNRETRIEVED_403",
                "observed_at": "2026-09-13T22:00:00Z",
                "fresh_until": "2026-09-18T23:59:59Z",
                "claims": [],
                "limitations": ["Buyer-controlled opportunity bytes not retained."]
            },
            {
                "source_id": "wri_fti_api",
                "authority": "BUYER_OWNED_PUBLIC_REPO",
                "url": "https://github.com/wri/fti_api",
                "access_state": "RETRIEVED",
                "observed_at": "2026-09-13T22:00:00Z",
                "fresh_until": "2026-09-18T23:59:59Z",
                "claims": ["rails_backend"],
                "limitations": ["Repository evidence is technical context, not procurement authority."]
            }
        ],
        "controlling_unknowns": [
            {"category": name, "blocking": True, "description": f"Unresolved {name}.", "resolution_evidence": None}
            for name in sorted(engine._BLOCKING_UNKNOWN_CATEGORIES)
        ],
        "technical_baseline": baseline,
        "workstreams": [
            {
                "workstream_id": f"ws-{index}",
                "bucket": bucket,
                "objective": f"Deliver {bucket}.",
                "activities": [f"Implement {bucket}."],
                "acceptance_evidence": [f"Evidence for {bucket}."],
                "assumptions": []
            }
            for index, bucket in enumerate(sorted(engine._REQUIRED_WORKSTREAMS), 1)
        ],
        "company_evidence": {
            "ruby_rails_delivery": "UNVERIFIED",
            "legal_vendor_eligibility": "UNKNOWN",
            "relevant_past_performance": "UNVERIFIED",
            "named_staffing": "UNKNOWN"
        },
        "commercial": {
            "currency": "USD",
            "amount_minor": None,
            "pricing_status": "OWNER_DECISION_REQUIRED",
            "pricing_basis": "No customer price is committed by this carrier.",
            "offer_status": "NOT_SUBMITTED",
            "assumptions": []
        }
    }


class WriSourceBoundEngineTests(unittest.TestCase):
    def test_registry_is_pinned_to_immutable_wri_git_evidence(self):
        root, binding = engine._load_repo_evidence_registry()
        self.assertEqual(root, engine.EVIDENCE_REGISTRY_SHA256)
        self.assertEqual(binding["commit_sha"], "dc9f33b1d54c6765af67187e4e055125ec952ade")
        blobs = {row["path"]: row["git_blob_sha"] for row in binding["files"]}
        self.assertEqual(blobs["README.md"], "d15e4fea003fae2904b9c08b72a60276cdc0aaf8")
        self.assertEqual(blobs[".ruby-version"], "7636e75650d437ffe0ab5f1e269cc6f5d3095546")

    def test_valid_baseline_is_source_bound_but_submission_stays_hold(self):
        report = engine._compile_at(_packet(), TEST_NOW)
        self.assertEqual(report["technical_readiness"], "TECHNICALLY_READY_SOURCE_BOUND")
        self.assertEqual(report["submission_readiness"], "HOLD_CONTROLLING_SOURCE")
        self.assertFalse(report["external_submission_authorized"])
        self.assertTrue(all(value is False for value in report["authority"].values()))
        self.assertEqual(report["repo_evidence"]["registry_sha256"], engine.EVIDENCE_REGISTRY_SHA256)

    def test_predecessor_killer_unchanged_sources_cannot_validate_contradictory_baseline(self):
        mutations = {
            "runtime": "Ruby 99",
            "database": "Oracle 31",
            "spatial_extension": "SpatialMagic 7",
            "queue": "RabbitMQ",
            "hosting": "unrelated serverless platform",
            "provisioning": "manual shell commands",
            "deployment": "scp directly to production",
            "test_command": "echo pass",
            "parallel_test_command": "true"
        }
        original = _packet()
        original_sources = deepcopy(original["sources"])
        for key, wrong in mutations.items():
            with self.subTest(key=key):
                candidate = deepcopy(original)
                candidate["technical_baseline"][key] = wrong
                self.assertEqual(candidate["sources"], original_sources)
                with self.assertRaisesRegex(engine.ContractError, "repo-pinned WRI evidence"):
                    engine.normalize(candidate)

    def test_caller_claims_cannot_redefine_pinned_baseline(self):
        candidate = _packet()
        candidate["sources"][1]["claims"] = ["rails_backend", "oracle", "rabbitmq"]
        normalized = engine.normalize(candidate)
        self.assertEqual(normalized["technical_baseline"]["database"], "PostgreSQL 18")
        self.assertEqual(normalized["technical_baseline"]["queue"], "Sidekiq with Redis")
        self.assertTrue(normalized["repo_evidence"]["commit_sha"].startswith("dc9f33b1"))

    def test_candidate_cannot_self_resolve_procurement_unknowns(self):
        candidate = _packet()
        candidate["controlling_unknowns"][0]["resolution_evidence"] = "trust me"
        with self.assertRaisesRegex(engine.ContractError, "cannot self-resolve"):
            engine.normalize(candidate)

    def test_public_compile_has_no_caller_clock(self):
        candidate = _packet()
        with self.assertRaises(TypeError):
            engine.compile_proposal(candidate, as_of=TEST_NOW)  # type: ignore[call-arg]

    def test_public_clock_ignores_module_datetime_rebinding(self):
        candidate = _packet()
        fake = datetime(2001, 1, 1, 0, 0, 0, tzinfo=UTC)
        real_datetime = datetime

        class FakeDatetime:
            @classmethod
            def now(cls, tz=None):
                return fake

            @classmethod
            def strptime(cls, text, fmt):
                return real_datetime.strptime(text, fmt)

        with patch.object(engine, "datetime", FakeDatetime):
            report = engine.compile_proposal(candidate)
        self.assertNotEqual(report["evaluated_at"], "2001-01-01T00:00:00Z")

    def test_verification_detects_exact_historical_report(self):
        candidate = _packet()
        report = engine._compile_at(candidate, TEST_NOW)
        with patch.object(engine, "_PROCESS_UTC_NOW", lambda: TEST_NOW):
            verification = engine.verify_report(candidate, report)
        self.assertEqual(verification["verdict"], "CURRENT_SOURCE_BOUND_TECHNICAL_CARRIER_VERIFIED")
        self.assertFalse(verification["external_submission_authorized"])


if __name__ == "__main__":
    unittest.main()
