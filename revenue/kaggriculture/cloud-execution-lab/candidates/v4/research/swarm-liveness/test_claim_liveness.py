import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

from claim_liveness import (
    AuditError,
    DEFAULT_CANONICAL_ROOT,
    audit_events,
    load_jsonl,
)

NOW = 2_000.0


def e(ts, lane="L", session="A", event="CLAIM", **kw):
    return {"ts": ts, "lane": lane, "session": session, "event": event, **kw}


class ClaimLivenessTests(unittest.TestCase):
    def audit(self, events, **kw):
        return audit_events(events, as_of=NOW, ttl_seconds=100, **kw)

    def row(self, report, lane="L"):
        return next(r for r in report["lanes"] if r["lane"] == lane)

    def test_fresh_claim_active(self):
        r = self.audit([e(1950)])
        self.assertEqual("ACTIVE", self.row(r)["status"])

    def test_stale_claim_is_recovery_candidate_not_authority(self):
        r = self.audit([e(1800)])
        row = self.row(r)
        self.assertEqual("STALE_CLAIM", row["status"])
        self.assertEqual(["A"], row["recovery_candidates"])
        self.assertFalse(r["policy"]["stale_is_overwrite_authority"])

    def test_fresh_owner_blocks_stale_recovery(self):
        r = self.audit([e(1800, session="A"), e(1950, session="B")])
        row = self.row(r)
        self.assertEqual("ACTIVE_WITH_STALE_OWNER", row["status"])
        self.assertEqual([], row["recovery_candidates"])

    def test_two_fresh_owners_collision(self):
        r = self.audit([e(1950, session="A"), e(1960, session="B")])
        self.assertEqual("COLLISION", self.row(r)["status"])
        self.assertEqual(1, r["summary"]["collisions"])

    def test_repeat_active_claim_cannot_reset_epoch_precedence(self):
        r = self.audit([
            e(1910, session="A", event_id="a-open"),
            e(1920, session="B", event_id="b-open"),
            e(1990, session="A", event_id="a-repeat"),
        ])
        row = self.row(r)
        owners = {owner["session"]: owner for owner in row["owners"]}
        self.assertEqual("COLLISION", row["status"])
        self.assertEqual("A", row["arbitration"]["preferred_owner"])
        self.assertEqual(1910.0, owners["A"]["claim_ts"])
        self.assertEqual(1910.0, owners["A"]["last_ts"])
        self.assertIn("repeat_claim_while_active", {a["kind"] for a in r["anomalies"]})
        self.assertFalse(r["policy"]["repeat_active_claims_authoritative"])

    def test_repeat_active_claim_contract_drift_is_anomaly_not_mutation(self):
        r = self.audit([
            e(1950, scope_key="scope-a", requires_artifact=True, artifact="pr#1"),
            e(1960, scope_key="scope-b", requires_artifact=False, artifact="pr#2"),
        ])
        row = self.row(r)
        owner = row["owners"][0]
        kinds = {a["kind"] for a in r["anomalies"]}
        self.assertIn("repeat_claim_while_active", kinds)
        self.assertIn("scope_key_drift", kinds)
        self.assertIn("active_claim_contract_drift", kinds)
        self.assertEqual(1950.0, owner["claim_ts"])
        self.assertEqual(1950.0, owner["last_ts"])
        self.assertEqual("scope-a", owner["scope_key"])
        self.assertEqual("pr#1", owner["artifact"])

    def test_terminal_then_fresh_claim_starts_new_epoch(self):
        r = self.audit([
            e(1800, event_id="open-1"),
            e(1850, event="COMPLETE", event_id="done-1", artifact="pr#1"),
            e(1950, event_id="open-2", scope_key="new-scope"),
        ])
        row = self.row(r)
        owner = row["owners"][0]
        self.assertEqual("ACTIVE", row["status"])
        self.assertEqual(1950.0, owner["claim_ts"])
        self.assertEqual(1950.0, owner["last_ts"])
        self.assertEqual("new-scope", owner["scope_key"])
        self.assertNotIn("repeat_claim_while_active", {a["kind"] for a in r["anomalies"]})

    def test_heartbeat_extends_claim(self):
        r = self.audit([e(1800), e(1990, event="HEARTBEAT")])
        self.assertEqual("ACTIVE", self.row(r)["status"])

    def test_heartbeat_without_claim_is_anomaly(self):
        r = self.audit([e(1990, event="HEARTBEAT")])
        self.assertIn("heartbeat_without_active_claim", {a["kind"] for a in r["anomalies"]})

    def test_complete_closes_claim(self):
        r = self.audit([e(1800), e(1900, event="COMPLETE", artifact="pr#1")])
        self.assertEqual("CLOSED", self.row(r)["status"])
        self.assertEqual({"A": "COMPLETE"}, self.row(r)["terminal_owners"])

    def test_blocked_is_terminal_not_stale(self):
        r = self.audit([e(1700), e(1750, event="BLOCKED")])
        self.assertEqual("CLOSED", self.row(r)["status"])

    def test_required_artifact_is_enforced(self):
        r = self.audit([e(1900, requires_artifact=True), e(1950, event="COMPLETE")])
        self.assertIn("completion_without_required_artifact", {a["kind"] for a in r["anomalies"]})

    def test_terminal_without_claim_is_anomaly(self):
        r = self.audit([e(1950, event="RELEASED")])
        self.assertIn("terminal_without_claim", {a["kind"] for a in r["anomalies"]})

    def test_noncanonical_root_is_anomaly_and_claim_is_quarantined(self):
        r = self.audit([e(1950, canonical_root="main:other/v4")])
        self.assertIn("noncanonical_root", {a["kind"] for a in r["anomalies"]})
        self.assertEqual([], r["lanes"])
        self.assertFalse(r["policy"]["noncanonical_root_events_authoritative"])

    def test_noncanonical_heartbeat_cannot_refresh_canonical_claim(self):
        r = self.audit([
            e(1800, canonical_root=DEFAULT_CANONICAL_ROOT, event_id="claim"),
            e(1990, event="HEARTBEAT", canonical_root="main:other/v4", event_id="beat"),
        ])
        row = self.row(r)
        self.assertEqual("STALE_CLAIM", row["status"])
        self.assertEqual(1800.0, row["owners"][0]["last_ts"])
        self.assertIn("noncanonical_root", {a["kind"] for a in r["anomalies"]})

    def test_noncanonical_terminal_cannot_close_canonical_claim(self):
        r = self.audit([
            e(1950, canonical_root=DEFAULT_CANONICAL_ROOT, event_id="claim"),
            e(1960, event="COMPLETE", canonical_root="main:other/v4", event_id="done"),
        ])
        row = self.row(r)
        self.assertEqual("ACTIVE", row["status"])
        self.assertEqual({}, row["terminal_owners"])
        self.assertEqual(1950.0, row["owners"][0]["last_ts"])

    def test_noncanonical_event_id_cannot_shadow_later_canonical_event(self):
        r = self.audit([
            e(1900, canonical_root="main:other/v4", event_id="x"),
            e(1950, canonical_root=DEFAULT_CANONICAL_ROOT, event_id="x"),
        ])
        self.assertEqual("ACTIVE", self.row(r)["status"])
        kinds = [a["kind"] for a in r["anomalies"]]
        self.assertIn("noncanonical_root", kinds)
        self.assertNotIn("duplicate_event_id", kinds)

    def test_repo_write_requires_exact_root_binding(self):
        r = self.audit([e(1950, writes_repo=True)])
        self.assertIn("repo_write_without_root", {a["kind"] for a in r["anomalies"]})
        self.assertEqual([], r["lanes"])
        self.assertTrue(r["policy"]["repo_writes_require_exact_canonical_root"])
        self.assertFalse(r["policy"]["repo_write_without_canonical_root_authoritative"])

    def test_rootless_repo_write_heartbeat_cannot_refresh(self):
        r = self.audit([
            e(1800, canonical_root=DEFAULT_CANONICAL_ROOT),
            e(1990, event="HEARTBEAT", writes_repo=True),
        ])
        row = self.row(r)
        self.assertEqual("STALE_CLAIM", row["status"])
        self.assertEqual(1800.0, row["owners"][0]["last_ts"])

    def test_rootless_repo_write_terminal_cannot_close(self):
        r = self.audit([
            e(1950, canonical_root=DEFAULT_CANONICAL_ROOT),
            e(1960, event="COMPLETE", writes_repo=True),
        ])
        row = self.row(r)
        self.assertEqual("ACTIVE", row["status"])
        self.assertEqual({}, row["terminal_owners"])

    def test_repo_write_exact_canonical_root_remains_authoritative(self):
        r = self.audit([
            e(1950, writes_repo=True, canonical_root=DEFAULT_CANONICAL_ROOT),
        ])
        self.assertEqual("ACTIVE", self.row(r)["status"])

    def test_writer_epoch_rootless_readonly_heartbeat_is_quarantined_without_id_shadow(self):
        r = self.audit([
            e(1800, writes_repo=True, canonical_root=DEFAULT_CANONICAL_ROOT,
              scope_key="writer-scope", event_id="claim"),
            e(1990, event="HEARTBEAT", writes_repo=False, event_id="x",
              artifact="bad", scope_key="foreign-scope"),
            e(1995, event="HEARTBEAT", writes_repo=False,
              canonical_root=DEFAULT_CANONICAL_ROOT, event_id="x",
              artifact="good", scope_key="writer-scope"),
        ])
        row = self.row(r)
        owner = row["owners"][0]
        kinds = [a["kind"] for a in r["anomalies"]]
        self.assertEqual("ACTIVE", row["status"])
        self.assertEqual(1995.0, owner["last_ts"])
        self.assertEqual("good", owner["artifact"])
        self.assertEqual("writer-scope", owner["scope_key"])
        self.assertTrue(owner["claim_writes_repo"])
        self.assertEqual(DEFAULT_CANONICAL_ROOT, owner["claim_canonical_root"])
        self.assertIn("writer_epoch_followup_root_unbound", kinds)
        self.assertNotIn("duplicate_event_id", kinds)
        self.assertTrue(r["policy"]["writer_epoch_followups_require_claim_root"])
        self.assertFalse(r["policy"]["quarantined_events_reserve_provider_ids"])

    def test_writer_epoch_rootless_terminal_is_quarantined_without_id_shadow(self):
        r = self.audit([
            e(1950, writes_repo=True, canonical_root=DEFAULT_CANONICAL_ROOT,
              requires_artifact=True, event_id="claim"),
            e(1960, event="COMPLETE", writes_repo=False, event_id="done",
              artifact="bad"),
            e(1970, event="COMPLETE", writes_repo=False,
              canonical_root=DEFAULT_CANONICAL_ROOT, event_id="done",
              artifact="good"),
        ])
        row = self.row(r)
        owner = row["owners"][0]
        kinds = [a["kind"] for a in r["anomalies"]]
        self.assertEqual("CLOSED", row["status"])
        self.assertEqual({"A": "COMPLETE"}, row["terminal_owners"])
        self.assertEqual(1970.0, owner["last_ts"])
        self.assertEqual("good", owner["artifact"])
        self.assertIn("writer_epoch_followup_root_unbound", kinds)
        self.assertNotIn("duplicate_event_id", kinds)

    def test_writer_epoch_exact_root_readonly_followup_remains_authoritative(self):
        r = self.audit([
            e(1950, writes_repo=True, canonical_root=DEFAULT_CANONICAL_ROOT),
            e(1990, event="HEARTBEAT", writes_repo=False,
              canonical_root=DEFAULT_CANONICAL_ROOT),
        ])
        row = self.row(r)
        owner = row["owners"][0]
        self.assertEqual("ACTIVE", row["status"])
        self.assertEqual(1990.0, owner["last_ts"])
        self.assertTrue(owner["claim_writes_repo"])
        self.assertEqual(DEFAULT_CANONICAL_ROOT, owner["claim_canonical_root"])

    def test_read_only_epoch_rootless_followups_remain_compatible(self):
        r = self.audit([
            e(1950, writes_repo=False, event_id="claim"),
            e(1960, event="HEARTBEAT", writes_repo=False, event_id="beat"),
            e(1970, event="COMPLETE", writes_repo=False, event_id="done"),
        ])
        row = self.row(r)
        self.assertEqual("CLOSED", row["status"])
        self.assertEqual({"A": "COMPLETE"}, row["terminal_owners"])
        self.assertNotIn(
            "writer_epoch_followup_root_unbound",
            {a["kind"] for a in r["anomalies"]},
        )

    def test_read_only_rootless_event_remains_compatible(self):
        r = self.audit([e(1950, writes_repo=False)])
        self.assertEqual("ACTIVE", self.row(r)["status"])
        self.assertTrue(r["policy"]["read_only_missing_root_authoritative"])

    def test_duplicate_event_id_is_anomaly(self):
        r = self.audit([e(1900, event_id="x"), e(1950, event="HEARTBEAT", event_id="x")])
        self.assertIn("duplicate_event_id", {a["kind"] for a in r["anomalies"]})

    def test_conflicting_duplicate_claim_complete_is_quarantined_in_both_orders(self):
        claim = e(1950, event_id="x")
        complete = e(1960, event="COMPLETE", event_id="x")
        for events in ([claim, complete], [complete, claim]):
            with self.subTest(order=[row["event"] for row in events]):
                r = self.audit(events)
                self.assertEqual([], r["lanes"])
                self.assertEqual(0, r["summary"]["lanes"])
                self.assertIn("duplicate_event_id", {a["kind"] for a in r["anomalies"]})

    def test_duplicate_heartbeat_cannot_refresh_stale_claim(self):
        r = self.audit([
            e(1700, event_id="claim"),
            e(1800, event="HEARTBEAT", event_id="beat"),
            e(1980, event="HEARTBEAT", event_id="beat"),
        ])
        row = self.row(r)
        self.assertEqual("STALE_CLAIM", row["status"])
        self.assertEqual(["A"], row["recovery_candidates"])
        self.assertEqual(1700.0, row["owners"][0]["last_ts"])
        self.assertIn("duplicate_event_id", {a["kind"] for a in r["anomalies"]})
        self.assertFalse(r["policy"]["duplicate_event_id_replays_authoritative"])

    def test_conflicting_duplicate_heartbeats_are_permutation_invariant(self):
        claim = e(1700, event_id="claim")
        old = e(1800, event="HEARTBEAT", event_id="beat")
        fresh = e(1980, event="HEARTBEAT", event_id="beat")
        for events in ([claim, old, fresh], [claim, fresh, old]):
            with self.subTest(order=[row["ts"] for row in events]):
                r = self.audit(events)
                row = self.row(r)
                self.assertEqual("STALE_CLAIM", row["status"])
                self.assertEqual(1700.0, row["owners"][0]["last_ts"])
                self.assertEqual(["A"], row["recovery_candidates"])

    def test_duplicate_claim_cannot_reopen_terminal_epoch(self):
        r = self.audit([
            e(1700, event_id="claim"),
            e(1800, event="COMPLETE", event_id="done", artifact="pr#1"),
            e(1950, event_id="claim"),
        ])
        row = self.row(r)
        self.assertEqual("CLOSED", row["status"])
        self.assertEqual({"A": "COMPLETE"}, row["terminal_owners"])
        self.assertEqual(1800.0, row["owners"][0]["last_ts"])

    def test_timezone_aware_iso_timestamp(self):
        r = audit_events(
            [e("1970-01-01T00:30:00+00:00")],
            as_of="1970-01-01T00:31:00Z",
            ttl_seconds=100,
        )
        self.assertEqual("ACTIVE", self.row(r)["status"])

    def test_boolean_timestamp_rejected(self):
        with self.assertRaises(AuditError):
            self.audit([e(True)])

    def test_future_event_is_anomaly(self):
        r = self.audit([e(2100)])
        self.assertIn("future_event", {a["kind"] for a in r["anomalies"]})

    def test_future_heartbeat_cannot_refresh_stale_claim(self):
        r = self.audit([e(1800), e(2100, event="HEARTBEAT")])
        row = self.row(r)
        self.assertEqual("STALE_CLAIM", row["status"])
        self.assertEqual(["A"], row["recovery_candidates"])
        self.assertEqual(1800.0, row["owners"][0]["last_ts"])
        self.assertFalse(r["policy"]["future_events_authoritative"])

    def test_future_claim_does_not_create_owner_or_lane(self):
        r = self.audit([e(2100, lane="FUTURE")])
        self.assertEqual([], r["lanes"])
        self.assertEqual(0, r["summary"]["lanes"])
        self.assertIn("future_event", {a["kind"] for a in r["anomalies"]})

    def test_future_duplicate_does_not_reserve_event_id(self):
        r = self.audit([
            e(2100, event_id="x"),
            e(1950, event_id="x"),
        ])
        self.assertEqual("ACTIVE", self.row(r)["status"])
        kinds = [a["kind"] for a in r["anomalies"]]
        self.assertEqual(1, kinds.count("future_event"))
        self.assertNotIn("duplicate_event_id", kinds)

    def test_jsonl_comments_and_blank_lines(self):
        rows = load_jsonl(io.StringIO('\n# comment\n{"ts":1,"lane":"L","session":"A","event":"CLAIM"}\n'))
        self.assertEqual(1, len(rows))

    def test_jsonl_duplicate_event_id_key_rejected(self):
        payload = (
            '{"ts":1,"lane":"L","session":"A","event":"CLAIM",'
            '"event_id":"first","event_id":"second"}\n'
        )
        with self.assertRaisesRegex(AuditError, "duplicate JSON object key 'event_id'"):
            load_jsonl(io.StringIO(payload))

    def test_jsonl_duplicate_canonical_root_key_rejected(self):
        payload = (
            '{"ts":1,"lane":"L","session":"A","event":"CLAIM",'
            '"canonical_root":"main:other/v4",'
            '"canonical_root":"main:revenue/kaggriculture/cloud-execution-lab/candidates/v4"}\n'
        )
        with self.assertRaisesRegex(AuditError, "duplicate JSON object key 'canonical_root'"):
            load_jsonl(io.StringIO(payload))

    def test_jsonl_nested_duplicate_key_rejected_recursively(self):
        payload = (
            '{"ts":1,"lane":"L","session":"A","event":"CLAIM",'
            '"metadata":{"source":"slack","source":"github"}}\n'
        )
        with self.assertRaisesRegex(AuditError, "duplicate JSON object key 'source'"):
            load_jsonl(io.StringIO(payload))

    def test_output_is_deterministic_under_lane_input_permutation(self):
        a = self.audit([e(1950, lane="Z"), e(1940, lane="A")])
        b = self.audit([e(1940, lane="A"), e(1950, lane="Z")])
        self.assertEqual(
            json.dumps(a, sort_keys=True, separators=(",", ":")),
            json.dumps(b, sort_keys=True, separators=(",", ":")),
        )

    def test_cli_emits_canonical_json(self):
        here = os.path.dirname(__file__)
        payload = json.dumps(e(1950, canonical_root=DEFAULT_CANONICAL_ROOT)) + "\n"
        proc = subprocess.run(
            [sys.executable, os.path.join(here, "claim_liveness.py"),
             "--as-of", str(NOW), "--ttl-seconds", "100"],
            input=payload, text=True, capture_output=True, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        parsed = json.loads(proc.stdout)
        self.assertEqual("titan-v4-claim-liveness/v1", parsed["schema"])
        self.assertEqual("ACTIVE", parsed["lanes"][0]["status"])

    def test_cli_rejects_duplicate_json_object_keys(self):
        here = os.path.dirname(__file__)
        payload = (
            '{"ts":1950,"lane":"L","session":"A","event":"CLAIM",'
            '"event_id":"first","event_id":"second"}\n'
        )
        proc = subprocess.run(
            [sys.executable, os.path.join(here, "claim_liveness.py"),
             "--as-of", str(NOW), "--ttl-seconds", "100"],
            input=payload, text=True, capture_output=True, check=False,
        )
        self.assertEqual(2, proc.returncode)
        self.assertEqual("", proc.stdout)
        self.assertIn("duplicate JSON object key 'event_id'", proc.stderr)


if __name__ == "__main__":
    unittest.main()
