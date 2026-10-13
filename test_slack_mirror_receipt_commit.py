"""Regression proof for the post-provider-acceptance receipt-commit boundary.

A valid Slack timestamp followed by local SQLite receipt persistence failure is a
may-have-delivered outcome. The exact pre-transport attempt must remain pending,
the first call must classify UNCERTAIN immediately, and an ordinary retry must
not invoke the provider again.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from host import slack_mirror as sm
from host.slack_mirror_state import DeliveryError, DeliveryUncertain, MirrorStore


def fail_receipt_commit(store, *args, **kwargs):
    if kwargs.get("receipt") is not None:
        raise DeliveryError("simulated local receipt commit failure")
    return ORIGINAL_FINISH(store, *args, **kwargs)


ORIGINAL_FINISH = MirrorStore._finish


class ReceiptCommitBoundaryTests(unittest.TestCase):
    def test_direct_api_is_immediately_uncertain_and_restart_does_not_resend(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.sqlite3"
            store = MirrorStore(db)
            calls = []

            def sender(text, thread):
                calls.append((text, thread))
                return "1789564000.000001"

            with patch.object(MirrorStore, "_finish", fail_receipt_commit):
                with self.assertRaises(DeliveryUncertain) as caught:
                    store.send("receipt:v1", ["Delivery update."], sender, channel="C1")
            self.assertIn("provider receipt could not be durably recorded", str(caught.exception))
            self.assertEqual(len(calls), 1)

            first = store.inspect("receipt:v1", ["Delivery update."], channel="C1")
            self.assertEqual(first["state"], "UNCERTAIN_OR_IN_FLIGHT")
            self.assertEqual(first["receipts"], [])
            self.assertEqual(first["in_flight"]["part"], 0)
            attempt = first["in_flight"]["attempt"]

            with self.assertRaises(DeliveryUncertain):
                store.send("receipt:v1", ["Delivery update."], sender, channel="C1")
            second = store.inspect("receipt:v1", ["Delivery update."], channel="C1")
            self.assertEqual(second["in_flight"]["attempt"], attempt)
            self.assertEqual(len(calls), 1)

    def test_cli_returns_three_immediately_and_restart_does_not_resend(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "state.sqlite3"
            source = root / "source.md"
            source.write_text("from: TEST\nid: source\n---\nDelivery update.\n", encoding="utf-8")
            parts = sm.format_mirror(source)
            response = io.BytesIO(json.dumps({
                "ok": True, "channel": "C1", "ts": "1789564000.000001"
            }).encode("utf-8"))

            env = {
                "SLACK_BOT_TOKEN": "fixture-token",
                "COMMONS_SLACK_CHANNEL": "C1",
                "COMMONS_SLACK_THREAD_TS": "",
                "COMMONS_SLACK_MIRROR_STATE": str(db),
            }
            with patch.dict(os.environ, env, clear=True), \
                    patch.object(sm.urllib.request, "urlopen", return_value=response) as http:
                out, err = io.StringIO(), io.StringIO()
                with patch.object(MirrorStore, "_finish", fail_receipt_commit), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    first_code = sm.main(["slack_mirror.py", "send", str(source)])
                self.assertEqual(first_code, 3)
                self.assertIn("UNCERTAIN:", err.getvalue())
                self.assertEqual(http.call_count, 1)

                state = MirrorStore(db).inspect(sm.source_link(source), parts, channel="C1")
                self.assertEqual(state["state"], "UNCERTAIN_OR_IN_FLIGHT")
                self.assertEqual(state["receipts"], [])
                attempt = state["in_flight"]["attempt"]

                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    second_code = sm.main(["slack_mirror.py", "send", str(source)])
                self.assertEqual(second_code, 3)
                self.assertIn(attempt, err.getvalue())
                self.assertEqual(http.call_count, 1)

                again = MirrorStore(db).inspect(sm.source_link(source), parts, channel="C1")
                self.assertEqual(again["in_flight"]["attempt"], attempt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
