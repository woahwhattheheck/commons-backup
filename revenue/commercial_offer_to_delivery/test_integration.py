from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from . import build_scope_bridge, create_operator_verification, verify_scope_bridge
from .fixtures import FOUR, NOW, OWNER_KEY, THREE, TWO, VERIFY_KEY, offer, scope_acceptance, service_window


class LandedRailsIntegration(unittest.TestCase):
    def test_actual_commercial_rail_to_actual_scope_validator(self):
        try:
            from revenue.commercial_offer_contract.offer_contract import approve_offer, authorize_send, capture_buyer_acceptance, compile_offer
            from host.scope_to_delivery import validate_agreement
        except Exception as exc:
            self.skipTest(f"landed Commons dependencies unavailable in isolated local packet: {exc}")
        spec = offer(); compiled = compile_offer(spec)
        approved = approve_offer(compiled, OWNER_KEY, key_id="sales-owner-v1", approved_at="2026-09-13T10:01:00Z")
        sent = authorize_send(approved, OWNER_KEY, destination_sha256=FOUR, channel="email", authorized_at="2026-09-13T10:02:00Z")
        captured = capture_buyer_acceptance(
            sent, OWNER_KEY,
            acceptance={"offer_sha256": sent["offer_sha256"], "buyer_ref": spec["buyer_ref"], "accepted_at": "2026-09-13T10:03:00Z", "evidence_sha256": TWO, "identity_verification_sha256": THREE},
            trusted_now="2026-09-13T10:04:00Z",
        )
        root = Path(__file__).resolve().parents[2]
        catalog = json.loads((root / "revenue" / "outcome_commerce" / "catalog.json").read_text())
        window = service_window(); accepted_scope = scope_acceptance(captured, catalog, window)
        receipt = create_operator_verification(
            captured, OWNER_KEY, VERIFY_KEY, verifier_id="operator-001", key_id="acceptance-key-v2",
            verified_at="2026-09-13T10:06:00Z", public_ref="p/accepted-scope-terms.md",
            catalog=catalog, service_window=window, scope_terms_acceptance=accepted_scope, trusted_now=NOW,
        )
        out = build_scope_bridge(captured, receipt, OWNER_KEY, VERIFY_KEY, catalog=catalog, trusted_now=NOW)
        self.assertEqual(validate_agreement(copy.deepcopy(out["agreement"]), copy.deepcopy(catalog)), out["agreement"])
        self.assertEqual(verify_scope_bridge(out, captured, OWNER_KEY, VERIFY_KEY, catalog=catalog, trusted_now=NOW), out)


if __name__ == "__main__":
    unittest.main()
