"""Focused regression for Fieldwork terminal request immutability."""
import tempfile
import unittest
from pathlib import Path

from queue_cancel import cancel_request
from server import Desk, Problem, ROOT


class TerminalImmutabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "desk.sqlite3"
        self.desk = Desk(self.db)
        workspace = self.desk.create_workspace({"name": "Terminal guard test"})
        self.wid = workspace["id"]
        self.rid = self.desk.create_request(
            {
                "workspace_id": self.wid,
                "title": "Cancelled design",
                "brief": "Original brief",
                "priority": 100,
            }
        )["request_id"]

    def tearDown(self):
        self.temp.cleanup()

    def request(self):
        return next(
            request
            for request in self.desk.snapshot(self.wid)["requests"]
            if request["id"] == self.rid
        )

    def test_cancelled_request_rejects_brief_edit_without_mutation(self):
        cancel_request(self.db, self.rid, 1, "Customer withdrew request")
        before = self.request()
        with self.assertRaises(Problem) as caught:
            self.desk.change_request(
                self.rid,
                {
                    "version": before["version"],
                    "action": "brief",
                    "brief": "Post-cancel mutation",
                },
            )
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(str(caught.exception), "Terminal requests are immutable")
        self.assertEqual(self.request(), before)

    def test_ui_treats_cancelled_and_complete_as_terminal(self):
        source = (ROOT / "index.html").read_text()
        self.assertIn(
            '.card[data-status="complete"],.card[data-status="cancelled"]{opacity:.8}',
            source,
        )
        self.assertIn("complete:2,cancelled:2", source)
        self.assertIn(
            "if(!['complete','cancelled'].includes(req.status)){const edit=",
            source,
        )


if __name__ == "__main__":
    unittest.main()
