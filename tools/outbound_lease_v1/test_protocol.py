from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from tools.outbound_lease_v1.protocol import (  # noqa: E402
    CHANNEL_ID,
    PROTOCOL_ROOT_TS,
    LeaseError,
    compile_snapshot,
    organization_key,
    purpose_fingerprint,
    render_intent,
    route_fingerprint,
    strict_loads,
)


def msg(ts: str, text: str, *, root: bool = True):
    return {"ts": ts, "is_root": root, "text": text}


def snap(messages, candidate, **overrides):
    value = {
        "schema": "outbound-lease-v1/snapshot",
        "channel_id": CHANNEL_ID,
        "protocol_root_ts": PROTOCOL_ROOT_TS,
        "read_ok": True,
        "history_complete": True,
        "canonical_custody_gate": "CLEAN",
        "provider_gate": "CLEAN",
        "relationship_gate": "CLEAN",
        "dnr_gate": "CLEAN",
        "candidate": candidate,
        "messages": messages,
    }
    value.update(overrides)
    return value


class Keys(unittest.TestCase):
    def test_org_key_normalizes_case_and_trailing_dot(self):
        self.assertEqual(organization_key("Example.COM."), organization_key("example.com"))

    def test_org_key_idna_is_stable(self):
        self.assertEqual(organization_key("bücher.example"), organization_key("xn--bcher-kva.example"))

    def test_org_key_rejects_route_not_domain(self):
        for bad in ["https://example.com", "a@example.com", "example.com/path", "localhost"]:
            with self.subTest(bad=bad), self.assertRaises(LeaseError):
                organization_key(bad)

    def test_same_org_different_routes_share_key(self):
        key = organization_key("systeminnovators.com")
        self.assertEqual(key, organization_key("SYSTEMINNOVATORS.COM"))
        self.assertNotEqual(route_fingerprint("sales@systeminnovators.com"), route_fingerprint("contact-form:systeminnovators.com"))

    def test_fingerprints_are_domain_separated(self):
        text = "same"
        self.assertNotEqual(route_fingerprint(text), purpose_fingerprint(text))


class Grammar(unittest.TestCase):
    def setUp(self):
        self.key = organization_key("example.com")
        self.route = route_fingerprint("sales@example.com")
        self.purpose = purpose_fingerprint("one paid pilot")
        self.intent = render_intent(key=self.key, seat="Z-A", nonce="n1", route=self.route, purpose=self.purpose, source="receipt1")
        self.candidate = {"key": self.key, "seat": "Z-A", "nonce": "n1"}

    def test_earliest_active_intent_wins(self):
        later = render_intent(key=self.key, seat="Z-B", nonce="n2", route=self.route, purpose=self.purpose, source="receipt2")
        report = compile_snapshot(snap([msg("10.000001", self.intent), msg("10.000002", later)], self.candidate))
        self.assertTrue(report["coordination_clean"])
        self.assertEqual(report["winner"]["seat"], "Z-A")

    def test_later_claim_yields(self):
        first = render_intent(key=self.key, seat="Z-B", nonce="n2", route=self.route, purpose=self.purpose, source="receipt2")
        mine = render_intent(key=self.key, seat="Z-A", nonce="n1", route=self.route, purpose=self.purpose, source="receipt1")
        report = compile_snapshot(snap([msg("10.000001", first), msg("10.000002", mine)], self.candidate))
        self.assertFalse(report["coordination_clean"])
        self.assertIn("LATER_CLAIM_YIELDS", report["blockers"])

    def test_unrelated_chatter_is_ignored(self):
        report = compile_snapshot(snap([msg("9.000001", "hello channel"), msg("10.000001", self.intent)], self.candidate))
        self.assertTrue(report["coordination_clean"])

    def test_malformed_recognized_record_fails_closed(self):
        with self.assertRaises(LeaseError):
            compile_snapshot(snap([msg("10.000001", "INTENT v1 nope")], self.candidate))

    def test_intent_must_be_root(self):
        with self.assertRaises(LeaseError):
            compile_snapshot(snap([msg("10.000001", self.intent, root=False)], self.candidate))

    def test_terminal_must_reference_existing_claim(self):
        terminal = f"SENT v1 key={self.key} claim_ts=9.000001 evidence=gmail-1"
        with self.assertRaises(LeaseError):
            compile_snapshot(snap([msg("10.000002", terminal)], self.candidate))

    def test_terminal_must_follow_claim(self):
        terminal = f"SENT v1 key={self.key} claim_ts=10.000001 evidence=gmail-1"
        with self.assertRaises(LeaseError):
            compile_snapshot(snap([msg("10.000001", self.intent), msg("9.999999", terminal)], self.candidate))

    def test_duplicate_primary_terminal_rejected(self):
        sent = f"SENT v1 key={self.key} claim_ts=10.000001 evidence=gmail-1"
        unknown = f"OUTCOME_UNKNOWN v1 key={self.key} claim_ts=10.000001 evidence=uncertain"
        with self.assertRaises(LeaseError):
            compile_snapshot(snap([msg("10.000001", self.intent), msg("10.000002", sent), msg("10.000003", unknown)], self.candidate))

    def test_released_claim_allows_next_generation(self):
        release = f"UNSENT_RELEASED v1 key={self.key} claim_ts=10.000001 evidence=provider-not-attempted"
        mine = render_intent(key=self.key, seat="Z-A", nonce="n2", route=self.route, purpose=self.purpose, source="receipt2")
        candidate = {"key": self.key, "seat": "Z-A", "nonce": "n2"}
        report = compile_snapshot(snap([msg("10.000001", self.intent), msg("10.000002", release), msg("10.000003", mine)], candidate))
        self.assertTrue(report["coordination_clean"])

    def test_outcome_unknown_blocks_retry(self):
        unknown = f"OUTCOME_UNKNOWN v1 key={self.key} claim_ts=10.000001 evidence=provider-timeout"
        mine = render_intent(key=self.key, seat="Z-A", nonce="n2", route=self.route, purpose=self.purpose, source="receipt2")
        candidate = {"key": self.key, "seat": "Z-A", "nonce": "n2"}
        report = compile_snapshot(snap([msg("10.000001", self.intent), msg("10.000002", unknown), msg("10.000003", mine)], candidate))
        self.assertFalse(report["coordination_clean"])
        self.assertIn("OUTCOME_UNKNOWN_BLOCKS_RETRY", report["blockers"])

    def test_sent_requires_relationship_event_for_new_generation(self):
        sent = f"SENT v1 key={self.key} claim_ts=10.000001 evidence=gmail-1"
        mine = render_intent(key=self.key, seat="Z-A", nonce="n2", route=self.route, purpose=self.purpose, source="receipt2")
        candidate = {"key": self.key, "seat": "Z-A", "nonce": "n2"}
        report = compile_snapshot(snap([msg("10.000001", self.intent), msg("10.0000002", sent), msg("10.000003", mine)], candidate))
        self.assertFalse(report["coordination_clean"])
        self.assertIn("PRIOR_SENT_REQUIRES_RELATIONSHIP_EVENT", report["blockers"])

    def test_sent_plus_inbound_and_authorizing_relationship_allows_new_generation(self):
        sent = f"SENT v1 key={self.key} claim_ts=10.000001 evidence=gmail-1"
        inbound = f"INBOUND v1 key={self.key} claim_ts=10.000001 evidence=gmail-reply-1"
        mine = render_intent(key=self.key, seat="Z-A", nonce="n2", route=self.route, purpose=self.purpose, source="receipt2")
        candidate = {"key": self.key, "seat": "Z-A", "nonce": "n2"}
        report = compile_snapshot(snap(
            [msg("10.000001", self.intent), msg("10.000002", sent), msg("10.000003", inbound), msg("10.000004", mine)],
            candidate, relationship_gate="EVENT_AUTHORIZES"))
        self.assertTrue(report["coordination_clean"])

    def test_history_or_read_failure_blocks(self):
        for field in ("history_complete", "read_ok"):
            with self.subTest(field=field):
                report = compile_snapshot(snap([msg("10.000001", self.intent)], self.candidate, **{field: False}))
                self.assertFalse(report["coordination_clean"])

    def test_canonical_custody_gate_blocks(self):
        report = compile_snapshot(snap([msg("10.000001", self.intent)], self.candidate, canonical_custody_gate="UNKNOWN"))
        self.assertFalse(report["coordination_clean"])
        self.assertIn("CANONICAL_CUSTODY_GATE_UNKNOWN", report["blockers"])
        self.assertFalse(report["external_send_authorized"])

    def test_provider_dnr_and_relationship_unknown_block(self):
        cases = [
            {"provider_gate": "BLOCK"},
            {"dnr_gate": "BLOCK"},
            {"relationship_gate": "UNKNOWN"},
        ]
        for override in cases:
            with self.subTest(override=override):
                report = compile_snapshot(snap([msg("10.000001", self.intent)], self.candidate, **override))
                self.assertFalse(report["coordination_clean"])

    def test_candidate_must_exist(self):
        report = compile_snapshot(snap([], self.candidate))
        self.assertFalse(report["coordination_clean"])
        self.assertIn("CANDIDATE_INTENT_MISSING", report["blockers"])

    def test_digest_is_order_stable(self):
        one = compile_snapshot(snap([msg("10.000001", self.intent)], self.candidate))
        two = compile_snapshot(json.loads(json.dumps(snap([msg("10.000001", self.intent)], self.candidate), sort_keys=True)))
        self.assertEqual(one["semantic_sha256"], two["semantic_sha256"])


class StrictJSON(unittest.TestCase):
    def test_duplicate_key_rejected(self):
        with self.assertRaises(LeaseError):
            strict_loads('{"a":1,"a":2}')

    def test_float_and_nonfinite_rejected(self):
        for raw in ('{"a":1.5}', '{"a":NaN}', '{"a":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(LeaseError):
                strict_loads(raw)


class CLI(unittest.TestCase):
    def test_cli_key_and_verify(self):
        key = organization_key("example.com")
        route = route_fingerprint("sales@example.com")
        purpose = purpose_fingerprint("one paid pilot")
        intent = render_intent(key=key, seat="Z-A", nonce="n1", route=route, purpose=purpose, source="receipt1")
        snapshot = snap([msg("10.000001", intent)], {"key": key, "seat": "Z-A", "nonce": "n1"})
        cli = HERE / "cli.py"
        key_run = subprocess.run([sys.executable, str(cli), "org-key", "Example.COM"], text=True, capture_output=True, check=False)
        self.assertEqual(key_run.returncode, 0, key_run.stderr)
        self.assertEqual(key_run.stdout.strip(), key)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "snapshot.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            run = subprocess.run([sys.executable, str(cli), "verify", str(path)], text=True, capture_output=True, check=False)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(json.loads(run.stdout)["coordination_clean"])

    def test_cli_refuses_symlink_input(self):
        cli = HERE / "cli.py"
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "real.json"
            target.write_text("{}", encoding="utf-8")
            link = Path(td) / "link.json"
            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlink unavailable")
            run = subprocess.run([sys.executable, str(cli), "verify", str(link)], text=True, capture_output=True, check=False)
        self.assertEqual(run.returncode, 2)
        self.assertIn("BLOCKED", run.stderr)


if __name__ == "__main__":
    unittest.main()
