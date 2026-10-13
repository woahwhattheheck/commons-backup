# SPDX-License-Identifier: Apache-2.0
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pq.store import (
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_PENDING,
    Queue,
    QueueError,
)


def _entry(queue, digest):
    entry, created = queue.submit(
        submission_id=f"pq-test-{digest[:8]}",
        name=f"cand-{digest[:8]}",
        pin_id=f"pin-{digest[:8]}",
        input_digest=digest,
    )
    return entry, created


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.queue = Queue(Path(self.td.name) / "q")

    def tearDown(self):
        self.td.cleanup()

    def test_submit_and_fifo_order(self):
        first, _ = _entry(self.queue, "a" * 64)
        second, _ = _entry(self.queue, "b" * 64)
        self.assertEqual(self.queue.next_pending()["id"], first["id"])
        self.queue.set_status(first["id"], STATUS_PASSED)
        self.assertEqual(self.queue.next_pending()["id"], second["id"])

    def test_submit_dedupes_identical_inputs(self):
        first, created = _entry(self.queue, "c" * 64)
        self.assertTrue(created)
        again, created = _entry(self.queue, "c" * 64)
        self.assertFalse(created)
        self.assertEqual(again["id"], first["id"])
        self.assertEqual(len(self.queue.list()), 1)

    def test_status_tracking(self):
        entry, _ = _entry(self.queue, "d" * 64)
        self.assertEqual(entry["status"], STATUS_PENDING)
        updated = self.queue.set_status(entry["id"], STATUS_FAILED)
        self.assertEqual(updated["status"], STATUS_FAILED)
        self.assertEqual(self.queue.get(entry["id"])["status"], STATUS_FAILED)

    def test_list_filters_by_status(self):
        e1, _ = _entry(self.queue, "e" * 64)
        _entry(self.queue, "f" * 64)
        self.queue.set_status(e1["id"], STATUS_PASSED)
        self.assertEqual(len(self.queue.list(STATUS_PENDING)), 1)
        self.assertEqual(len(self.queue.list(STATUS_PASSED)), 1)

    def test_rerun_failed_returns_to_pending_and_keeps_history(self):
        entry, _ = _entry(self.queue, "g" * 64)
        self.queue.record_attempt(
            entry["id"], {"n": 1, "kind": "run", "verdict": "REJECT"}
        )
        self.queue.set_status(entry["id"], STATUS_FAILED)
        requeued = self.queue.rerun(entry["id"])
        self.assertEqual(requeued["status"], STATUS_PENDING)
        kinds = [a["kind"] for a in requeued["attempts"]]
        self.assertEqual(kinds, ["run", "requeue"])
        # the failed run verdict is still recorded
        self.assertEqual(requeued["attempts"][0]["verdict"], "REJECT")
        self.assertIsNone(requeued["last_receipt"])

    def test_rerun_running_is_rejected(self):
        entry, _ = _entry(self.queue, "h" * 64)
        self.queue.set_status(entry["id"], "running")
        with self.assertRaises(QueueError):
            self.queue.rerun(entry["id"])

    def test_unknown_submission_raises(self):
        with self.assertRaises(QueueError):
            self.queue.get("pq-nope")
        with self.assertRaises(QueueError):
            self.queue.rerun("pq-nope")


if __name__ == "__main__":
    unittest.main()
