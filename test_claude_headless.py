#!/usr/bin/env python3
"""Headless Claude gateway: start, watch, follow up, cancel, recover — against a stub CLI.

These tests never invoke the real Claude CLI and spend no model usage. A stub
``claude`` (a Python script) speaks the CLI's stream-json shape and keeps a
per-session memory file so ``--resume`` continuity is observable. The live
round trip against the real CLI is recorded in the receipt and in
integrations/claude_headless/ACCEPTANCE.md, not here.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

MODULE_PATH = Path(__file__).parent / "integrations" / "claude_headless" / "gateway.py"
SPEC = importlib.util.spec_from_file_location("claude_headless_gateway", MODULE_PATH)
gateway = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = gateway
SPEC.loader.exec_module(gateway)

CLIENT_PATH = Path(__file__).parent / "integrations" / "claude_headless" / "client.py"
CSPEC = importlib.util.spec_from_file_location("claude_headless_client", CLIENT_PATH)
client_mod = importlib.util.module_from_spec(CSPEC)
assert CSPEC.loader is not None
sys.modules[CSPEC.name] = client_mod
CSPEC.loader.exec_module(client_mod)


STUB = r'''
import json, os, sys, time, uuid
args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
if "--version" in args:
    print("0.0.0-stub (claude stub)"); sys.exit(0)
sid = opt("--session-id") or opt("--resume") or str(uuid.uuid4())
prompt = sys.stdin.read()
def emit(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
claude_env = sorted(k for k in os.environ if k == "CLAUDECODE" or k.startswith("CLAUDE_"))
emit({"type": "system", "subtype": "init", "session_id": sid, "model": opt("--model", "stub-model"),
      "cwd": os.getcwd(), "claudecode_env": "CLAUDECODE" in os.environ, "claude_env": claude_env,
      "run_env": os.environ.get("CLAUDE_HEADLESS_RUN_ID"), "resumed": "--resume" in args, "argv": args})
mem_dir = os.environ.get("STUB_MEMORY_DIR", ".")
mem = os.path.join(mem_dir, sid + ".txt")
if prompt.startswith("REMEMBER "):
    open(mem, "w").write(prompt.split(" ", 1)[1].strip()); text = "stored"
elif prompt.startswith("RECALL"):
    text = open(mem).read() if os.path.exists(mem) else "nothing"
elif prompt.startswith("SLEEP "):
    time.sleep(float(prompt.split()[1])); text = "woke"
elif prompt.startswith("FAIL"):
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": "boom"}]}, "session_id": sid})
    emit({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "boom",
          "session_id": sid, "num_turns": 1})
    sys.exit(1)
elif prompt.startswith("CRASH"):
    sys.stderr.write("stub crashed on purpose\n"); sys.exit(3)
else:
    text = "echo:" + prompt.strip()
emit({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
      "session_id": sid})
emit({"type": "result", "subtype": "success", "is_error": False, "result": text, "session_id": sid,
      "num_turns": 1, "total_cost_usd": 0.0, "duration_ms": 5, "modelUsage": {"stub-model": {}}})
'''


def http(method, url, body=None, timeout=30):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


class Fixture:
    def __init__(self, state_dir=None, max_concurrent=3, mem_dir=None, root=None, min_free_mb=0, free_mb_fn=None):
        self.tmp = None if root else tempfile.TemporaryDirectory()
        self.root = Path(root) if root else Path(self.tmp.name)
        self.state_dir = Path(state_dir) if state_dir else self.root / "state"
        self.stub = self.root / "stub_claude.py"
        self.stub.write_text(STUB, encoding="utf-8")
        self.mem = Path(mem_dir) if mem_dir else self.root / "mem"
        self.mem.mkdir(exist_ok=True)
        env = dict(os.environ)
        env["CLAUDECODE"] = "1"  # the gateway must strip these before the child starts
        env["CLAUDE_CODE_ENTRYPOINT"] = "test"
        env["CLAUDE_CODE_SESSION_ID"] = "parent-session"
        env["CLAUDE_CODE_MESSAGING_TOKEN"] = "not-for-children"
        env["CLAUDE_PID"] = "1"
        env["CLAUDE_HEADLESS_KEEP_ENV"] = "CLAUDE_CODE_KEEP_ME"
        env["CLAUDE_CODE_KEEP_ME"] = "kept"
        env["STUB_MEMORY_DIR"] = str(self.mem)
        self.server = gateway.Gateway(
            ("127.0.0.1", 0),
            state_dir=self.state_dir,
            claude_cmd=[sys.executable, str(self.stub)],
            max_concurrent=max_concurrent,
            env_base=env,
            min_free_mb=min_free_mb,
            free_mb_fn=free_mb_fn,
        )
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = client_mod.HeadlessClient(self.base)

    def close(self):
        self.server.shutdown_gateway()

    def cleanup(self):
        if self.tmp is not None:
            self.tmp.cleanup()

    def submit(self, prompt, **fields):
        status, body = http("POST", self.base + "/v1/runs", {"prompt": prompt, "cwd": str(self.root), **fields})
        assert status == 202, (status, body)
        return body

    def wait(self, run_id, seconds=15):
        status, body = http("GET", self.base + f"/v1/runs/{run_id}?wait_ms={int(seconds * 1000)}")
        assert status == 200, (status, body)
        return body["run"]

    def until(self, run_id, wanted, seconds=10):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            status, body = http("GET", self.base + f"/v1/runs/{run_id}")
            if body["run"]["status"] in wanted:
                return body["run"]
            time.sleep(0.05)
        raise AssertionError(f"run {run_id} never reached {wanted}: {body['run']['status']}")


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.close()
        self.fx.cleanup()

    def test_submit_runs_headless_and_completes_with_durable_session(self):
        ack = self.fx.submit("hello there", label="first", peer="TESTPEER")
        self.assertEqual(ack["status"], "queued")
        self.assertEqual(ack["run"]["status"], "queued")
        uuid.UUID(ack["session_id"])
        run = self.fx.wait(ack["run_id"])
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["result_text"], "echo:hello there")
        self.assertEqual(run["reply"], "echo:hello there")
        self.assertEqual(run["kind"], "new")
        self.assertEqual(run["submitted_by"], "TESTPEER")
        self.assertEqual(run["exit_code"], 0)
        self.assertEqual(run["num_turns"], 1)
        self.assertEqual(run["child_model"], "stub-model")
        self.assertIn("--session-id", run["command"])
        self.assertIn(ack["session_id"], run["command"])
        self.assertNotIn("hello there", " ".join(run["command"]), "prompt travels over stdin, not argv")
        status, page = http("GET", self.fx.base + f"/v1/runs/{ack['run_id']}/events")
        kinds = [e["kind"] for e in page["events"]]
        statuses = [e["status"] for e in page["events"] if e["kind"] == "gateway"]
        self.assertEqual(statuses, ["queued", "starting", "running", "completed"])
        self.assertEqual(kinds[:4], ["gateway", "gateway", "gateway", "system"])
        self.assertIn("assistant", kinds)
        self.assertIn("result", kinds)
        for e in page["events"]:
            self.assertEqual(e["seq"], e["event_id"])
            self.assertEqual(e["event"], e["payload"])
        init = next(e for e in page["events"] if e["kind"] == "system")["payload"]
        self.assertFalse(init["claudecode_env"], "CLAUDECODE must not reach the child")
        self.assertNotIn("CLAUDE_CODE_SESSION_ID", init["claude_env"])
        self.assertNotIn("CLAUDE_CODE_MESSAGING_TOKEN", init["claude_env"])
        self.assertNotIn("CLAUDE_PID", init["claude_env"])
        self.assertIn("CLAUDE_CODE_KEEP_ME", init["claude_env"], "keep list must be honoured")
        self.assertIn("CLAUDE_HEADLESS_RUN_ID", init["claude_env"])
        self.assertEqual(init["run_env"], ack["run_id"])
        self.assertEqual(init["session_id"], ack["session_id"])
        files = self.fx.state_dir / "runs" / ack["run_id"]
        self.assertTrue((files / "events.jsonl").is_file())
        self.assertTrue((files / "prompt.txt").is_file())
        self.assertEqual((files / "prompt.txt").read_text(encoding="utf-8"), "hello there")
        self.assertEqual(run["events_file"], str(files / "events.jsonl"))

    def test_followup_resumes_the_exact_same_conversation(self):
        first = self.fx.submit("REMEMBER pearl")
        self.assertEqual(self.fx.wait(first["run_id"])["result_text"], "stored")
        status, ack = http("POST", self.fx.base + f"/v1/runs/{first['run_id']}/followup", {"prompt": "RECALL"})
        self.assertEqual(status, 202, ack)
        self.assertEqual(ack["session_id"], first["session_id"])
        run = self.fx.wait(ack["run_id"])
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["result_text"], "pearl")
        self.assertEqual(run["kind"], "followup")
        self.assertEqual(run["parent_run_id"], first["run_id"])
        self.assertIn("--resume", run["command"])
        self.assertNotIn("--session-id", run["command"])
        # a coordinator holding only the session id can also continue it, on either route
        for route in ("runs", "followup"):
            status, ack2 = http("POST", self.fx.base + f"/v1/sessions/{first['session_id']}/{route}", {"prompt": "RECALL"})
            self.assertEqual(status, 202, ack2)
            self.assertEqual(self.fx.wait(ack2["run_id"])["result_text"], "pearl")
        status, view = http("GET", self.fx.base + f"/v1/sessions/{first['session_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(view["run_count"], 4)
        self.assertEqual([r["kind"] for r in view["runs"]], ["new", "followup", "followup", "followup"])
        self.assertTrue(view["resumable"])
        self.assertIn("transcript_path", view)

    def test_session_followup_without_cwd_inherits_the_conversation_cwd(self):
        work = self.fx.root / "work"
        work.mkdir()
        first = self.fx.submit("REMEMBER here", cwd=str(work))
        self.fx.wait(first["run_id"])
        status, ack = http("POST", self.fx.base + f"/v1/sessions/{first['session_id']}/followup", {"prompt": "RECALL"})
        run = self.fx.wait(ack["run_id"])
        self.assertEqual(run["cwd"], str(work))
        self.assertEqual(run["result_text"], "here")
        init = next(e for e in http("GET", self.fx.base + f"/v1/runs/{ack['run_id']}/events")[1]["events"] if e["kind"] == "system")
        self.assertEqual(Path(init["payload"]["cwd"]).resolve(), work.resolve())
        elsewhere = self.fx.root / "elsewhere"
        elsewhere.mkdir()
        status, ack2 = http("POST", self.fx.base + f"/v1/sessions/{first['session_id']}/followup", {"prompt": "RECALL", "cwd": str(elsewhere)})
        self.assertEqual(self.fx.wait(ack2["run_id"])["cwd"], str(elsewhere))

    def test_cancel_stops_that_run_only_and_session_stays_resumable(self):
        first = self.fx.submit("REMEMBER anchor")
        self.fx.wait(first["run_id"])
        status, sleeper = http("POST", self.fx.base + f"/v1/runs/{first['run_id']}/followup", {"prompt": "SLEEP 30"})
        running = self.fx.until(sleeper["run_id"], {"running"})
        pid = running["pid"]
        self.assertTrue(gateway.pid_alive(pid))
        started = time.monotonic()
        status, outcome = http("POST", self.fx.base + f"/v1/runs/{sleeper['run_id']}/cancel", {})
        self.assertEqual(status, 200, outcome)
        self.assertEqual(outcome["status"], "cancelled")
        self.assertIsInstance(outcome["killed_pids"], list)
        if os.name == "nt":
            self.assertIn(pid, outcome["killed_pids"])
        self.assertLess(time.monotonic() - started, 10)
        run = self.fx.wait(sleeper["run_id"], 5)
        self.assertEqual(run["status"], "cancelled")
        self.assertTrue(run["cancel_requested"])
        deadline = time.monotonic() + 5
        while gateway.pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(gateway.pid_alive(pid), "the cancelled run's process must be gone")
        status, ack = http("POST", self.fx.base + f"/v1/runs/{first['run_id']}/followup", {"prompt": "RECALL"})
        self.assertEqual(self.fx.wait(ack["run_id"])["result_text"], "anchor")
        status, again = http("POST", self.fx.base + f"/v1/runs/{sleeper['run_id']}/cancel", {})
        self.assertEqual(status, 409)
        self.assertEqual(again["error"], "already_terminal")
        self.assertEqual(again["status"], "cancelled")

    def test_cancel_before_start_never_spawns(self):
        blocker = self.fx.submit("SLEEP 3")
        self.fx.until(blocker["run_id"], {"running"})
        status, queued = http("POST", self.fx.base + f"/v1/runs/{blocker['run_id']}/followup", {"prompt": "never"})
        self.assertEqual(self.fx.until(queued["run_id"], {"queued"})["status"], "queued")
        status, outcome = http("POST", self.fx.base + f"/v1/runs/{queued['run_id']}/cancel", {})
        self.assertEqual(outcome["status"], "cancelled")
        run = self.fx.wait(queued["run_id"], 2)
        self.assertIsNone(run["pid"])
        self.assertEqual(run["error"], "cancelled before start")
        http("POST", self.fx.base + f"/v1/runs/{blocker['run_id']}/cancel", {})

    def test_error_result_and_crash_are_reported_not_hidden(self):
        failed = self.fx.wait(self.fx.submit("FAIL")["run_id"])
        self.assertEqual(failed["status"], "error")
        self.assertEqual(failed["result_text"], "boom")
        self.assertIn("is_error=True", failed["error"])
        crashed = self.fx.wait(self.fx.submit("CRASH")["run_id"])
        self.assertEqual(crashed["status"], "error")
        self.assertEqual(crashed["exit_code"], 3)
        self.assertIn("without a result event", crashed["error"])
        self.assertIn("stub crashed on purpose", crashed["stderr_tail"])

    def test_same_session_is_fifo_and_other_sessions_run_concurrently(self):
        a1 = self.fx.submit("SLEEP 2")
        self.fx.until(a1["run_id"], {"running"})
        status, a2 = http("POST", self.fx.base + f"/v1/runs/{a1['run_id']}/followup", {"prompt": "second"})
        time.sleep(0.3)
        self.assertEqual(self.fx.until(a2["run_id"], {"queued"})["status"], "queued")
        b1 = self.fx.submit("other session")
        b_done = self.fx.wait(b1["run_id"], 5)
        self.assertEqual(b_done["status"], "completed")
        self.assertIn(self.fx.until(a1["run_id"], {"running", "completed"})["status"], {"running", "completed"})
        self.assertEqual(self.fx.wait(a2["run_id"], 10)["result_text"], "echo:second")
        self.assertEqual(self.fx.wait(a1["run_id"], 1)["result_text"], "woke")

    def test_events_cursor_long_polls_and_never_repeats(self):
        status, before = http("GET", self.fx.base + "/v1/events?after=0")
        cursor = before["next_cursor"]
        box = {}

        def poll():
            box["page"] = http("GET", self.fx.base + f"/v1/events?after={cursor}&wait_ms=8000")[1]

        thread = threading.Thread(target=poll)
        thread.start()
        time.sleep(0.2)
        ack = self.fx.submit("ping")
        thread.join(timeout=10)
        page = box["page"]
        self.assertTrue(page["events"], "long poll must wake on the new event")
        self.assertTrue(all(e["event_id"] > cursor for e in page["events"]))
        self.assertEqual(page["events"][0]["run_id"], ack["run_id"])
        self.fx.wait(ack["run_id"])
        status, rest = http("GET", self.fx.base + f"/v1/events?after={page['next_cursor']}")
        ids = [e["event_id"] for e in rest["events"]]
        self.assertEqual(ids, sorted(set(ids)))
        self.assertTrue(all(i > page["next_cursor"] for i in ids))

    def test_message_alias_matches_gemini_gateway_shape(self):
        status, body = http("POST", self.fx.base + "/v1/message", {"peer": "CLAUDE", "message": "shape", "wait_ms": 10000})
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        self.assertEqual(body["reply"], "echo:shape")
        self.assertEqual(body["reply_utf8_base64"], "ZWNobzpzaGFwZQ==")
        self.assertEqual(body["request_id"], body["run_id"])
        status, req = http("GET", self.fx.base + f"/v1/requests/{body['run_id']}")
        self.assertEqual(req["event"]["status"], "completed")
        status, asyn = http("POST", self.fx.base + "/v1/message", {"peer": "ANY", "message": "later", "async": True})
        self.assertEqual(status, 202)
        self.assertEqual(asyn["status"], "queued")
        self.fx.wait(asyn["run_id"])

    def test_health_reports_cli_counts_and_scrub(self):
        status, health = http("GET", self.fx.base + "/health")
        self.assertTrue(health["ok"])
        self.assertEqual(health["service"], gateway.SERVICE)
        self.assertTrue(health["cli"]["ok"])
        self.assertIn("stub", health["cli"]["version"])
        self.assertEqual(health["claude_version"], health["cli"]["version"])
        self.assertIn("CLAUDECODE", health["env_scrub"])
        self.assertIn("CLAUDE_CODE_SESSION_ID", health["env_scrub"])
        self.assertNotIn("CLAUDE_CODE_KEEP_ME", health["env_scrub"])
        self.assertIn("POST /v1/runs", health["endpoints"])
        self.assertIn("POST /v1/recover", health["endpoints"])
        self.assertEqual(health["runs_dir"], str(self.fx.state_dir / "runs"))
        self.fx.wait(self.fx.submit("x")["run_id"])
        status, health = http("GET", self.fx.base + "/health")
        self.assertEqual(health["counts"].get("completed"), 1)
        self.assertGreater(health["event_cursor"], 0)

    def test_tools_alias_and_partial_flag_reach_the_command(self):
        ack = self.fx.submit("opts", tools=["Read", "Bash(git *)"], partial=True, model="m1")
        run = self.fx.wait(ack["run_id"])
        cmd = run["command"]
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1:cmd.index("--allowedTools") + 3], ["Read", "Bash(git *)"])
        self.assertIn("--include-partial-messages", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "m1")

    def test_bad_requests_are_explained(self):
        status, body = http("POST", self.fx.base + "/v1/runs", {"prompt": "   "})
        self.assertEqual(status, 400)
        self.assertIn("nonempty", body["message"])
        status, body = http("POST", self.fx.base + "/v1/runs", {"prompt": "x", "session_id": "not-a-uuid"})
        self.assertEqual(status, 400)
        status, body = http("POST", self.fx.base + "/v1/runs/nope/followup", {"prompt": "x"})
        self.assertEqual(status, 400)
        status, body = http("GET", self.fx.base + "/v1/runs/nope")
        self.assertEqual(status, 404)
        status, body = http("POST", self.fx.base + "/v1/runs", {"prompt": "x", "cwd": str(self.fx.root / "missing")})
        self.assertEqual(status, 400)

    def test_any_loopback_caller_is_served_without_identity_fields(self):
        status, body = http("POST", self.fx.base + "/v1/runs", {"prompt": "no identity fields at all"})
        self.assertEqual(status, 202, body)
        run = self.fx.wait(body["run_id"])
        self.assertEqual(run["status"], "completed")
        self.assertIsNone(run["submitted_by"])

    def test_recover_endpoint_is_idempotent_while_serving(self):
        ack = self.fx.submit("SLEEP 1")
        self.fx.until(ack["run_id"], {"running"})
        status, body = http("POST", self.fx.base + "/v1/recover", {})
        self.assertEqual(status, 200)
        self.assertEqual(body["recovered"], [])
        self.assertIn(ack["run_id"], body["still_running"])
        self.assertEqual(self.fx.wait(ack["run_id"])["status"], "completed")

    def test_client_module_round_trip_against_the_real_gateway(self):
        c = self.fx.client
        ack = c.submit("via client", cwd=str(self.fx.root), peer="CLIENT")
        view = c.wait(ack["run_id"], 15)
        self.assertEqual(client_mod.unwrap_run(view)["result_text"], "echo:via client")
        follow = c.followup(ack["run_id"], "again")
        self.assertEqual(client_mod.unwrap_run(c.wait(follow["run_id"], 15))["result_text"], "echo:again")
        res = c.resume(ack["session_id"], "third")
        self.assertEqual(client_mod.unwrap_run(c.wait(res["run_id"], 15))["result_text"], "echo:third")
        events = c.events(ack["run_id"])
        self.assertTrue(events["events"])
        self.assertTrue(all("seq" in e and "event" in e for e in events["events"]))
        self.assertEqual(c.session(ack["session_id"])["run_count"], 3)
        self.assertTrue(c.health()["ok"])
        self.assertTrue(c.recover()["ok"])
        sleeper = c.followup(ack["run_id"], "SLEEP 30")
        self.fx.until(sleeper["run_id"], {"running"})
        self.assertEqual(c.cancel(sleeper["run_id"])["status"], "cancelled")
        again = c.cancel(sleeper["run_id"])
        self.assertEqual(again["http_status"], 409)


class MemoryGuardTests(unittest.TestCase):
    def test_queued_runs_hold_under_the_floor_and_release_above_it(self):
        free = {"mb": 200}
        fx = Fixture(min_free_mb=1024, free_mb_fn=lambda: free["mb"])
        try:
            ack = fx.submit("held until ram returns")
            time.sleep(1.6)  # two dispatcher ticks
            run = http("GET", fx.base + f"/v1/runs/{ack['run_id']}")[1]["run"]
            self.assertEqual(run["status"], "queued")
            self.assertIsNone(run["pid"])
            events = http("GET", fx.base + f"/v1/runs/{ack['run_id']}/events")[1]["events"]
            held = [e for e in events if e["kind"] == "gateway" and e["status"] == "held"]
            self.assertEqual(len(held), 1, "held is journaled once per run, not once per tick")
            self.assertEqual(held[0]["payload"]["free_mb"], 200)
            self.assertEqual(held[0]["payload"]["min_free_mb"], 1024)
            health = http("GET", fx.base + "/health")[1]
            self.assertEqual(health["memory_guard"], {"free_mb": 200, "min_free_mb": 1024, "holding": [ack["run_id"]]})
            free["mb"] = 4096
            final = fx.wait(ack["run_id"], 15)
            self.assertEqual(final["status"], "completed")
            self.assertEqual(final["result_text"], "echo:held until ram returns")
            statuses = [e["status"] for e in http("GET", fx.base + f"/v1/runs/{ack['run_id']}/events")[1]["events"] if e["kind"] == "gateway"]
            self.assertEqual(statuses, ["queued", "held", "released", "starting", "running", "completed"])
            self.assertEqual(http("GET", fx.base + "/health")[1]["memory_guard"]["holding"], [])
        finally:
            fx.close()
            fx.cleanup()

    def test_floor_of_zero_disables_the_guard_and_unknown_memory_never_holds(self):
        fx = Fixture(min_free_mb=0, free_mb_fn=lambda: 1)
        try:
            self.assertEqual(fx.wait(fx.submit("no floor")["run_id"])["status"], "completed")
        finally:
            fx.close()
            fx.cleanup()
        fx = Fixture(min_free_mb=1024, free_mb_fn=lambda: None)
        try:
            self.assertEqual(fx.wait(fx.submit("unknown ram")["run_id"])["status"], "completed")
            self.assertEqual(http("GET", fx.base + "/health")[1]["memory_guard"]["free_mb"], None)
        finally:
            fx.close()
            fx.cleanup()

    def test_default_floor_and_concurrency_are_laptop_sized(self):
        self.assertEqual(gateway.DEFAULT_MAX_CONCURRENT, 1)
        self.assertEqual(gateway.DEFAULT_MIN_FREE_MB, 1024)
        value = gateway.free_physical_mb()
        self.assertTrue(value is None or (isinstance(value, int) and value >= 0))


class RecoveryTests(unittest.TestCase):
    def test_restart_finalizes_from_disk_marks_dead_interrupted_and_dispatches_queued(self):
        first = Fixture()
        state_dir = first.state_dir
        root = first.root
        done = first.wait(first.submit("REMEMBER before-restart")["run_id"])
        session_id = done["session_id"]
        store = first.server.store
        # (a) a run whose child died with no result on disk
        dead = {
            "run_id": uuid.uuid4().hex, "session_id": str(uuid.uuid4()), "parent_run_id": None, "kind": "new",
            "label": None, "submitted_by": None, "cwd": str(root), "prompt": "orphan", "prompt_sha256": "x",
            "prompt_bytes": 6, "options": {}, "status": "running", "created_at": gateway.utc_now(), "pid": 2_000_000_000,
        }
        store.insert_run(dead)
        # (b) a run whose child finished after the gateway died: result is on disk, pid gone
        finished = {**dead, "run_id": uuid.uuid4().hex, "session_id": str(uuid.uuid4()), "prompt": "finished alone"}
        store.insert_run(finished)
        fdir = state_dir / "runs" / finished["run_id"]
        fdir.mkdir(parents=True)
        lines = [
            {"type": "system", "subtype": "init", "session_id": finished["session_id"]},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "done alone"}]}},
            {"type": "result", "subtype": "success", "is_error": False, "result": "done alone", "num_turns": 1},
        ]
        (fdir / "events.jsonl").write_text("".join(json.dumps(l) + "\n" for l in lines), encoding="utf-8")
        # (c) a run queued but never started, prompt retained on disk
        queued = {**dead, "run_id": uuid.uuid4().hex, "session_id": str(uuid.uuid4()), "prompt": "late start", "status": "queued", "pid": None}
        store.insert_run(queued)
        qdir = state_dir / "runs" / queued["run_id"]
        qdir.mkdir(parents=True)
        (qdir / "prompt.txt").write_text("late start", encoding="utf-8")
        first.close()
        second = Fixture(state_dir=state_dir, mem_dir=first.mem, root=root)
        try:
            rec = second.server.recovery
            self.assertIn(dead["run_id"], rec["interrupted"])
            self.assertIn(finished["run_id"], rec["finalized_from_disk"])
            self.assertIn(queued["run_id"], rec["requeued"])
            interrupted = http("GET", second.base + f"/v1/runs/{dead['run_id']}")[1]["run"]
            self.assertEqual(interrupted["status"], "interrupted")
            self.assertIn("follow up to continue", interrupted["error"])
            self.assertFalse(interrupted["pid_alive"])
            fin = http("GET", second.base + f"/v1/runs/{finished['run_id']}")[1]["run"]
            self.assertEqual(fin["status"], "completed")
            self.assertEqual(fin["result_text"], "done alone")
            self.assertIsNone(fin["exit_code"])
            self.assertIn("finalized from events.jsonl", fin["note"])
            kinds = [e["kind"] for e in http("GET", second.base + f"/v1/runs/{finished['run_id']}/events")[1]["events"]]
            self.assertEqual(kinds.count("result"), 1)
            late = second.wait(queued["run_id"], 15)
            self.assertEqual(late["status"], "completed")
            self.assertEqual(late["result_text"], "echo:late start")
            status, ack = http("POST", second.base + f"/v1/sessions/{session_id}/followup", {"prompt": "RECALL"})
            self.assertEqual(status, 202, ack)
            self.assertEqual(second.wait(ack["run_id"])["result_text"], "before-restart")
            status, health = http("GET", second.base + "/health")
            self.assertEqual(health["counts"]["interrupted"], 1)
            self.assertEqual(health["recovery"]["finalized_from_disk"], [finished["run_id"]])
        finally:
            second.close()
            first.cleanup()

    def test_run_in_flight_outlives_the_gateway_and_is_adopted_on_restart(self):
        first = Fixture()
        state_dir, root = first.state_dir, first.root
        ack = first.submit("SLEEP 2")
        running = first.until(ack["run_id"], {"running"})
        pid = running["pid"]
        first.close()  # gateway gone, child still sleeping
        self.assertTrue(gateway.pid_alive(pid))
        second = Fixture(state_dir=state_dir, mem_dir=first.mem, root=root)
        try:
            self.assertIn(ack["run_id"], second.server.recovery["still_alive"])
            view = http("GET", second.base + f"/v1/runs/{ack['run_id']}")[1]["run"]
            self.assertIn(view["status"], {"running", "completed"})
            self.assertTrue(view["adopted"] or view["status"] == "completed")
            final = second.wait(ack["run_id"], 15)
            self.assertEqual(final["status"], "completed")
            self.assertEqual(final["result_text"], "woke")
            self.assertIsNone(final["exit_code"], "an adopted child has no exit code; the honest value is null")
            self.assertIn("adopted", final["note"])
            events = http("GET", second.base + f"/v1/runs/{ack['run_id']}/events")[1]["events"]
            statuses = [e["status"] for e in events if e["kind"] == "gateway"]
            self.assertEqual(statuses, ["queued", "starting", "running", "adopted", "completed"])
            self.assertEqual([e["kind"] for e in events].count("result"), 1)
            # the session is still FIFO-continuable after adoption
            status, more = http("POST", second.base + f"/v1/sessions/{ack['session_id']}/followup", {"prompt": "after adopt"})
            self.assertEqual(second.wait(more["run_id"])["result_text"], "echo:after adopt")
        finally:
            second.close()
            first.cleanup()

    def test_adopted_run_can_be_cancelled(self):
        first = Fixture()
        state_dir, root = first.state_dir, first.root
        ack = first.submit("SLEEP 30")
        pid = first.until(ack["run_id"], {"running"})["pid"]
        first.close()
        second = Fixture(state_dir=state_dir, mem_dir=first.mem, root=root)
        try:
            self.assertIn(ack["run_id"], second.server.recovery["still_alive"])
            status, outcome = http("POST", second.base + f"/v1/runs/{ack['run_id']}/cancel", {})
            self.assertEqual(status, 200, outcome)
            self.assertEqual(outcome["status"], "cancelled")
            deadline = time.monotonic() + 5
            while gateway.pid_alive(pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertFalse(gateway.pid_alive(pid))
            self.assertEqual(second.wait(ack["run_id"], 5)["status"], "cancelled")
        finally:
            second.close()
            first.cleanup()


class PureFunctionTests(unittest.TestCase):
    def test_transcript_path_matches_claude_code_folder_naming(self):
        cwd = r"C:\Users\lucys\AppData\Local\Temp\claude\C--\c1d88905-bcd5-4af0-9ec8-00b8c9e56ac3\scratchpad\c1probe"
        path = gateway.transcript_path(cwd, "836f29ca-035f-4b5c-85ac-590a43db541d", home=Path("/h"))
        self.assertEqual(path.name, "836f29ca-035f-4b5c-85ac-590a43db541d.jsonl")
        self.assertEqual(
            path.parent.name,
            "C--Users-lucys-AppData-Local-Temp-claude-C---c1d88905-bcd5-4af0-9ec8-00b8c9e56ac3-scratchpad-c1probe",
        )

    def test_env_scrub_removes_session_markers_and_honours_keep_list(self):
        base = {
            "CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "x", "CLAUDE_CODE_SESSION_ID": "s", "CLAUDE_CODE_MESSAGING_TOKEN": "t",
            "CLAUDE_PID": "9", "CLAUDE_EFFORT": "max", "ANTHROPIC_BASE_URL": "https://api.anthropic.com", "PATH": "p",
            "CLAUDE_HEADLESS_KEEP_ENV": "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_BEDROCK": "1",
        }
        env = gateway.headless_env(base, "run1")
        for gone in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_PID", "CLAUDE_EFFORT"):
            self.assertNotIn(gone, env)
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://api.anthropic.com", "not scrubbed, per TENON's correction")
        self.assertEqual(env["CLAUDE_CODE_USE_BEDROCK"], "1")
        self.assertEqual(env["CLAUDE_HEADLESS_RUN_ID"], "run1")
        self.assertEqual(env["PATH"], "p")
        self.assertEqual(gateway.scrub_names(base, {"CLAUDE_CODE_USE_BEDROCK"}), sorted(["CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_PID", "CLAUDE_EFFORT"]))

    def test_popen_kwargs_are_headless_and_file_backed(self):
        kwargs = gateway.build_popen_kwargs(".", {"PATH": "p"}, "IN", "OUT", "ERR")
        self.assertEqual((kwargs["stdin"], kwargs["stdout"], kwargs["stderr"]), ("IN", "OUT", "ERR"))
        if os.name == "nt":
            self.assertTrue(kwargs["creationflags"] & 0x08000000, "CREATE_NO_WINDOW")
            self.assertTrue(kwargs["creationflags"] & 0x00000200, "CREATE_NEW_PROCESS_GROUP")
        else:
            self.assertTrue(kwargs["start_new_session"])

    def test_allow_reuse_address_is_off_on_windows(self):
        self.assertEqual(gateway.Gateway.allow_reuse_address, os.name != "nt")

    @unittest.skipIf(os.name == "nt", "zombies are a POSIX state; Windows reports the exit code directly")
    def test_pid_alive_treats_an_unreaped_zombie_as_dead(self):
        import subprocess

        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        try:
            deadline = time.monotonic() + 10
            state = ""
            while time.monotonic() < deadline:
                try:
                    with open(f"/proc/{proc.pid}/stat", encoding="ascii", errors="replace") as fh:
                        state = fh.read().rsplit(")", 1)[1].split()[0]
                except OSError:
                    state = "?"
                if state in ("Z", "X", "?"):
                    break
                time.sleep(0.02)
            # the child has exited but nobody has called wait(): a zombie, not a live run
            self.assertFalse(gateway.pid_alive(proc.pid), f"/proc state {state!r} must read as dead")
        finally:
            proc.wait(timeout=10)
        self.assertFalse(gateway.pid_alive(proc.pid))

    def test_taskkill_parser_takes_only_terminated_pids(self):
        text = ("SUCCESS: The process with PID 3520 (child process of PID 20496) has been terminated.\n"
                "SUCCESS: The process with PID 20496 (child process of PID 6700) has been terminated.\n")
        self.assertEqual([int(m) for m in gateway.TASKKILL_PID.findall(text)], [3520, 20496])

    def test_build_command_passes_only_requested_options(self):
        run = {"kind": "new", "session_id": "s", "options": {"model": "sonnet", "max_turns": 3, "strict_mcp_config": True,
                                                            "allowed_tools": ["Read", "Bash(git *)"], "fork_session": False, "partial": True}}
        cmd = gateway.build_command(["claude"], run)
        self.assertEqual(cmd[:6], ["claude", "-p", "--output-format", "stream-json", "--verbose", "--session-id"])
        self.assertIn("--model", cmd)
        self.assertEqual(cmd[cmd.index("--max-turns") + 1], "3")
        self.assertIn("--strict-mcp-config", cmd)
        self.assertIn("--include-partial-messages", cmd)
        self.assertNotIn("--fork-session", cmd)
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1:cmd.index("--allowedTools") + 3], ["Read", "Bash(git *)"])
        follow = gateway.build_command(["claude"], {"kind": "followup", "session_id": "s", "options": {}})
        self.assertIn("--resume", follow)
        self.assertNotIn("--session-id", follow)

    def test_parse_events_file_returns_result_and_skips_garbage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "events.jsonl"
            p.write_bytes(b'{"type":"system"}\nnot json\n{"type":"result","result":"ok"}\n{"type":"trunc')
            events, result = gateway.parse_events_file(p)
            self.assertEqual([e["type"] for e in events], ["system", "result"])
            self.assertEqual(result["result"], "ok")
            self.assertEqual(gateway.parse_events_file(Path(tmp) / "missing.jsonl"), ([], None))


if __name__ == "__main__":
    unittest.main()
