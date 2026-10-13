"""Vercel Python function for hosted CUA-S1 choice scoring."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.cua_s1_cloud import runtime_onnx  # noqa: E402


def handle_request(method: str, path: str, body: bytes) -> tuple[int, dict]:
    if path.split("?", 1)[0] not in {"/cua-s1", "/cua-s1/", "/api/cua_s1", "/api/cua_s1/"}:
        return 404, {"error": "not_found"}
    if method == "GET":
        return 200, {"ok": True, "model": "cua-ai/cua-s1-forms", "revision": runtime_onnx.REVISION,
                     "artifact_sha256": runtime_onnx.MODEL_SHA256,
                     "context_tokens": runtime_onnx.CONTEXT_TOKENS,
                     "option_tokens": runtime_onnx.OPTION_TOKENS,
                     "max_options": runtime_onnx.MAX_OPTIONS}
    if method != "POST":
        return 405, {"error": "method_not_allowed"}
    if len(body) > 65536:
        return 413, {"error": "body_too_large"}
    try:
        return 200, runtime_onnx.score(json.loads(body))
    except (ValueError, UnicodeDecodeError) as exc:
        return 400, {"error": "invalid_request", "message": str(exc)}


class handler(BaseHTTPRequestHandler):
    def _respond(self, status: int, payload: dict):
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._respond(*handle_request("GET", self.path, b""))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 65536:
            return self._respond(413, {"error": "body_size_invalid"})
        self._respond(*handle_request("POST", self.path, self.rfile.read(length)))
