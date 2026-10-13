import copy
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import router

AS_OF = dt.datetime(2026, 9, 14, 3, 20, 0, tzinfo=dt.timezone.utc)
H = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64


def org(org_id, scope, tags, *, relationship="UNCONTACTED", route="LIVE", authority=True, signal="PUBLISHED_NEED", observed="2026-09-14T02:00:00Z"):
    return {
        "org_id": org_id,
        "buyer_scope": scope,
        "relationship_state": relationship,
        "relationship_generation_sha256": H,
        "relationship_observed_at": observed,
        "route_state": route,
        "route_evidence_sha256": B,
        "named_decision_authority": authority,
        "decision_authority_evidence_sha256": C,
        "buying_signal": signal,
        "pain_tags": tags,
        "pain_evidence_sha256": D,
    }


def offer(offer_id, family, tags, price, *, proof=True, fulfillment=True, pay="READY", label=None):
    return {
        "offer_id": offer_id,
        "offer_generation_sha256": H,
        "family": family,
        "price_minor": price,
        "currency": "USD",
        "paid_scope_label": label or f"Paid {offer_id} fixed-scope engagement",
        "scope_sha256": B,
        "acceptance_criteria_sha256": C,
        "fit_tags": tags,
        "proof_ready": proof,
        "proof_evidence_sha256": D,
        "fulfillment_ready": fulfillment,
        "fulfillment_evidence_sha256": E,
        "payment_path_state": pay,
        "payment_path_evidence_sha256": F,
    }


def packet():
    return {
        "schema": router.INPUT_SCHEMA,
        "campaign": {
            "campaign_id": "synthetic-sept14",
            "campaign_generation_sha256": H,
            "max_selected_total": 3,
        },
        "policy": {
            "max_source_age_hours": 48,
            "max_per_family": {"SERVICE": 2, "PRODUCT": 1, "EXPERTISE": 1, "DATA": 1},
            "max_per_offer": {"evidence-diagnostic": 2, "room-turn": 1, "agent-survival": 1},
        },
        "organizations": [
            org("org-alpha", "scope-alpha", ["evidence", "compliance"], signal="ACTIVE_PROCUREMENT"),
            org("org-beta", "scope-beta", ["hospitality", "room-turn"]),
            org("org-gamma", "scope-gamma", ["agents", "reliability"], signal="PUBLIC_PAIN"),
            org("org-hot", "scope-hot", ["evidence"], relationship="HOT_REQUIRES_OWNER", signal="ACTIVE_PROCUREMENT"),
            org("org-wait", "scope-wait", ["agents"], relationship="WAITING_REPLY"),
            org("org-dead", "scope-dead", ["hospitality"], route="DEAD"),
        ],
        "offers": [
            offer("evidence-diagnostic", "SERVICE", ["evidence", "compliance"], 350000),
            offer("room-turn", "SERVICE", ["hospitality", "room-turn"], 250000),
            offer("agent-survival", "EXPERTISE", ["agents", "reliability"], 1500000),
        ],
    }


class RouterTests(unittest.TestCase):
    def test_one_offer_per_org(self):
        p = packet()
        p["offers"].append(offer("evidence-alt", "PRODUCT", ["evidence"], 900000))
        p["policy"]["max_per_offer"]["evidence-alt"] = 2
        result = router.compile_portfolio(p, as_of=AS_OF)
        selected = [r for r in result["selected"] if r["org_id"] == "org-alpha"]
        self.assertEqual(1, len(selected))
        self.assertEqual("evidence-diagnostic", selected[0]["offer_id"])

    def test_hot_wait_and_active_relationships_are_suppressed(self):
        p = packet()
        p["organizations"].append(org("org-active", "scope-active", ["evidence"], relationship="ACTIVE_OUTREACH"))
        result = router.compile_portfolio(p, as_of=AS_OF)
        for org_id in ("org-hot", "org-wait", "org-active"):
            rows = [r for r in result["decisions"] if r["org_id"] == org_id]
            self.assertTrue(rows)
            self.assertTrue(all(r["state"] == "HOLD" for r in rows))
            self.assertTrue(any(any(x.startswith("RELATIONSHIP_") for x in r["reason_codes"]) for r in rows))

    def test_dead_route_is_not_rejection(self):
        result = router.compile_portfolio(packet(), as_of=AS_OF)
        rows = [r for r in result["decisions"] if r["org_id"] == "org-dead"]
        self.assertTrue(all("ROUTE_DEAD" in r["reason_codes"] for r in rows))
        self.assertFalse(any(any("HARD_DNR" in x for x in r["reason_codes"]) for r in rows))

    def test_missing_proof_fulfillment_or_payment_holds(self):
        p = packet()
        p["offers"].append(offer("weak", "DATA", ["evidence"], 99000000, proof=False, fulfillment=False, pay="UNKNOWN"))
        p["policy"]["max_per_offer"]["weak"] = 10
        result = router.compile_portfolio(p, as_of=AS_OF)
        row = next(r for r in result["decisions"] if r["org_id"] == "org-alpha" and r["offer_id"] == "weak")
        self.assertEqual("HOLD", row["state"])
        self.assertEqual({"PROOF_NOT_READY", "FULFILLMENT_NOT_READY", "PAYMENT_PATH_UNKNOWN"}, set(row["reason_codes"]))

    def test_price_cannot_override_better_fit(self):
        p = packet()
        p["offers"].append(offer("expensive-loose-fit", "PRODUCT", ["evidence"], 99999999))
        p["policy"]["max_per_offer"]["expensive-loose-fit"] = 3
        result = router.compile_portfolio(p, as_of=AS_OF)
        alpha = next(r for r in result["selected"] if r["org_id"] == "org-alpha")
        self.assertEqual("evidence-diagnostic", alpha["offer_id"])

    def test_campaign_capacity(self):
        p = packet()
        p["campaign"]["max_selected_total"] = 1
        result = router.compile_portfolio(p, as_of=AS_OF)
        self.assertEqual(1, result["summary"]["selected_count"])
        self.assertTrue(any("CAMPAIGN_CAPACITY_REACHED" in r["reason_codes"] for r in result["decisions"]))

    def test_family_capacity(self):
        p = packet()
        p["policy"]["max_per_family"]["SERVICE"] = 1
        result = router.compile_portfolio(p, as_of=AS_OF)
        service_selected = [r for r in result["selected"] if r["family"] == "SERVICE"]
        self.assertEqual(1, len(service_selected))
        self.assertTrue(any("FAMILY_CAPACITY_REACHED" in r["reason_codes"] for r in result["decisions"]))

    def test_scarcity_preserves_campaign_capacity(self):
        p = {
            "schema": router.INPUT_SCHEMA,
            "campaign": {"campaign_id": "scarcity", "campaign_generation_sha256": H, "max_selected_total": 2},
            "policy": {
                "max_source_age_hours": 48,
                "max_per_family": {"SERVICE": 2},
                "max_per_offer": {"offer-a": 1, "offer-b": 1},
            },
            "organizations": [
                org("org-flex", "scope-flex", ["a", "b"]),
                org("org-only", "scope-only", ["a"]),
            ],
            "offers": [
                offer("offer-a", "SERVICE", ["a"], 500000),
                offer("offer-b", "SERVICE", ["b"], 400000),
            ],
        }
        result = router.compile_portfolio(p, as_of=AS_OF)
        self.assertEqual(2, result["summary"]["selected_count"])
        pairs = {(r["org_id"], r["offer_id"]) for r in result["selected"]}
        self.assertEqual({("org-only", "offer-a"), ("org-flex", "offer-b")}, pairs)

    def test_stale_source_holds(self):
        p = packet()
        p["organizations"][0]["relationship_observed_at"] = "2026-09-01T00:00:00Z"
        result = router.compile_portfolio(p, as_of=AS_OF)
        rows = [r for r in result["decisions"] if r["org_id"] == "org-alpha"]
        self.assertTrue(all("SOURCE_REFRESH_REQUIRED" in r["reason_codes"] for r in rows))

    def test_future_source_rejected(self):
        p = packet()
        p["organizations"][0]["relationship_observed_at"] = "2026-09-15T00:00:00Z"
        with self.assertRaises(router.RouterError):
            router.compile_portfolio(p, as_of=AS_OF)

    def test_duplicate_buyer_scope_rejected(self):
        p = packet()
        p["organizations"][1]["buyer_scope"] = p["organizations"][0]["buyer_scope"]
        with self.assertRaises(router.RouterError):
            router.compile_portfolio(p, as_of=AS_OF)

    def test_bool_int_alias_rejected(self):
        p = packet()
        p["offers"][0]["price_minor"] = True
        with self.assertRaises(router.RouterError):
            router.compile_portfolio(p, as_of=AS_OF)

    def test_unknown_field_rejected(self):
        p = packet()
        p["organizations"][0]["email"] = "nobody@example.invalid"
        with self.assertRaises(router.RouterError):
            router.compile_portfolio(p, as_of=AS_OF)

    def test_pii_address_in_scope_label_rejected(self):
        p = packet()
        p["offers"][0]["paid_scope_label"] = "Email buyer@example.com for paid work"
        with self.assertRaises(router.RouterError):
            router.compile_portfolio(p, as_of=AS_OF)

    def test_order_invariance(self):
        p1 = packet()
        p2 = packet()
        p2["organizations"] = list(reversed(p2["organizations"]))
        p2["offers"] = list(reversed(p2["offers"]))
        self.assertEqual(
            router.canonical_bytes(router.compile_portfolio(p1, as_of=AS_OF)),
            router.canonical_bytes(router.compile_portfolio(p2, as_of=AS_OF)),
        )

    def test_no_external_authority(self):
        result = router.compile_portfolio(packet(), as_of=AS_OF)
        self.assertFalse(result["authority"]["external_send_authorized"])
        self.assertTrue(all(not r["external_send_authorized"] for r in result["decisions"]))
        self.assertTrue(all(not r["buyer_acceptance_evidenced"] for r in result["decisions"]))
        self.assertTrue(all(not r["payment_evidenced"] for r in result["decisions"]))
        self.assertTrue(all(not r["revenue_evidenced"] for r in result["decisions"]))

    def test_receipt_and_tamper_verification(self):
        p = packet()
        result = router.compile_portfolio(p, as_of=AS_OF)
        self.assertTrue(router.verify_portfolio(p, result, as_of=AS_OF))
        tampered = copy.deepcopy(result)
        tampered["selected"][0]["price_minor"] += 1
        self.assertFalse(router.verify_portfolio(p, tampered, as_of=AS_OF))

    def test_verifier_allows_later_trusted_time_while_source_current(self):
        p = packet()
        result = router.compile_portfolio(p, as_of=AS_OF)
        later = AS_OF + dt.timedelta(hours=1)
        self.assertTrue(router.verify_portfolio(p, result, as_of=later))

    def test_verifier_expires_when_source_freshness_expires(self):
        p = packet()
        result = router.compile_portfolio(p, as_of=AS_OF)
        later = AS_OF + dt.timedelta(hours=72)
        self.assertFalse(router.verify_portfolio(p, result, as_of=later))

    def test_duplicate_json_key_rejected(self):
        raw = b'{"schema":"x","schema":"y"}'
        with self.assertRaises(router.RouterError):
            router.load_json_strict_bytes(raw)

    def test_cli_create_exclusive(self):
        p = packet()
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in.json"
            out = Path(td) / "out.json"
            md = Path(td) / "out.md"
            inp.write_bytes(router.canonical_bytes(p))
            rc = router.cli(["compile", "--input", str(inp), "--json-out", str(out), "--md-out", str(md)])
            self.assertEqual(0, rc)
            rc2 = router.cli(["compile", "--input", str(inp), "--json-out", str(out), "--md-out", str(md)])
            self.assertEqual(2, rc2)

    def test_markdown_names_selected_paid_scope(self):
        result = router.compile_portfolio(packet(), as_of=AS_OF)
        md = router.render_markdown(result)
        self.assertIn("no send authority", md)
        self.assertIn("$", md)
        self.assertIn("evidence-diagnostic", md)


if __name__ == "__main__":
    unittest.main()
