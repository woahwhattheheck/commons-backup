from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.outbound_send_guard import relationship_census as rc

KEY = bytes.fromhex("42" * 32)
NOW = datetime(2026, 9, 14, 2, 40, 0, tzinfo=timezone.utc)
R1 = "11" * 32
R2 = "22" * 32
EVENT = "33" * 32
WORKSPACE = "44" * 32
REL = "worker-alpha"
TARGET = "account-funto-v1"


def base_manifest(state="ACTIVE_OWNER", owner=REL, generation=3):
    rows = []
    for route in (R1, R2):
        rows.append(
            {
                "route_sha256": route,
                "target_binding_sha256": rc.target_binding_sha256(TARGET, route),
                "state": state,
                "owner": owner,
                "generation": generation,
                "observed_at": "2026-09-14T02:38:00Z",
                "event_sha256": EVENT,
            }
        )
    raw = {
        "schema_version": rc.CENSUS_SCHEMA,
        "target_scope": TARGET,
        "route_sha256s": [R2, R1],
        "current_worker": REL,
        "claimed_generation": generation,
        "census": {
            "provider": "gmail",
            "workspace_sha256": WORKSPACE,
            "snapshot_id": "snap-001",
            "snapshot_at": "2026-09-14T02:39:00Z",
            "coverage_started_at": "2025-09-14T00:00:00Z",
            "complete": True,
            "route_observations": rows,
            "relationship": {
                "state": state,
                "owner": owner,
                "generation": generation,
            },
            "transfer": None,
        },
        "authority": {
            "schema_version": rc.AUTHORITY_SCHEMA,
            "scheme": "HMAC-SHA256",
            "key_id": "gmail-workspace-key-v1",
            "signature_sha256": "00" * 32,
        },
    }
    return sign(raw)


def sign(raw):
    candidate = copy.deepcopy(raw)
    candidate["authority"]["signature_sha256"] = "00" * 32
    normalized = rc._normalize(candidate)
    raw["authority"]["signature_sha256"] = rc.compute_signature(normalized, KEY)
    return raw


class RelationshipCensusTests(unittest.TestCase):
    def evaluate(self, raw):
        return rc.evaluate(raw, provider_hmac_key=KEY, now=NOW)

    def test_current_owner_live_generation_projects_custody_only(self):
        result = self.evaluate(base_manifest())
        self.assertEqual(result["payload"]["decision"], "CURRENT_OWNER")
        self.assertFalse(result["payload"]["external_send_authorized"])
        self.assertTrue(result["payload"]["requires_outbound_send_guard"])
        self.assertNotIn("@", json.dumps(result))

    def test_clear_history_can_only_clear_custody_gate(self):
        raw = base_manifest(state="CLEAR", owner=None, generation=0)
        result = self.evaluate(raw)
        self.assertEqual(result["payload"]["decision"], "CUSTODY_CLEAR")
        self.assertFalse(result["payload"]["external_send_authorized"])

    def test_other_owner_holds(self):
        raw = base_manifest(owner="worker-old")
        raw["current_worker"] = "worker-new"
        raw = sign(raw)
        result = self.evaluate(raw)
        self.assertEqual(result["payload"]["decision"], "HOLD")
        self.assertIn("CURRENT_OWNER_MISMATCH", result["payload"]["reasons"])

    def test_generation_mismatch_holds(self):
        raw = base_manifest()
        raw["claimed_generation"] = 2
        # current_worker/generation claim is intentionally outside provider signature.
        result = self.evaluate(raw)
        self.assertEqual(result["payload"]["decision"], "HOLD")
        self.assertIn("CLAIMED_GENERATION_MISMATCH", result["payload"]["reasons"])

    def test_invalid_signature_holds_not_raises(self):
        raw = base_manifest()
        raw["authority"]["signature_sha256"] = "ff" * 32
        result = self.evaluate(raw)
        self.assertEqual(result["payload"]["decision"], "HOLD")
        self.assertIn("AUTHORITY_SIGNATURE_INVALID", result["payload"]["reasons"])

    def test_incomplete_stale_future_hold(self):
        incomplete = base_manifest()
        incomplete["census"]["complete"] = False
        incomplete = sign(incomplete)
        self.assertIn("CENSUS_INCOMPLETE", self.evaluate(incomplete)["payload"]["reasons"])

        stale = base_manifest()
        stale["census"]["snapshot_at"] = "2026-09-14T01:00:00Z"
        stale = sign(stale)
        self.assertIn("SNAPSHOT_STALE", self.evaluate(stale)["payload"]["reasons"])

        future = base_manifest()
        future["census"]["snapshot_at"] = "2026-09-14T03:00:00Z"
        future = sign(future)
        self.assertIn("SNAPSHOT_IN_FUTURE", self.evaluate(future)["payload"]["reasons"])

    def test_cross_target_transplant_holds_even_when_snapshot_is_resigned(self):
        raw = base_manifest()
        raw["target_scope"] = "account-other-v1"
        # Route target bindings still point at account-funto-v1. Re-signing the
        # snapshot cannot make those observations transplantable.
        raw = sign(raw)
        reasons = self.evaluate(raw)["payload"]["reasons"]
        self.assertTrue(any(reason.startswith("TARGET_BINDING_MISMATCH:") for reason in reasons))

    def test_restricted_contact_state_holds_even_for_owner(self):
        for state in ("UNSUBSCRIBED", "DNR", "HARD_BOUNCE"):
            raw = base_manifest(state=state, owner=REL)
            result = self.evaluate(raw)
            self.assertEqual(result["payload"]["decision"], "HOLD", state)
            self.assertIn(f"CONTACT_BLOCKED:{state}", result["payload"]["reasons"])

    def test_valid_explicit_transfer_increments_generation_and_receipts(self):
        raw = base_manifest(state="TRANSFERRED", owner="worker-new", generation=4)
        raw["current_worker"] = "worker-new"
        raw["claimed_generation"] = 4
        raw["census"]["transfer"] = {
            "schema_version": rc.TRANSFER_SCHEMA,
            "target_route_set_sha256": rc.route_set_sha256(TARGET, [R1, R2]),
            "from_owner": REL,
            "to_owner": "worker-new",
            "from_generation": 3,
            "to_generation": 4,
            "release_actor": REL,
            "release_authority": "OWNER",
            "released_at": "2026-09-14T02:36:00Z",
            "release_ref_sha256": "55" * 32,
            "accept_actor": "worker-new",
            "accepted_at": "2026-09-14T02:37:00Z",
            "accept_ref_sha256": "66" * 32,
        }
        raw = sign(raw)
        result = self.evaluate(raw)
        self.assertEqual(result["payload"]["decision"], "CURRENT_OWNER")
        self.assertRegex(result["payload"]["transfer_receipt_sha256"], r"^[0-9a-f]{64}$")

    def test_bad_transfer_release_or_generation_holds(self):
        raw = base_manifest(state="TRANSFERRED", owner="worker-new", generation=4)
        raw["current_worker"] = "worker-new"
        raw["claimed_generation"] = 4
        raw["census"]["transfer"] = {
            "schema_version": rc.TRANSFER_SCHEMA,
            "target_route_set_sha256": rc.route_set_sha256(TARGET, [R1, R2]),
            "from_owner": REL,
            "to_owner": "worker-new",
            "from_generation": 1,
            "to_generation": 4,
            "release_actor": "intruder",
            "release_authority": "OWNER",
            "released_at": "2026-09-14T02:36:00Z",
            "release_ref_sha256": "55" * 32,
            "accept_actor": "worker-new",
            "accepted_at": "2026-09-14T02:37:00Z",
            "accept_ref_sha256": "66" * 32,
        }
        raw = sign(raw)
        reasons = self.evaluate(raw)["payload"]["reasons"]
        self.assertTrue(
            "TRANSFER_GENERATION_NOT_INCREMENTED" in reasons
            or "TRANSFER_RELEASE_NOT_AUTHORIZED" in reasons
        )

    def test_strict_json_rejects_duplicate_and_nonfinite(self):
        with self.assertRaises(rc.CensusError):
            rc.parse_json_bytes(b'{"x":1,"x":2}')
        with self.assertRaises(rc.CensusError):
            rc.parse_json_bytes(b'{"x":NaN}')

    def test_exact_bytes_digest_and_create_exclusive_publication(self):
        raw = base_manifest()
        encoded = json.dumps(raw, sort_keys=True).encode()
        result = rc.evaluate_bytes(encoded, provider_hmac_key=KEY, now=NOW)
        self.assertEqual(
            result["payload"]["source_exact_bytes_sha256"],
            __import__("hashlib").sha256(encoded).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "receipt.json"
            rc._atomic_publish_new(out, b"one")
            with self.assertRaises(rc.CensusError):
                rc._atomic_publish_new(out, b"two")
            self.assertEqual(out.read_bytes(), b"one")

    def test_unsigned_authority_holds(self):
        raw = base_manifest()
        raw.pop("authority")
        result = self.evaluate(raw)
        self.assertEqual(result["payload"]["decision"], "HOLD")
        self.assertIn("AUTHORITY_SIGNATURE_INVALID", result["payload"]["reasons"])

    def test_clear_aggregate_cannot_hide_nonclear_route(self):
        raw = base_manifest(state="CLEAR", owner=None, generation=0)
        raw["census"]["route_observations"][0]["state"] = "ACTIVE_OWNER"
        raw["census"]["route_observations"][0]["owner"] = REL
        raw = sign(raw)
        reasons = self.evaluate(raw)["payload"]["reasons"]
        self.assertIn("RELATIONSHIP_CLEAR_WITH_NONCLEAR_ROUTE", reasons)

    def test_echoed_worker_identity_rejects_raw_email(self):
        raw = base_manifest()
        raw["current_worker"] = "worker@example.com"
        with self.assertRaises(rc.CensusError):
            self.evaluate(raw)

    def test_target_scope_rejects_raw_email(self):
        raw = base_manifest()
        raw["target_scope"] = "person@example.com"
        with self.assertRaises(rc.CensusError):
            self.evaluate(raw)


if __name__ == "__main__":
    unittest.main()
