#!/usr/bin/env python3
"""Order-verifying merchant edge for the Voice Support Desk.

This module is intentionally a separate edge.  It keeps per-order support
verifiers out of the desk's order table, snapshots, exports, and source bundle,
and delegates to the mature desk state machine only after a verifier succeeds.
It does not authenticate the telephone provider: run it on loopback behind an
existing trusted relay that performs that separate check.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import io
import ipaddress
import json
import re
import secrets
import sqlite3
import sys
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import desk

HERE = Path(__file__).resolve().parent
ACCESS_COLUMNS = ("order_ref", "support_code")
PBKDF2_ROUNDS = 200_000
DUMMY_SALT = b"hive006-dummy-v1"
DUMMY_VERIFIER = b"\0" * hashlib.sha256().digest_size
CODE_RE = re.compile(r"[0-9]{8,12}")
AGENT_VALUES = {"0", "agent", "human", "person", "team", "speak to an agent"}


def _loopback(value: str) -> str:
    value = value.strip()
    if value.lower() == "localhost":
        return value
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("merchant edge --bind must be loopback") from exc
    if not address.is_loopback:
        raise argparse.ArgumentTypeError("merchant edge --bind must be loopback")
    return value


def _code(value: str) -> str:
    value = value.strip().rstrip("#").lower().rstrip(".")
    words = value.split()
    if words and all(word in desk.DIGIT_WORDS for word in words):
        value = "".join(desk.DIGIT_WORDS[word] for word in words)
    if not CODE_RE.fullmatch(value):
        raise ValueError("support code must contain 8 to 12 digits")
    return value


def _derive(code: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", code.encode("ascii"), salt, PBKDF2_ROUNDS)


def _call_key(call_id: str) -> str:
    return "merchant-" + hashlib.sha256(call_id.encode("utf-8")).hexdigest()[:32]


def _request_hash(speech: str, digits: str) -> str:
    return hashlib.sha256(desk.canonical([speech, digits]).encode("utf-8")).hexdigest()


class MerchantGate:
    """Persistent verifier gate in the same SQLite file as ``desk.Store``."""

    def __init__(self, path, today=None):
        self.base = desk.Store(path, today=today)
        with self.base.connection(write=True) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS merchant_access (
                    order_ref TEXT PRIMARY KEY REFERENCES orders(order_ref),
                    salt BLOB NOT NULL,
                    verifier BLOB NOT NULL,
                    rounds INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS merchant_calls (
                    call_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    order_ref TEXT NOT NULL DEFAULT '',
                    base_call_id TEXT NOT NULL,
                    next_turn INTEGER NOT NULL,
                    verified INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS merchant_turns (
                    call_id TEXT NOT NULL REFERENCES merchant_calls(call_id),
                    turn INTEGER NOT NULL,
                    request_hash TEXT NOT NULL,
                    response TEXT NOT NULL,
                    PRIMARY KEY(call_id, turn)
                );
                """
            )

    def import_access_csv(self, content: str) -> dict[str, int]:
        desk.text(content, "merchant access CSV", 2_000_000)
        reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff"), newline=""))
        if reader.fieldnames != list(ACCESS_COLUMNS):
            raise ValueError("merchant access CSV header must be: " + ",".join(ACCESS_COLUMNS))
        rows: list[tuple[str, str]] = []
        seen: set[str] = set()
        for number, row in enumerate(reader, 2):
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("wrong column count")
                ref = desk.order_reference(row["order_ref"])
                if ref in seen:
                    raise ValueError("duplicate order reference in this import")
                seen.add(ref)
                rows.append((ref, _code(row["support_code"])))
            except ValueError as exc:
                raise ValueError(f"merchant access CSV row {number}: {exc}") from exc
        if not rows:
            raise ValueError("merchant access CSV has no rows")

        with self.base.connection(write=True) as db:
            existing = {
                row[0]
                for row in db.execute(
                    "SELECT order_ref FROM orders WHERE order_ref IN (%s)"
                    % ",".join("?" for _ in rows),
                    [ref for ref, _code_value in rows],
                )
            }
            missing = sorted(ref for ref, _code_value in rows if ref not in existing)
            if missing:
                raise ValueError("merchant access references unknown order(s): " + ", ".join(missing))
            stamp = desk.dt.datetime.now(desk.dt.timezone.utc).isoformat()
            stored = []
            for ref, code in rows:
                salt = secrets.token_bytes(16)
                stored.append((ref, salt, _derive(code, salt), PBKDF2_ROUNDS, stamp))
            db.executemany(
                """INSERT INTO merchant_access(order_ref,salt,verifier,rounds,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(order_ref) DO UPDATE SET
                     salt=excluded.salt,verifier=excluded.verifier,
                     rounds=excluded.rounds,updated_at=excluded.updated_at""",
                stored,
            )
        return {"provisioned": len(rows)}

    @staticmethod
    def _public(result: dict, outer_call_id: str, *, verified: bool) -> dict:
        value = dict(result)
        value["call_id"] = outer_call_id
        if value.get("next_turn") is not None:
            value["next_turn"] += 1
        if not verified:
            value["order_ref"] = None
        value["twiml"] = desk.twiml(value)
        return value

    @staticmethod
    def _gate_result(call_id: str, message: str, state: str, next_turn: int | None) -> dict:
        result = {
            "call_id": call_id,
            "message": message,
            "state": state,
            "order_ref": None,
            "next_turn": next_turn,
        }
        result["twiml"] = desk.twiml(result)
        return result

    @staticmethod
    def _stored_turn(db, call_id: str, turn: int, digest: str):
        row = db.execute(
            "SELECT request_hash,response FROM merchant_turns WHERE call_id=? AND turn=?",
            (call_id, turn),
        ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != digest:
            raise desk.Conflict("this merchant call turn already has different input")
        return json.loads(row["response"])

    def _finish(self, call_id: str, turn: int, digest: str, expected_next: int, result: dict, *, state: str, verified: bool, order_ref: str | None = None):
        with self.base.connection(write=True) as db:
            replay = self._stored_turn(db, call_id, turn, digest)
            if replay is not None:
                return replay
            call = db.execute("SELECT * FROM merchant_calls WHERE call_id=?", (call_id,)).fetchone()
            if call is None or call["next_turn"] != expected_next or call["state"] == "ended":
                raise desk.Conflict("merchant call changed while this turn was processed")
            new_next = result["next_turn"] if result["next_turn"] is not None else expected_next + 1
            db.execute(
                "UPDATE merchant_calls SET state=?,order_ref=?,next_turn=?,verified=? WHERE call_id=?",
                (state, call["order_ref"] if order_ref is None else order_ref, new_next, int(verified), call_id),
            )
            db.execute(
                "INSERT INTO merchant_turns VALUES(?,?,?,?)",
                (call_id, turn, digest, desk.canonical(result)),
            )
            return result

    def _agent_handoff(self, outer_call_id: str, base_call_id: str) -> dict:
        self.base.turn(base_call_id, 0)
        result = self.base.turn(base_call_id, 1, speech="agent")
        return self._public(result, outer_call_id, verified=False)

    def turn(self, call_id, turn, speech="", digits=""):
        call_id = desk.text(call_id, "call_id", 100)
        speech = desk.text(speech, "speech", 1000, empty=True)
        digits = desk.text(digits, "digits", 32, empty=True)
        if digits and not re.fullmatch(r"[0-9*#]+", digits):
            raise ValueError("digits contains a non-keypad character")
        if type(turn) is not int or turn < 0:
            raise ValueError("turn must be a nonnegative integer")
        digest = _request_hash(speech, digits)

        with self.base.connection(write=True) as db:
            replay = self._stored_turn(db, call_id, turn, digest)
            if replay is not None:
                return replay
            call = db.execute("SELECT * FROM merchant_calls WHERE call_id=?", (call_id,)).fetchone()
            if call is None:
                if turn != 0 or speech or digits:
                    raise desk.Conflict("a merchant call must start with empty turn 0")
                base_call_id = _call_key(call_id)
                db.execute(
                    "INSERT INTO merchant_calls(call_id,state,base_call_id,next_turn) VALUES(?,?,?,?)",
                    (call_id, "order", base_call_id, 1),
                )
                result = self._gate_result(
                    call_id,
                    "Welcome to the secure order desk. Enter your order reference, then pound, or speak its digits individually. Say agent or press 0 for the team.",
                    "order",
                    1,
                )
                db.execute(
                    "INSERT INTO merchant_turns VALUES(?,?,?,?)",
                    (call_id, 0, digest, desk.canonical(result)),
                )
                return result
            if turn != call["next_turn"] or call["state"] == "ended":
                raise desk.Conflict("not the next active merchant call turn")
            snapshot = dict(call)

        raw_value = (digits or speech).lower().strip().rstrip(".")
        if snapshot["state"] in {"order", "verify"} and raw_value in AGENT_VALUES:
            result = self._agent_handoff(call_id, snapshot["base_call_id"])
            return self._finish(
                call_id,
                turn,
                digest,
                snapshot["next_turn"],
                result,
                state="ended",
                verified=False,
            )

        if snapshot["state"] == "order":
            try:
                ref = desk.spoken_reference(raw_value)
            except ValueError:
                ref = ""
            result = self._gate_result(
                call_id,
                "Enter the 8 to 12 digit support code from your order confirmation, then pound, or speak its digits individually. Say agent or press 0 for the team.",
                "verify",
                snapshot["next_turn"] + 1,
            )
            return self._finish(
                call_id,
                turn,
                digest,
                snapshot["next_turn"],
                result,
                state="verify",
                verified=False,
                order_ref=ref,
            )

        if snapshot["state"] == "verify":
            try:
                supplied = _code(digits or speech)
            except ValueError:
                supplied = ""
            with self.base.connection() as db:
                access = db.execute(
                    "SELECT salt,verifier,rounds FROM merchant_access WHERE order_ref=?",
                    (snapshot["order_ref"],),
                ).fetchone()
            valid = False
            if supplied:
                salt = access["salt"] if access is not None else DUMMY_SALT
                expected = access["verifier"] if access is not None else DUMMY_VERIFIER
                stored_rounds = int(access["rounds"]) if access is not None else PBKDF2_ROUNDS
                candidate = hashlib.pbkdf2_hmac(
                    "sha256",
                    supplied.encode("ascii"),
                    salt,
                    PBKDF2_ROUNDS,
                )
                matched = hmac.compare_digest(candidate, expected)
                valid = access is not None and stored_rounds == PBKDF2_ROUNDS and matched
            if not valid:
                result = self._gate_result(
                    call_id,
                    "We could not verify those order details. No order information was disclosed and no return was created. Please contact the shop through its usual support channel.",
                    "ended",
                    None,
                )
                return self._finish(
                    call_id,
                    turn,
                    digest,
                    snapshot["next_turn"],
                    result,
                    state="ended",
                    verified=False,
                )

            self.base.turn(snapshot["base_call_id"], 0)
            base_result = self.base.turn(
                snapshot["base_call_id"], 1, speech=snapshot["order_ref"]
            )
            result = self._public(base_result, call_id, verified=True)
            return self._finish(
                call_id,
                turn,
                digest,
                snapshot["next_turn"],
                result,
                state=result["state"],
                verified=True,
            )

        if not snapshot["verified"]:
            raise desk.Conflict("merchant call is not verified")
        base_result = self.base.turn(
            snapshot["base_call_id"], turn - 1, speech=speech, digits=digits
        )
        result = self._public(base_result, call_id, verified=True)
        return self._finish(
            call_id,
            turn,
            digest,
            snapshot["next_turn"],
            result,
            state=result["state"],
            verified=True,
        )

    def dial_result(self, call_id, status):
        call_id = desk.text(call_id, "CallSid", 100)
        with self.base.connection() as db:
            call = db.execute(
                "SELECT base_call_id,verified FROM merchant_calls WHERE call_id=?", (call_id,)
            ).fetchone()
        if call is None or not call["verified"]:
            raise desk.Conflict("no verified merchant call for dial result")
        return self._public(
            self.base.dial_result(call["base_call_id"], status), call_id, verified=True
        )


def make_handler(gate: MerchantGate):
    class Handler(BaseHTTPRequestHandler):
        server_version = "VoiceSupportMerchantGate/1"

        def log_message(self, *_args):
            pass

        def send(self, body, status=200, mime="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else (body.encode() if isinstance(body, str) else desk.canonical(body).encode())
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if urlsplit(self.path).path == "/health":
                self.send({"status": "ok", "order_verification": "required", "provider_authentication": "external_trusted_relay_required"})
            else:
                self.send({"error": "not found"}, 404)

        def do_POST(self):
            route = urlsplit(self.path)
            try:
                if route.path not in ("/voice", "/dial-result"):
                    return self.send({"error": "not found"}, 404)
                raw_length = self.headers.get("Content-Length", "")
                if not raw_length.isdecimal() or not 0 < int(raw_length) <= 2_000_000:
                    raise ValueError("Content-Length must be between 1 and 2000000")
                if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                    raise ValueError("voice requests require form-urlencoded input")
                body = self.rfile.read(int(raw_length)).decode("utf-8")
                form = parse_qs(body, keep_blank_values=True, strict_parsing=True, encoding="utf-8", errors="strict")
                if any(len(values) != 1 for values in form.values()):
                    raise ValueError("duplicate form field")
                params = {key: values[0] for key, values in form.items()}
                if route.path == "/dial-result":
                    result = gate.dial_result(params.get("CallSid", ""), params.get("DialCallStatus", ""))
                else:
                    query = parse_qs(route.query, keep_blank_values=True)
                    if set(query) - {"turn"} or len(query.get("turn", ["0"])) != 1:
                        raise ValueError("invalid turn query")
                    stamp = query.get("turn", ["0"])[0]
                    if not re.fullmatch(r"0|[1-9][0-9]*", stamp):
                        raise ValueError("invalid turn query")
                    result = gate.turn(params.get("CallSid", ""), int(stamp), params.get("SpeechResult", ""), params.get("Digits", ""))
                self.send(result["twiml"], mime="application/xml; charset=utf-8")
            except (ValueError, UnicodeError, csv.Error, OverflowError) as exc:
                self.send({"error": str(exc)}, 409 if isinstance(exc, desk.Conflict) else 400)
            except sqlite3.Error:
                self.send({"error": "database operation failed; retry the same request"}, 503)

    return Handler


def bundle(destination: Path) -> str:
    names = [
        "desk.py",
        "index.html",
        "README.md",
        "test_desk.py",
        "orders.example.csv",
        "merchant_auth.py",
        "test_merchant_auth.py",
        "merchant-access.example.csv",
        "MERCHANT-AUTH.md",
    ]
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(HERE / name, "voice-support-desk/" + name)
    return str(destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="voice-support.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    access = sub.add_parser("access")
    access.add_argument("csv_file", type=Path)
    serve = sub.add_parser("serve")
    serve.add_argument("--bind", type=_loopback, default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8097)
    package = sub.add_parser("bundle")
    package.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "bundle":
            print(bundle(args.destination))
            return 0
        gate = MerchantGate(args.db)
        if args.command == "access":
            print(desk.canonical(gate.import_access_csv(args.csv_file.read_text(encoding="utf-8-sig"))))
        else:
            with ThreadingHTTPServer((args.bind, args.port), make_handler(gate)) as server:
                print(f"Voice Support Merchant Gate: http://{args.bind}:{server.server_port}", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
        return 0
    except (ValueError, OSError, sqlite3.Error, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
