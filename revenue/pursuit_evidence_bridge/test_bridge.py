from __future__ import annotations

import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from revenue.bidder_qualification_vault import (
    AUTHORITY_SCHEMA,
    QUERY_SCHEMA,
    REGISTRY_SCHEMA,
    canonical_sha256,
    compile_vault,
    roots,
)
from revenue.pursuit_evidence_bridge import bridge

UTC = timezone.utc
NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)


class BridgeTests(unittest.TestCase):
    def _vault_fixture(self, *, max_age_seconds: int = 3600):
        source_sha = "a" * 64
        authority = {
            "schema": AUTHORITY_SCHEMA,
            "authority_id": "corp-evidence",
            "generation": 1,
            "previous_authority_sha256": None,
            "issued_at": "2026-09-14T11:00:00Z",
            "evidence": [{
                "evidence_id": "entity-standing-1",
                "kind": "ENTITY_STANDING",
                "source_sha256": source_sha,
            }],
        }
        registry = {
            "schema": REGISTRY_SCHEMA,
            "registry_id": "corp-registry",
            "authority_id": "corp-evidence",
            "authority_generation": 1,
            "generated_at": "2026-09-14T11:59:30Z",
            "items": [{
                "evidence_id": "entity-standing-1",
                "kind": "ENTITY_STANDING",
                "source_sha256": source_sha,
                "observed_at": "2026-09-14T11:59:30Z",
                "max_age_seconds": max_age_seconds,
                "valid_through": "2026-09-30",
                "state": "EVIDENCED",
                "metadata": {"jurisdiction": "US-IN", "standing": "GOOD"},
            }],
        }
        query = {
            "schema": QUERY_SCHEMA,
            "query_id": "entity-current",
            "subject_id": "demo-pursuit",
            "authority_id": "corp-evidence",
            "authority_generation": 1,
            "registry_id": "corp-registry",
            "registry_max_age_seconds": max_age_seconds,
            "requirements": [{
                "requirement_id": "entity-standing",
                "kind": "ENTITY_STANDING",
                "min_count": 1,
                "exact": {"jurisdiction": "US-IN", "standing": "GOOD"},
            }],
        }
        authority_sha, registry_sha = roots(authority, registry)
        bundle = compile_vault(
            authority, registry, query,
            expected_authority_sha256=authority_sha,
            expected_registry_sha256=registry_sha,
            evaluated_at=NOW,
        )
        return authority, registry, query, bundle, authority_sha, registry_sha

    def _synthetic_binding(self, source, manifest, authority_sha, registry_sha, query):
        return bridge._normalize_binding({
            "binding_id": "synthetic-live",
            "opportunity_id": "DEMO-1",
            "source_ledger_path": "opportunities/demo/source.json",
            "source_ledger_sha256": bridge._digest(source),
            "submission_manifest_path": "opportunities/demo/manifest.json",
            "submission_manifest_sha256": bridge._digest(manifest),
            "deadline_utc": "2026-09-20T00:00:00Z",
            "vault_authority_sha256": authority_sha,
            "vault_registry_sha256": registry_sha,
            "vault_query_sha256": canonical_sha256(query),
            "static_holds": [],
        }, 0)

    def test_production_binding_matches_landed_jersey_bytes_and_holds(self):
        root = Path(__file__).resolve().parents[2]
        source = json.loads((root / "opportunities/jersey_connecting_health_cdr_openehr_dn827803/sources.json").read_text())
        manifest = json.loads((root / "opportunities/jersey_connecting_health_cdr_openehr_dn827803/fixtures/public_hold.json").read_text())
        with patch.object(bridge, "_process_now", return_value=NOW):
            result = bridge.compile_bridge("jersey-dn827803-main-v1", source, manifest, None)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("TENDER_PACK_NOT_ACQUIRED", result["reason_codes"])
        self.assertIn("CONTROLLING_TENDER_PACK_NOT_REVIEWED", result["reason_codes"])
        self.assertIn("VAULT_ROOTS_NOT_PINNED", result["reason_codes"])
        self.assertFalse(result["external_submission_authorized"])
        self.assertTrue(all(value is False for value in result["authority"].values()))

    def test_positive_path_integrates_real_vault_verification(self):
        source, manifest = {"source": "trusted"}, {"manifest": "trusted"}
        authority, registry, query, bundle, authority_sha, registry_sha = self._vault_fixture()
        binding = self._synthetic_binding(source, manifest, authority_sha, registry_sha, query)
        vault = {"authority": authority, "registry": registry, "query": query, "bundle": bundle}
        with patch.object(bridge, "_load_binding_registry", return_value=("f" * 64, {binding["binding_id"]: binding})), \
             patch.object(bridge, "_process_now", return_value=NOW):
            result = bridge.compile_bridge(binding["binding_id"], source, manifest, vault)
        self.assertEqual(result["status"], "OPPORTUNITY_EVIDENCE_READY")
        self.assertEqual(result["reason_codes"], [])
        self.assertEqual(result["vault"]["current_status"], "EVIDENCE_READY")
        self.assertTrue(all(value is False for value in result["authority"].values()))

    def test_current_vault_hold_propagates_after_evidence_ages_out(self):
        source, manifest = {"source": "trusted"}, {"manifest": "trusted"}
        authority, registry, query, bundle, authority_sha, registry_sha = self._vault_fixture(max_age_seconds=60)
        binding = self._synthetic_binding(source, manifest, authority_sha, registry_sha, query)
        vault = {"authority": authority, "registry": registry, "query": query, "bundle": bundle}
        later = datetime(2026, 9, 14, 12, 2, 0, tzinfo=UTC)
        with patch.object(bridge, "_load_binding_registry", return_value=("f" * 64, {binding["binding_id"]: binding})), \
             patch.object(bridge, "_process_now", return_value=later):
            result = bridge.compile_bridge(binding["binding_id"], source, manifest, vault)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("BIDDER_EVIDENCE_HOLD", result["reason_codes"])

    def test_query_transplant_is_rejected_before_vault_verification(self):
        source, manifest = {"source": "trusted"}, {"manifest": "trusted"}
        authority, registry, query, bundle, authority_sha, registry_sha = self._vault_fixture()
        binding = self._synthetic_binding(source, manifest, authority_sha, registry_sha, query)
        bad_query = deepcopy(query)
        bad_query["query_id"] = "other-query"
        vault = {"authority": authority, "registry": registry, "query": bad_query, "bundle": bundle}
        with patch.object(bridge, "_load_binding_registry", return_value=("f" * 64, {binding["binding_id"]: binding})), \
             patch.object(bridge, "_process_now", return_value=NOW):
            with self.assertRaisesRegex(bridge.BridgeError, "query root mismatch"):
                bridge.compile_bridge(binding["binding_id"], source, manifest, vault)

    def test_source_and_manifest_roots_are_not_caller_selected(self):
        registry_sha, bindings = bridge._load_binding_registry()
        binding = bindings["jersey-dn827803-main-v1"]
        self.assertRegex(registry_sha, r"^[0-9a-f]{64}$")
        with self.assertRaisesRegex(bridge.BridgeError, "source_ledger root mismatch"):
            bridge._evaluate_at(binding, registry_sha, {"fake": True}, {}, None, NOW)
        source = json.loads((Path(__file__).resolve().parents[2] / binding["source_ledger_path"]).read_text())
        with self.assertRaisesRegex(bridge.BridgeError, "submission_manifest root mismatch"):
            bridge._evaluate_at(binding, registry_sha, source, {"fake": True}, None, NOW)

    def test_deadline_uses_process_clock_and_public_api_has_no_as_of(self):
        registry_sha, bindings = bridge._load_binding_registry()
        binding = bindings["jersey-dn827803-main-v1"]
        root = Path(__file__).resolve().parents[2]
        source = json.loads((root / binding["source_ledger_path"]).read_text())
        manifest = json.loads((root / binding["submission_manifest_path"]).read_text())
        after = datetime(2026, 9, 29, 22, 30, 0, tzinfo=UTC)
        with patch.object(bridge, "_process_now", return_value=after):
            result = bridge.compile_bridge(binding["binding_id"], source, manifest, None)
        self.assertIn("PROPOSAL_DEADLINE_EXPIRED", result["reason_codes"])
        with self.assertRaises(TypeError):
            bridge.compile_bridge(binding["binding_id"], source, manifest, None, evaluated_at=NOW)  # type: ignore[call-arg]

    def test_runtime_cannot_supply_unpinned_vault_roots(self):
        registry_sha, bindings = bridge._load_binding_registry()
        binding = bindings["jersey-dn827803-main-v1"]
        root = Path(__file__).resolve().parents[2]
        source = json.loads((root / binding["source_ledger_path"]).read_text())
        manifest = json.loads((root / binding["submission_manifest_path"]).read_text())
        fake_vault = {"authority": {}, "registry": {}, "query": {}, "bundle": {}}
        with self.assertRaisesRegex(bridge.BridgeError, "cannot self-authorize"):
            bridge._evaluate_at(binding, registry_sha, source, manifest, fake_vault, NOW)

    def test_public_api_rejects_nested_container_subclasses(self):
        class MutatingDict(dict):
            pass

        registry_sha, bindings = bridge._load_binding_registry()
        binding = bindings["jersey-dn827803-main-v1"]
        root = Path(__file__).resolve().parents[2]
        source = json.loads((root / binding["source_ledger_path"]).read_text())
        manifest = json.loads((root / binding["submission_manifest_path"]).read_text())
        source["tender_pack"] = MutatingDict(source["tender_pack"])
        with patch.object(bridge, "_process_now", return_value=NOW):
            with self.assertRaisesRegex(bridge.BridgeError, "plain JSON builtins required"):
                bridge.compile_bridge(binding["binding_id"], source, manifest, None)

    def test_envelope_rejects_caller_clock_and_expected_roots(self):
        for extra in ("as_of", "deadline_utc", "expected_authority_sha256", "expected_source_sha256"):
            with self.subTest(extra=extra):
                with self.assertRaises(bridge.BridgeError):
                    bridge._parse_envelope({"source_ledger": {}, "submission_manifest": {}, "vault": None, extra: "x"})

    def test_binding_vault_roots_are_all_or_none(self):
        raw = {
            "binding_id": "bad", "opportunity_id": "BAD",
            "source_ledger_path": "a", "source_ledger_sha256": "a" * 64,
            "submission_manifest_path": "b", "submission_manifest_sha256": "b" * 64,
            "deadline_utc": "2026-09-20T00:00:00Z",
            "vault_authority_sha256": "c" * 64,
            "vault_registry_sha256": None,
            "vault_query_sha256": None,
            "static_holds": [],
        }
        with self.assertRaisesRegex(bridge.BridgeError, "all pinned or all null"):
            bridge._normalize_binding(raw, 0)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(bridge.BridgeError, "duplicate JSON key"):
            bridge.load_json(b'{"source_ledger":{},"source_ledger":{}}')


if __name__ == "__main__":
    unittest.main()
