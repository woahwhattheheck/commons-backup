from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flourish_relay import ContractError, route, verify_replay
from provider_adapter import build_provider_handoff
import pack


def request(**changes):
    base = {
        "request_id": "r1",
        "topic": "food-support",
        "requested_at": "2026-09-14T20:00:00-04:00",
        "owner_fields": {"county": "Jefferson"},
        "budget_cents": 0,
        "consent_to_recommend": True,
        "sensitive_context": False,
        "desired_actions": ["RECOMMEND"],
    }
    base.update(changes)
    return base


def resource(**changes):
    base = {
        "resource_id": "a",
        "name": "Pantry A",
        "source_url": "https://example.org/a",
        "observed_at": "2026-09-10T12:00:00Z",
        "expires_at": "2026-10-01T00:00:00Z",
        "capacity": "AVAILABLE",
        "topics": ["food-support"],
        "requires_owner_fields": ["county"],
        "min_budget_cents": 0,
        "max_budget_cents": 0,
    }
    base.update(changes)
    return base


class RoutingTests(unittest.TestCase):
    def test_supported(self):
        result = route(request(), [resource()])
        self.assertEqual(result["packet"]["status"], "SUPPORTED")
        self.assertEqual(result["packet"]["permitted_actions"], ["RECOMMEND"])
        self.assertFalse(any(result["packet"]["authority"].values()))

    def test_no_consent_holds(self):
        self.assertEqual(route(request(consent_to_recommend=False), [resource()])["packet"]["status"], "HOLD")

    def test_sensitive_context_holds(self):
        self.assertEqual(route(request(sensitive_context=True), [resource()])["packet"]["status"], "HOLD")

    def test_external_action_holds(self):
        result = route(request(desired_actions=["RECOMMEND", "CONTACT"]), [resource()])
        self.assertEqual(result["packet"]["status"], "HOLD")
        self.assertEqual(result["packet"]["permitted_actions"], [])

    def test_missing_owner_fact_requests_input(self):
        result = route(request(owner_fields={}), [resource()])
        self.assertEqual(result["packet"]["status"], "OWNER_INPUT")
        self.assertEqual(result["packet"]["missing_owner_fields"], ["county"])

    def test_missing_budget_requests_input(self):
        result = route(request(budget_cents=None), [resource()])
        self.assertEqual(result["packet"]["status"], "OWNER_INPUT")
        self.assertIn("budget_cents", result["packet"]["missing_owner_fields"])

    def test_stale(self):
        old = resource(observed_at="2026-01-01T00:00:00Z", expires_at=None)
        self.assertEqual(route(request(), [old], max_age_days=30)["packet"]["status"], "STALE")

    def test_future_observation_stale(self):
        future = resource(observed_at="2026-09-20T00:00:00Z", expires_at=None)
        self.assertEqual(route(request(), [future])["packet"]["status"], "STALE")

    def test_closed_is_gap(self):
        self.assertEqual(route(request(), [resource(capacity="CLOSED")])["packet"]["status"], "GAP")

    def test_unknown_capacity_needs_owner_input(self):
        self.assertEqual(route(request(), [resource(capacity="UNKNOWN")])["packet"]["status"], "OWNER_INPUT")

    def test_budget_outside_is_gap(self):
        res = resource(min_budget_cents=500, max_budget_cents=1000)
        self.assertEqual(route(request(budget_cents=100), [res])["packet"]["status"], "GAP")

    def test_no_topic_is_gap(self):
        self.assertEqual(route(request(topic="shelter"), [resource()])["packet"]["status"], "GAP")

    def test_unknown_request_field_fails(self):
        raw = request()
        raw["secret_note"] = "do not retain"
        with self.assertRaises(ContractError):
            route(raw, [resource()])

    def test_owner_field_keys_must_be_lowercase(self):
        with self.assertRaises(ContractError):
            route(request(owner_fields={"County": "Jefferson"}), [resource()])

    def test_owner_field_nested_values_fail(self):
        with self.assertRaises(ContractError):
            route(request(owner_fields={"county": {"raw": "nested"}}), [resource()])

    def test_insecure_source_fails(self):
        with self.assertRaises(ContractError):
            route(request(), [resource(source_url="http://example.org/a")])

    def test_duplicate_resource_id_fails(self):
        with self.assertRaises(ContractError):
            route(request(), [resource(), resource(name="Other")])

    def test_resource_order_is_deterministic(self):
        a = resource(resource_id="a", name="A")
        b = resource(resource_id="b", name="B")
        self.assertEqual(route(request(), [a, b]), route(request(), [b, a]))

    def test_replay_accepts_exact_and_rejects_tamper(self):
        original = route(request(), [resource()])
        self.assertTrue(verify_replay(request(), [resource()], original))
        tampered = copy.deepcopy(original)
        tampered["packet"]["status"] = "SUPPORTED-BUT-NOT-REAL"
        self.assertFalse(verify_replay(request(), [resource()], tampered))

    def test_owner_values_not_echoed(self):
        result = route(request(owner_fields={"county": "DO-NOT-ECHO-THIS"}), [resource()])
        serialized = json.dumps(result["packet"], sort_keys=True)
        self.assertNotIn("DO-NOT-ECHO-THIS", serialized)
        self.assertIn("county", serialized)


class ProviderBoundaryTests(unittest.TestCase):
    def test_missing_provider_evidence_is_explicit(self):
        result = route(request(), [resource()])
        env = build_provider_handoff(result)
        self.assertEqual(env["provider_state"], "PROVIDER_EVIDENCE_REQUIRED")
        self.assertEqual(env["executable_external_actions"], [])
        self.assertFalse(any(env["authority"].values()))

    def test_verified_evidence_still_does_not_grant_authority(self):
        result = route(request(), [resource()])
        ev = {
            "provider": "example-provider",
            "captured_at": "2026-09-14T23:00:00Z",
            "artifact_sha256": "a" * 64,
            "verified": True,
        }
        env = build_provider_handoff(result, ev)
        self.assertEqual(env["provider_state"], "EVIDENCE_PRESENT_EXTERNAL_AUTHORITY_STILL_REQUIRED")
        self.assertEqual(env["executable_external_actions"], [])

    def test_unverified_evidence_fails(self):
        result = route(request(), [resource()])
        with self.assertRaises(ContractError):
            build_provider_handoff(result, {"provider":"x","captured_at":"x","artifact_sha256":"a"*64,"verified":False})


class PackageTests(unittest.TestCase):
    def test_bundle_is_deterministic_and_verifies(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            root = td / "src"
            root.mkdir()
            (root / "a.txt").write_text("alpha\n", encoding="utf-8")
            (root / "b.txt").write_text("beta\n", encoding="utf-8")
            one, two = td / "one.zip", td / "two.zip"
            r1 = pack.build(root, one)
            r2 = pack.build(root, two)
            self.assertEqual(one.read_bytes(), two.read_bytes())
            self.assertEqual(r1["archive_sha256"], r2["archive_sha256"])
            self.assertTrue(pack.verify(one)["verified"])

    def test_bundle_tamper_fails(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            root = td / "src"
            root.mkdir()
            (root / "a.txt").write_text("alpha\n", encoding="utf-8")
            original = td / "original.zip"
            bad = td / "bad.zip"
            pack.build(root, original)
            with zipfile.ZipFile(original, "r") as zf, zipfile.ZipFile(bad, "w") as out:
                for info in zf.infolist():
                    data = zf.read(info.filename)
                    if info.filename == "a.txt":
                        data = b"tampered\n"
                    out.writestr(info, data)
            with self.assertRaises(ValueError):
                pack.verify(bad)

    def test_extra_member_fails(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            root = td / "src"
            root.mkdir()
            (root / "a.txt").write_text("alpha\n", encoding="utf-8")
            original = td / "original.zip"
            bad = td / "bad.zip"
            pack.build(root, original)
            with zipfile.ZipFile(original, "r") as zf, zipfile.ZipFile(bad, "w") as out:
                for info in zf.infolist():
                    out.writestr(info, zf.read(info.filename))
                out.writestr("evil.txt", b"nope")
            with self.assertRaises(ValueError):
                pack.verify(bad)


if __name__ == "__main__":
    unittest.main()
