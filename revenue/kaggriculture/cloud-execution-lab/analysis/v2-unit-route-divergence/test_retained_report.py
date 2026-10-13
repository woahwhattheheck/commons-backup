#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Retained-identity and synthetic report contracts for the V2 unit-route audit."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from audit_common import AuditError, canonical_json, sha256_bytes
from audit_report import build_report
from test_unit_route_audit import (
    AGENT,
    two_replays,
    valid_root,
    write_manifest,
    write_replay,
)

HERE = Path(__file__).resolve().parent
README = HERE / "README.md"
MANIFEST = HERE / "evidence" / "input-manifest.json"
RETAINED_REPORT = HERE / "evidence" / "report.json"
RETAINED_PAYLOAD_SHA256 = "38480d11f872bf6abcb017b2c86a4ca3e5b9f4f2932e01e6c0e7d787c643fbd9"

DOCUMENTED_REPLAYS = (
    {
        "episode_id": 107130860,
        "seed": 539131249,
        "opponent": "Apa",
        "seat": 1,
        "gzip_sha256": "9337c7c734eff0804400f732d48c155dedb6d6f12b3afdefbc620f78fdfc686b",
    },
    {
        "episode_id": 107140666,
        "seed": 1834999074,
        "opponent": "cununn",
        "seat": 1,
        "gzip_sha256": "120f9a62911e897adb085d7397f1f3a67100bf8c241065e4e424adb540bdf916",
    },
    {
        "episode_id": 107162106,
        "seed": 1885507524,
        "opponent": "ominteam",
        "seat": 1,
        "gzip_sha256": "b41bfdfcef73f35d71d617fb1b025e2bc25422600e43816805363d5470fa496f",
    },
    {
        "episode_id": 107172662,
        "seed": 65112964,
        "opponent": "Gappy",
        "seat": 1,
        "gzip_sha256": "385f506e7fd0ea82b963407f7d9dd6231f02f5d324d44b3a1f4cdad7f39f6279",
    },
)


class RetainedReportTests(unittest.TestCase):
    def test_manifest_matches_readme_identities(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["agent_name"], AGENT)
        self.assertEqual(manifest["expected_episode_steps"], 720)
        rows = [
            {
                "episode_id": row["episode_id"],
                "seed": row["seed"],
                "opponent": row["opponent"],
                "seat": row["seat"],
                "gzip_sha256": row["gzip_sha256"],
            }
            for row in manifest["replays"]
        ]
        self.assertEqual(rows, list(DOCUMENTED_REPLAYS))
        text = README.read_text(encoding="utf-8")
        for row in DOCUMENTED_REPLAYS:
            self.assertIn(str(row["episode_id"]), text)
            self.assertIn(row["gzip_sha256"], text)
            self.assertIn(row["opponent"], text)

    def test_readme_states_retained_report_custody_truthfully(self) -> None:
        text = README.read_text(encoding="utf-8")
        self.assertIn(RETAINED_PAYLOAD_SHA256, text)
        if RETAINED_REPORT.is_file():
            report = json.loads(RETAINED_REPORT.read_text(encoding="utf-8"))
            payload = {key: value for key, value in report.items() if key != "report_payload_sha256"}
            self.assertEqual(report["report_payload_sha256"], RETAINED_PAYLOAD_SHA256)
            self.assertEqual(sha256_bytes(canonical_json(payload)), RETAINED_PAYLOAD_SHA256)
        else:
            self.assertNotIn("The retained `report.json` has payload SHA-256", text)
            self.assertIn("`evidence/report.json` is not retained in this Git tree", text)
            self.assertIn("HISTORICAL_EXTERNAL_EVIDENCE", text)

    def test_underfilled_hire_interval_attribution(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            loss = valid_root(
                episode_id=107130860,
                seed=11,
                episode_steps=5,
                turns_per_day=5,
                hire_requested=4,
                hire_completed=3,
                later_hand_commands=4,
                reward=-13112,
                rival_reward=0,
            )
            win = valid_root(
                episode_id=107162106,
                seed=12,
                opponent="ominteam",
                episode_steps=5,
                turns_per_day=5,
                hire_requested=1,
                hire_completed=1,
                later_hand_commands=1,
                reward=2684,
                rival_reward=0,
            )
            rows = [
                write_replay(directory, "loss.json.gz", loss),
                write_replay(directory, "win.json.gz", win),
            ]
            manifest = write_manifest(directory, rows, steps=5)
            report = build_report(manifest, directory)
            loss_ep = next(ep for ep in report["episodes"] if ep["episode_id"] == 107130860)
            self.assertEqual(loss_ep["result"], "LOSS")
            self.assertEqual(len(loss_ep["hire_shortfalls"]), 1)
            self.assertEqual(loss_ep["hire_shortfalls"][0]["requested_executable_hires"], 4)
            self.assertEqual(loss_ep["hire_shortfalls"][0]["completed_hires"], 3)
            self.assertEqual(loss_ep["hire_shortfalls"][0]["shortfall"], 1)
            self.assertGreater(loss_ep["unbound_hand_commands_total"], 0)
            self.assertTrue(loss_ep["unbound_hand_command_intervals"])
            self.assertEqual(
                loss_ep["unbound_hand_command_intervals"][0]["attribution"],
                "underfilled_hire",
            )
            self.assertEqual(report["summary"]["episodes_with_underfilled_hires"], [107130860])
            self.assertIn("no environment execution", report["summary"]["truth_boundary"])

    def test_completed_hire_surplus_is_not_underfilled(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            left = valid_root(
                episode_id=1,
                episode_steps=4,
                turns_per_day=4,
                hire_requested=1,
                hire_completed=1,
                later_hand_commands=2,
            )
            right = valid_root(
                episode_id=2,
                seed=9,
                opponent="Gappy",
                episode_steps=4,
                turns_per_day=4,
                hire_requested=1,
                hire_completed=1,
                later_hand_commands=1,
            )
            rows = [
                write_replay(directory, "left.json.gz", left),
                write_replay(directory, "right.json.gz", right),
            ]
            manifest = write_manifest(directory, rows, steps=4)
            report = build_report(manifest, directory)
            episode = report["episodes"][0]
            self.assertEqual(episode["hire_shortfalls"], [])
            self.assertTrue(episode["unbound_hand_command_intervals"])
            self.assertEqual(
                episode["unbound_hand_command_intervals"][0]["attribution"],
                "no_observed_hire_fill_shortfall",
            )
            self.assertEqual(report["summary"]["underfilled_hire_events"], 0)

    def test_duplicate_bytes_reported_before_duplicate_episode(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            root = valid_root(episode_id=44, seed=1)
            first = write_replay(directory, "a.json.gz", root)
            copy = dict(first)
            copy["file"] = "b.json.gz"
            copy["episode_id"] = first["episode_id"]
            (directory / "b.json.gz").write_bytes((directory / "a.json.gz").read_bytes())
            manifest = write_manifest(directory, [first, copy])
            with self.assertRaisesRegex(AuditError, "duplicate replay bytes"):
                build_report(manifest, directory)

    def test_report_payload_sha256_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest, _ = two_replays(directory)
            first = build_report(manifest, directory)
            second = build_report(manifest, directory)
            self.assertEqual(first["report_payload_sha256"], second["report_payload_sha256"])
            payload = {key: value for key, value in first.items() if key != "report_payload_sha256"}
            self.assertEqual(first["report_payload_sha256"], sha256_bytes(canonical_json(payload)))
            self.assertEqual(first["replay_count"], 2)
            self.assertEqual(len(first["pairwise"]), 1)


if __name__ == "__main__":
    unittest.main()
