"""Exercise an export while a real second SQLite connection commits a review."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
import threading
import unittest

from study import Workspace


class ExportSnapshotTests(unittest.TestCase):
    def test_export_uses_one_snapshot_during_concurrent_review(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "workspace.sqlite3"
            reader, writer = Workspace(path), Workspace(path)
            document_id = reader.import_document(
                b"Latency: the elapsed time between a request and its response.", "notes.txt"
            )["id"]
            card = reader.cards(document_id)[0]
            cards_read = threading.Event()
            committed = threading.Event()
            errors = []

            def commit_review():
                try:
                    if not cards_read.wait(5):
                        raise RuntimeError("The export did not reach its card read.")
                    writer.review(card["id"], "Latency", "concurrent-review", 1)
                except Exception as exc:
                    errors.append(exc)
                finally:
                    committed.set()

            original_connection = reader.connection

            @contextmanager
            def interleaved_connection():
                with original_connection() as db:
                    def trace(sql):
                        if sql.startswith("SELECT * FROM cards WHERE document_id=") and not cards_read.is_set():
                            cards_read.set()
                            if not committed.wait(5):
                                errors.append(RuntimeError("The concurrent writer did not commit."))
                    db.set_trace_callback(trace)
                    yield db

            reader.connection = interleaved_connection
            thread = threading.Thread(target=commit_review, daemon=True)
            thread.start()
            try:
                exported = reader.export(document_id)
            finally:
                thread.join(timeout=6)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertTrue(cards_read.is_set())
            self.assertEqual(len(writer.export(document_id)["reviews"]), 1)
            # An export may be before or after a write, but not a mixture of both.
            self.assertEqual(sum(c["attempts"] for c in exported["cards"]), len(exported["reviews"]))
            self.assertEqual(exported["cards"][0]["attempts"], 0)
            self.assertEqual(exported["reviews"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
