import copy
import json
import unittest

from tools.swarm_work_router.router import (
    RouterError,
    channel_registry,
    compile_route,
    compile_scratch,
    loads_strict,
    publication_key,
    verify_receipt,
)


def item(**overrides):
    base = {
        "schema": "swarm-work-item/v1",
        "work_id": "ZFATHOM:test-001",
        "kind": "build",
        "target": "Acme Incorporated",
        "opportunity": "Accounts-payable operations build",
        "purpose": "Deliver fixed-scope operations software",
        "value_usd": 15000,
        "external_publish": False,
        "route_family": "none",
        "repository": "woahwhattheheck/commons",
        "artifact_scope": "tools/swarm_work_router/**",
    }
    base.update(overrides)
    return base


class RouterTests(unittest.TestCase):
    def test_specialist_routes(self):
        expected = {
            "build": "build-demand",
            "bug_bounty": "bug-bounty",
            "business_pack": "business-packs",
            "competition": "international-competitions",
            "data_science_bounty": "data-science-bounties",
            "feature_bounty": "feature-bounties",
            "github_inbox": "github-inbox",
            "hive_commerce": "hive-commerce-builds",
            "hive_media": "hive-media-builds",
            "hive_original": "hive-original-builds",
            "hive_saas": "hive-saas-builds",
            "integration_bounty": "integration-bounties",
            "lead": "leads",
            "math_bounty": "math-bounties",
            "merge_review": "awaiting-merge",
            "product": "products",
            "shipped": "shipped-builds",
        }
        for kind, name in expected.items():
            with self.subTest(kind=kind):
                receipt = compile_route(item(kind=kind))
                self.assertEqual(receipt["primary_channel"]["name"], name)
                self.assertTrue(verify_receipt(receipt))

    def test_external_outbound_requires_muse_but_never_authorizes_send(self):
        receipt = compile_route(item(kind="outbound", external_publish=True, route_family="email"))
        self.assertEqual(receipt["primary_channel"]["name"], "hot-leads")
        self.assertTrue(receipt["requires_muse_arbitration"])
        self.assertEqual(receipt["muse_dm_id"], "D0C1U7TUZEC")
        self.assertFalse(receipt["external_publish_authorized"])
        self.assertFalse(receipt["side_effects_authorized"])

    def test_publication_key_collides_across_transports(self):
        a = item(kind="outbound", external_publish=True, route_family="email")
        b = item(kind="outbound", external_publish=True, route_family="contact_form")
        self.assertEqual(publication_key(a), publication_key(b))
        self.assertEqual(compile_route(a)["publication_key"], compile_route(b)["publication_key"])

    def test_publication_key_normalizes_case_and_whitespace(self):
        a = item(target=" ACME   Incorporated ", opportunity="X  Y", purpose="Do THING")
        b = item(target="acme incorporated", opportunity="x y", purpose="do thing")
        self.assertEqual(publication_key(a), publication_key(b))

    def test_unknown_kind_fails_closed_to_coordination(self):
        receipt = compile_route(item(kind="new_unclassified_lane"))
        self.assertEqual(receipt["classification"], "HOLD_CLASSIFICATION_UNKNOWN")
        self.assertEqual(receipt["primary_channel"]["name"], "coordination-channel-created-today-please-use")
        self.assertFalse(receipt["side_effects_authorized"])

    def test_central_queues_not_default_primary(self):
        registry = channel_registry()["channels"]
        flags = {row["name"]: row["default_primary_allowed"] for row in registry}
        self.assertFalse(flags["delegations"])
        self.assertFalse(flags["awaiting-merge"])
        for kind in ["build", "product", "lead", "math_bounty", "integration_bounty"]:
            self.assertNotIn(compile_route(item(kind=kind))["primary_channel"]["name"], {"delegations", "awaiting-merge"})

    def test_route_receipt_is_deterministic(self):
        self.assertEqual(compile_route(item()), compile_route(copy.deepcopy(item())))

    def test_route_receipt_tamper_is_detected(self):
        receipt = compile_route(item())
        receipt["primary_channel"]["name"] = "delegations"
        self.assertFalse(verify_receipt(receipt))

    def test_strict_json_duplicate_key_rejected(self):
        with self.assertRaises(RouterError):
            loads_strict('{"schema":"a","schema":"b"}')

    def test_unknown_and_missing_fields_rejected(self):
        raw = item()
        raw["extra"] = 1
        with self.assertRaises(RouterError):
            compile_route(raw)
        raw = item()
        del raw["purpose"]
        with self.assertRaises(RouterError):
            compile_route(raw)

    def test_bool_is_not_valid_integer_value(self):
        with self.assertRaises(RouterError):
            compile_route(item(value_usd=True))

    def test_external_route_family_consistency(self):
        with self.assertRaises(RouterError):
            compile_route(item(external_publish=True, route_family="none"))
        with self.assertRaises(RouterError):
            compile_route(item(external_publish=False, route_family="email"))

    def test_scratch_open_clear_and_reopen_chain(self):
        open_r = compile_scratch(item(), "OPEN")
        self.assertEqual(open_r["state"], "OPEN")
        self.assertTrue(verify_receipt(open_r))
        clear_r = compile_scratch(item(), "CLEAR", open_r)
        self.assertEqual(clear_r["state"], "CLEARED")
        self.assertEqual(clear_r["previous_receipt_sha256"], open_r["receipt_sha256"])
        reopen_r = compile_scratch(item(), "OPEN", clear_r)
        self.assertEqual(reopen_r["state"], "OPEN")
        self.assertEqual(reopen_r["previous_receipt_sha256"], clear_r["receipt_sha256"])

    def test_scratch_rejects_invalid_transitions(self):
        with self.assertRaises(RouterError):
            compile_scratch(item(), "CLEAR")
        open_r = compile_scratch(item(), "OPEN")
        with self.assertRaises(RouterError):
            compile_scratch(item(), "OPEN", open_r)
        clear_r = compile_scratch(item(), "CLEAR", open_r)
        with self.assertRaises(RouterError):
            compile_scratch(item(), "CLEAR", clear_r)

    def test_scratch_tamper_and_cross_item_rejected(self):
        open_r = compile_scratch(item(), "OPEN")
        tampered = copy.deepcopy(open_r)
        tampered["work_id"] = "ZFATHOM:other"
        with self.assertRaises(RouterError):
            compile_scratch(item(), "CLEAR", tampered)
        with self.assertRaises(RouterError):
            compile_scratch(item(work_id="ZFATHOM:other"), "CLEAR", open_r)

    def test_cli_file_shape_is_strict_json_compatible(self):
        # Guards accidental non-JSON values in the public receipt surface.
        encoded = json.dumps(compile_route(item()), sort_keys=True, separators=(",", ":"))
        decoded = json.loads(encoded)
        self.assertEqual(decoded["schema"], "swarm-work-route-receipt/v1")


if __name__ == "__main__":
    unittest.main()
