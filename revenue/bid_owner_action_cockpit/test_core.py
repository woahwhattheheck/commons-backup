from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone

from .core import ValidationError, canonical_json_bytes, compile_cockpit, load_json_bytes, render_markdown, verify_cockpit

T0 = datetime(2026, 9, 13, 22, 0, 0, tzinfo=timezone.utc)
H = "a" * 64
H2 = "b" * 64
H4 = "d" * 64
POLICY = {"max_source_age_minutes": 1440, "critical_window_minutes": 1440, "high_window_minutes": 4320}


def evidence(ref="ev"):
    return [{"ref": ref, "sha256": H4}]


def gate(gid, action, label, req=H, generation=1, category="LEGAL", status="MISSING", blocking=True, owner=True, prereq=None, ev=None):
    return {
        "id": gid,
        "action_key": action,
        "action_label": label,
        "requirement_sha256": req,
        "generation": generation,
        "category": category,
        "status": status,
        "blocking": blocking,
        "owner_required": owner,
        "evidence": evidence(gid) if ev is None and status == "PROVEN" else (ev or []),
        "prerequisites": prereq or [],
    }


def opp(oid, deadline_hours=24, complete=True, captured_minutes_ago=5, route="PRIME", gates=None):
    deadline = None if deadline_hours is None else (T0 + timedelta(hours=deadline_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    captured = (T0 - timedelta(minutes=captured_minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "id": oid,
        "owner_ref": "owner-" + oid,
        "route_state": route,
        "deadline_utc": deadline,
        "source": {"packet_id": "source-" + oid, "packet_sha256": H2, "captured_at": captured, "complete": complete},
        "gates": gates or [],
    }


def packet(opps=None):
    return {"schema_version": 1, "snapshot_id": "snapshot-1", "opportunities": opps or [opp("alpha", gates=[gate("g1", "LEGAL_ENTITY", "Confirm legal entity")])]}


class CockpitTests(unittest.TestCase):
    def compile(self, p=None, now=T0):
        return compile_cockpit(p or packet(), POLICY, as_of=now)

    def test_owner_action_now(self):
        out = self.compile()
        row = next(r for r in out["rows"] if r["action_key"] == "LEGAL_ENTITY")
        self.assertEqual("OWNER_ACTION_NOW", row["state"])
        self.assertEqual("CRITICAL", row["priority_band"])
        self.assertFalse(out["authority"]["external_actions_authorized"])

    def test_shared_exact_requirement_aggregates(self):
        a = opp("alpha", 20, gates=[gate("a1", "SIGNED_FORM", "Sign owner form", H, 2, "SIGNATURE")])
        b = opp("beta", 48, gates=[gate("b1", "SIGNED_FORM", "Sign owner form", H, 2, "SIGNATURE")])
        rows = [r for r in self.compile(packet([a, b]))["rows"] if r["action_key"] == "SIGNED_FORM"]
        self.assertEqual(1, len(rows))
        self.assertEqual(["alpha", "beta"], rows[0]["affected_opportunity_ids"])

    def test_same_label_different_requirement_never_aggregates(self):
        a = opp("alpha", gates=[gate("a1", "W9_FORM", "Complete tax form", H, 1, "TAX")])
        b = opp("beta", gates=[gate("b1", "W9_FORM", "Complete tax form", H2, 1, "TAX")])
        rows = [r for r in self.compile(packet([a, b]))["rows"] if r["action_key"] == "W9_FORM"]
        self.assertEqual(2, len(rows))
        self.assertTrue(all("INCOMPATIBLE_ACTION_VARIANTS_EXIST" in r["reason_codes"] for r in rows))

    def test_same_req_different_generation_never_aggregates(self):
        a = opp("alpha", gates=[gate("a1", "FORM", "Form", H, 1)])
        b = opp("beta", gates=[gate("b1", "FORM", "Form", H, 2)])
        rows = [r for r in self.compile(packet([a, b]))["rows"] if r["action_key"] == "FORM"]
        self.assertEqual(2, len(rows))

    def test_proven_does_not_cure_missing_peer(self):
        a = opp("alpha", gates=[gate("a1", "FORM", "Form", H, status="PROVEN")])
        b = opp("beta", gates=[gate("b1", "FORM", "Form", H, status="MISSING")])
        row = next(r for r in self.compile(packet([a, b]))["rows"] if r["action_key"] == "FORM")
        self.assertEqual("OWNER_ACTION_NOW", row["state"])

    def test_pending_external_waits(self):
        p = packet([opp("alpha", gates=[gate("g1", "PARTNER_LETTER", "Await partner letter", category="PARTNER", status="PENDING_EXTERNAL", owner=False)])])
        row = next(r for r in self.compile(p)["rows"] if r["action_key"] == "PARTNER_LETTER")
        self.assertEqual("WAIT_EXTERNAL", row["state"])

    def test_hold_gate_holds(self):
        p = packet([opp("alpha", gates=[gate("g1", "FINANCE", "Review finance evidence", category="FINANCE", status="HOLD")])])
        row = next(r for r in self.compile(p)["rows"] if r["action_key"] == "FINANCE")
        self.assertEqual("HOLD", row["state"])

    def test_non_owner_missing_is_prep(self):
        p = packet([opp("alpha", gates=[gate("g1", "PACK", "Prepare packet", owner=False)])])
        row = next(r for r in self.compile(p)["rows"] if r["action_key"] == "PACK")
        self.assertEqual("OWNER_PREP_REQUIRED", row["state"])

    def test_dependency_blocked(self):
        g1 = gate("identity", "IDENTITY", "Confirm identity")
        g2 = gate("sign", "SIGN", "Sign certification", prereq=["identity"], category="SIGNATURE")
        row = next(r for r in self.compile(packet([opp("alpha", gates=[g1, g2])]))["rows"] if r["action_key"] == "SIGN")
        self.assertEqual("DEPENDENCY_BLOCKED", row["state"])

    def test_dependency_unblocked_when_proven(self):
        g1 = gate("identity", "IDENTITY", "Confirm identity", status="PROVEN")
        g2 = gate("sign", "SIGN", "Sign certification", prereq=["identity"], category="SIGNATURE")
        row = next(r for r in self.compile(packet([opp("alpha", gates=[g1, g2])]))["rows"] if r["action_key"] == "SIGN")
        self.assertEqual("OWNER_ACTION_NOW", row["state"])

    def test_source_incomplete_suppresses_gate_trust(self):
        out = self.compile(packet([opp("alpha", complete=False, gates=[gate("g1", "FORM", "Form")])]))
        self.assertTrue(any(r["state"] == "SOURCE_REFRESH_REQUIRED" for r in out["rows"]))
        self.assertFalse(any(r["action_key"] == "FORM" for r in out["rows"]))

    def test_source_stale_suppresses_gate_trust(self):
        out = self.compile(packet([opp("alpha", captured_minutes_ago=1441, gates=[gate("g1", "FORM", "Form")])]))
        self.assertEqual("SOURCE_REFRESH_REQUIRED", out["rows"][0]["state"])
        self.assertIn("SOURCE_STALE", out["rows"][0]["reason_codes"])

    def test_source_exact_age_is_current(self):
        p = packet([opp("alpha", captured_minutes_ago=1440, gates=[gate("g1", "FORM", "Form")])])
        self.assertTrue(any(r["action_key"] == "FORM" for r in self.compile(p)["rows"]))

    def test_future_source_rejected(self):
        p = packet()
        p["opportunities"][0]["source"]["captured_at"] = (T0 + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.assertRaises(ValidationError):
            self.compile(p)

    def test_expired_deadline_terminal(self):
        out = self.compile(packet([opp("alpha", deadline_hours=-1, gates=[gate("g1", "FORM", "Form")])]))
        self.assertEqual("TERMINAL", out["rows"][0]["state"])
        self.assertIn("DEADLINE_EXPIRED", out["rows"][0]["reason_codes"])

    def test_no_bid_terminal(self):
        p = packet([opp("alpha", route="NO_BID", gates=[gate("g1", "FORM", "Form")])])
        self.assertEqual("TERMINAL", self.compile(p)["rows"][0]["state"])

    def test_missing_prerequisite_rejected(self):
        with self.assertRaises(ValidationError):
            self.compile(packet([opp("alpha", gates=[gate("g1", "FORM", "Form", prereq=["nope"])])]))

    def test_dependency_cycle_rejected(self):
        a = gate("a", "A", "A", prereq=["b"])
        b = gate("b", "B", "B", prereq=["a"])
        with self.assertRaises(ValidationError):
            self.compile(packet([opp("alpha", gates=[a, b])]))

    def test_duplicate_gate_id_across_opportunities_rejected(self):
        a = opp("alpha", gates=[gate("same", "A", "A")])
        b = opp("beta", gates=[gate("same", "B", "B")])
        with self.assertRaises(ValidationError):
            self.compile(packet([a, b]))

    def test_order_invariance(self):
        a = opp("alpha", gates=[gate("a1", "A", "Action A"), gate("a2", "B", "Action B", H2)])
        b = opp("beta", gates=[gate("b1", "A", "Action A")])
        p1 = packet([a, b])
        p2 = packet([copy.deepcopy(b), copy.deepcopy(a)])
        p2["opportunities"][0]["gates"].reverse()
        self.assertEqual(canonical_json_bytes(self.compile(p1)), canonical_json_bytes(self.compile(p2)))

    def test_receipt_tamper_fails(self):
        p = packet()
        out = self.compile(p)
        bad = copy.deepcopy(out)
        bad["rows"][0]["action_label"] = "Changed"
        self.assertFalse(verify_cockpit(p, POLICY, bad, current_as_of=T0))

    def test_verify_exact_current(self):
        p = packet()
        out = self.compile(p)
        self.assertTrue(verify_cockpit(p, POLICY, out, current_as_of=T0 + timedelta(minutes=1)))

    def test_verify_fails_when_priority_band_crosses_time(self):
        p = packet([opp("alpha", deadline_hours=73, gates=[gate("g1", "FORM", "Form")])])
        out = self.compile(p)
        self.assertEqual("NORMAL", next(r for r in out["rows"] if r["action_key"] == "FORM")["priority_band"])
        self.assertFalse(verify_cockpit(p, POLICY, out, current_as_of=T0 + timedelta(hours=2)))

    def test_verify_fails_when_deadline_expires(self):
        p = packet([opp("alpha", deadline_hours=1, gates=[gate("g1", "FORM", "Form")])])
        self.assertFalse(verify_cockpit(p, POLICY, self.compile(p), current_as_of=T0 + timedelta(hours=2)))

    def test_verify_fails_when_source_becomes_stale(self):
        p = packet([opp("alpha", captured_minutes_ago=1430, deadline_hours=None, gates=[gate("g1", "FORM", "Form")])])
        self.assertFalse(verify_cockpit(p, POLICY, self.compile(p), current_as_of=T0 + timedelta(minutes=20)))

    def test_markdown_deterministic(self):
        out = self.compile()
        self.assertEqual(render_markdown(out), render_markdown(copy.deepcopy(out)))
        self.assertIn("owner decision support only", render_markdown(out))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ValidationError):
            load_json_bytes(b'{"schema_version":1,"schema_version":1}')

    def test_bool_as_generation_rejected(self):
        p = packet()
        p["opportunities"][0]["gates"][0]["generation"] = True
        with self.assertRaises(ValidationError):
            self.compile(p)

    def test_unknown_field_rejected(self):
        p = packet()
        p["opportunities"][0]["gates"][0]["surprise"] = 1
        with self.assertRaises(ValidationError):
            self.compile(p)

    def test_proven_requires_evidence(self):
        p = packet()
        p["opportunities"][0]["gates"][0]["status"] = "PROVEN"
        with self.assertRaises(ValidationError):
            self.compile(p)

    def test_not_applicable_cannot_block(self):
        p = packet()
        p["opportunities"][0]["gates"][0]["status"] = "NOT_APPLICABLE"
        with self.assertRaises(ValidationError):
            self.compile(p)

    def test_critical_source_refresh_sorts_first(self):
        stale = opp("urgent", deadline_hours=2, complete=False, gates=[gate("u1", "FORM", "Form")])
        normal = opp("later", deadline_hours=100, gates=[gate("l1", "LEGAL", "Legal")])
        self.assertEqual("source:urgent", self.compile(packet([normal, stale]))["rows"][0]["row_id"])

    def test_unlock_breadth_makes_high_priority(self):
        opps = [
            opp("a", deadline_hours=None, gates=[gate("a1", "COMMON", "Common action")]),
            opp("b", deadline_hours=None, gates=[gate("b1", "COMMON", "Common action")]),
            opp("c", deadline_hours=None, gates=[gate("c1", "COMMON", "Common action")]),
        ]
        row = next(r for r in self.compile(packet(opps))["rows"] if r["action_key"] == "COMMON")
        self.assertEqual("HIGH", row["priority_band"])

    def test_category_projection(self):
        p = packet([opp("alpha", gates=[gate("g1", "TAX1", "Tax", category="TAX"), gate("g2", "LEGAL1", "Legal", H2, category="LEGAL")])])
        out = self.compile(p)
        self.assertIn("TAX", out["category_projection"])
        self.assertIn("LEGAL", out["category_projection"])

    def test_same_action_key_category_difference_is_variant(self):
        a = opp("a", gates=[gate("a1", "SAME", "Same", category="LEGAL")])
        b = opp("b", gates=[gate("b1", "SAME", "Same", category="TAX")])
        rows = [r for r in self.compile(packet([a, b]))["rows"] if r["action_key"] == "SAME"]
        self.assertEqual(2, len(rows))
        self.assertTrue(all("INCOMPATIBLE_ACTION_VARIANTS_EXIST" in r["reason_codes"] for r in rows))

    def test_same_identity_label_drift_rejected(self):
        a = opp("a", gates=[gate("a1", "SAME", "Label one", category="LEGAL")])
        b = opp("b", gates=[gate("b1", "SAME", "Label two", category="LEGAL")])
        with self.assertRaises(ValidationError):
            self.compile(packet([a, b]))

    def test_variant_row_ids_are_unique(self):
        a = opp("a", gates=[gate("a1", "SAME", "Same", category="LEGAL")])
        b = opp("b", gates=[gate("b1", "SAME", "Same", category="TAX")])
        rows = [r for r in self.compile(packet([a, b]))["rows"] if r["action_key"] == "SAME"]
        self.assertEqual(len(rows), len({r["row_id"] for r in rows}))


if __name__ == "__main__":
    unittest.main()
