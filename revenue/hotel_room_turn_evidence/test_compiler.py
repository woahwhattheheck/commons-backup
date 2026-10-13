#!/usr/bin/env python3
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    from . import compiler as c
except ImportError:  # direct execution from the product directory
    import compiler as c  # type: ignore


HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
NOW = dt.datetime(2026, 9, 13, 15, 30, tzinfo=dt.timezone.utc)
LATER = dt.datetime(2026, 9, 13, 17, 30, tzinfo=dt.timezone.utc)


def load(name: str):
    return c.loads_strict((FIXTURES / name).read_bytes())


class HotelRoomTurnEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load("policy.json")
        self.evidence = load("evidence.json")
        self.report = c.compile_report(
            self.policy,
            self.evidence,
            expected_policy_sha256=c.RETAINED_POLICY_SHA256,
            now=NOW,
        )
        self.receipt = c.report_receipt(self.report)

    def compile(self, evidence=None, policy=None, now=NOW, policy_sha=None):
        use_policy = copy.deepcopy(self.policy if policy is None else policy)
        use_evidence = copy.deepcopy(self.evidence if evidence is None else evidence)
        use_sha = policy_sha or hashlib.sha256(c.canon(use_policy)).hexdigest()
        return c.compile_report(
            use_policy,
            use_evidence,
            expected_policy_sha256=use_sha,
            now=now,
        )

    def room(self, report, room_id):
        return next(room for room in report["rooms"] if room["room_id"] == room_id)

    def test_retained_policy_bytes_match_compiled_root(self):
        raw, parsed = c.load_retained_policy()
        self.assertEqual(
            hashlib.sha256(c.canon(raw)).hexdigest(),
            c.RETAINED_POLICY_SHA256,
        )
        self.assertEqual(parsed["policy_sha256"], c.RETAINED_POLICY_SHA256)

    def test_frozen_fixture_decisions(self):
        self.assertEqual(self.report["summary"], {"ready": 2, "blocked": 4, "total": 6})
        self.assertEqual(self.room(self.report, "101")["status"], "READY")
        self.assertEqual(self.room(self.report, "102")["status"], "READY")
        self.assertIn(
            "BLOCK_HOUSEKEEPING:DIRTY",
            self.room(self.report, "103")["reasons"],
        )
        self.assertIn(
            "MISSING_MANAGER_RELEASE",
            self.room(self.report, "103")["reasons"],
        )
        self.assertIn(
            "STALE_HOUSEKEEPING",
            self.room(self.report, "104")["reasons"],
        )
        self.assertIn(
            "CONFLICT_MAINTENANCE",
            self.room(self.report, "105")["reasons"],
        )
        self.assertIn(
            "WRONG_TURN_MANAGER_RELEASE:1",
            self.room(self.report, "106")["reasons"],
        )

    def test_exact_replay_is_idempotent(self):
        without_duplicate = copy.deepcopy(self.evidence)
        without_duplicate["events"].pop()
        self.assertEqual(self.compile(without_duplicate), self.report)

    def test_changed_replay_is_rejected(self):
        hostile = copy.deepcopy(self.evidence)
        duplicate = hostile["events"][-1]
        self.assertEqual(duplicate["event_id"], "e102-mgr")
        duplicate["detail_code"] = "CHANGED"
        with self.assertRaisesRegex(c.ContractError, "replay content mismatch"):
            self.compile(hostile)

    def test_input_order_is_deterministic(self):
        reordered = copy.deepcopy(self.evidence)
        reordered["events"] = list(reversed(reordered["events"]))
        self.assertEqual(c.canon(self.compile(reordered)), c.canon(self.report))

    def test_duplicate_json_key_is_rejected(self):
        with self.assertRaisesRegex(c.ContractError, "duplicate JSON key"):
            c.loads_strict('{"a":1,"a":2}')

    def test_property_mismatch_is_rejected(self):
        hostile = copy.deepcopy(self.evidence)
        hostile["property_id"] = "OTHER"
        with self.assertRaisesRegex(c.ContractError, "property_id mismatch"):
            self.compile(hostile)

    def test_unknown_room_is_rejected(self):
        hostile = copy.deepcopy(self.evidence)
        event = copy.deepcopy(hostile["events"][0])
        event["event_id"] = "unknown-room-event"
        event["room_id"] = "999"
        hostile["events"].append(event)
        with self.assertRaisesRegex(c.ContractError, "unknown rooms"):
            self.compile(hostile)

    def test_unauthorized_manager_fails_closed(self):
        hostile = copy.deepcopy(self.evidence)
        event = next(
            event for event in hostile["events"] if event["event_id"] == "e101-mgr"
        )
        event["actor_id"] = "intruder-manager"
        report = self.compile(hostile)
        self.assertIn("UNAUTHORIZED_MANAGER", self.room(report, "101")["reasons"])

    def test_future_event_fails_closed(self):
        hostile = copy.deepcopy(self.evidence)
        event = next(
            event for event in hostile["events"] if event["event_id"] == "e101-hk"
        )
        event["observed_at"] = "2026-09-13T15:31:00Z"
        report = self.compile(hostile)
        self.assertIn("FUTURE_HOUSEKEEPING", self.room(report, "101")["reasons"])

    def test_policy_hash_mismatch_is_rejected(self):
        with self.assertRaisesRegex(c.ContractError, "policy sha256 mismatch"):
            c.compile_report(
                self.policy,
                self.evidence,
                expected_policy_sha256="0" * 64,
                now=NOW,
            )

    def test_commercial_bool_int_alias_is_rejected(self):
        hostile = copy.deepcopy(self.policy)
        hostile["price_usd"] = True
        digest = hashlib.sha256(c.canon(hostile)).hexdigest()
        with self.assertRaisesRegex(c.ContractError, "must be integer"):
            c.compile_report(
                hostile,
                self.evidence,
                expected_policy_sha256=digest,
                now=NOW,
            )

    def test_report_embedded_tamper_is_rejected(self):
        hostile = copy.deepcopy(self.report)
        hostile["summary"]["ready"] = 99
        with self.assertRaises(c.ContractError):
            c.verify_report_history(
                hostile,
                expected_policy_sha256=c.RETAINED_POLICY_SHA256,
                expected_report_sha256=self.receipt,
            )

    def test_resealed_report_still_fails_retained_receipt(self):
        hostile = copy.deepcopy(self.report)
        hostile["generated_at"] = "2026-09-13T15:31:00Z"
        core = dict(hostile)
        del core["report_sha256"]
        hostile["report_sha256"] = hashlib.sha256(c.canon(core)).hexdigest()
        with self.assertRaisesRegex(c.ContractError, "retained receipt mismatch"):
            c.verify_report_history(
                hostile,
                expected_policy_sha256=c.RETAINED_POLICY_SHA256,
                expected_report_sha256=self.receipt,
            )

    def test_historical_integrity_is_explicitly_not_current_readiness(self):
        verified = c.verify_report_history(
            self.report,
            expected_policy_sha256=c.RETAINED_POLICY_SHA256,
            expected_report_sha256=self.receipt,
        )
        self.assertEqual(verified["summary"]["ready"], 2)
        current = c.replay_current(
            self.report,
            self.evidence,
            expected_report_sha256=self.receipt,
            now=LATER,
            retained_policy_raw=self.policy,
        )
        self.assertEqual(current["summary"]["ready"], 0)

    def test_previously_ready_room_cannot_render_as_current_ready_after_ttl(self):
        current = c.replay_current(
            self.report,
            self.evidence,
            expected_report_sha256=self.receipt,
            now=LATER,
            retained_policy_raw=self.policy,
        )
        rendered = c.render_current_markdown(
            current,
            historical_report_sha256=self.receipt,
        ).decode("utf-8")
        self.assertIn("Current READY: **0**", rendered)
        self.assertNotIn("| 101 | turn-101-20260913 | READY |", rendered)
        self.assertIn("| 101 | turn-101-20260913 | BLOCKED |", rendered)
        self.assertIn("STALE_HOUSEKEEPING", rendered)

    def test_current_replay_rejects_different_evidence(self):
        hostile = copy.deepcopy(self.evidence)
        event = next(
            event for event in hostile["events"] if event["event_id"] == "e101-hk"
        )
        event["detail_code"] = "CHANGED"
        with self.assertRaisesRegex(c.ContractError, "evidence binding"):
            c.replay_current(
                self.report,
                hostile,
                expected_report_sha256=self.receipt,
                now=NOW,
                retained_policy_raw=self.policy,
            )

    def test_rewritten_policy_with_matching_new_root_is_not_production_authority(self):
        hostile_policy = copy.deepcopy(self.policy)
        hostile_policy["allowed_managers"].append("intruder-manager")
        hostile_policy["max_age_minutes"] = {
            "housekeeping": 1440,
            "maintenance": 1440,
            "manager_release": 1440,
        }
        hostile_sha = hashlib.sha256(c.canon(hostile_policy)).hexdigest()
        hostile_report = c.compile_report(
            hostile_policy,
            self.evidence,
            expected_policy_sha256=hostile_sha,
            now=LATER,
        )
        hostile_receipt = c.report_receipt(hostile_report)
        with self.assertRaisesRegex(c.ContractError, "policy root mismatch"):
            c.replay_current(
                hostile_report,
                self.evidence,
                expected_report_sha256=hostile_receipt,
                now=LATER,
                retained_policy_raw=self.policy,
            )

    def test_current_replay_rejects_report_property_drift_even_if_resealed(self):
        hostile = copy.deepcopy(self.report)
        hostile["property_id"] = "ATTACKER-PROPERTY"
        core = dict(hostile)
        del core["report_sha256"]
        hostile["report_sha256"] = hashlib.sha256(c.canon(core)).hexdigest()
        hostile_receipt = c.report_receipt(hostile)
        with self.assertRaisesRegex(c.ContractError, "property differs"):
            c.replay_current(
                hostile,
                self.evidence,
                expected_report_sha256=hostile_receipt,
                now=NOW,
                retained_policy_raw=self.policy,
            )

    def test_current_replay_rejects_report_scope_drift_even_if_resealed(self):
        hostile = copy.deepcopy(self.report)
        hostile["rooms"][0]["turn_id"] = "attacker-turn"
        core = dict(hostile)
        del core["report_sha256"]
        hostile["report_sha256"] = hashlib.sha256(c.canon(core)).hexdigest()
        hostile_receipt = c.report_receipt(hostile)
        with self.assertRaisesRegex(c.ContractError, "scope differs"):
            c.replay_current(
                hostile,
                self.evidence,
                expected_report_sha256=hostile_receipt,
                now=NOW,
                retained_policy_raw=self.policy,
            )

    def test_authority_drift_is_rejected(self):
        hostile = copy.deepcopy(self.report)
        hostile["authority"]["pms_write"] = True
        core = dict(hostile)
        del core["report_sha256"]
        hostile["report_sha256"] = hashlib.sha256(c.canon(core)).hexdigest()
        receipt = c.report_receipt(hostile)
        with self.assertRaisesRegex(c.ContractError, "authority drift"):
            c.verify_report_history(
                hostile,
                expected_policy_sha256=c.RETAINED_POLICY_SHA256,
                expected_report_sha256=receipt,
            )

    def test_production_cli_has_no_policy_or_root_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "compiler.py"),
                    "compile",
                    "--policy",
                    str(FIXTURES / "policy.json"),
                    "--expected-policy-sha256",
                    c.RETAINED_POLICY_SHA256,
                    "--evidence",
                    str(FIXTURES / "evidence.json"),
                    "--out",
                    str(out),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unrecognized arguments", proc.stderr)

    def test_cli_clock_override_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "compiler.py"),
                    "compile",
                    "--evidence",
                    str(FIXTURES / "evidence.json"),
                    "--out",
                    str(out),
                    "--now",
                    "2026-09-13T15:30:00Z",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unrecognized arguments", proc.stderr)

    def test_cli_output_is_create_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            command = [
                sys.executable,
                str(HERE / "compiler.py"),
                "compile",
                "--evidence",
                str(FIXTURES / "evidence.json"),
                "--out",
                str(out),
            ]
            first = subprocess.run(command, text=True, capture_output=True, check=False)
            second = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(len(first.stdout.strip()), 64)
            self.assertEqual(second.returncode, 2)
            self.assertIn("cannot create exclusive output", second.stderr)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_symlink_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.json"
            link = Path(tmp) / "link.json"
            target.write_bytes((FIXTURES / "evidence.json").read_bytes())
            os.symlink(target, link)
            with self.assertRaises(c.ContractError):
                c._read_regular(link)

    def test_normal_and_optimized_fixed_time_bytes_match(self):
        project_root = HERE.parents[1]
        script = (
            "import datetime as dt, json, pathlib, sys;"
            f"sys.path.insert(0,{str(project_root)!r});"
            "from revenue.hotel_room_turn_evidence import compiler as c;"
            f"p=c.loads_strict(pathlib.Path({str(FIXTURES / 'policy.json')!r}).read_bytes());"
            f"e=c.loads_strict(pathlib.Path({str(FIXTURES / 'evidence.json')!r}).read_bytes());"
            "r=c.compile_report(p,e,expected_policy_sha256=c.RETAINED_POLICY_SHA256,"
            "now=dt.datetime(2026,9,13,15,30,tzinfo=dt.timezone.utc));"
            "sys.stdout.buffer.write(c.canon(r))"
        )
        normal = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            check=False,
        )
        optimized = subprocess.run(
            [sys.executable, "-O", "-c", script],
            capture_output=True,
            check=False,
        )
        self.assertEqual(normal.returncode, 0, normal.stderr)
        self.assertEqual(optimized.returncode, 0, optimized.stderr)
        self.assertEqual(normal.stdout, optimized.stdout)

    def test_current_verify_summary_is_receipt_bound(self):
        current = c.replay_current(
            self.report,
            self.evidence,
            expected_report_sha256=self.receipt,
            now=NOW,
            retained_policy_raw=self.policy,
        )
        self.assertEqual(current["evidence_sha256"], self.report["evidence_sha256"])
        self.assertEqual(current["policy_sha256"], c.RETAINED_POLICY_SHA256)
        self.assertEqual(current["summary"]["ready"], 2)


if __name__ == "__main__":
    unittest.main()
