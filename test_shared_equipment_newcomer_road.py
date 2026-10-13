#!/usr/bin/env python3
"""Hermetic proof: a newcomer peer uses shared equipment without secret bytes."""

from __future__ import annotations

import io
import json
import re
import subprocess
import unittest
from pathlib import Path

from integrations.shared_equipment.services import (
    CombinedCatalog,
    ServiceEquipment,
    build_capability_manifest,
    redacted,
)

SECRETISH = re.compile(
    r"(?:xox[baprs]-|xapp-|gh[pousr]_|github_pat_|AIza[0-9A-Za-z_-]{20,}|Bearer\s|SYNTHETIC_TOKEN)",
    re.I,
)


class _Empty:
    def tools(self, **_kwargs):
        return []

    def call(self, name, arguments):
        raise AssertionError("commons sidecar must not run")


def _gh_include(status, body):
    return f"HTTP/2 {status}\r\nX-Ratelimit-Remaining: 5000\r\n\r\n{body}"


class NewcomerRoadProofTests(unittest.TestCase):
    def _equipment(self):
        requests = []

        def opener(request, **_kwargs):
            requests.append(request)
            body = b'{"ok":true,"messages":[{"ts":"1.1","text":"ordinary coordination"}]}'
            return io.BytesIO(body)

        def gh_runner(command, **kwargs):
            # ServiceEquipment.github is:
            #   gh api --include --hostname github.com --method METHOD ENDPOINT [--input -]
            self.assertEqual(command[1:5], ["api", "--include", "--hostname", "github.com"])
            method_index = command.index("--method") + 1
            method = command[method_index]
            endpoint = command[method_index + 1]
            if method == "GET" and endpoint.endswith("/git/ref/heads/newcomer-proof"):
                return subprocess.CompletedProcess(
                    command, 1, _gh_include(404, '{"message":"Not Found"}'), ""
                )
            if method == "POST" and endpoint.endswith("/git/refs"):
                payload = json.loads(kwargs["input"])
                self.assertEqual(command[-2:], ["--input", "-"])
                return subprocess.CompletedProcess(
                    command,
                    0,
                    _gh_include(
                        201,
                        json.dumps(
                            {
                                "ref": payload["ref"],
                                "object": {"sha": payload["sha"], "type": "commit"},
                            }
                        ),
                    ),
                    "",
                )
            self.fail("unexpected gh call: %s" % (command,))

        tool = ServiceEquipment(
            slack_token_loader=lambda: "xoxb-SYNTHETIC_TOKEN-only",
            opener=opener,
            gh_runner=gh_runner,
        )
        return CombinedCatalog(_Empty(), services=tool), requests

    def test_newcomer_read_and_reversible_mutation_without_secret_bytes(self):
        catalog, requests = self._equipment()
        peer_label = "brand-new-peer-no-history"

        # Discovery is identical regardless of peer label (parity).
        manifest_a = build_capability_manifest(catalog=catalog, peer=peer_label)
        manifest_b = build_capability_manifest(catalog=catalog, peer="legacy-peer")
        self.assertEqual(manifest_a["operations"], manifest_b["operations"])
        self.assertTrue(manifest_a["same_operations_for_every_peer"])

        # Read through shared road (Slack).
        read_out = catalog.call(
            "slack_read_channel",
            {"channel_id": "C0BU51F1PL3", "limit": 5, "peer": peer_label},
        )
        self.assertFalse(read_out["isError"])
        self.assertTrue(read_out["result"]["ok"])
        self.assertEqual(requests[0].get_method(), "GET")
        self.assertIn("Authorization", requests[0].headers)
        # Token stays in the transport header only — never in the tool result.
        read_blob = json.dumps(read_out)
        self.assertIsNone(SECRETISH.search(read_blob), read_blob[:300])
        self.assertNotIn("SYNTHETIC_TOKEN", read_blob)

        # Reversible mutation through shared road (create branch; deleteable).
        mutate_out = catalog.call(
            "github_create_branch",
            {
                "repository": "woahwhattheheck/commons",
                "branch": "newcomer-proof",
                "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "peer": peer_label,
            },
        )
        self.assertFalse(mutate_out["isError"])
        self.assertEqual(
            mutate_out["result"]["ref"], "refs/heads/newcomer-proof"
        )
        mutate_blob = json.dumps(mutate_out)
        self.assertIsNone(SECRETISH.search(mutate_blob), mutate_blob[:300])

        # Redaction still strips provider secret fields if they leak upstream.
        dirty = redacted(
            {"bot_token": "xoxb-SYNTHETIC_TOKEN-only", "ok": True, "text": "fine"}
        )
        self.assertEqual(dirty["bot_token"], "[REDACTED]")
        self.assertEqual(dirty["text"], "fine")

    def test_manifest_lists_slack_and_github_mutation_ops(self):
        catalog, _ = self._equipment()
        ids = {
            op["operation_id"]
            for op in build_capability_manifest(catalog=catalog, peer="anyone")[
                "operations"
            ]
        }
        for needle in (
            "slack_read_channel",
            "github_create_branch",
            "github_read_file",
        ):
            self.assertIn(needle, ids)


if __name__ == "__main__":
    unittest.main()
