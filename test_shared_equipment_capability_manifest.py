#!/usr/bin/env python3
"""Hermetic parity: every peer gets the same non-secret capability manifest."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SECRETISH = re.compile(
    r"(?:xox[baprs]-|xapp-|gh[pousr]_|github_pat_|AIza[0-9A-Za-z_-]{20,}|Bearer\s)",
    re.I,
)


class CapabilityManifestTests(unittest.TestCase):
    def test_two_peer_labels_receive_identical_operation_ids(self):
        from integrations.shared_equipment.services import build_capability_manifest

        a = build_capability_manifest(peer="NEWCOMER_A")
        b = build_capability_manifest(peer="NEWCOMER_B")
        self.assertEqual(a["operations"], b["operations"])
        self.assertEqual(a["roads"], b["roads"])
        self.assertTrue(a["same_operations_for_every_peer"])
        self.assertTrue(a["peer_label_does_not_change_inventory"])
        self.assertFalse(a["credential_bytes_in_manifest"])
        self.assertTrue(a["peer_argument_ignored"])
        ids = [op["operation_id"] for op in a["operations"]]
        self.assertEqual(ids, sorted(ids))
        for needle in (
            "slack_read_channel",
            "slack_post_message",
            "github_read_file",
            "github_commit_files",
            "grokbot_submit",
            "grokbot_pools",
        ):
            self.assertIn(needle, ids)
        blob = json.dumps(a)
        self.assertIsNone(SECRETISH.search(blob), blob[:400])

    def test_cli_manifest_subprocess_lists_roads_and_ops(self):
        env = dict(**{k: v for k, v in __import__("os").environ.items()})
        env["PYTHONPATH"] = str(ROOT)
        proc = subprocess.run(
            [sys.executable, "-m", "integrations.shared_equipment.services", "manifest"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema"], "commons.shared_equipment.capability_manifest.v1")
        names = {op["operation_id"] for op in payload["operations"]}
        self.assertIn("github_read_file", names)
        self.assertIn("grokbot_submit", names)
        road_ids = {r["road_id"] for r in payload["roads"]}
        self.assertEqual(
            road_ids,
            {
                "owner_pc_shared_equipment",
                "owner_pc_grokbot_control",
                "workspace_shared_equipment",
            },
        )
        self.assertIsNone(SECRETISH.search(proc.stdout))

    def test_carrier_manifest_name_journals_without_provider_tool(self):
        from integrations.gemini_slack.peer_tool_gateway import ToolCallStore
        from integrations.shared_equipment.services import (
            build_capability_manifest,
            build_cli_catalog,
        )
        from integrations.shared_equipment.slack_carrier import parse_request

        catalog = build_cli_catalog()
        text = (
            "<commons_equipment_request>"
            '{"request_id":"r","call_id":"m","name":"equipment_capability_manifest",'
            '"arguments":{"peer":"brand-new-peer"}}'
            "</commons_equipment_request>"
        )
        request = parse_request(text)
        self.assertEqual(request["name"], "equipment_capability_manifest")
        with tempfile.TemporaryDirectory() as directory:
            calls = ToolCallStore(Path(directory) / "calls.db")
            result = calls.execute_journaled(
                "equipment:" + request["request_id"],
                request["call_id"],
                request["name"],
                request.get("arguments", {}),
                lambda _n, args: build_capability_manifest(
                    catalog=catalog, peer=args.get("peer")
                ),
            )
            expected = build_capability_manifest(peer="other")
            self.assertEqual(
                [op["operation_id"] for op in result["operations"]],
                [op["operation_id"] for op in expected["operations"]],
            )
            calls.close()


if __name__ == "__main__":
    unittest.main()
