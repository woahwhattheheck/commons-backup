"""Real-state CLI/transport integration; only the Slack HTTP boundary is mocked."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from host import slack_mirror as sm
from host.slack_mirror_state import DeliveryError, DeliveryUncertain, MirrorStore, RejectedSend
from commons_publication_policy import PublicationPolicyViolation


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "state.sqlite3"
        self.source = self.root / "source.md"
        self.source.write_text("from: TEST\nid: source\n---\nDelivery update.\n", encoding="utf-8")
        self.env = patch.dict(os.environ, {"SLACK_BOT_TOKEN": "fixture-token",
            "COMMONS_SLACK_CHANNEL": "C1", "COMMONS_SLACK_THREAD_TS": "",
            "COMMONS_SLACK_MIRROR_STATE": str(self.db)}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def response(self, value=None, raw=None):
        if raw is None:
            raw = json.dumps(value or {"ok": True, "channel": "C1", "ts": "1.000001"}).encode()
        return io.BytesIO(raw)

    def send(self, **kwargs):
        return sm.send_parts(["Delivery update."], "fixture-token", channel="C1",
                             event_id="source:v1", state_path=self.db, **kwargs)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sm.main(["slack_mirror.py", *args])
        return code, out.getvalue(), err.getvalue()

    def test_cli_defaults_to_durable_receipts(self):
        with patch.object(sm.urllib.request, "urlopen", return_value=self.response()) as http:
            first = self.cli("send", str(self.source))
            second = self.cli("send", str(self.source))
        self.assertEqual(first, second)
        self.assertEqual(first[0], 0)
        self.assertIn("sent ts=1.000001 channel=C1", first[1])
        self.assertEqual(http.call_count, 1)
        code, out, _ = self.cli("status", str(self.source))
        self.assertEqual(code, 0)
        state = json.loads(out)
        self.assertEqual(state["state"], "COMPLETE")
        self.assertEqual(state["identity"]["source_event"], sm.source_link(self.source))

    def test_cli_multipart_resumes_with_recorded_root(self):
        self.source.write_text("Delivery update. " * 800, encoding="utf-8")
        parts = sm.format_mirror(self.source)
        calls = []
        def first_http(req, **_):
            calls.append(json.loads(req.data))
            if len(calls) == 2:
                raise TimeoutError("fixture-token must not escape")
            return self.response()
        with patch.object(sm.urllib.request, "urlopen", side_effect=first_http):
            first = self.cli("send", str(self.source))
            blocked = self.cli("send", str(self.source))
        self.assertEqual(first[0], 3)
        self.assertEqual(blocked[0], 3)
        self.assertNotIn("fixture-token", first[2])
        self.assertEqual(len(calls), 2)
        self.assertNotIn("thread_ts", calls[0])
        self.assertEqual(calls[1]["thread_ts"], "1.000001")
        state = MirrorStore(self.db).inspect(sm.source_link(self.source), parts, channel="C1")
        with patch.object(sm.urllib.request, "urlopen") as http:
            reconciled = self.cli("reconcile", str(self.source), "--part", "2", "--attempt",
                state["in_flight"]["attempt"], "--accepted-ts", "1.000002",
                "--evidence", "native direct-thread receipt")
            http.assert_not_called()
        self.assertEqual(reconciled[0], 0)
        next_index = 2
        def remaining(req, **_):
            nonlocal next_index
            next_index += 1
            payload = json.loads(req.data)
            self.assertEqual(payload["thread_ts"], "1.000001")
            self.assertEqual(payload["text"], parts[next_index - 1])
            return self.response({"ok": True, "channel": "C1", "ts": f"1.{next_index:06d}"})
        with patch.object(sm.urllib.request, "urlopen", side_effect=remaining) as http:
            resumed = self.cli("send", str(self.source))
        self.assertEqual(resumed[0], 0)
        self.assertEqual(http.call_count, len(parts) - 2)

    def test_cli_dark_has_no_database_or_transport(self):
        os.environ.pop("SLACK_BOT_TOKEN")
        with patch.object(sm.urllib.request, "urlopen") as http:
            result = self.cli("send", str(self.source))
        self.assertEqual(result[0], 0)
        self.assertIn("DARK:", result[1])
        self.assertFalse(self.db.exists())
        http.assert_not_called()

    def test_format_unchanged_and_no_state(self):
        with patch.object(sm.urllib.request, "urlopen") as http:
            result = self.cli("format", str(self.source))
        parts = sm.format_mirror(self.source)
        self.assertEqual(result[1], "".join(f"--- part {i+1}/{len(parts)} ({len(p)} chars) ---\n{p}\n"
                                            for i, p in enumerate(parts)))
        self.assertEqual(result[0], 0)
        self.assertFalse(self.db.exists())
        http.assert_not_called()

    def test_explicit_thread_alias_and_channel(self):
        with patch.object(sm.urllib.request, "urlopen", return_value=self.response()) as http:
            self.assertEqual(self.cli("send", str(self.source), "--thread-ts", "8.000008")[0], 0)
        self.assertEqual(json.loads(http.call_args.args[0].data)["thread_ts"], "8.000008")

    def test_native_request_shape_and_token_not_in_state(self):
        with patch.object(sm.urllib.request, "urlopen", return_value=self.response()) as http:
            self.send()
        req = http.call_args.args[0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.full_url, "https://slack.com/api/chat.postMessage")
        self.assertEqual(req.get_header("Authorization"), "Bearer fixture-token")
        self.assertEqual(json.loads(req.data), {"channel": "C1", "text": "Delivery update.", "mrkdwn": True})
        self.assertNotIn(b"fixture-token", self.db.read_bytes())

    def test_unknown_provider_errors_are_not_retried(self):
        for code in ("internal_error", "fatal_error", "service_unavailable", "new_error", None, {}):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "receipt.db"
                with patch.object(sm.urllib.request, "urlopen", return_value=self.response({"ok": False, "error": code})) as http:
                    for _ in range(2):
                        with self.assertRaises(DeliveryUncertain):
                            sm.send_parts(["Delivery update."], "token", channel="C1", event_id="e", state_path=path)
                    self.assertEqual(http.call_count, 1)

    def test_definite_auth_rejection_can_retry_after_correction(self):
        with patch.object(sm.urllib.request, "urlopen", return_value=self.response({"ok": False, "error": "invalid_auth"})):
            with self.assertRaises(RejectedSend):
                self.send()
        with patch.object(sm.urllib.request, "urlopen", return_value=self.response()) as http:
            self.assertEqual(self.send(), ["1.000001"])
            self.assertEqual(http.call_count, 1)

    def test_http_429_persists_server_delay_and_blocks_immediate_retry(self):
        error = urllib.error.HTTPError("https://slack.com/api/chat.postMessage", 429, "limit", {"Retry-After": "37"}, None)
        with patch.object(sm.urllib.request, "urlopen", side_effect=error) as http:
            for _ in range(2):
                with self.assertRaises(RejectedSend) as caught:
                    self.send()
                self.assertGreaterEqual(caught.exception.retry_after, 36)
            self.assertEqual(http.call_count, 1)

    def test_http_500_remains_uncertain(self):
        error = urllib.error.HTTPError("https://slack.com/api/chat.postMessage", 500, "unknown", {}, None)
        with patch.object(sm.urllib.request, "urlopen", side_effect=error) as http:
            for _ in range(2):
                with self.assertRaises(DeliveryUncertain):
                    self.send()
            self.assertEqual(http.call_count, 1)

    def test_bad_receipts_never_become_complete(self):
        cases = [{"ok": 1, "channel": "C1", "ts": "1.000001"},
                 {"ok": True, "channel": "C2", "ts": "1.000001"},
                 {"ok": True, "channel": "C1", "ts": None},
                 {"ok": True, "channel": "C1", "ts": "None"}, [],
                 {"ok": True, "ts": "1.000001"}]
        for i, value in enumerate(cases):
            with self.subTest(value=value), patch.object(sm.urllib.request, "urlopen", return_value=self.response(raw=json.dumps(value).encode())):
                with self.assertRaises(DeliveryUncertain):
                    sm.send_parts(["Delivery update."], "token", channel="C1", event_id=f"e{i}", state_path=self.db)

    def test_malformed_json_and_network_failure_no_replay(self):
        for i, result in enumerate([self.response(raw=b"not json"), OSError("fixture-token")]):
            with patch.object(sm.urllib.request, "urlopen", side_effect=[result] if not isinstance(result, Exception) else result) as http:
                for _ in range(2):
                    with self.assertRaises(DeliveryUncertain) as caught:
                        sm.send_parts(["Delivery update."], "fixture-token", channel="C1", event_id=f"e{i}", state_path=self.db)
                    self.assertNotIn("fixture-token", str(caught.exception))
                self.assertEqual(http.call_count, 1)

    def test_publication_rejection_precedes_state_and_network(self):
        with patch.object(sm.urllib.request, "urlopen") as http:
            with self.assertRaises(PublicationPolicyViolation):
                sm.send_parts(["I disagree."], "token", channel="C1", event_id="e", state_path=self.db)
        self.assertFalse(self.db.exists())
        http.assert_not_called()

    def test_whole_payload_checked_before_first_chunk(self):
        with patch.object(sm, "require_publication", side_effect=DeliveryError("policy fixture")) as policy, patch.object(sm.urllib.request, "urlopen") as http:
            with self.assertRaises(DeliveryError):
                sm.send_parts(["part one", "part two"], "token", channel="C1", event_id="e", state_path=self.db)
        policy.assert_called_once_with("part one\npart two")
        http.assert_not_called()
        self.assertFalse(self.db.exists())

    def test_legacy_api_remains_explicitly_one_shot(self):
        with patch.object(sm.urllib.request, "urlopen", side_effect=lambda *a, **k: self.response()) as http:
            for _ in range(2):
                self.assertEqual(sm.send_parts(["Delivery update."], "token", channel="C1"), ["1.000001"])
        self.assertEqual(http.call_count, 2)
        self.assertFalse(self.db.exists())

    def test_state_without_event_is_rejected(self):
        with patch.object(sm.urllib.request, "urlopen") as http:
            with self.assertRaises(DeliveryError):
                sm.send_parts(["Delivery update."], "token", state_path=self.db)
        http.assert_not_called()
        self.assertFalse(self.db.exists())

    def test_channel_aliases_rejected_in_durable_mode(self):
        with patch.object(sm.urllib.request, "urlopen") as http:
            for channel in ("#commons", "commons", "", " C1 "):
                if channel == " C1 ":
                    continue  # surrounding whitespace normalizes before identity
                self.assertEqual(self.cli("send", str(self.source), "--channel", channel)[0], 2)
        http.assert_not_called()
        self.assertFalse(self.db.exists())

    def test_changed_source_requires_explicit_new_event(self):
        with patch.object(sm.urllib.request, "urlopen", side_effect=lambda *a, **k: self.response()) as http:
            self.assertEqual(self.cli("send", str(self.source))[0], 0)
            self.source.write_text("Updated delivery detail.", encoding="utf-8")
            self.assertEqual(self.cli("send", str(self.source))[0], 2)
            self.assertEqual(http.call_count, 1)
            self.assertEqual(self.cli("send", str(self.source), "--event-id", "source:v2")[0], 0)
            self.assertEqual(http.call_count, 2)

    def test_status_and_not_sent_reconciliation_need_no_token(self):
        with patch.object(sm.urllib.request, "urlopen", side_effect=TimeoutError()):
            self.assertEqual(self.cli("send", str(self.source))[0], 3)
        os.environ.pop("SLACK_BOT_TOKEN")
        with patch.object(sm.urllib.request, "urlopen") as http:
            result = self.cli("status", str(self.source))
            attempt = json.loads(result[1])["in_flight"]["attempt"]
            result = self.cli("reconcile", str(self.source), "--part", "1", "--attempt", attempt,
                              "--not-sent", "--evidence", "stopped worker; direct native non-delivery evidence")
            self.assertEqual(result[0], 0)
            self.assertEqual(json.loads(result[1])["state"], "READY")
            http.assert_not_called()

    def test_bad_reconciliation_flags_cannot_send(self):
        with patch.object(sm.urllib.request, "urlopen") as http:
            with self.assertRaises(SystemExit) as caught:
                self.cli("send", str(self.source), "--not-sent")
        self.assertEqual(caught.exception.code, 2)
        http.assert_not_called()

    def test_receipt_commit_failure_leaves_durable_intent(self):
        original = MirrorStore._finish
        def fail_commit(store, *args, **kwargs):
            if kwargs.get("receipt"):
                raise DeliveryError("simulated local receipt commit failure")
            return original(store, *args, **kwargs)
        with patch.object(sm.urllib.request, "urlopen", return_value=self.response()) as http:
            with patch.object(MirrorStore, "_finish", fail_commit):
                with self.assertRaises(DeliveryError):
                    self.send()
            with self.assertRaises(DeliveryUncertain):
                self.send()
            self.assertEqual(http.call_count, 1)


if __name__ == "__main__":
    unittest.main()
