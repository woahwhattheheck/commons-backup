from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentwitness import event_key


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str, input_bytes: bytes | None = None):
        return subprocess.run(
            [sys.executable, "-m", "agentwitness.cli", *args],
            cwd=ROOT,
            input=input_bytes,
            capture_output=True,
            check=False,
        )

    def test_event_key_matches_library(self):
        path = ROOT / "examples" / "gmail_reply_event.json"
        expected = event_key(json.loads(path.read_text(encoding="utf-8")))
        got = self.run_cli("event-key", str(path))
        self.assertEqual(0, got.returncode, got.stderr.decode())
        self.assertEqual(expected, got.stdout.decode().strip())

    def test_canonical_event_from_stdin(self):
        raw = b'{"provider":"gmail","event_id":"x-1","namespace":"demo/outbound","network":"monad","version":"agentwitness-event-v1"}'
        got = self.run_cli("canonical-event", "-", input_bytes=raw)
        self.assertEqual(0, got.returncode, got.stderr.decode())
        self.assertEqual(b'{"event_id":"x-1","namespace":"demo/outbound","network":"monad","provider":"gmail","version":"agentwitness-event-v1"}\n', got.stdout)

    def test_private_hash_never_echoes_payload(self):
        secret = b"private customer body not for publication"
        got = self.run_cli("intent-hash", "-", input_bytes=secret)
        self.assertEqual(0, got.returncode, got.stderr.decode())
        self.assertNotIn(secret, got.stdout)
        self.assertRegex(got.stdout.decode().strip(), r"^0x[0-9a-f]{64}$")

    def test_invalid_event_fails_closed(self):
        raw = b'{"version":"agentwitness-event-v1","network":"monad","namespace":"demo/outbound","provider":"gmail","event_id":"x","draft":"leak"}'
        got = self.run_cli("event-key", "-", input_bytes=raw)
        self.assertEqual(2, got.returncode)
        self.assertEqual(b"", got.stdout)
        self.assertIn(b"schema mismatch", got.stderr)

    def test_checked_schema_files_are_closed(self):
        event_schema = json.loads((ROOT / "schema" / "event-v1.schema.json").read_text(encoding="utf-8"))
        receipt_schema = json.loads((ROOT / "schema" / "receipt-v1.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(event_schema["additionalProperties"])
        self.assertFalse(receipt_schema["additionalProperties"])
        self.assertEqual("agentwitness-event-v1", event_schema["properties"]["version"]["const"])
        self.assertEqual("agentwitness-receipt-v1", receipt_schema["properties"]["version"]["const"])


if __name__ == "__main__":
    unittest.main()
