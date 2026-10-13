import copy
import unittest
from pathlib import Path

import validate_pack as vp

ROOT = Path(__file__).resolve().parent


class SingleWriterLeaseTests(unittest.TestCase):
    def setUp(self):
        self.pack = vp._load(ROOT / "pack.json")
        self.nc = vp._load(ROOT / "overlays" / "NC_DHHS_DHB_30_2025_037_DHB.json")
        self.il = vp._load(ROOT / "overlays" / "IL_DOIT_CDB_27_448DOIT_ADMIN_B_52519.json")
        self.authority = {
            "schema": vp.TARGET_AUTHORITY_SCHEMA,
            "opportunity_id": "NC-DHHS-DHB-30-2025-037-DHB",
            "organization_id": "org:mitratech",
            "route_id": "route:partner-inbox",
            "display_company": "Mitratech",
            "display_route": "partner route A",
            "generation": 7,
            "captured_utc": "2026-09-17T23:00:00Z",
            "source_ref": "target-registry:mitratech:v7",
        }
        self.authority_sha = vp.sha256_obj(self.authority)
        self.lease = {
            "schema": vp.LEASE_RECEIPT_SCHEMA,
            "opportunity_id": self.authority["opportunity_id"],
            "organization_id": self.authority["organization_id"],
            "route_id": self.authority["route_id"],
            "arbiter": "arbiter:swarm-coordination",
            "generation": 11,
            "status": "ACQUIRED",
            "acquired_utc": "2026-09-18T03:00:00Z",
            "expires_utc": "2026-09-18T04:00:00Z",
            "receipt_ref": "coordination:lease:11",
            "target_authority_sha256": self.authority_sha,
        }
        self.lease_sha = vp.sha256_obj(self.lease)

    def build(self, **overrides):
        args = {
            "target_authority": self.authority,
            "expected_target_authority_sha256": self.authority_sha,
            "lease_receipt": self.lease,
            "expected_lease_receipt_sha256": self.lease_sha,
            "review_utc": "2026-09-18T03:30:00Z",
            "relationship_checked": True,
            "provider_history_rechecked": True,
            "opportunity_facts_revalidated": True,
        }
        args.update(overrides)
        return vp.build_target_packet(self.pack, self.nc, **args)

    def test_ready_packet_keeps_external_actions_false(self):
        packet = self.build()
        self.assertTrue(packet["controls_clear"])
        self.assertEqual(packet["state"], "READY_FOR_OWNER_TRANSPORT_REVIEW")
        self.assertEqual(packet["deadline_state"], "OPEN")
        self.assertFalse(packet["external_send_authorized"])
        self.assertFalse(packet["submission_authorized"])
        self.assertFalse(packet["payment_authorized"])

    def test_display_aliases_share_one_collision_key(self):
        first = self.build()
        authority = copy.deepcopy(self.authority)
        authority["display_company"] = "Mitratech, Inc."
        authority["display_route"] = "PARTNER-ROUTING alias"
        authority_sha = vp.sha256_obj(authority)
        lease = copy.deepcopy(self.lease)
        lease["target_authority_sha256"] = authority_sha
        lease_sha = vp.sha256_obj(lease)
        second = self.build(
            target_authority=authority,
            expected_target_authority_sha256=authority_sha,
            lease_receipt=lease,
            expected_lease_receipt_sha256=lease_sha,
        )
        self.assertEqual(first["collision_key"], second["collision_key"])

    def test_route_identity_change_changes_collision_key(self):
        authority = copy.deepcopy(self.authority)
        authority["route_id"] = "route:partner-inbox-secondary"
        authority_sha = vp.sha256_obj(authority)
        lease = copy.deepcopy(self.lease)
        lease["route_id"] = authority["route_id"]
        lease["target_authority_sha256"] = authority_sha
        lease_sha = vp.sha256_obj(lease)
        second = self.build(
            target_authority=authority,
            expected_target_authority_sha256=authority_sha,
            lease_receipt=lease,
            expected_lease_receipt_sha256=lease_sha,
        )
        self.assertNotEqual(self.build()["collision_key"], second["collision_key"])

    def test_independent_target_root_mismatch_rejected(self):
        with self.assertRaises(vp.ContractError):
            self.build(expected_target_authority_sha256="0" * 64)

    def test_independent_lease_root_mismatch_rejected(self):
        with self.assertRaises(vp.ContractError):
            self.build(expected_lease_receipt_sha256="0" * 64)

    def test_lease_identity_mismatch_rejected(self):
        lease = copy.deepcopy(self.lease)
        lease["organization_id"] = "org:someone-else"
        lease_sha = vp.sha256_obj(lease)
        with self.assertRaises(vp.ContractError):
            self.build(lease_receipt=lease, expected_lease_receipt_sha256=lease_sha)

    def test_lease_bound_to_other_target_rejected(self):
        lease = copy.deepcopy(self.lease)
        lease["target_authority_sha256"] = "1" * 64
        lease_sha = vp.sha256_obj(lease)
        with self.assertRaises(vp.ContractError):
            self.build(lease_receipt=lease, expected_lease_receipt_sha256=lease_sha)

    def test_released_and_expired_lease_hold(self):
        released = copy.deepcopy(self.lease)
        released["status"] = "RELEASED"
        released_packet = self.build(
            lease_receipt=released,
            expected_lease_receipt_sha256=vp.sha256_obj(released),
        )
        self.assertIn("LEASE_STATUS_RELEASED", released_packet["hold_reasons"])

        expired = copy.deepcopy(self.lease)
        expired["expires_utc"] = "2026-09-18T03:15:00Z"
        expired_packet = self.build(
            lease_receipt=expired,
            expected_lease_receipt_sha256=vp.sha256_obj(expired),
        )
        self.assertIn("LEASE_EXPIRED_AT_REVIEW", expired_packet["hold_reasons"])

    def test_unknown_status_and_nonpositive_generation_rejected(self):
        bad = copy.deepcopy(self.lease)
        bad["status"] = "SELECTED_MAYBE"
        with self.assertRaises(vp.ContractError):
            self.build(lease_receipt=bad, expected_lease_receipt_sha256=vp.sha256_obj(bad))
        bad = copy.deepcopy(self.lease)
        bad["generation"] = 0
        with self.assertRaises(vp.ContractError):
            self.build(lease_receipt=bad, expected_lease_receipt_sha256=vp.sha256_obj(bad))

    def test_future_authority_and_lease_rejected(self):
        authority = copy.deepcopy(self.authority)
        authority["captured_utc"] = "2026-09-18T03:45:00Z"
        authority_sha = vp.sha256_obj(authority)
        lease = copy.deepcopy(self.lease)
        lease["target_authority_sha256"] = authority_sha
        with self.assertRaises(vp.ContractError):
            self.build(
                target_authority=authority,
                expected_target_authority_sha256=authority_sha,
                lease_receipt=lease,
                expected_lease_receipt_sha256=vp.sha256_obj(lease),
            )
        lease = copy.deepcopy(self.lease)
        lease["acquired_utc"] = "2026-09-18T03:45:00Z"
        lease["expires_utc"] = "2026-09-18T04:45:00Z"
        with self.assertRaises(vp.ContractError):
            self.build(lease_receipt=lease, expected_lease_receipt_sha256=vp.sha256_obj(lease))

        authority = copy.deepcopy(self.authority)
        authority["captured_utc"] = "2026-09-18T03:15:00Z"
        authority_sha = vp.sha256_obj(authority)
        lease = copy.deepcopy(self.lease)
        lease["target_authority_sha256"] = authority_sha
        with self.assertRaises(vp.ContractError):
            self.build(
                target_authority=authority,
                expected_target_authority_sha256=authority_sha,
                lease_receipt=lease,
                expected_lease_receipt_sha256=vp.sha256_obj(lease),
            )

    def test_live_census_and_deadline_are_review_time_controls(self):
        packet = self.build(relationship_checked=False, provider_history_rechecked=False)
        self.assertIn("RELATIONSHIP_CENSUS_NOT_CURRENT", packet["hold_reasons"])
        self.assertIn("PROVIDER_HISTORY_NOT_CURRENT", packet["hold_reasons"])

        lease = copy.deepcopy(self.lease)
        lease["expires_utc"] = "2026-10-25T00:00:00Z"
        packet = self.build(
            lease_receipt=lease,
            expected_lease_receipt_sha256=vp.sha256_obj(lease),
            review_utc="2026-10-24T00:00:00Z",
        )
        self.assertEqual(packet["deadline_state"], "CLOSED")
        self.assertIn("OPPORTUNITY_DEADLINE_CLOSED", packet["hold_reasons"])

    def test_unknown_deadline_timezone_holds(self):
        authority = copy.deepcopy(self.authority)
        authority["opportunity_id"] = self.il["opportunity_id"]
        authority_sha = vp.sha256_obj(authority)
        lease = copy.deepcopy(self.lease)
        lease["opportunity_id"] = self.il["opportunity_id"]
        lease["target_authority_sha256"] = authority_sha
        packet = vp.build_target_packet(
            self.pack,
            self.il,
            target_authority=authority,
            expected_target_authority_sha256=authority_sha,
            lease_receipt=lease,
            expected_lease_receipt_sha256=vp.sha256_obj(lease),
            review_utc="2026-09-18T03:30:00Z",
            relationship_checked=True,
            provider_history_rechecked=True,
            opportunity_facts_revalidated=True,
        )
        self.assertEqual(packet["deadline_state"], "UNRESOLVED")
        self.assertIn("OPPORTUNITY_DEADLINE_UNRESOLVED", packet["hold_reasons"])

    def test_old_boolean_lease_surface_does_not_exist(self):
        with self.assertRaises(TypeError):
            vp.build_target_packet(
                self.pack,
                self.nc,
                target_authority=self.authority,
                expected_target_authority_sha256=self.authority_sha,
                lease_acquired=True,
                review_utc="2026-09-18T03:30:00Z",
                relationship_checked=True,
                provider_history_rechecked=True,
                opportunity_facts_revalidated=True,
            )

    def test_bool_int_alias_rejected(self):
        with self.assertRaises(vp.ContractError):
            self.build(relationship_checked=1)

    def test_semantic_verifier_rejects_resealed_tamper(self):
        kwargs = {
            "target_authority": self.authority,
            "expected_target_authority_sha256": self.authority_sha,
            "lease_receipt": self.lease,
            "expected_lease_receipt_sha256": self.lease_sha,
            "review_utc": "2026-09-18T03:30:00Z",
            "relationship_checked": True,
            "provider_history_rechecked": True,
            "opportunity_facts_revalidated": True,
        }
        packet = vp.build_target_packet(self.pack, self.nc, **kwargs)
        self.assertTrue(vp.verify_target_packet(packet, self.pack, self.nc, **kwargs))
        tampered = copy.deepcopy(packet)
        tampered["display_company"] = "Other"
        tampered["packet_sha256"] = vp.sha256_obj(
            {k: v for k, v in tampered.items() if k != "packet_sha256"}
        )
        self.assertFalse(vp.verify_target_packet(tampered, self.pack, self.nc, **kwargs))


if __name__ == "__main__":
    unittest.main()
