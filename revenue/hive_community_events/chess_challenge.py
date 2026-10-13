#!/usr/bin/env python3
"""Optional chess-puzzle presentation for Lantern's existing event engine.

This module does not implement chess rules. Hosts author a board position and an
explicit square-to-square move for each ordinary answer choice. Lantern remains
responsible for scheduling, first-answer-wins persistence, scoring, reconnects,
and leaderboards.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from app import Problem, Store, integer, make_handler, text

SQUARE_RE = re.compile(r"^[a-h][1-8]$")
PIECES = frozenset("KQRBNPkqrbnp")


def square(value, label: str) -> str:
    value = text(value, label, 2)
    if not SQUARE_RE.fullmatch(value):
        raise Problem(422, f"{label} must be a square from a1 to h8")
    return value


def validate_chess(value, choice_count: int):
    """Return canonical host-authored board metadata or None.

    Move legality is deliberately not inferred. Every authored choice must map
    to exactly one distinct from/to pair; the core event's ``correct`` index
    remains the only scoring key and stays hidden until finish.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise Problem(422, "Chess metadata must be an object")
    orientation = value.get("orientation", "white")
    if orientation not in ("white", "black"):
        raise Problem(422, "Chess orientation must be white or black")
    raw_pieces = value.get("pieces")
    if not isinstance(raw_pieces, dict) or not 1 <= len(raw_pieces) <= 32:
        raise Problem(422, "Chess pieces must contain 1–32 occupied squares")
    pieces = {}
    for raw_square, raw_piece in raw_pieces.items():
        board_square = square(raw_square, "Piece square")
        if board_square in pieces:
            raise Problem(422, "Chess piece squares must be distinct")
        if not isinstance(raw_piece, str) or raw_piece not in PIECES:
            raise Problem(422, "Chess pieces use one of KQRBNPkqrbnp")
        pieces[board_square] = raw_piece

    raw_moves = value.get("moves")
    if not isinstance(raw_moves, list) or len(raw_moves) != choice_count:
        raise Problem(422, "Chess moves must map every answer choice exactly once")
    moves, pairs, choices = [], set(), set()
    for raw_move in raw_moves:
        if not isinstance(raw_move, dict):
            raise Problem(422, "Each chess move must be an object")
        start = square(raw_move.get("from"), "Move from")
        end = square(raw_move.get("to"), "Move to")
        choice = integer(raw_move.get("choice"), "Move choice", 0, choice_count - 1)
        if start not in pieces:
            raise Problem(422, "Every authored move must start on an occupied square")
        pair = (start, end)
        if pair in pairs:
            raise Problem(422, "Chess move square pairs must be distinct")
        if choice in choices:
            raise Problem(422, "Each answer choice may have only one chess move")
        pairs.add(pair)
        choices.add(choice)
        moves.append({"from": start, "to": end, "choice": choice})
    if choices != set(range(choice_count)):
        raise Problem(422, "Chess moves must cover every answer choice")
    moves.sort(key=lambda item: item["choice"])
    return {"orientation": orientation,
            "pieces": {key: pieces[key] for key in sorted(pieces)},
            "moves": moves}


class ChessStore(Store):
    """Lantern Store with an additive sidecar for optional board metadata."""

    def __init__(self, database, clock=None):
        if clock is None:
            super().__init__(database)
        else:
            super().__init__(database, clock)
        with self.connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS chess_questions (
                    event TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                    question INTEGER NOT NULL,
                    metadata TEXT NOT NULL,
                    PRIMARY KEY(event, question));
            """)

    def create(self, payload):
        raw_questions = payload.get("questions") if isinstance(payload, dict) else None
        chess_rows = []
        if isinstance(raw_questions, list):
            for index, question in enumerate(raw_questions):
                # Let core Store.create issue its normal shape/choice errors.
                if isinstance(question, dict) and isinstance(question.get("choices"), list):
                    metadata = validate_chess(question.get("chess"), len(question["choices"]))
                    if metadata is not None:
                        chess_rows.append((index, metadata))
        result = super().create(payload)
        event_id = result["id"]
        if chess_rows:
            try:
                with self.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.executemany("INSERT INTO chess_questions(event,question,metadata) VALUES(?,?,?)",
                                   [(event_id, index, json.dumps(metadata, sort_keys=True, separators=(",", ":")))
                                    for index, metadata in chess_rows])
            except Exception:
                # A sidecar write must never leave a half-created chess event.
                with self.connect() as db:
                    db.execute("DELETE FROM events WHERE id=?", (event_id,))
                raise
        return result

    def state(self, event_id, member_id=None):
        state = super().state(event_id, member_id)
        if not state["questions"]:
            return state
        with self.connect() as db:
            rows = db.execute("SELECT question,metadata FROM chess_questions WHERE event=? ORDER BY question",
                              (event_id,)).fetchall()
        metadata = {row["question"]: json.loads(row["metadata"]) for row in rows}
        for index, question in enumerate(state["questions"]):
            if index in metadata:
                question["chess"] = metadata[index]
        return state


def make_chess_handler(store: ChessStore):
    Core = make_handler(store)

    class Handler(Core):
        def route(self, method):
            path = urlsplit(self.path).path
            if method == "GET" and path == "/chess":
                return self.send(200, Path(__file__).with_name("chess.html").read_bytes(),
                                 "text/html; charset=utf-8")
            if method == "GET" and path == "/chess-ui.js":
                return self.send(200, Path(__file__).with_name("chess_ui.js").read_bytes(),
                                 "application/javascript; charset=utf-8")
            return super().route(method)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="events.sqlite3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    store = ChessStore(args.db)
    server = ThreadingHTTPServer((args.host, args.port), make_chess_handler(store))
    print(f"Lantern chess companion is serving on http://{args.host}:{server.server_port}/chess", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
