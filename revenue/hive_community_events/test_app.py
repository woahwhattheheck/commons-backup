"""Focused tests use real SQLite transactions and a real loopback HTTP server."""
import concurrent.futures
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

from app import Problem, Store, make_handler


def payload(opens=1000, ends=2000):
    return {"title": "Logic night", "room": "Community A", "opens": opens, "ends": ends,
            "questions": [{"prompt": "Two plus two?", "choices": ["Three", "Four"], "correct": 1, "points": 100},
                          {"prompt": "Nine minus one?", "choices": ["Eight", "Ten"], "correct": 0, "points": 50}]}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1100
        self.path = Path(self.temp.name) / "events.sqlite3"
        self.store = Store(self.path, lambda: self.now)
        created = self.store.create(payload())
        self.event, self.host_key = created["id"], created["host_key"]
        self.member = self.store.join(self.event, {"name": "Lantern test"})["id"]

    def answer(self, question=0, choice=1, member=None):
        return self.store.answer(self.event, {"member_id": member or self.member, "question": question, "choice": choice})

    def error(self, status, call):
        with self.assertRaises(Problem) as ctx:
            call()
        self.assertEqual(ctx.exception.status, status)

    def test_host_capability_is_unique_hashed_and_absent_from_public_state(self):
        other = self.store.create(payload())
        self.assertNotEqual(self.host_key, other["host_key"])
        self.assertTrue(self.store.state(self.event)["host_protected"])
        self.assertNotIn("host_key", self.store.state(self.event))
        self.assertNotIn("host_key", self.store.listing()[0])
        with self.store.connect() as db:
            stored = db.execute("SELECT host_hash FROM events WHERE id=?", (self.event,)).fetchone()[0]
            dump = "\n".join(db.iterdump())
        self.assertNotEqual(stored, self.host_key)
        self.assertEqual(len(stored), 64)
        self.assertNotIn(self.host_key, dump)
        self.assertEqual(self.store.verify_host(self.event, self.host_key), {"host": True, "legacy": False})
        for hostile in ("wrong", None, "x" * 257, "\ud800"):
            with self.subTest(hostile=repr(hostile)):
                self.error(403, lambda hostile=hostile: self.store.verify_host(self.event, hostile))

    def make_legacy_database(self, path, identifier="legacy"):
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE events (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, room TEXT NOT NULL,
                opens REAL NOT NULL, ends REAL NOT NULL, closed INTEGER NOT NULL DEFAULT 0,
                questions TEXT NOT NULL, created REAL NOT NULL)""")
            db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
                       (identifier, "Old round", "Old room", 1000, 2000, 0,
                        json.dumps(payload()["questions"]), 900))

    def test_legacy_database_migrates_without_locking_existing_events(self):
        legacy_path = Path(self.temp.name) / "legacy.sqlite3"
        self.make_legacy_database(legacy_path)
        reopened = Store(legacy_path, lambda: self.now)
        with reopened.connect() as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(events)")}
            row = db.execute("SELECT host_hash FROM events WHERE id='legacy'").fetchone()
        self.assertIn("host_hash", columns)
        self.assertIsNone(row["host_hash"])
        self.assertEqual(reopened.verify_host("legacy", None), {"host": True, "legacy": True})
        self.assertEqual(reopened.finish("legacy"), {"finished": True})

    def test_parallel_legacy_schema_migration_converges(self):
        legacy_path = Path(self.temp.name) / "legacy-race.sqlite3"
        self.make_legacy_database(legacy_path)
        def open_store(_):
            return Store(legacy_path, lambda: self.now).state("legacy")["host_protected"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(open_store, range(4))), [False] * 4)
        reopened = Store(legacy_path, lambda: self.now)
        with reopened.connect() as db:
            names = [row["name"] for row in db.execute("PRAGMA table_info(events)")]
        self.assertEqual(names.count("host_hash"), 1)

    def test_schedule_hides_questions_and_prevents_early_answers(self):
        self.now = 999
        state = self.store.state(self.event)
        self.assertEqual(state["phase"], "scheduled")
        self.assertEqual(state["questions"], [])
        self.error(409, self.answer)
        self.now = 1000
        self.assertTrue(self.answer()["accepted"])

    def test_answer_retries_are_identical_and_do_not_rescore(self):
        self.assertFalse(self.answer()["replayed"])
        self.assertTrue(self.answer()["replayed"])
        self.store.finish(self.event)
        state = self.store.state(self.event, self.member)
        self.assertEqual(state["leaderboard"][0]["points"], 100)
        self.assertEqual(len(state["answers"]), 1)

    def test_changed_retry_is_rejected_without_overwrite(self):
        self.answer(choice=0)
        self.error(409, self.answer)
        self.store.finish(self.event)
        self.assertEqual(self.store.state(self.event, self.member)["answers"][0]["choice"], 0)

    def test_parallel_retries_commit_exactly_one_answer(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.answer(), range(16)))
        self.assertEqual(sum(not r["replayed"] for r in results), 1)
        self.store.finish(self.event)
        self.assertEqual(self.store.state(self.event)["leaderboard"][0]["points"], 100)

    def test_competing_choices_preserve_the_first_committed_answer(self):
        def attempt(choice):
            try:
                return self.answer(choice=choice)
            except Problem as exc:
                return exc.status
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [0, 1]))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertIn(409, results)

    def test_reconnect_and_restart_preserve_all_scores(self):
        self.answer()
        self.answer(1, 0)
        self.store.finish(self.event)
        before = self.store.state(self.event, self.member)
        reopened = Store(self.path, lambda: self.now)
        self.assertEqual(reopened.join(self.event, {"member_id": self.member})["id"], self.member)
        self.assertEqual(reopened.state(self.event, self.member), before)
        self.assertEqual(reopened.verify_host(self.event, self.host_key), {"host": True, "legacy": False})

    def test_finished_event_allows_identical_retry_but_no_new_answer(self):
        self.answer()
        self.now = 2000
        self.assertTrue(self.answer()["replayed"])
        self.error(409, lambda: self.answer(1, 0))
        self.error(409, lambda: self.store.join(self.event, {"name": "Late player"}))

    def test_answer_keys_and_scores_are_not_exposed_until_finish(self):
        self.answer()
        state = self.store.state(self.event, self.member)
        self.assertEqual(state["leaderboard"], [])
        self.assertTrue(all("correct" not in q for q in state["questions"]))
        self.assertNotIn("points", state["answers"][0])
        self.store.finish(self.event)
        self.assertEqual(self.store.state(self.event)["questions"][0]["correct"], 1)

    def test_tied_scores_share_rank_with_competition_gap(self):
        second = self.store.join(self.event, {"name": "Second"})["id"]
        self.store.join(self.event, {"name": "Third"})
        self.answer()
        self.answer(member=second)
        self.store.finish(self.event)
        self.assertEqual([p["rank"] for p in self.store.state(self.event)["leaderboard"]], [1, 1, 3])

    def test_zero_answers_have_zero_points(self):
        self.store.finish(self.event)
        person = self.store.state(self.event)["leaderboard"][0]
        self.assertEqual((person["points"], person["answered"]), (0, 0))

    def test_participants_and_answers_stay_in_their_event(self):
        other = self.store.create(payload())["id"]
        self.error(404, lambda: self.store.answer(other, {"member_id": self.member, "question": 0, "choice": 1}))
        self.error(404, lambda: self.store.state(other, self.member))
        self.assertEqual(self.store.state(other)["players"], 0)

    def test_names_are_not_unique_identity_or_a_join_requirement(self):
        other = self.store.join(self.event, {"name": "Lantern test"})["id"]
        self.assertNotEqual(other, self.member)
        self.assertEqual(self.store.state(self.event)["players"], 2)

    def test_invalid_question_sets_are_atomic(self):
        invalid = [[], [None], [{"prompt": "X", "choices": ["same", "SAME"], "correct": 0}],
                   [{"prompt": "X", "choices": ["a", "b"], "correct": True}],
                   [{"prompt": "X", "choices": ["a", "b"], "correct": 2}],
                   [{"prompt": "X", "choices": ["a", "b"], "correct": 0, "points": 0}]]
        for questions in invalid:
            with self.subTest(questions=questions):
                self.error(422, lambda: self.store.create({**payload(), "questions": questions}))
        self.assertEqual(len(self.store.listing()), 1)

    def test_invalid_times_include_nonfinite_boolean_and_huge_integer(self):
        for value in (float("nan"), float("inf"), True, -1, "1000", 10**500):
            with self.subTest(value=str(value)[:40]):
                self.error(422, lambda: self.store.create({**payload(), "opens": value}))
        self.error(422, lambda: self.store.create(payload(2000, 1000)))

    def test_invalid_indices_and_empty_name_do_not_change_state(self):
        for q, c in ((True, 0), (0, False), (2, 0), (0, 2), (-1, 0)):
            self.error(422, lambda: self.answer(q, c))
        self.error(422, lambda: self.store.join(self.event, {"name": " "}))
        self.assertEqual(self.store.state(self.event, self.member)["answers"], [])

    def test_listing_has_schedule_and_room_but_no_question_keys(self):
        event = self.store.listing()[0]
        self.assertEqual((event["room"], event["players"], event["phase"]), ("Community A", 1, "open"))
        self.assertNotIn("questions", event)
        self.assertTrue(event["host_protected"])

    def test_finish_is_idempotent_and_does_not_change_scoring(self):
        self.answer()
        self.assertEqual(self.store.finish(self.event), self.store.finish(self.event))
        self.assertEqual(self.store.state(self.event)["leaderboard"][0]["points"], 100)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store = Store(Path(cls.temp.name) / "events.sqlite3", lambda: 1100)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.store))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def request(self, path, data=None, raw=None):
        encoded = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
        request = Request(self.base+path, data=encoded, headers={"Content-Type": "application/json"})
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            body = response.read()
            return response.status, (json.loads(body) if "application/json" in response.headers.get("Content-Type", "") else body)

    def test_full_http_create_join_answer_reconnect_finish_flow(self):
        status, event = self.request('/api/events', payload())
        self.assertEqual(status, 201)
        self.assertIn('host_key', event)
        base = '/api/events/'+event['id']
        status, member = self.request(base+'/join', {'name': 'HTTP player'})
        self.assertEqual(status, 200)
        answer = {'member_id': member['id'], 'question': 0, 'choice': 1}
        self.assertFalse(self.request(base+'/answers', answer)[1]['replayed'])
        self.assertTrue(self.request(base+'/answers', answer)[1]['replayed'])
        state = self.request(base+'?member='+member['id'])[1]
        self.assertEqual(state['answers'][0]['choice'], 1)
        self.assertTrue(state['host_protected'])
        self.assertNotIn('host_key', state)
        self.assertEqual(self.request(base+'/finish', {'host_key': event['host_key']})[0], 200)
        self.assertEqual(self.request(base)[1]['leaderboard'][0]['points'], 100)

    def test_http_finish_and_host_verify_reject_missing_wrong_and_hostile_capabilities(self):
        _, event = self.request('/api/events', payload())
        base = '/api/events/'+event['id']
        for hostile in ('wrong', None, 'x' * 257, '\ud800'):
            with self.subTest(hostile=repr(hostile)):
                self.assertEqual(self.request(base+'/host/verify', {'host_key': hostile})[0], 403)
        self.assertEqual(self.request(base+'/finish', {})[0], 403)
        self.assertEqual(self.request(base+'/finish', {'host_key': 'wrong'})[0], 403)
        self.assertEqual(self.request(base)[1]['phase'], 'open')
        self.assertEqual(self.request(base+'/host/verify', {'host_key': event['host_key']})[1],
                         {'host': True, 'legacy': False})
        self.assertEqual(self.request(base+'/finish', {'host_key': event['host_key']})[0], 200)
        self.assertEqual(self.request(base)[1]['phase'], 'finished')

    def test_invalid_json_objects_and_deep_payloads_are_reported(self):
        self.assertEqual(self.request('/api/events', raw=b'{broken')[0], 400)
        self.assertEqual(self.request('/api/events', raw=b'[]')[0], 422)
        self.assertIn(self.request('/api/events', raw=b'['*2000+b']'*2000)[0], (400, 422))

    def test_unknown_routes_events_and_oversized_bodies(self):
        self.assertEqual(self.request('/api/events/missing')[0], 404)
        self.assertEqual(self.request('/missing')[0], 404)
        self.assertEqual(self.request('/api/events', raw=b' '*256001)[0], 413)

    def test_page_and_health_are_served_without_external_dependencies(self):
        status, body = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn(b'<title>Lantern', body)
        self.assertNotIn(b'<script src=', body)
        self.assertEqual(self.request('/health'), (200, {'ok': True}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
