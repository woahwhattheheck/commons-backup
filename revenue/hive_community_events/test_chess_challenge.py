"""Focused actual SQLite/HTTP tests for Lantern's optional chess presentation."""
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import Problem, Store
from chess_challenge import ChessStore, make_chess_handler, validate_chess


def chess_question():
    return {"prompt": "Choose the authored knight move.",
            "choices": ["g1 to f3", "g1 to h3"], "correct": 0, "points": 100,
            "chess": {"orientation": "white", "pieces": {"e1": "K", "g1": "N", "e8": "k"},
                      "moves": [{"from": "g1", "to": "f3", "choice": 0},
                                {"from": "g1", "to": "h3", "choice": 1}]}}


def payload(opens=1000, ends=2000):
    return {"title": "Chess night", "room": "Room", "opens": opens, "ends": ends,
            "questions": [chess_question(),
                          {"prompt": "Two plus two?", "choices": ["3", "4"], "correct": 1, "points": 50}]}


class ChessStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "events.sqlite3"
        self.now = 1100
        self.store = ChessStore(self.path, lambda: self.now)

    def error(self, status, fn):
        with self.assertRaises(Problem) as caught: fn()
        self.assertEqual(caught.exception.status, status)

    def test_validation_canonicalizes_without_chess_inference(self):
        meta = validate_chess(chess_question()["chess"], 2)
        self.assertEqual(meta["orientation"], "white")
        self.assertEqual([m["choice"] for m in meta["moves"]], [0, 1])
        self.assertEqual(meta["pieces"]["g1"], "N")
        self.assertNotIn("legal", meta)

    def test_invalid_metadata_is_rejected_before_event_creation(self):
        invalid = []
        base = chess_question()["chess"]
        invalid.append({**base, "orientation": "sideways"})
        invalid.append({**base, "pieces": {"z9": "N"}})
        invalid.append({**base, "pieces": {"g1": "X"}})
        invalid.append({**base, "moves": [{"from": "g1", "to": "f3", "choice": 0}]})
        invalid.append({**base, "moves": [{"from": "g1", "to": "f3", "choice": 0}, {"from": "g1", "to": "f3", "choice": 1}]})
        invalid.append({**base, "moves": [{"from": "a1", "to": "f3", "choice": 0}, {"from": "g1", "to": "h3", "choice": 1}]})
        for chess in invalid:
            with self.subTest(chess=chess):
                question = {**chess_question(), "chess": chess}
                self.error(422, lambda: self.store.create({**payload(), "questions": [question]}))
        self.assertEqual(self.store.listing(), [])

    def test_duplicate_canonical_piece_square_is_rejected_before_event_creation(self):
        base = chess_question()["chess"]
        duplicate = {**base, "pieces": {"g1": "N", " g1 ": "B", "e8": "k"}}
        question = {**chess_question(), "chess": duplicate}
        self.error(422, lambda: self.store.create({**payload(), "questions": [question]}))
        self.assertEqual(self.store.listing(), [])

    def test_open_state_attaches_board_but_hides_correct_index(self):
        event = self.store.create(payload())["id"]
        state = self.store.state(event)
        self.assertEqual(state["phase"], "open")
        self.assertEqual(state["questions"][0]["chess"]["moves"][0], {"from": "g1", "to": "f3", "choice": 0})
        self.assertNotIn("correct", state["questions"][0])
        self.assertNotIn("chess", state["questions"][1])

    def test_schedule_hides_board_and_question_until_open(self):
        self.now = 900
        event = self.store.create(payload(1000, 2000))["id"]
        self.assertEqual(self.store.state(event)["questions"], [])
        self.now = 1100
        self.assertIn("chess", self.store.state(event)["questions"][0])

    def test_answer_scoring_reconnect_and_restart_remain_core_semantics(self):
        event = self.store.create(payload())["id"]
        member = self.store.join(event, {"name": "Player"})["id"]
        first = self.store.answer(event, {"member_id": member, "question": 0, "choice": 0})
        replay = self.store.answer(event, {"member_id": member, "question": 0, "choice": 0})
        self.assertFalse(first["replayed"]); self.assertTrue(replay["replayed"])
        reopened = ChessStore(self.path, lambda: self.now)
        self.assertEqual(reopened.join(event, {"member_id": member})["id"], member)
        reopened.finish(event)
        state = reopened.state(event, member)
        self.assertEqual(state["leaderboard"][0]["points"], 100)
        self.assertEqual(state["questions"][0]["correct"], 0)
        self.assertIn("chess", state["questions"][0])

    def test_plain_lantern_store_remains_compatible_fallback(self):
        event = self.store.create(payload())["id"]
        plain = Store(self.path, lambda: self.now)
        state = plain.state(event)
        self.assertEqual(state["questions"][0]["choices"], ["g1 to f3", "g1 to h3"])
        self.assertNotIn("chess", state["questions"][0])


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.now = 1100
        cls.store = ChessStore(Path(cls.temp.name)/"events.sqlite3", lambda: cls.now)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_chess_handler(cls.store))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(); cls.temp.cleanup()

    def request(self, path, data=None):
        raw = None if data is None else json.dumps(data).encode()
        req = Request(self.base+path, data=raw, headers={"Content-Type":"application/json"})
        try: response = urlopen(req, timeout=5)
        except HTTPError as exc: response = exc
        with response:
            body = response.read(); ctype=response.headers.get("Content-Type","")
            return response.status, json.loads(body) if "application/json" in ctype else body

    def test_chess_page_is_additive_and_dependency_free(self):
        status, page = self.request("/chess")
        self.assertEqual(status, 200)
        self.assertIn(b"Lantern chess challenges", page)
        self.assertIn(b"function chessBoard", page)
        self.assertIn(b'src="/chess-ui.js"', page)
        self.assertNotIn(b"https://", page)
        status, helper = self.request("/chess-ui.js")
        self.assertEqual(status, 200)
        self.assertIn(b"choiceForMove", helper)

    def test_http_create_join_square_mapped_choice_answer_and_reconnect(self):
        status, created = self.request("/api/events", payload())
        self.assertEqual(status, 201)
        base = "/api/events/"+created["id"]
        status, state = self.request(base)
        self.assertEqual(status, 200)
        move = state["questions"][0]["chess"]["moves"][0]
        self.assertEqual((move["from"], move["to"], move["choice"]), ("g1", "f3", 0))
        self.assertNotIn("correct", state["questions"][0])
        _, member = self.request(base+"/join", {"name":"HTTP player"})
        answer = {"member_id":member["id"], "question":0, "choice":move["choice"]}
        self.assertFalse(self.request(base+"/answers", answer)[1]["replayed"])
        self.assertTrue(self.request(base+"/answers", answer)[1]["replayed"])
        self.assertEqual(self.request(base+"?member="+member["id"])[1]["answers"][0]["choice"], 0)
        self.assertEqual(self.request(base+"/finish", {"host_key": created["host_key"]})[0], 200)
        finished = self.request(base)[1]
        self.assertEqual(finished["leaderboard"][0]["points"], 100)
        self.assertEqual(finished["questions"][0]["correct"], 0)


if __name__ == "__main__": unittest.main(verbosity=2)
