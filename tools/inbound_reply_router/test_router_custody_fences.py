from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    from .router import Policy, RouterError, load_json, preflight_cli_artifacts, route_reply, write_receipt_atomic
    from .test_router import NOW, context, evidence, event
except ImportError:
    from router import Policy, RouterError, load_json, preflight_cli_artifacts, route_reply, write_receipt_atomic
    from test_router import NOW, context, evidence, event


class OwnerFreshnessTests(unittest.TestCase):
    def test_stale_active_owner_holds(self):
        value = evidence(event("HUMAN_INTERESTED"))
        value["owner_bindings"][0]["observed_at"] = "2026-09-13T08:00:00Z"
        receipt = route_reply(context(), value, evaluated_at=NOW)
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("owner_binding_stale", receipt["basis"])
        self.assertFalse(receipt["authority"]["reply_send_authorized"])

    def test_exact_owner_freshness_boundary_is_accepted(self):
        value = evidence(event("HUMAN_INTERESTED"))
        value["owner_bindings"][0]["observed_at"] = "2026-09-13T08:15:00Z"
        receipt = route_reply(
            context(),
            value,
            evaluated_at=NOW,
            policy=Policy(max_owner_binding_age_seconds=900),
        )
        self.assertEqual(receipt["action"], "OWNER_REPLY_REQUIRED")
        self.assertNotIn("owner_binding_stale", receipt["basis"])

    def test_fresh_reassigned_owner_still_holds(self):
        value = evidence(event("HUMAN_INTERESTED"))
        value["owner_bindings"][0]["owner_id"] = "new-owner"
        receipt = route_reply(context(), value, evaluated_at=NOW)
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("active_owner_mismatch", receipt["basis"])
        self.assertNotIn("owner_binding_stale", receipt["basis"])

    def test_invalid_owner_freshness_policy_rejected(self):
        with self.assertRaises(RouterError):
            route_reply(
                context(),
                evidence(),
                evaluated_at=NOW,
                policy=Policy(max_owner_binding_age_seconds=-1),
            )


class CliCustodyTests(unittest.TestCase):
    def _write_sources(self, root: Path) -> tuple[Path, Path]:
        context_path = root / "context.json"
        evidence_path = root / "evidence.json"
        context_path.write_text(json.dumps(context()), encoding="utf-8")
        evidence_path.write_text(json.dumps(evidence(event("HUMAN_QUESTION"))), encoding="utf-8")
        return context_path, evidence_path

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context_path, evidence_path = self._write_sources(root)
            link = root / "context-link.json"
            link.symlink_to(context_path.name)
            with self.assertRaisesRegex(RouterError, "context must not be a symlink"):
                preflight_cli_artifacts(link, evidence_path, root / "receipt.json")
            with self.assertRaisesRegex(RouterError, "JSON input must not be a symlink"):
                load_json(link)

    def test_direct_output_alias_rejected_before_json_parse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context_path = root / "context.json"
            evidence_path = root / "evidence.json"
            context_bytes = b"this is deliberately not JSON\n"
            context_path.write_bytes(context_bytes)
            evidence_path.write_text(json.dumps(evidence()), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("router.py")),
                    "--context",
                    str(context_path),
                    "--evidence",
                    str(evidence_path),
                    "--evaluated-at",
                    NOW,
                    "--output",
                    str(context_path),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertIn("output and context", proc.stderr)
            self.assertEqual(context_bytes, context_path.read_bytes())

    def test_hardlink_output_alias_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context_path, evidence_path = self._write_sources(root)
            output = root / "receipt.json"
            os.link(evidence_path, output)
            with self.assertRaisesRegex(RouterError, "output and evidence"):
                preflight_cli_artifacts(context_path, evidence_path, output)

    def test_symlink_output_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context_path, evidence_path = self._write_sources(root)
            real = root / "real.json"
            real.write_text("old\n", encoding="utf-8")
            output = root / "receipt.json"
            output.symlink_to(real.name)
            with self.assertRaisesRegex(RouterError, "output must not be a symlink"):
                preflight_cli_artifacts(context_path, evidence_path, output)
            self.assertEqual("old\n", real.read_text(encoding="utf-8"))

    def test_symlinked_output_parent_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context_path, evidence_path = self._write_sources(root)
            outside = root / "outside"
            outside.mkdir()
            linked = root / "linked"
            linked.symlink_to(outside, target_is_directory=True)
            output = linked / "receipt.json"
            with self.assertRaisesRegex(RouterError, "parent must not traverse a symlink"):
                preflight_cli_artifacts(context_path, evidence_path, output)
            self.assertFalse((outside / "receipt.json").exists())

    def test_parent_swap_after_preflight_rejected_at_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context_path, evidence_path = self._write_sources(root)
            parent = root / "receipt-dir"
            outside = root / "outside"
            parent.mkdir()
            outside.mkdir()
            outside_target = outside / "receipt.json"
            outside_target.write_text("outside-old\n", encoding="utf-8")
            output = parent / "receipt.json"
            preflight_cli_artifacts(context_path, evidence_path, output)
            parent.rmdir()
            parent.symlink_to(outside, target_is_directory=True)
            receipt = route_reply(context(), evidence(), evaluated_at=NOW)
            with self.assertRaisesRegex(RouterError, "parent must not traverse a symlink"):
                write_receipt_atomic(receipt, output)
            self.assertEqual("outside-old\n", outside_target.read_text(encoding="utf-8"))
            self.assertEqual([], list(outside.glob(".receipt.json.*.tmp")))


if __name__ == "__main__":
    unittest.main()
