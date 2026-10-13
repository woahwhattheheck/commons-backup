#!/usr/bin/env python3
"""Headless Claude peer client against a fake gateway that speaks TENON's C1 contract.

No model usage is spent here. The fake gateway implements the routes TENON
posted as built (2026-09-04 20:43 EDT): /health, POST /v1/runs, GET
/v1/runs/{id}?wait_ms=, GET /v1/runs/{id}/events (seq/event), POST
/v1/runs/{id}/followup, POST /v1/sessions/{sid}/followup, GET
/v1/sessions/{sid}, POST /v1/runs/{id}/cancel (409 when terminal), POST
/v1/recover, GET /v1/events. The live acceptance against the real gateway is
recorded in integrations/claude_headless/ACCEPTANCE.md.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import threading
import time
import unittest
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODULE_PATH = Path(__file__).parent / "integrations" / "claude_headless" / "client.py"
SPEC = importlib.util.spec_from_file_location("claude_headless_client", MODULE_PATH)
client_mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = client_mod
SPEC.loader.exec_module(client_mod)

TERMINAL = {"completed", "error", "cancelled", "interrupted"}


class FakeGateway(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), FakeHandler)
        self.runs: dict[str, dict] = {}
        self.events: dict[str, list[dict]] = {}
        self.journal: list[dict] = []
        self.requests: list[tuple[str, str, dict]] = []
        self.lock = threading.Lock()
        self.complete_after = 0.15

    def new_run(self, prompt: str, session_id: str | None, extra: dict) -> dict:
        run_id = uuid.uuid4().hex[:16]
        session_id = session_id or str(uuid.uuid4())
        run = {
            "run_id": run_id,
            "session_id": session_id,
            "status": "queued",
            "result_text": None,
            "num_turns": None,
            "cost_usd": None,
            "duration_ms": None,
            "exit_code": None,
            "error": None,
            "pid": None,
            "cwd": extra.get("cwd") or ".",
            "label": extra.get("label"),
            "peer": extra.get("peer"),
            "prompt": prompt,
            "headless": {"foreground_unchanged": True, "child_visible_windows": 0},
        }
        with self.lock:
            self.runs[run_id] = run
            self.events[run_id] = []
            self.journal.append({"seq": len(self.journal) + 1, "run_id": run_id, "status": "queued"})
        threading.Thread(target=self._execute, args=(run,), daemon=True).start()
        return run

    def _emit(self, run: dict, event: dict) -> None:
        with self.lock:
            seq = len(self.events[run["run_id"]]) + 1
            self.events[run["run_id"]].append({"seq": seq, "event": event})

    def _execute(self, run: dict) -> None:
        time.sleep(0.05)
        with self.lock:
            run["status"] = "running"
            run["pid"] = 4242
            self.journal.append({"seq": len(self.journal) + 1, "run_id": run["run_id"], "status": "running"})
        self._emit(run, {"type": "system", "subtype": "init", "session_id": run["session_id"]})
        prompt = run["prompt"]
        if prompt.startswith("SLEEP"):
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and run["status"] == "running":
                time.sleep(0.02)
            return
        time.sleep(self.complete_after)
        if run["status"] != "running":
            return
        text = "boom" if prompt.startswith("FAIL") else f"echo:{prompt}"
        self._emit(run, {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
        self._emit(run, {"type": "result", "subtype": "success", "result": text})
        with self.lock:
            run["status"] = "error" if prompt.startswith("FAIL") else "completed"
            run["result_text"] = text
            run["num_turns"] = 1
            run["cost_usd"] = 0.0
            run["duration_ms"] = 5
            run["exit_code"] = 1 if run["status"] == "error" else 0
            run["error"] = "stub error" if run["status"] == "error" else None
            self.journal.append({"seq": len(self.journal) + 1, "run_id": run["run_id"], "status": run["status"]})


class FakeHandler(BaseHTTPRequestHandler):
    server: FakeGateway
    protocol_version = "HTTP/1.1"

    def log_message(self, _fmt, *_args):
        return

    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict:
        size = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(size) if size else b""
        return json.loads(raw.decode()) if raw.strip() else {}

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        parts = [p for p in parsed.path.split("/") if p]
        self.server.requests.append(("GET", parsed.path, q))
        if parsed.path == "/health":
            self._send(200, {"ok": True, "service": "commons-claude-headless-gateway", "claude": "claude", "claude_version": "stub", "root": "/tmp", "active_runs": [], "event_cursor": len(self.server.journal), "env_scrub": ["CLAUDECODE"]})
            return
        if parts == ["v1", "events"]:
            after = int(q.get("after", 0))
            items = [e for e in self.server.journal if e["seq"] > after and (not q.get("run_id") or e["run_id"] == q["run_id"])]
            self._send(200, {"ok": True, "events": items, "next_cursor": max([after] + [e["seq"] for e in items])})
            return
        if len(parts) == 3 and parts[:2] == ["v1", "runs"]:
            run = self.server.runs.get(parts[2])
            if run is None:
                self._send(404, {"ok": False, "error": "run_not_found"})
                return
            wait_ms = int(q.get("wait_ms", 0))
            deadline = time.monotonic() + wait_ms / 1000
            while run["status"] not in TERMINAL and time.monotonic() < deadline:
                time.sleep(0.02)
            self._send(200, {"ok": True, "run": dict(run)})
            return
        if len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "events":
            run = self.server.runs.get(parts[2])
            if run is None:
                self._send(404, {"ok": False, "error": "run_not_found"})
                return
            after = int(q.get("after", 0))
            wait_ms = int(q.get("wait_ms", 0))
            deadline = time.monotonic() + wait_ms / 1000
            while True:
                items = [e for e in self.server.events[run["run_id"]] if e["seq"] > after]
                if items or time.monotonic() >= deadline or run["status"] in TERMINAL:
                    break
                time.sleep(0.02)
            limit = int(q.get("limit", 100))
            items = items[:limit]
            self._send(200, {"ok": True, "events": items, "next_cursor": max([after] + [e["seq"] for e in items])})
            return
        if len(parts) == 3 and parts[:2] == ["v1", "sessions"]:
            runs = [dict(r) for r in self.server.runs.values() if r["session_id"] == parts[2]]
            if not runs:
                self._send(404, {"ok": False, "error": "session_not_found"})
                return
            self._send(200, {"ok": True, "session_id": parts[2], "runs": runs, "resumable": True, "transcript_paths": ["/tmp/x.jsonl"]})
            return
        self._send(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        body = self._body()
        self.server.requests.append(("POST", parsed.path, body))
        if parts == ["v1", "runs"]:
            if not str(body.get("prompt", "")).strip():
                self._send(400, {"ok": False, "error": "prompt_required"})
                return
            run = self.server.new_run(body["prompt"], body.get("session_id"), body)
            self._send(202, {"ok": True, "run_id": run["run_id"], "session_id": run["session_id"], "status": run["status"], "run": dict(run)})
            return
        if len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "followup":
            parent = self.server.runs.get(parts[2])
            if parent is None:
                self._send(404, {"ok": False, "error": "run_not_found"})
                return
            run = self.server.new_run(body["prompt"], parent["session_id"], {**body, "cwd": parent["cwd"]})
            self._send(202, {"ok": True, "run_id": run["run_id"], "session_id": run["session_id"], "status": run["status"], "run": dict(run)})
            return
        if len(parts) == 4 and parts[:2] == ["v1", "sessions"] and parts[3] == "followup":
            run = self.server.new_run(body["prompt"], parts[2], body)
            self._send(202, {"ok": True, "run_id": run["run_id"], "session_id": run["session_id"], "status": run["status"], "run": dict(run)})
            return
        if len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "cancel":
            run = self.server.runs.get(parts[2])
            if run is None:
                self._send(404, {"ok": False, "error": "run_not_found"})
                return
            if run["status"] in TERMINAL:
                self._send(409, {"ok": False, "error": "already_terminal", "status": run["status"]})
                return
            with self.server.lock:
                run["status"] = "cancelled"
                self.server.journal.append({"seq": len(self.server.journal) + 1, "run_id": run["run_id"], "status": "cancelled"})
            self._send(200, {"ok": True, "status": "cancelled", "tree": [4242], "killed_pids": [4242]})
            return
        if parts == ["v1", "recover"]:
            self._send(200, {"ok": True, "recovered": [], "still_running": [r["run_id"] for r in self.server.runs.values() if r["status"] == "running"]})
            return
        self._send(404, {"ok": False, "error": "not_found"})


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = FakeGateway()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.client = client_mod.HeadlessClient(self.base)
        self.server.requests.clear()

    def test_health_is_passed_through(self):
        health = self.client.health()
        self.assertTrue(health["ok"])
        self.assertEqual(health["service"], "commons-claude-headless-gateway")
        self.assertEqual(health["http_status"], 200)

    def test_submit_sends_contract_fields_and_wait_returns_terminal_run(self):
        ack = self.client.submit("hello", peer="TESTPEER", label="t1", cwd="/w", model="sonnet", tools=["Read"], permission_mode="plan", partial=True)
        self.assertEqual(ack["http_status"], 202)
        self.assertEqual(ack["status"], "queued")
        method, path, body = self.server.requests[-1]
        self.assertEqual((method, path), ("POST", "/v1/runs"))
        self.assertEqual(body, {"prompt": "hello", "peer": "TESTPEER", "label": "t1", "cwd": "/w", "model": "sonnet", "tools": ["Read"], "permission_mode": "plan", "partial": True})
        final = self.client.wait(ack["run_id"], 10)
        run = client_mod.unwrap_run(final)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["result_text"], "echo:hello")
        self.assertEqual(run["peer"], "TESTPEER")
        self.assertTrue(any(p == f"/v1/runs/{ack['run_id']}" and q.get("wait_ms") for m, p, q in self.server.requests if m == "GET"), "wait must long-poll with wait_ms")

    def test_followup_and_resume_use_the_contract_routes_and_same_session(self):
        first = self.client.submit("REMEMBER x")
        self.client.wait(first["run_id"], 10)
        f = self.client.followup(first["run_id"], "again", peer="P")
        self.assertEqual(self.server.requests[-1][:2], ("POST", f"/v1/runs/{first['run_id']}/followup"))
        self.assertEqual(f["session_id"], first["session_id"])
        r = self.client.resume(first["session_id"], "and again")
        self.assertEqual(self.server.requests[-1][:2], ("POST", f"/v1/sessions/{first['session_id']}/followup"))
        self.assertEqual(r["session_id"], first["session_id"])
        self.client.wait(f["run_id"], 10)
        self.client.wait(r["run_id"], 10)
        view = self.client.session(first["session_id"])
        self.assertEqual(len(view["runs"]), 3)
        self.assertTrue(view["resumable"])

    def test_events_cursor_and_follow_stop_at_terminal(self):
        ack = self.client.submit("stream me")
        self.client.wait(ack["run_id"], 10)
        page = self.client.events(ack["run_id"], after=0)
        seqs = [e["seq"] for e in page["events"]]
        self.assertEqual(seqs, [1, 2, 3])
        self.assertEqual(page["next_cursor"], 3)
        self.assertEqual(page["events"][0]["event"]["type"], "system")
        buf = io.StringIO()
        final = self.client.follow(ack["run_id"], after=0, out=buf, wait_ms=500)
        lines = [json.loads(l) for l in buf.getvalue().splitlines()]
        self.assertEqual([l["seq"] for l in lines], [1, 2, 3])
        self.assertEqual(final["run"]["status"], "completed")
        self.assertEqual(final["next_cursor"], 3)

    def test_cancel_running_then_409_on_terminal(self):
        ack = self.client.submit("SLEEP")
        deadline = time.monotonic() + 5
        while client_mod.unwrap_run(self.client.status(ack["run_id"]))["status"] != "running" and time.monotonic() < deadline:
            time.sleep(0.02)
        outcome = self.client.cancel(ack["run_id"])
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["status"], "cancelled")
        self.assertEqual(outcome["killed_pids"], [4242])
        again = self.client.cancel(ack["run_id"])
        self.assertFalse(again["ok"])
        self.assertEqual(again["http_status"], 409)
        self.assertEqual(again["status"], "cancelled")

    def test_error_status_is_terminal_for_wait(self):
        ack = self.client.submit("FAIL now")
        final = client_mod.unwrap_run(self.client.wait(ack["run_id"], 10))
        self.assertEqual(final["status"], "error")
        self.assertEqual(final["exit_code"], 1)

    def test_recover_and_journal(self):
        rec = self.client.recover()
        self.assertTrue(rec["ok"])
        self.assertIn("recovered", rec)
        self.assertIn("still_running", rec)
        ack = self.client.submit("journal me")
        self.client.wait(ack["run_id"], 10)
        page = self.client.journal(after=0, run_id=ack["run_id"])
        self.assertEqual([e["status"] for e in page["events"]], ["queued", "running", "completed"])
        self.assertTrue(all(e["run_id"] == ack["run_id"] for e in page["events"]))

    def test_unreachable_gateway_is_reported_not_raised(self):
        dead = client_mod.HeadlessClient("http://127.0.0.1:9", timeout=1)
        body = dead.health()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "unreachable")

    def test_not_found_is_reported_with_status(self):
        body = self.client.status("nope")
        self.assertFalse(body["ok"])
        self.assertEqual(body["http_status"], 404)

    def test_cli_round_trip_prints_json_and_exit_codes(self):
        buf = io.StringIO()
        code = client_mod.main(["--base", self.base, "submit", "cli prompt", "--peer", "CLI", "--wait", "10"], out=buf)
        self.assertEqual(code, 0)
        body = json.loads(buf.getvalue())
        run = client_mod.unwrap_run(body)
        self.assertEqual(run["result_text"], "echo:cli prompt")
        buf = io.StringIO()
        code = client_mod.main(["--base", self.base, "status", "missing-run"], out=buf)
        self.assertEqual(code, 1)
        buf = io.StringIO()
        self.assertEqual(client_mod.main(["--base", self.base, "health"], out=buf), 0)
        self.assertTrue(json.loads(buf.getvalue())["ok"])
        buf = io.StringIO()
        self.assertEqual(client_mod.main(["--base", self.base, "recover"], out=buf), 0)
        # followup and resume by id, with --wait, must not double-pass the positional id
        buf = io.StringIO()
        self.assertEqual(client_mod.main(["--base", self.base, "followup", run["run_id"], "next", "--peer", "CLI", "--wait", "10"], out=buf), 0)
        follow = client_mod.unwrap_run(json.loads(buf.getvalue()))
        self.assertEqual(follow["result_text"], "echo:next")
        self.assertEqual(follow["session_id"], run["session_id"])
        buf = io.StringIO()
        self.assertEqual(client_mod.main(["--base", self.base, "resume", run["session_id"], "again", "--label", "r", "--wait", "10"], out=buf), 0)
        resumed = client_mod.unwrap_run(json.loads(buf.getvalue()))
        self.assertEqual(resumed["result_text"], "echo:again")
        self.assertEqual(resumed["session_id"], run["session_id"])
        posted = [b for m, p, b in self.server.requests if m == "POST" and p == f"/v1/sessions/{run['session_id']}/followup"]
        self.assertEqual(posted[-1].get("label"), "r")
        self.assertNotIn("session_id", posted[-1], "resume route carries the id in the path only")
        buf = io.StringIO()
        self.assertEqual(client_mod.main(["--base", self.base, "submit", "explicit", "--session-id", run["session_id"], "--wait", "10"], out=buf), 0)
        self.assertEqual(client_mod.unwrap_run(json.loads(buf.getvalue()))["session_id"], run["session_id"])
        buf = io.StringIO()
        self.assertEqual(client_mod.main(["--base", self.base, "events", run["run_id"]], out=buf), 0)
        self.assertTrue(json.loads(buf.getvalue())["events"])
        buf = io.StringIO()
        self.assertEqual(client_mod.main(["--base", self.base, "session", run["session_id"]], out=buf), 0)
        self.assertGreaterEqual(len(json.loads(buf.getvalue())["runs"]), 4)
        buf = io.StringIO()
        self.assertEqual(client_mod.main(["--base", self.base, "tail", "--after", "0"], out=buf), 0)
        self.assertTrue(json.loads(buf.getvalue())["events"])


if __name__ == "__main__":
    unittest.main()
