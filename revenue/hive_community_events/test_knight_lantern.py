"""Consume the original knight packs through Lantern's actual SQLite and HTTP app."""
from collections import Counter
from contextlib import redirect_stdout
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest

from app import Problem, Store, make_handler
import knight_pack as pack

ROOT = Path(__file__).resolve().parent


def questions(week):
    return json.loads((ROOT / f"knight-week-{week}.json").read_text(encoding="utf-8"))


def payload(rows, opens=900):
    return {"title": "Original knight challenges", "room": "Synthetic test room",
            "opens": opens, "ends": 2000, "questions": rows}


class LanternPackTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "events.sqlite3"
        self.now = 1000
        self.store = Store(self.database, clock=lambda: self.now)

    def test_committed_packs_match_native_adapter_and_balanced_answers(self):
        for week in (1, 2):
            with self.subTest(week=week):
                rows = questions(week)
                expected = pack.adapt(pack.generate(f"community-knight-week-{week}"),
                                      answer_key="correct", explanation_key=None)
                self.assertEqual(rows, expected)
                self.assertEqual(len(rows), 12)
                self.assertEqual(Counter(row["correct"] for row in rows), {0: 3, 1: 3, 2: 3, 3: 3})
                self.assertTrue(all(set(row) == {"prompt", "choices", "correct"} for row in rows))

    def test_both_packs_complete_with_retries_and_persisted_reconnect(self):
        for week in (1, 2):
            with self.subTest(week=week):
                rows = questions(week)
                event_id = self.store.create(payload(rows))["id"]
                member = self.store.join(event_id, {"name": "Synthetic player"})
                state = self.store.state(event_id, member["id"])
                self.assertEqual(state["question_count"], 12)
                self.assertTrue(all("correct" not in row for row in state["questions"]))
                for index, row in enumerate(rows):
                    answer = {"member_id": member["id"], "question": index, "choice": row["correct"]}
                    self.assertFalse(self.store.answer(event_id, answer)["replayed"])
                    self.assertTrue(self.store.answer(event_id, answer)["replayed"])
                self.store.finish(event_id)
                reopened = Store(self.database, clock=lambda: self.now)
                self.assertEqual(reopened.join(event_id, {"member_id": member["id"]}), member)
                final = reopened.state(event_id, member["id"])
                self.assertEqual(final["phase"], "finished")
                self.assertEqual(len(final["answers"]), 12)
                self.assertEqual(final["leaderboard"][0]["points"], 1200)
                self.assertEqual(final["leaderboard"][0]["rank"], 1)

    def test_scheduled_pack_and_wrong_answer_use_existing_semantics(self):
        rows = questions(1)
        event_id = self.store.create(payload(rows, opens=1100))["id"]
        member = self.store.join(event_id, {"name": "Synthetic player"})
        self.assertEqual(self.store.state(event_id)["questions"], [])
        answer = {"member_id": member["id"], "question": 0, "choice": (rows[0]["correct"] + 1) % 4}
        with self.assertRaises(Problem) as error:
            self.store.answer(event_id, answer)
        self.assertEqual(error.exception.status, 409)
        self.now = 1100
        self.store.answer(event_id, answer)
        with self.assertRaises(Problem) as error:
            self.store.answer(event_id, dict(answer, choice=rows[0]["correct"]))
        self.assertEqual(error.exception.status, 409)
        self.store.finish(event_id)
        self.assertEqual(self.store.state(event_id)["leaderboard"][0]["points"], 0)

    def test_documented_cli_output_works_at_consumer_limit(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            pack.main(["--count", "50", "--answer-key", "correct", "--omit-explanation"])
        event = self.store.create(payload(json.loads(stdout.getvalue())))
        self.assertEqual(self.store.state(event["id"])["question_count"], 50)

    def test_canonical_answer_rows_require_the_native_adapter(self):
        with self.assertRaises(Problem) as error:
            self.store.create(payload(pack.adapt(pack.generate())))
        self.assertEqual(error.exception.status, 422)

    def test_actual_http_round_and_reconnect(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.store))
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        def cleanup():
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
        self.addCleanup(cleanup)
        def request(method, path, data=None):
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                body = None if data is None else json.dumps(data).encode("utf-8")
                connection.request(method, path, body, {"Content-Type": "application/json"})
                response = connection.getresponse()
                result = json.loads(response.read())
                self.assertIn(response.status, (200, 201), result)
                return result
            finally:
                connection.close()
        rows = questions(2)
        event_id = request("POST", "/api/events", payload(rows))["id"]
        base = "/api/events/" + event_id
        member = request("POST", base + "/join", {"name": "Synthetic HTTP player"})
        for index, row in enumerate(rows):
            answer = {"member_id": member["id"], "question": index, "choice": row["correct"]}
            self.assertFalse(request("POST", base + "/answers", answer)["replayed"])
            self.assertTrue(request("POST", base + "/answers", answer)["replayed"])
        request("POST", base + "/finish", {})
        self.assertEqual(request("POST", base + "/join", {"member_id": member["id"]}), member)
        final = request("GET", base + "?member=" + member["id"])
        self.assertEqual(final["leaderboard"][0]["points"], 1200)
        self.assertEqual(len(final["answers"]), 12)
        self.assertEqual(final, self.store.state(event_id, member["id"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
