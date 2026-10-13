from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import turnbench

MAX_REQUEST = 1_000_000


def evaluate_payload(payload):
    obj = turnbench._expect_exact_keys(payload, {"scenario", "trace"}, where="request")
    scenario = turnbench.validate_scenario(obj["scenario"])
    trace = turnbench.validate_trace(obj["trace"])
    return turnbench.evaluate(scenario, trace)


class handler(BaseHTTPRequestHandler):
    def _send(self, status, obj):
        data = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n <= 0 or n > MAX_REQUEST:
                raise ValueError("request size invalid")
            raw = self.rfile.read(n)
            payload = turnbench.loads_strict(raw)
            self._send(200, evaluate_payload(payload))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._send(400, {"error": str(exc)})
        except Exception:
            self._send(500, {"error": "internal error"})

    def do_GET(self):
        self._send(200, {"service": "turnbench-evaluator", "schema": turnbench.RECEIPT_SCHEMA, "status": "ok"})
