from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse

from .core import PolicyError, attach_model_advisory, compile_plan, verify_receipt
from .gloo import simulated_advisory


class AppHandler(BaseHTTPRequestHandler):
    static_dir = Path(__file__).resolve().parent.parent / "static"
    fixtures_dir = Path(__file__).resolve().parent.parent / "fixtures"

    def _json(self, status: int, payload):
        body = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1_000_000:
            raise ValueError("request body length invalid")
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            body = (self.static_dir / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/demo":
            request_data = json.loads((self.fixtures_dir / "request.json").read_text())
            catalog = json.loads((self.fixtures_dir / "resources.json").read_text())
            package = compile_plan(request_data, catalog)
            package = attach_model_advisory(package, simulated_advisory(package["plan"]))
            self._json(200, package)
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self._read_json()
            if path == "/api/plan":
                package = compile_plan(data["request"], data["catalog"])
                package = attach_model_advisory(package, simulated_advisory(package["plan"]))
                self._json(200, package)
                return
            if path == "/api/verify":
                result = verify_receipt(data)
                self._json(200 if result.get("ok") else 422, result)
                return
            self._json(404, {"error": "not_found"})
        except (ValueError, KeyError, PolicyError, json.JSONDecodeError) as exc:
            self._json(400, {"error": "invalid_request", "detail": str(exc)})

    def log_message(self, format, *args):
        return


def serve(host="127.0.0.1", port=8765):
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"NeighborSignal local demo: http://{host}:{port}")
    print("No external send/spend capability is exposed by this server.")
    server.serve_forever()
