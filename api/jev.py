"""Hosted Commons Jev decisions on the existing Vercel project.

The TypeSafe key is read only from the Vercel server environment. Requests
contain state and typed questions; responses contain provider answers and usage.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "host") not in sys.path:
    sys.path.insert(0, str(ROOT / "host"))

import jev  # noqa: E402

MAX_BODY_BYTES = 256 * 1024


def _json(status: int, payload: dict[str, Any]) -> tuple[int, bytes]:
    return status, json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def handle_request(
    method: str,
    path: str,
    body: bytes,
    *,
    evaluator: Callable[..., dict[str, Any]] = jev.systemone,
    key: str | None = None,
) -> tuple[int, bytes]:
    """Pure HTTP boundary used by the Vercel handler and focused tests."""
    if path.split("?", 1)[0] not in ("/jev", "/jev/", "/api/jev", "/api/jev/"):
        return _json(404, {"ok": False, "error": {"code": "NOT_FOUND"}})
    if method == "GET":
        return _json(200, {"ok": True, "service": "commons-jev", "model": jev.DEFAULT_MODEL,
                           "configured": bool((key if key is not None else os.environ.get(jev.ENV_KEY, "")).strip())})
    if method != "POST":
        return _json(405, {"ok": False, "error": {"code": "METHOD_NOT_ALLOWED"}})
    if len(body) > MAX_BODY_BYTES:
        return _json(413, {"ok": False, "error": {"code": "BODY_TOO_LARGE"}})
    try:
        request = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return _json(400, {"ok": False, "error": {"code": "BAD_JSON"}})
    if not isinstance(request, dict) or not {"state", "questions"}.issubset(request):
        return _json(400, {"ok": False, "error": {"code": "BAD_REQUEST", "message": "Supply state and questions"}})
    state, questions = request["state"], request["questions"]
    if not isinstance(state, str) or not state.strip():
        return _json(400, {"ok": False, "error": {"code": "EMPTY_STATE"}})
    if len(state.encode("utf-8")) > jev.MAX_STATE_BYTES:
        return _json(413, {"ok": False, "error": {"code": "STATE_TOO_LARGE"}})
    problems = jev.validate_questions(questions)
    if problems:
        return _json(400, {"ok": False, "error": {"code": "BAD_QUESTIONS", "problems": problems[:5]}})
    secret = key if key is not None else os.environ.get(jev.ENV_KEY, "").strip()
    if not secret:
        return _json(503, {"ok": False, "error": {"code": "NO_KEY"}})
    try:
        answer = evaluator(state, questions, model=jev.DEFAULT_MODEL, timeout=30, key=secret)
    except jev.JevError as exc:
        code = str(exc).split(":", 1)[0]
        status = 503 if code == "NO_KEY" else 502
        return _json(status, {"ok": False, "error": {"code": code}})
    if not isinstance(answer, dict) or not isinstance(answer.get("answers"), dict):
        return _json(502, {"ok": False, "error": {"code": "BAD_REPLY"}})
    return _json(200, {"ok": True, "model": answer.get("model"),
                       "answers": answer["answers"], "usage": answer.get("usage")})


class handler(BaseHTTPRequestHandler):
    """Vercel Python function entry point."""

    def _dispatch(self, method: str) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0:
            status, blob = _json(400, {"ok": False, "error": {"code": "BAD_LENGTH"}})
        elif length > MAX_BODY_BYTES:
            status, blob = _json(413, {"ok": False, "error": {"code": "BODY_TOO_LARGE"}})
        else:
            body = self.rfile.read(length) if method == "POST" else b""
            status, blob = handle_request(method, self.path, body)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(blob)

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_HEAD(self) -> None:
        self._dispatch("HEAD")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def log_request(self, code: Any = "-", size: Any = "-") -> None:
        return
