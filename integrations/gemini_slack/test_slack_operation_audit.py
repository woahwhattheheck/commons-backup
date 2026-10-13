import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from integrations.gemini_slack.slack_operation_audit import AuditError, correlate, slack_post_receipts


SCHEMA_SQL = """
CREATE TABLE tool_calls(
    request_id TEXT NOT NULL,
    call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments_sha256 TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('started','completed','error')),
    result_json TEXT,
    updated_at REAL NOT NULL,
    PRIMARY KEY(request_id, call_id)
)
"""


def row(request_id, call_id, tool_name, state, result, updated_at):
    return (
        request_id,
        call_id,
        tool_name,
        "0" * 64,
        state,
        None if result is None else json.dumps(result, separators=(",", ":")),
        updated_at,
    )


class SlackOperationAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "calls.sqlite3"
        db = sqlite3.connect(self.path)
        db.execute(SCHEMA_SQL)
        db.executemany(
            "INSERT INTO tool_calls VALUES(?,?,?,?,?,?,?)",
            [
                row(
                    "equipment-return:req-a",
                    "call-a:1788824940.900000:1",
                    "slack_post_message",
                    "completed",
                    {
                        "isError": False,
                        "result": {
                            "ok": True,
                            "channel": "C0C0Z8AHGP2",
                            "ts": "1788824940.990139",
                            "permalink": "https://example.invalid/not-emitted",
                            "text": "secret body must not be emitted",
                        },
                        "uncertain": False,
                    },
                    1.0,
                ),
                row(
                    "equipment-return:req-b",
                    "call-b:1788824941.300000:1",
                    "slack_post_message",
                    "completed",
                    {
                        "isError": False,
                        "result": {
                            "ok": True,
                            "channel": "C0C0Z8AHGP2",
                            "ts": "1788824941.412599",
                            "text": "same rendered body",
                        },
                        "uncertain": False,
                    },
                    2.0,
                ),
                row(
                    "peer-request",
                    "tool-1",
                    "github_read_file",
                    "completed",
                    {"isError": False, "result": {"content": "not relevant"}},
                    3.0,
                ),
                row(
                    "equipment-return:req-uncertain",
                    "call-c:1788825000.000000:1",
                    "slack_post_message",
                    "started",
                    {
                        "isError": True,
                        "uncertain": True,
                        "error": "post_response_unconfirmed",
                    },
                    4.0,
                ),
            ],
        )
        db.commit()
        db.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_extracts_only_slack_send_receipts(self):
        receipts = slack_post_receipts(self.path)
        self.assertEqual(len(receipts), 3)
        self.assertEqual(receipts[0]["carrier_request_id"], "req-a")
        self.assertEqual(receipts[0]["returned_slack_ts"], "1788824940.990139")
        self.assertEqual(receipts[0]["channel_id"], "C0C0Z8AHGP2")

    def test_does_not_emit_message_body_or_permalink(self):
        encoded = json.dumps(slack_post_receipts(self.path), sort_keys=True)
        self.assertNotIn("secret body", encoded)
        self.assertNotIn("same rendered body", encoded)
        self.assertNotIn("example.invalid", encoded)

    def test_correlates_exact_returned_timestamp_only(self):
        audit = correlate(
            self.path,
            ["1788824940.990139", "1788824940.990140"],
        )
        self.assertEqual(
            audit["observations"][0]["receipts"][0]["journal_request_id"],
            "equipment-return:req-a",
        )
        self.assertEqual(audit["observations"][1]["receipts"], [])
        self.assertEqual(audit["unmatched_slack_ts"], ["1788824940.990140"])

    def test_preserves_multiple_operations_for_same_returned_timestamp(self):
        db = sqlite3.connect(self.path)
        db.execute(
            "INSERT INTO tool_calls VALUES(?,?,?,?,?,?,?)",
            row(
                "equipment-return:req-d",
                "call-d:1788824941.350000:1",
                "slack_post_message",
                "completed",
                {
                    "isError": False,
                    "result": {
                        "ok": True,
                        "channel": "C0C0Z8AHGP2",
                        "ts": "1788824941.412599",
                    },
                    "uncertain": False,
                },
                5.0,
            ),
        )
        db.commit()
        db.close()
        audit = correlate(self.path, ["1788824941.412599"])
        ids = [
            item["journal_request_id"]
            for item in audit["observations"][0]["receipts"]
        ]
        self.assertEqual(ids, ["equipment-return:req-b", "equipment-return:req-d"])

    def test_uncertain_send_is_preserved_without_inventing_timestamp(self):
        receipt = slack_post_receipts(self.path)[-1]
        self.assertEqual(receipt["state"], "started")
        self.assertTrue(receipt["uncertain"])
        self.assertEqual(receipt["error"], "post_response_unconfirmed")
        self.assertIsNone(receipt["returned_slack_ts"])

    def test_rejects_non_timestamp_input(self):
        with self.assertRaises(AuditError):
            correlate(self.path, ["same text"])

    def test_incompatible_database_fails_closed(self):
        bad = Path(self.temp.name) / "bad.sqlite3"
        db = sqlite3.connect(bad)
        db.execute("CREATE TABLE something_else(x TEXT)")
        db.commit()
        db.close()
        with self.assertRaises(AuditError):
            slack_post_receipts(bad)

    def test_read_only_open_does_not_create_missing_database(self):
        missing = Path(self.temp.name) / "missing.sqlite3"
        with self.assertRaises(AuditError):
            slack_post_receipts(missing)
        self.assertFalse(missing.exists())

    def test_nested_slack_error_is_preserved_without_body_fields(self):
        db = sqlite3.connect(self.path)
        db.execute(
            "INSERT INTO tool_calls VALUES(?,?,?,?,?,?,?)",
            row(
                "equipment-return:req-error",
                "call-error",
                "slack_post_message",
                "error",
                {
                    "isError": True,
                    "result": {"ok": False, "error": "channel_not_found", "text": "drop me"},
                    "uncertain": False,
                },
                5.5,
            ),
        )
        db.commit()
        db.close()
        receipt = slack_post_receipts(self.path)[-1]
        self.assertEqual(receipt["error"], "channel_not_found")
        self.assertNotIn("drop me", json.dumps(receipt))

    def test_read_only_uri_handles_spaces_in_path(self):
        spaced = Path(self.temp.name) / "space dir"
        spaced.mkdir()
        target = spaced / "calls copy.sqlite3"
        target.write_bytes(self.path.read_bytes())
        receipts = slack_post_receipts(target)
        self.assertEqual(receipts[0]["returned_slack_ts"], "1788824940.990139")

    def test_cli_outputs_metadata_only(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "integrations.gemini_slack.slack_operation_audit",
                "--db",
                str(self.path),
                "--slack-ts",
                "1788824940.990139",
            ],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["message_body_inspected"])
        self.assertNotIn("secret body", result.stdout)
        self.assertEqual(
            payload["observations"][0]["receipts"][0]["carrier_request_id"],
            "req-a",
        )


if __name__ == "__main__":
    unittest.main()
