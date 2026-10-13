#!/usr/bin/env python3
"""Tiny localhost browser desk for editing/validating/rendering short-video projects."""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from studio import ProjectError, render_project, validate_project

ROOT = pathlib.Path(__file__).resolve().parent
INDEX = ROOT / "index.html"


class Handler(BaseHTTPRequestHandler):
    server_version = "ShortVideoStudio/1"

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/":
            body = INDEX.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/health":
            self._json(200, {"ok": True, "network": "unused", "publishing": "manual"})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "invalid Content-Length"})
            return
        if size <= 0 or size > 512_000:
            self._json(400, {"error": "body must be 1..512000 bytes"})
            return
        try:
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            self._json(400, {"error": f"invalid JSON: {exc}"})
            return
        if self.path == "/api/validate":
            try:
                normalized = validate_project(payload, ROOT)
            except (ProjectError, TypeError) as exc:
                self._json(422, {"error": str(exc)})
                return
            self._json(200, {"ok": True, "project": normalized})
            return
        if self.path == "/api/render":
            name = self.headers.get("X-Output-Name", "rendered.mp4")
            safe = pathlib.Path(name).name
            if not safe.lower().endswith(".mp4"):
                safe += ".mp4"
            exports = ROOT / "workspace" / "exports"
            exports.mkdir(parents=True, exist_ok=True)
            try:
                with tempfile.NamedTemporaryFile("w", suffix=".json", dir=ROOT, delete=False, encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                    temp_project = pathlib.Path(handle.name)
                try:
                    result = render_project(temp_project, exports / safe)
                finally:
                    temp_project.unlink(missing_ok=True)
            except (ProjectError, RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
                self._json(422, {"error": str(exc)})
                return
            self._json(200, {"ok": True, "output": result["output"], "captions": result["captions"], "probe": result["probe"]})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, format: str, *args) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8877)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Short Video Studio on http://{args.host}:{server.server_port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
