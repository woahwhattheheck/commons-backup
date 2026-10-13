from __future__ import annotations

import copy
import hashlib
import inspect
import unittest
from datetime import UTC, datetime, timedelta

from revenue.cross_provider_outbound_census import census


def sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def ts(base: str, seconds: int) -> str:
    dt = datetime.fromisoformat(base.replace("Z", "+00:00")) + timedelta(seconds=seconds)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


BASE = "2026-09-14T16:00:00Z"
GH = sha("github-route")
GM = sha("gmail-route")
SL = sha("slack-route")


def request(**intent_changes):
    intent = {
        "provider": "github",
        "route_sha256": GH,
        "claimant_scope": "sol-z12",
        "claim_scope": "issue-16863",
        "requested_at": ts(BASE, -3),
    }
    intent.update(intent_changes)
    return {
        "schema": census.REQUEST_SCHEMA,
        "lease_input": {
            "schema": "outbound-connector-lease/v1",
            "buyer_scope": "example.org",
            "opportunity": {
                "kind": "external",
                "authority": "github.com",
                "id": "owner/repo/issues/16863",
            },
        },
        "intent": intent,
    }


class FakeAuthority(census.TrustedCensusAuthority):
    def __init__(self):
        self.now = BASE
        self.registry_status = "COMPLETE"
        self.registry_observed = ts(BASE, -2)
        self.registry_generation = "registry-gen-001"
        self.aliases = [
            {"provider": "github", "route_sha256": GH},
            {"provider": "gmail", "route_sha256": GM},
        ]
        self.snapshots = {
            "github": self._snap("github", [GH]),
            "gmail": self._snap("gmail", [GM]),
        }
        self.raise_registry = False
        self.raise_provider = set()

    def _snap(self, provider, routes, *, status="COMPLETE", events=None,
              observed=None, generation=None):
        return {
            "schema": census.PROVIDER_SCHEMA,
            "lease_seam_sha256": None,
            "registry_generation_id": self.registry_generation,
            "generation_id": generation or f"{provider}-gen-001",
            "provider": provider,
            "status": status,
            "observed_at": observed or ts(BASE, -1),
            "source_receipt_sha256": sha(f"{provider}-source-receipt"),
            "covered_routes": list(routes),
            "events": copy.deepcopy(events or []),
        }

    def current_utc(self):
        return self.now

    def alias_registry(self, lease_key):
        if self.raise_registry:
            raise census.AuthorityUnavailable("registry down")
        return {
            "schema": census.REGISTRY_SCHEMA,
            "lease_seam_sha256": lease_key["seam_sha256"],
            "generation_id": self.registry_generation,
            "status": self.registry_status,
            "observed_at": self.registry_observed,
            "source_receipt_sha256": sha("registry-source-receipt"),
            "aliases": copy.deepcopy(self.aliases),
        }

    def provider_census(self, lease_key, provider, registered_routes,
                        registry_generation_id, intent):
        if provider in self.raise_provider:
            raise census.AuthorityUnavailable("provider down")
        snap = copy.deepcopy(self.snapshots.get(provider))
        if snap is None:
            return None
        snap["lease_seam_sha256"] = lease_key["seam_sha256"]
        snap["registry_generation_id"] = registry_generation_id
        return snap


def event(route, kind, label="event", at=None):
    return {
        "route_sha256": route,
        "event": kind,
        "event_at": at or ts(BASE, -2),
        "evidence_sha256": sha(label),
    }


class CensusTests(unittest.TestCase):
    def clear(self, auth=None, req=None):
        auth = auth or FakeAuthority()
        packet = census.compile_census(req or request(), authority=auth)
        self.assertEqual(packet["result"], "CLEAR_FOR_DOWNSTREAM_GATES", packet["reasons"])
        self.assertFalse(packet["external_send_authorized"])
        self.assertFalse(packet["lease_authorized"])
        self.assertFalse(packet["provider_mutation_authorized"])
        return packet, auth

    def test_clean_registry_and_two_provider_census_clears(self):
        packet, _ = self.clear()
        self.assertEqual(len(packet["authority"]["providers"]), 2)
        self.assertEqual(packet["clear_until"], ts(BASE, 297))

    def test_candidate_cannot_supply_alias_universe(self):
        req = request()
        req["aliases"] = [{"provider": "github", "route_sha256": GH}]
        with self.assertRaisesRegex(census.CensusError, "fields differ"):
            census.compile_census(req, authority=FakeAuthority())

    def test_candidate_cannot_supply_provider_snapshots(self):
        req = request()
        req["snapshots"] = []
        with self.assertRaisesRegex(census.CensusError, "fields differ"):
            census.compile_census(req, authority=FakeAuthority())

    def test_candidate_cannot_supply_trusted_now(self):
        req = request()
        req["trusted_now"] = ts(BASE, -3)
        with self.assertRaisesRegex(census.CensusError, "fields differ"):
            census.compile_census(req, authority=FakeAuthority())

    def test_public_api_has_no_trusted_now_parameter_or_cli(self):
        self.assertNotIn("trusted_now", inspect.signature(census.compile_census).parameters)
        self.assertNotIn("trusted_now", inspect.signature(census.verify_census).parameters)
        self.assertFalse(hasattr(census, "main"))

    def test_wrong_authority_object_rejected(self):
        with self.assertRaisesRegex(census.CensusError, "TrustedCensusAuthority"):
            census.compile_census(request(), authority=object())

    def test_missing_gmail_census_holds_exact_cross_provider_hostile(self):
        auth = FakeAuthority()
        auth.snapshots.pop("gmail")
        packet = census.compile_census(request(), authority=auth)
        self.assertEqual(packet["result"], "HOLD")
        self.assertIn("PROVIDER_CENSUS_MISSING:gmail", packet["reasons"])

    def test_unavailable_gmail_census_holds(self):
        auth = FakeAuthority()
        auth.raise_provider.add("gmail")
        packet = census.compile_census(request(), authority=auth)
        self.assertIn("PROVIDER_CENSUS_MISSING:gmail", packet["reasons"])

    def test_retained_gmail_sent_event_holds_github_retry(self):
        auth = FakeAuthority()
        auth.snapshots["gmail"]["events"] = [event(GM, "PROVIDER_SENT", "prior-email-submit")]
        packet = census.compile_census(request(), authority=auth)
        self.assertIn("EXISTING_TOUCH_HISTORY", packet["reasons"])
        self.assertEqual(packet["history_evidence"][0]["provider"], "gmail")

    def test_retained_human_reply_holds(self):
        auth = FakeAuthority()
        auth.snapshots["gmail"]["events"] = [event(GM, "HUMAN_REPLY")]
        self.assertIn("EXISTING_TOUCH_HISTORY",
                      census.compile_census(request(), authority=auth)["reasons"])

    def test_dnr_holds(self):
        auth = FakeAuthority()
        auth.snapshots["gmail"]["events"] = [event(GM, "DNR")]
        self.assertIn("SUPPRESSION_HISTORY",
                      census.compile_census(request(), authority=auth)["reasons"])

    def test_bounce_is_route_repair_not_buyer_rejection(self):
        auth = FakeAuthority()
        auth.snapshots["gmail"]["events"] = [event(GM, "HARD_BOUNCE")]
        packet = census.compile_census(request(), authority=auth)
        self.assertIn("ROUTE_REPAIR_HISTORY", packet["reasons"])
        self.assertNotIn("EXISTING_TOUCH_HISTORY", packet["reasons"])

    def test_ambiguous_effect_holds(self):
        auth = FakeAuthority()
        auth.snapshots["github"]["events"] = [event(GH, "AMBIGUOUS_EFFECT")]
        self.assertIn("AMBIGUOUS_PROVIDER_HISTORY",
                      census.compile_census(request(), authority=auth)["reasons"])

    def test_incomplete_provider_preserves_known_event(self):
        auth = FakeAuthority()
        auth.snapshots["gmail"]["status"] = "THROTTLED"
        auth.snapshots["gmail"]["events"] = [event(GM, "PROVIDER_SENT")]
        packet = census.compile_census(request(), authority=auth)
        self.assertIn("PROVIDER_CENSUS_THROTTLED:gmail", packet["reasons"])
        self.assertIn("EXISTING_TOUCH_HISTORY", packet["reasons"])
        self.assertEqual(len(packet["history_evidence"]), 1)

    def test_registry_unavailable_fails_closed(self):
        auth = FakeAuthority()
        auth.raise_registry = True
        packet = census.compile_census(request(), authority=auth)
        self.assertEqual(packet["result"], "HOLD")
        self.assertIn("ALIAS_REGISTRY_UNAVAILABLE", packet["reasons"])
        self.assertIn("INTENT_ROUTE_NOT_IN_RETAINED_REGISTRY", packet["reasons"])

    def test_registry_ambiguous_holds(self):
        auth = FakeAuthority()
        auth.registry_status = "AMBIGUOUS"
        self.assertIn("ALIAS_REGISTRY_AMBIGUOUS",
                      census.compile_census(request(), authority=auth)["reasons"])

    def test_registry_snapshot_must_be_after_intent(self):
        auth = FakeAuthority()
        auth.registry_observed = ts(BASE, -4)
        self.assertIn("ALIAS_REGISTRY_BEFORE_INTENT",
                      census.compile_census(request(), authority=auth)["reasons"])

    def test_provider_snapshot_must_be_after_registry(self):
        auth = FakeAuthority()
        auth.registry_observed = ts(BASE, -1)
        auth.snapshots["gmail"]["observed_at"] = ts(BASE, -2)
        self.assertIn("PROVIDER_CENSUS_BEFORE_REGISTRY:gmail",
                      census.compile_census(request(), authority=auth)["reasons"])

    def test_missing_route_coverage_holds(self):
        auth = FakeAuthority()
        auth.snapshots["gmail"]["covered_routes"] = []
        self.assertIn("PROVIDER_ROUTE_COVERAGE_MISSING:gmail",
                      census.compile_census(request(), authority=auth)["reasons"])

    def test_unknown_route_coverage_holds(self):
        auth = FakeAuthority()
        auth.snapshots["gmail"]["covered_routes"] = [GM, SL]
        self.assertIn("PROVIDER_ROUTE_COVERAGE_UNKNOWN:gmail",
                      census.compile_census(request(), authority=auth)["reasons"])

    def test_event_on_unregistered_route_rejected(self):
        auth = FakeAuthority()
        auth.snapshots["gmail"]["events"] = [event(SL, "PROVIDER_SENT")]
        with self.assertRaisesRegex(census.CensusError, "retained registry"):
            census.compile_census(request(), authority=auth)

    def test_intent_route_must_be_in_retained_registry(self):
        packet = census.compile_census(request(route_sha256=SL), authority=FakeAuthority())
        self.assertIn("INTENT_ROUTE_NOT_IN_RETAINED_REGISTRY", packet["reasons"])

    def test_historical_request_cannot_be_resurrected_by_argument(self):
        auth = FakeAuthority()
        req = request(requested_at="2025-09-14T16:00:00Z")
        packet = census.compile_census(req, authority=auth)
        self.assertIn("INTENT_STALE", packet["reasons"])
        self.assertNotIn("trusted_now", inspect.signature(census.compile_census).parameters)

    def test_future_request_holds(self):
        packet = census.compile_census(request(requested_at=ts(BASE, 1)), authority=FakeAuthority())
        self.assertIn("INTENT_REQUESTED_IN_FUTURE", packet["reasons"])

    def test_future_provider_snapshot_holds(self):
        auth = FakeAuthority()
        auth.snapshots["gmail"]["observed_at"] = ts(BASE, 1)
        self.assertIn("PROVIDER_CENSUS_FUTURE:gmail",
                      census.compile_census(request(), authority=auth)["reasons"])

    def test_provider_registry_generation_mismatch_rejected(self):
        auth = FakeAuthority()
        original = auth.provider_census
        def mismatch(*args, **kwargs):
            snap = original(*args, **kwargs)
            if args[1] == "gmail":
                snap["registry_generation_id"] = "registry-gen-other"
            return snap
        auth.provider_census = mismatch
        with self.assertRaisesRegex(census.CensusError, "different registry generation"):
            census.compile_census(request(), authority=auth)

    def test_provider_seam_mismatch_rejected(self):
        auth = FakeAuthority()
        original = auth.provider_census
        def mismatch(*args, **kwargs):
            snap = original(*args, **kwargs)
            if args[1] == "gmail":
                snap["lease_seam_sha256"] = sha("different-seam")
            return snap
        auth.provider_census = mismatch
        with self.assertRaisesRegex(census.CensusError, "different lease seam"):
            census.compile_census(request(), authority=auth)

    def test_packet_is_deterministic_for_same_host_generation(self):
        auth = FakeAuthority()
        self.assertEqual(census.compile_census(request(), authority=auth),
                         census.compile_census(request(), authority=auth))

    def test_verify_clean_packet(self):
        packet, auth = self.clear()
        census.verify_census(request(), packet, authority=auth)

    def test_verify_rejects_packet_mutation(self):
        packet, auth = self.clear()
        packet["result"] = "HOLD"
        with self.assertRaisesRegex(census.CensusError, "receipt mismatch"):
            census.verify_census(request(), packet, authority=auth)

    def test_verify_rejects_registry_generation_change(self):
        packet, auth = self.clear()
        auth.registry_generation = "registry-gen-002"
        with self.assertRaises(census.CensusError):
            census.verify_census(request(), packet, authority=auth)

    def test_verify_rejects_provider_generation_change(self):
        packet, auth = self.clear()
        auth.snapshots["gmail"]["generation_id"] = "gmail-gen-002"
        with self.assertRaisesRegex(census.CensusError, "provider census generation changed"):
            census.verify_census(request(), packet, authority=auth)

    def test_verify_rejects_expired_clear_packet(self):
        packet, auth = self.clear()
        auth.now = ts(BASE, 400)
        with self.assertRaises(census.CensusError):
            census.verify_census(request(), packet, authority=auth)

    def test_duplicate_alias_rejected(self):
        auth = FakeAuthority()
        auth.aliases.append({"provider": "gmail", "route_sha256": GM})
        with self.assertRaisesRegex(census.CensusError, "duplicate retained"):
            census.compile_census(request(), authority=auth)

    def test_duplicate_evidence_rejected(self):
        auth = FakeAuthority()
        e = event(GM, "PROVIDER_SENT", "same")
        auth.snapshots["gmail"]["events"] = [e, copy.deepcopy(e)]
        with self.assertRaisesRegex(census.CensusError, "duplicate provider evidence"):
            census.compile_census(request(), authority=auth)

    def test_nonfinite_candidate_rejected(self):
        req = request()
        req["x"] = float("nan")
        with self.assertRaises(census.CensusError):
            census.compile_census(req, authority=FakeAuthority())


if __name__ == "__main__":
    unittest.main()
