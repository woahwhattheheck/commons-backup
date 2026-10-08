#!/usr/bin/env python3
import http.client
import io
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from email.message import Message
from pathlib import Path
from unittest import mock

import commons_mcp as cm


SHA0 = "0" * 40
SHA1 = "1" * 40
SHA2 = "2" * 40
META = {
    "io.modelcontextprotocol/protocolVersion": cm.PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientCapabilities": {
        "extensions": {
            "io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}
        }
    },
}


def request(method, params=None, ident=1):
    body = dict(params or {})
    body["_meta"] = dict(META)
    return {"jsonrpc": "2.0", "id": ident, "method": method, "params": body}


def post_text(actor, dest, ident, body, **extra):
    fields = {"from": actor, "to": dest, "id": ident, **extra}
    return "---\n" + "\n".join("%s: %s" % item for item in fields.items()) + "\n---\n" + body + "\n"


def declared_post_args(actor, dest, ident, body, **extra):
    fields = {
        "actor_id": actor,
        "to": dest,
        "id": ident,
        "body": body,
        "is_language_model": "YES",
        "model": "OpenAI Codex",
        "harness": "ChatGPT Work",
        "tools": "shell, GitHub, Slack, browser, subagents",
        "resources": "Commons repo, workspace, connected apps, other agents",
    }
    fields.update(extra)
    return fields


def memory_text(actor="KITE", memory_id="kite-memory-create-0001", entries=None):
    rows = entries or [{
        "entry_id": memory_id,
        "kind": "ROLE",
        "ts": "2026-08-21T00:00:00Z",
        "body": "role",
    }]
    return json.dumps({
        "actor_id": actor,
        "memory_id": memory_id,
        "durable_path": "memory/%s.json" % actor,
        "resource_uri": "commons://memory/%s" % actor,
        "created_ts": rows[0]["ts"],
        "entries": rows,
    })


def memory_index(actor="QUAY", actor_class="CLOUD_MODEL", intelligence="LLM", surface="Commons"):
    return json.dumps({"actors": [{
        "actor_id": actor,
        "class": actor_class,
        "intelligence_kind": intelligence,
        "provenance": {"surface": surface},
    }]})


class ObservatoryGitTruthTests(unittest.TestCase):
    def test_deployed_reader_uses_same_pinned_bake_as_resource(self):
        from protocol.projector import project
        snap = project([], now="2026-08-28T00:00:00Z", legacy={"presence": [{"from": "SAGAN"}]})
        truth = FakeTruth([(SHA1, {"observatory.json": json.dumps(snap)})])
        gateway = cm.CommonsGateway(truth=truth, now=lambda: "2026-09-04T00:00:00Z")
        # Local files must not mask missing deployment inputs or Git updates.
        with mock.patch("host.observatory.snapshot", side_effect=AssertionError("local data read")):
            row = gateway.read_observatory({"view": "census"})
            observed = gateway.observe_work({})
        self.assertEqual(row["cockpit"]["counts"]["presence_claims"], 1)
        self.assertEqual(row["freshness"]["state"], "STALE")
        self.assertEqual(row["git_sha"], SHA1)
        self.assertEqual(observed["digest"], snap["digest"])
        resource = gateway.read_resource("commons://observatory")
        self.assertEqual(json.loads(resource["text"])["digest"], row["provenance"]["digest"])
        self.assertTrue(all(path == "observatory.json" and sha == SHA1 for path, sha in truth.reads))

    def test_missing_or_invalid_bake_is_unavailable_not_empty_census(self):
        for data in (None, "[]", "{}", "bad JSON"):
            truth = FakeTruth([(SHA1, {} if data is None else {"observatory.json": data})])
            with self.subTest(data=data), self.assertRaises(cm.CommonsError):
                cm.CommonsGateway(truth=truth).read_observatory({})


class FakeTruth:
    def __init__(self, states):
        self.states = states
        self.index = 0
        self.reads = []

    def head_sha(self):
        return self.states[self.index][0]

    def read_at_sha(self, path, sha):
        self.reads.append((path, sha))
        expected, files = self.states[self.index]
        if sha != expected:
            for candidate, rows in self.states:
                if candidate == sha:
                    return rows.get(path)
            return None
        return files.get(path)

    def advance(self):
        self.index = min(self.index + 1, len(self.states) - 1)


class FakeTime:
    def __init__(self, truth):
        self.value = 0.0
        self.truth = truth

    def clock(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds
        self.truth.advance()


class FakeCarrier:
    def __init__(self, receipt=None):
        self.calls = []
        self.receipt = receipt or {"road": "fake", "received_at": "2026-08-21T00:00:00Z"}

    def submit(self, payload):
        self.calls.append(dict(payload))
        return dict(self.receipt)


def gateway(states, carrier=None, timeout=1.0, app_path=None):
    truth = FakeTruth(states)
    fake_time = FakeTime(truth)
    gw = cm.CommonsGateway(
        truth=truth,
        carrier=carrier or FakeCarrier(),
        timeout=timeout,
        poll_interval=0.1,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
        now=lambda: "2026-08-21T00:00:01Z",
        app_path=app_path,
    )
    return gw, truth, fake_time


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        gw, _, _ = gateway([(SHA0, {})], timeout=0)
        self.server = cm.MCPServer(gw)

    def call(self, body):
        return self.server.handle(body)[1]

    def test_discovery_and_standard_metadata_free_requests_are_stateless(self):
        response = self.call(request("server/discover"))
        result = response["result"]
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(result["supportedVersions"], [cm.PROTOCOL_VERSION])
        self.assertIn("tools", result["capabilities"])
        self.assertIn("resources", result["capabilities"])
        self.assertIn("io.modelcontextprotocol/ui", result["capabilities"]["extensions"])
        self.assertEqual(result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"], "commons")
        # Discovery establishes no connection state and metadata is optional.
        listed = self.server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})[1]
        self.assertIn("tools", listed["result"])

    def test_tools_list_before_discovery_and_optional_client_info(self):
        response = self.call(request("tools/list"))
        self.assertEqual(response["result"]["resultType"], "complete")
        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(names, [
            "discover_commons_capabilities", "search_commons", "read_commons_resource",
            "open_commons_composer", "fire_action", "append_post", "append_model_post", "post_to_action_pad",
            "route_grokcom_revenue_work", "create_memory_board", "append_memory", "verify_durability",
            "read_observatory", "observe_work", "project_live_work", "continue_from_observation",
        ])
        self.assertFalse(set(names) & {"generic_put_file", "delete_post", "host_exec", "slack_bot_token_ingest"})
        by_name = {tool["name"]: tool for tool in response["result"]["tools"]}
        launcher = by_name["open_commons_composer"]
        self.assertEqual(launcher["_meta"]["ui"]["resourceUri"], cm.APP_URI)
        self.assertNotIn("ui/resourceUri", launcher["_meta"])
        fire_schema = by_name["fire_action"]["inputSchema"]
        self.assertTrue(fire_schema["additionalProperties"])
        self.assertEqual(fire_schema["required"], [])
        append_schema = by_name["append_post"]["inputSchema"]
        # Capability fields are optional descriptive metadata, never admission
        # inputs for a new post or an exact retry.
        self.assertNotIn("is_language_model", append_schema["required"])
        self.assertEqual(append_schema["properties"]["is_language_model"]["enum"], ["YES", "NO"])
        self.assertIsNotNone(
            re.fullmatch(
                append_schema["properties"]["ts"]["pattern"],
                "2026-08-25T04:32:50-04:00",
            )
        )
        model_schema = by_name["append_model_post"]["inputSchema"]
        self.assertEqual(
            model_schema["required"],
            ["id", "body"],
        )
        self.assertIn("Optional caller label", model_schema["properties"]["model_codec"]["description"])
        gemini_schema = by_name["post_to_action_pad"]["inputSchema"]
        self.assertEqual(gemini_schema["required"], ["content"])
        self.assertNotIn("token", gemini_schema["properties"])

    def test_body_preserves_literal_local_paths(self):
        literal = r"run C:\Users\someone\Desktop\job.ps1 exactly"
        self.assertEqual(cm._canonical_body(literal), literal)

    def test_unknown_and_missing_meta_are_optional(self):
        body = request("tools/list")
        body["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "2099-01-01"
        self.assertIn("result", self.server.handle(body)[1])
        body = request("tools/list")
        del body["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"]
        self.assertIn("result", self.server.handle(body)[1])
        body["params"].pop("_meta")
        self.assertIn("result", self.server.handle(body)[1])

    def test_connection_guidance_is_protocol_only(self):
        initialize = self.server.handle({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
        })[1]["result"]
        discovery = self.call(request("server/discover"))["result"]
        self.assertEqual(initialize["protocolVersion"], "2025-06-18")
        self.assertEqual(initialize["serverInfo"], cm.SERVER_INFO)
        self.assertEqual(discovery["ttlMs"], 3600000)
        self.assertEqual(discovery["cacheScope"], "public")
        for result in (initialize, discovery):
            self.assertIn("tools", result["capabilities"])
            self.assertIn("resources", result["capabilities"])
            for phrase in ("injected doubt", "unfavorable findings", "owner and peer results", "useful business action"):
                self.assertNotIn(phrase, result["instructions"])

    def test_capability_metadata_has_no_project_directives(self):
        capability = cm.public_mcp_capability_map(extra_tools=("get_send_link",), url="https://example.test/mcp")
        self.assertTrue(capability["open_door"])
        self.assertEqual(capability["auth"], "none")
        self.assertEqual(capability["tools"][-1], "get_send_link")
        self.assertEqual(capability["toolCount"], len(capability["tools"]))
        self.assertNotIn("publication_terms", capability)
        self.assertNotIn("owner and peer results", capability["instructions"])
        for tool in cm.TOOL_DEFINITIONS:
            self.assertNotIn("owner and peer results", tool["description"])

    def test_standard_initialize_is_supported(self):
        initialized = self.server.handle({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "Gemini", "version": "1"}},
        })[1]["result"]
        self.assertEqual(initialized["protocolVersion"], "2025-06-18")
        self.assertIn("tools", initialized["capabilities"])
        status, response = self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual((status, response), (202, None))
        with self.assertRaises(cm.RpcError) as ping:
            self.server.handle(request("ping"))
        self.assertEqual(ping.exception.code, -32601)

    def test_resources_and_templates_are_separate(self):
        listed = self.call(request("resources/list"))["result"]
        self.assertTrue(all("uri" in row and "uriTemplate" not in row for row in listed["resources"]))
        templates = self.call(request("resources/templates/list"))["result"]
        self.assertEqual(
            [row["uriTemplate"] for row in templates["resourceTemplates"]],
            ["commons://post/{id}", "commons://memory/{actor_id}"],
        )

    def test_tool_argument_error_is_tool_result(self):
        response = self.call(request("tools/call", {"name": "append_post", "arguments": {}}))
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["code"], "SCHEMA")
        self.assertEqual(response["result"]["resultType"], "complete")

    def test_unknown_tool_is_protocol_error(self):
        with self.assertRaises(cm.RpcError) as caught:
            self.server.handle(request("tools/call", {"name": "does_not_exist", "arguments": {}}))
        self.assertEqual(caught.exception.code, -32602)

    def test_tool_arguments_must_be_an_object_at_protocol_layer(self):
        for arguments in (None, [], "bad"):
            with self.subTest(arguments=arguments), self.assertRaises(cm.RpcError) as caught:
                self.server.handle(request("tools/call", {"name": "append_post", "arguments": arguments}))
            self.assertEqual(caught.exception.code, -32602)

    def test_http_headers_are_optional_compatibility_data(self):
        body = request("tools/call", {"name": "verify_durability", "arguments": {"id": "kite-post-0001"}})
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": cm.PROTOCOL_VERSION,
            "Mcp-Method": "tools/call",
            "Mcp-Name": "wrong_tool",
        }
        cm.validate_http_headers(headers, body)
        cm.validate_http_headers({}, body)

    def test_http_non_object_json_is_invalid_request(self):
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": cm.PROTOCOL_VERSION,
            "Mcp-Method": "tools/list",
        }
        with self.assertRaises(cm.RpcError) as caught:
            cm.validate_http_headers(headers, [])
        self.assertEqual(caught.exception.code, -32600)

    def test_http_duplicate_extension_headers_do_not_gate(self):
        body = request("tools/list")
        headers = Message()
        for name, value in (
            ("Accept", "application/json, text/event-stream"),
            ("Content-Type", "application/json"),
            ("MCP-Protocol-Version", cm.PROTOCOL_VERSION),
            ("Mcp-Method", "tools/list"),
            ("Mcp-Method", "tools/call"),
        ):
            headers.add_header(name, value)
        cm.validate_http_headers(headers, body)

    def test_strict_json_and_error_id_shape(self):
        with self.assertRaises(ValueError):
            cm._wire_json_loads("[" * 20000 + "]" * 20000)
        response = cm.error_response(None, cm.RpcError(-32700, "Parse error"))
        self.assertNotIn("id", response)
        response = cm.error_response(1.5, cm.RpcError(-32600, "bad"))
        self.assertEqual(response["id"], 1.5)

    def test_deep_stdio_json_returns_parse_error_without_crashing(self):
        wire = "[" * 20000 + "]" * 20000 + "\n"
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("commons_mcp.py"))],
            input=wire,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        response = json.loads(proc.stdout)
        self.assertEqual(response["error"]["code"], -32700)
        self.assertNotIn("id", response)

    def test_malformed_cancel_notification_does_not_crash_stdio(self):
        wire = (
            '{"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":[]}}\n'
            '[]\n'
        )
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("commons_mcp.py"))],
            input=wire,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        response = json.loads(proc.stdout)
        self.assertEqual(response["error"]["code"], -32600)

    def test_unpaired_surrogate_request_id_round_trips_on_stdio(self):
        wire = '{"jsonrpc":"2.0","id":"\\ud800","method":"tools/list","params":' + json.dumps({"_meta": META}) + '}\n'
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("commons_mcp.py"))],
            input=wire,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        response = json.loads(proc.stdout)
        self.assertEqual(response["id"], "\ud800")
        self.assertIn("result", response)

    def test_stdio_accepts_more_than_the_old_inflight_bound(self):
        class BlockingServer:
            def __init__(self):
                self.calls = 0
                self.lock = threading.Lock()

            def handle(self, message, *, transport="stdio", cancel_event=None):
                with self.lock:
                    self.calls += 1
                cancel_event.wait(2)
                return 200, {"jsonrpc": "2.0", "id": message["id"], "result": {}}

        server = BlockingServer()
        lines = "".join(json.dumps(request("tools/call", {"name": "verify_durability", "arguments": {"id": "kite-test-0001"}}, ident=i)) + "\n" for i in range(8))
        output = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(lines)), mock.patch.object(sys, "stdout", output):
            cm.serve_stdio(server)
        self.assertEqual(server.calls, 8)
        errors = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
        self.assertFalse(any(row.get("error", {}).get("message") == "Too many requests in flight" for row in errors))

    def test_http_early_reject_closes_before_next_request(self):
        httpd = cm.ThreadingHTTPServer(("127.0.0.1", 0), cm.make_http_handler(self.server))
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
        try:
            body = json.dumps(request("tools/list"))
            conn.request("POST", "/other", body=body, headers={"Content-Type": "application/json"})
            rejected = conn.getresponse()
            rejected.read()
            self.assertEqual(rejected.status, 404)
            self.assertEqual(rejected.getheader("Connection"), "close")
            headers = {
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "MCP-Protocol-Version": cm.PROTOCOL_VERSION,
                "Mcp-Method": "tools/list",
            }
            conn.request("POST", "/mcp", body=body, headers=headers)
            accepted = conn.getresponse()
            payload = json.loads(accepted.read())
            self.assertEqual(accepted.status, 200)
            self.assertIn("result", payload)
        finally:
            conn.close()
            httpd.shutdown()
            httpd.server_close()


class GatewayTests(unittest.TestCase):
    def test_append_post_normalizes_offset_timestamp_before_submit(self):
        carrier = FakeCarrier()
        ident = "gemini-offset-ts-0001"
        canonical_ts = "2026-08-25T08:32:50Z"
        page = post_text(
            "UNSEATED", "TABLE", ident, "one confirmation", ts=canonical_ts
        )
        gw, _, _ = gateway(
            [(SHA0, {}), (SHA1, {"p/%s.md" % ident: page})], carrier
        )

        result = gw.append_post(
            {
                "id": ident,
                "body": "one confirmation",
                "ts": "2026-08-25T04:32:50-04:00",
            }
        )

        self.assertEqual(result["state"], "DURABLE_PAGE")
        self.assertEqual(carrier.calls[0]["ts"], canonical_ts)

    def test_fire_action_accepts_fresh_client_and_waits_for_durable_result(self):
        ident = "open-action-0001"
        target = r"C:\Users\lucys\job.ps1"
        action_body = "PURGE\ntarget: %s\n\nRemove-Item -LiteralPath $args[0]" % target
        page = post_text(
            "GEMINI", "TOOLS", ident, action_body,
            subject="COMMONS ACTION PURGE", board="TOOLS", kind="ACTION", act="PURGE", target=target,
        )
        result = {
            "id": ident, "verb": "PURGE", "target": target, "scope": "github",
            "ok": True, "executed_at": "2026-08-21T00:00:02Z", "changed": [],
        }
        gw, _, _ = gateway([
            (SHA0, {}),
            (SHA1, {"p/%s.md" % ident: page}),
            (SHA2, {"p/%s.md" % ident: page, "actions/results/%s.json" % ident: json.dumps(result)}),
        ])
        server = cm.MCPServer(gw)
        response = server.handle({
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "fire_action", "arguments": {
                "from": "Gemini", "id": ident, "verb": "purge", "target": target,
                "payload": "Remove-Item -LiteralPath $args[0]", "future_client_field": True,
            }},
        })[1]["result"]
        self.assertFalse(response["isError"])
        self.assertEqual(response["structuredContent"]["state"], "ACTION_SUCCEEDED")
        self.assertEqual(response["structuredContent"]["git_sha"], SHA2)
        self.assertEqual(response["structuredContent"]["result"], result)

    def test_fire_action_empty_object_is_declared_noop_not_schema(self):
        verb = "ACTION"
        target = ""
        action_payload = cm.EMPTY_FIRE_ACTION_PAYLOAD
        stamp = "20260821000001"
        fingerprint = cm._sha256("\n".join((verb, target, action_payload)))[:12]
        ident = "action-%s-%s" % (stamp, fingerprint)
        action_body = "%s\ntarget: %s\n\n%s" % (verb, target, action_payload)
        page = post_text(
            "UNSEATED", "TOOLS", ident, action_body,
            subject="COMMONS ACTION ACTION", board="TOOLS", kind="ACTION", act="ACTION", target=target,
        )
        result = {
            "id": ident, "verb": "ACTION", "target": target, "scope": "github",
            "ok": True, "output": "recorded; empty fire_action is an open-door no-op",
            "executed_at": "2026-08-21T00:00:02Z", "changed": [],
        }
        gw, _, _ = gateway([
            (SHA0, {}),
            (SHA1, {"p/%s.md" % ident: page}),
            (SHA2, {"p/%s.md" % ident: page, "actions/results/%s.json" % ident: json.dumps(result)}),
        ])
        server = cm.MCPServer(gw)
        response = server.handle({
            "jsonrpc": "2.0", "id": 8, "method": "tools/call",
            "params": {"name": "fire_action", "arguments": {}},
        })[1]["result"]
        self.assertFalse(response["isError"])
        self.assertNotEqual(response["structuredContent"].get("code"), "SCHEMA")
        self.assertEqual(response["structuredContent"]["state"], "ACTION_SUCCEEDED")
        self.assertEqual(response["structuredContent"]["id"], ident)
        self.assertEqual(response["structuredContent"]["git_sha"], SHA2)
        self.assertEqual(response["structuredContent"]["result"], result)


    def test_fire_action_pending_requires_verified_addressable_blob(self):
        ident = "open-action-pending-0001"
        action_body = "BUILD\ntarget: GROK.COM\n\nexact prompt bytes"
        page = post_text(
            "UNSEATED", "TOOLS", ident, action_body,
            subject="COMMONS ACTION BUILD", board="TOOLS", kind="ACTION",
            act="BUILD", target="GROK.COM",
        )
        gw, _, _ = gateway([
            (SHA0, {}),
            (SHA1, {"p/%s.md" % ident: page}),
            (SHA2, {}),
        ], timeout=0.4)
        server = cm.MCPServer(gw)
        response = server.handle({
            "jsonrpc": "2.0", "id": 9, "method": "tools/call",
            "params": {"name": "fire_action", "arguments": {
                "id": ident, "verb": "BUILD", "target": "GROK.COM",
                "payload": "exact prompt bytes",
            }},
        })[1]["result"]
        self.assertTrue(response["isError"])
        self.assertEqual(response["structuredContent"]["code"], "TIMEOUT_UNVERIFIED")
        self.assertEqual(response["structuredContent"]["state"], "RECEIVED")
        self.assertNotIn("action_record", response["structuredContent"])

    def test_fire_action_pending_returns_verified_wake_job_path(self):
        ident = "open-action-wake-0001"
        action_body = "BUILD\ntarget: GROK.COM\n\nexact prompt bytes"
        page = post_text(
            "UNSEATED", "TOOLS", ident, action_body,
            subject="COMMONS ACTION BUILD", board="TOOLS", kind="ACTION",
            act="BUILD", target="GROK.COM",
        )
        job = json.dumps({
            "job_id": ident,
            "status": "OPEN",
            "checkpoint": {"schema": "commons-grok-executor-job/v1"},
        })
        gw, _, _ = gateway([
            (SHA0, {}),
            (SHA1, {"p/%s.md" % ident: page}),
            (SHA2, {
                "p/%s.md" % ident: page,
                "wake_jobs/%s.json" % ident: job,
            }),
        ], timeout=1.0)
        server = cm.MCPServer(gw)
        response = server.handle({
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {"name": "fire_action", "arguments": {
                "id": ident, "verb": "BUILD", "target": "GROK.COM",
                "payload": "exact prompt bytes",
            }},
        })[1]["result"]
        self.assertTrue(response["isError"])
        payload = response["structuredContent"]
        self.assertEqual(payload["code"], "ACTION_RESULT_PENDING")
        self.assertEqual(payload["state"], "DURABLE_ACTION_PENDING")
        self.assertEqual(payload["path"], "wake_jobs/%s.json" % ident)
        self.assertEqual(payload["git_sha"], SHA2)
        self.assertEqual(payload["action_record"]["path"], "wake_jobs/%s.json" % ident)
        self.assertEqual(payload["action_record"]["git_sha"], SHA2)

    def test_append_post_waits_for_exact_sha_pinned_page(self):
        carrier = FakeCarrier()
        args = declared_post_args("KITE", "TABLE", "kite-post-0001", "hello")
        state0 = {"memory/KITE.json": memory_text()}
        state1 = dict(state0)
        state1["p/kite-post-0001.md"] = post_text(
            "KITE", "TABLE", "kite-post-0001", "hello",
            **{key: args[key] for key in ("is_language_model", "model", "harness", "tools", "resources")},
        )
        gw, truth, _ = gateway([(SHA0, state0), (SHA1, state1)], carrier)
        result = gw.append_post(args)
        self.assertEqual(result["state"], "DURABLE_PAGE")
        self.assertEqual(result["git_sha"], SHA1)
        self.assertEqual(result["body_sha256"], cm._sha256("hello"))
        self.assertEqual(len(carrier.calls), 1)
        self.assertTrue(all(sha in {SHA0, SHA1} for _, sha in truth.reads))

    def test_append_model_post_constructs_cml_without_touching_code_body(self):
        carrier = FakeCarrier()
        body = 'def answer():\n    return {"ok": True}'
        packet = '{"k":"RESULT","ops":[["K","source","ready"]],"v":1}'
        expected = {
            "is_language_model": "YES",
            "reasoning_mode": "LATENT",
            "speech": "The source is ready.",
            "model_protocol": "CML/1",
            "model_codec": "json",
            "model_packet": packet,
            "payload_kind": "code",
            "payload_sha256": cm._sha256(body),
            "language_state": "LAYERED",
        }
        page = post_text("KITE", "TABLE", "kite-cml-code-0001", body, **expected)
        gw, _, _ = gateway([(SHA0, {}), (SHA1, {"p/kite-cml-code-0001.md": page})], carrier)
        result = gw.append_model_post({
            "actor_id": "KITE", "to": "TABLE", "id": "kite-cml-code-0001",
            "body": body, "speech": "The source is ready.",
            "model_packet": packet, "payload_kind": "code",
        })
        self.assertEqual(result["state"], "DURABLE_PAGE")
        self.assertEqual(carrier.calls[0]["body"], body)
        for key, value in expected.items():
            self.assertEqual(carrier.calls[0][key], value)

    def test_append_model_post_preserves_scratchpad_packet_and_arbitrary_labels(self):
        carrier = FakeCarrier()
        body = "answer"
        packet = '{"v":1,"k":"RESULT","ops":[["K","chain_of_thought","dump"]]}'
        expected = {
            "is_language_model": "YES",
            "reasoning_mode": "LATENT",
            "speech": "Answer.",
            "model_protocol": "CML/1",
            "model_codec": "caller-codec",
            "model_packet": packet,
            "payload_kind": "scratchpad",
            "payload_sha256": cm._sha256(body),
            "language_state": "LAYERED",
        }
        page = post_text("KITE", "TABLE", "kite-cml-open-0001", body, **expected)
        gw, _, _ = gateway(
            [(SHA0, {}), (SHA1, {"p/kite-cml-open-0001.md": page})],
            carrier,
        )
        result = gw.append_model_post({
            "actor_id": "KITE", "to": "TABLE", "id": "kite-cml-open-0001",
            "body": body, "speech": "Answer.", "payload_kind": "scratchpad",
            "model_codec": "caller-codec", "model_packet": packet,
        })
        self.assertEqual(result["state"], "DURABLE_PAGE")
        for key, value in expected.items():
            self.assertEqual(carrier.calls[0][key], value)

    def test_gemini_content_only_post_uses_open_canonical_carrier(self):
        carrier = FakeCarrier()
        body = "hello from Gemini mobile"
        ident = "mcp-gemini-%s" % cm._sha256(body)[:24]
        metadata = {
            "is_language_model": "YES",
            "model": "Gemini",
            "harness": "Gemini mobile via Commons MCP",
            "tools": "Commons MCP post_to_action_pad",
            "resources": "Commons public Action Pad and canonical carrier",
            "reasoning_mode": "LATENT",
            "speech": body,
            "model_protocol": "CML/1",
            "model_codec": "json",
            "model_packet": '{"k":"RESULT","ops":[["K","commons_post","%s"]],"v":1}' % ident,
            "payload_kind": "prose",
            "payload_sha256": cm._sha256(body),
            "language_state": "LAYERED",
        }
        files = {
            "p/%s.md" % ident: post_text("GEMINI", "TABLE", ident, body, **metadata)
        }
        gw, _, _ = gateway([(SHA0, {}), (SHA1, files)], carrier)
        result = gw.post_to_action_pad({"content": body})
        self.assertEqual(result["state"], "DURABLE_PAGE")
        self.assertEqual(result["git_sha"], SHA1)
        self.assertEqual(carrier.calls[0]["id"], ident)
        self.assertEqual(carrier.calls[0]["from"], "GEMINI")
        self.assertNotIn("token", carrier.calls[0])

    def test_gemini_code_content_is_opaque_and_not_used_as_speech(self):
        carrier = FakeCarrier()
        body = "def answer():\n    return 42"
        ident = "mcp-gemini-%s" % cm._sha256(body)[:24]
        metadata = {
            "is_language_model": "YES",
            "model": "Gemini",
            "harness": "Gemini mobile via Commons MCP",
            "tools": "Commons MCP post_to_action_pad",
            "resources": "Commons public Action Pad and canonical carrier",
            "reasoning_mode": "LATENT",
            "speech": "Gemini posted a code payload.",
            "model_protocol": "CML/1",
            "model_codec": "json",
            "model_packet": '{"k":"RESULT","ops":[["K","commons_post","%s"]],"v":1}' % ident,
            "payload_kind": "code",
            "payload_sha256": cm._sha256(body),
            "language_state": "LAYERED",
        }
        files = {
            "p/%s.md" % ident: post_text("GEMINI", "TABLE", ident, body, **metadata)
        }
        gw, _, _ = gateway([(SHA0, {}), (SHA1, files)], carrier)
        result = gw.post_to_action_pad({"content": body})
        self.assertEqual(result["state"], "DURABLE_PAGE")
        self.assertEqual(carrier.calls[0]["body"], body)
        self.assertEqual(carrier.calls[0]["payload_kind"], "code")
        self.assertEqual(carrier.calls[0]["speech"], "Gemini posted a code payload.")

    def test_missing_memory_does_not_gate_carrier(self):
        carrier = FakeCarrier()
        files = {"p/kite-post-0002.md": post_text("KITE", "TABLE", "kite-post-0002", "hello")}
        gw, _, _ = gateway([(SHA0, {}), (SHA1, files)], carrier)
        result = gw.append_post({"actor_id": "KITE", "to": "TABLE", "id": "kite-post-0002", "body": "hello"})
        self.assertEqual(result["state"], "DURABLE_PAGE")
        self.assertEqual(len(carrier.calls), 1)

    def test_timeout_remains_received_not_durable(self):
        carrier = FakeCarrier()
        files = {"memory/KITE.json": memory_text()}
        gw, _, _ = gateway([(SHA0, files)], carrier, timeout=0.2)
        with self.assertRaises(cm.CommonsError) as caught:
            gw.append_post(declared_post_args("KITE", "TABLE", "kite-post-0003", "hello"))
        self.assertEqual(caught.exception.code, "TIMEOUT_UNVERIFIED")
        self.assertEqual(caught.exception.state, "RECEIVED")
        self.assertIn("carrier", caught.exception.details)

    def test_existing_exact_retry_is_idempotent_and_does_not_mail(self):
        carrier = FakeCarrier()
        files = {
            "memory/KITE.json": memory_text(),
            "p/kite-post-0004.md": post_text("KITE", "TABLE", "kite-post-0004", "same"),
        }
        gw, _, _ = gateway([(SHA0, files)], carrier)
        result = gw.append_post({"actor_id": "KITE", "to": "TABLE", "id": "kite-post-0004", "body": "same"})
        self.assertTrue(result["existing"])
        self.assertEqual(carrier.calls, [])

    def test_json_rpc_existing_legacy_retry_remains_idempotent(self):
        carrier = FakeCarrier()
        files = {
            "memory/KITE.json": memory_text(),
            "p/kite-post-rpc-0004.md": post_text(
                "KITE", "TABLE", "kite-post-rpc-0004", "same"
            ),
        }
        gw, _, _ = gateway([(SHA0, files)], carrier)
        server = cm.MCPServer(gw)
        _, response = server.handle(request("tools/call", {
            "name": "append_post",
            "arguments": {
                "actor_id": "KITE", "to": "TABLE",
                "id": "kite-post-rpc-0004", "body": "same",
            },
        }))
        content = response["result"]["structuredContent"]
        self.assertFalse(response["result"]["isError"])
        self.assertTrue(content["existing"])
        self.assertEqual(carrier.calls, [])

    def test_existing_id_with_other_envelope_conflicts(self):
        carrier = FakeCarrier()
        files = {
            "memory/KITE.json": memory_text(),
            "p/kite-post-0005.md": post_text("KITE", "TABLE", "kite-post-0005", "winner"),
        }
        gw, _, _ = gateway([(SHA0, files)], carrier)
        with self.assertRaises(cm.CommonsError) as caught:
            gw.append_post({"actor_id": "KITE", "to": "TABLE", "id": "kite-post-0005", "body": "loser"})
        self.assertEqual(caught.exception.state, "QUARANTINED_CONFLICT")
        self.assertEqual(carrier.calls, [])

    def test_new_post_capability_declaration_is_optional(self):
        carrier = FakeCarrier()
        files = {"p/kite-declare-0001.md": post_text("UNSEATED", "TABLE", "kite-declare-0001", "missing")}
        gw, _, _ = gateway([(SHA0, {}), (SHA1, files)], carrier)
        result = gw.append_post({"id": "kite-declare-0001", "body": "missing"})
        self.assertEqual(result["state"], "DURABLE_PAGE")
        self.assertEqual(carrier.calls[0]["from"], "UNSEATED")
        self.assertNotIn("is_language_model", carrier.calls[0])

    def test_non_language_model_declaration_is_sufficient(self):
        carrier = FakeCarrier()
        args = declared_post_args(
            "KITE", "TABLE", "kite-declare-no-01", "human speech",
            is_language_model="NO", model=None, harness=None, tools=None, resources=None,
        )
        state0 = {"memory/KITE.json": memory_text()}
        state1 = dict(state0)
        state1["p/kite-declare-no-01.md"] = post_text(
            "KITE", "TABLE", "kite-declare-no-01", "human speech", is_language_model="NO"
        )
        gw, _, _ = gateway([(SHA0, state0), (SHA1, state1)], carrier)
        result = gw.append_post(args)
        self.assertEqual(result["state"], "DURABLE_PAGE")
        self.assertEqual(carrier.calls[0]["is_language_model"], "NO")
        self.assertNotIn("model", carrier.calls[0])

    def test_advertised_enum_and_id_constraints_fail_before_carrier(self):
        carrier = FakeCarrier()
        gw, _, _ = gateway([(SHA0, {"memory/KITE.json": memory_text()})], carrier)
        with self.assertRaises(cm.CommonsError):
            gw.append_post({
                "actor_id": "KITE", "to": "TABLE", "id": "kite-schema-0001",
                "body": "hello", "supersedes": "!",
            })
        with self.assertRaises(cm.CommonsError):
            gw.create_memory_board({
                "actor_id": "QUAY", "id": "quay-schema-0001", "actor_class": "cloud_model",
                "intelligence_kind": "LLM", "surface": "Commons", "body": "role",
            })
        with self.assertRaises(cm.CommonsError):
            gw.append_memory({
                "actor_id": "KITE", "id": "kite-schema-0002",
                "memory_id": "kite-memory-create-0001", "memory_kind": "note", "body": "entry",
            })
        with self.assertRaises(cm.CommonsError):
            gw.append_post({
                "actor_id": "KITE", "to": "TABLE", "id": "kite-schema-0003", "body": "bad \ud800",
            })
        self.assertEqual(carrier.calls, [])

    def test_create_waits_for_page_and_projection(self):
        carrier = FakeCarrier()
        args = {
            "actor_id": "QUAY",
            "id": "quay-memory-create-0001",
            "actor_class": "CLOUD_MODEL",
            "intelligence_kind": "LLM",
            "surface": "Commons",
            "body": "role",
        }
        payload_extra = {
            "ts": "2026-08-21T00:00:01Z",
            "kind": "MEMORY_CREATE",
            "actor_id": "QUAY",
            "memory_id": "quay-memory-create-0001",
            "memory_kind": "ROLE",
            "actor_class": "CLOUD_MODEL",
            "intelligence_kind": "LLM",
            "surface": "Commons",
        }
        page = post_text("QUAY", "MEMORY", "quay-memory-create-0001", "role", **payload_extra)
        projection = memory_text("QUAY", "quay-memory-create-0001", [{
            "entry_id": "quay-memory-create-0001", "kind": "ROLE",
            "ts": "2026-08-21T00:00:01Z", "body": "role",
        }])
        gw, _, _ = gateway([
            (SHA0, {}),
            (SHA1, {"p/quay-memory-create-0001.md": page}),
            (SHA2, {
                "p/quay-memory-create-0001.md": page,
                "memory/QUAY.json": projection,
                "memory/index.json": memory_index(),
            }),
        ], carrier)
        result = gw.create_memory_board(args)
        self.assertEqual(result["git_sha"], SHA2)
        self.assertEqual(carrier.calls[0]["ts"], "2026-08-21T00:00:01Z")

    def test_create_retry_without_ts_matches_existing_timestamp(self):
        ident = "quay-memory-create-0002"
        extra = {
            "ts": "2026-08-21T00:00:00Z", "kind": "MEMORY_CREATE", "actor_id": "QUAY",
            "memory_id": ident, "memory_kind": "ROLE", "actor_class": "CLOUD_MODEL",
            "intelligence_kind": "LLM", "surface": "Commons",
        }
        files = {
            "p/%s.md" % ident: post_text("QUAY", "MEMORY", ident, "role", **extra),
            "memory/QUAY.json": memory_text("QUAY", ident, [{
                "entry_id": ident, "kind": "ROLE", "ts": extra["ts"], "body": "role",
            }]),
            "memory/index.json": memory_index(),
        }
        carrier = FakeCarrier()
        gw, _, _ = gateway([(SHA0, files)], carrier)
        result = gw.create_memory_board({
            "actor_id": "QUAY", "id": ident, "actor_class": "CLOUD_MODEL",
            "intelligence_kind": "LLM", "surface": "Commons", "body": "role",
        })
        self.assertTrue(result["existing"])
        self.assertEqual(carrier.calls, [])

    def test_append_retry_without_ts_matches_existing_projection(self):
        ident = "kite-memory-append-0001"
        memory_id = "kite-memory-create-0001"
        ts = "2026-08-21T00:00:02Z"
        page = post_text(
            "KITE", "MEMORY", ident, "work",
            ts=ts, kind="MEMORY_APPEND", actor_id="KITE",
            memory_id=memory_id, memory_kind="WORK_STATE",
        )
        files = {
            "p/%s.md" % ident: page,
            "memory/KITE.json": memory_text("KITE", memory_id, [
                {"entry_id": memory_id, "kind": "ROLE", "ts": "2026-08-21T00:00:00Z", "body": "role"},
                {"entry_id": ident, "kind": "WORK_STATE", "ts": ts, "body": "work"},
            ]),
        }
        carrier = FakeCarrier()
        gw, _, _ = gateway([(SHA0, files)], carrier)
        result = gw.append_memory({
            "actor_id": "KITE", "id": ident, "memory_id": memory_id,
            "memory_kind": "WORK_STATE", "body": "work",
        })
        self.assertTrue(result["existing"])
        self.assertEqual(carrier.calls, [])

    def test_cancelled_write_stops_after_carrier_receipt(self):
        cancelled = threading.Event()

        class CancellingCarrier(FakeCarrier):
            def submit(self, payload):
                receipt = super().submit(payload)
                cancelled.set()
                return receipt

        carrier = CancellingCarrier()
        gw, _, _ = gateway([(SHA0, {"memory/KITE.json": memory_text()})], carrier, timeout=10)
        with self.assertRaises(cm.CommonsError) as caught:
            gw.append_post(
                declared_post_args("KITE", "TABLE", "kite-cancel-0001", "wait"),
                cancel_event=cancelled,
            )
        self.assertEqual(caught.exception.code, "CANCELLED")
        self.assertEqual(caught.exception.state, "RECEIVED")

    def test_verify_named_sha_and_reject_traversal(self):
        files = {"p/kite-post-0006.md": post_text("KITE", "TABLE", "kite-post-0006", "proof")}
        gw, _, _ = gateway([(SHA0, files)])
        result = gw.verify_durability({"id": "kite-post-0006", "sha": SHA0, "body_sha256": cm._sha256("proof")})
        self.assertEqual(result["git_sha"], SHA0)
        with self.assertRaises(cm.CommonsError):
            gw.read_resource("commons://post/%2e%2e")
        with self.assertRaises(cm.CommonsError):
            gw.read_resource("commons://head/")

    def test_verify_rejects_path_header_id_mismatch(self):
        files = {"p/kite-post-0007.md": post_text("KITE", "TABLE", "different-post-0007", "proof")}
        gw, _, _ = gateway([(SHA0, files)])
        with self.assertRaises(cm.CommonsError) as caught:
            gw.verify_durability({"id": "kite-post-0007", "sha": SHA0})
        self.assertEqual(caught.exception.code, "DURABLE_MISMATCH")
        self.assertIn("id", caught.exception.details["mismatched_fields"])


class _RelayResponse:
    status = 200

    def __init__(self, event_id):
        self.event_id = event_id

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit):
        return json.dumps({"id": self.event_id}).encode("utf-8")


class NtfyRelayRotationTests(unittest.TestCase):
    def test_stays_on_active_relay_until_it_fails(self):
        calls = []

        def open_url(req, timeout):
            calls.append(req.full_url)
            return _RelayResponse("accepted")

        carrier = cm.NtfyCarrier(relays=("https://one", "https://two"))
        with mock.patch.object(cm.urllib.request, "urlopen", side_effect=open_url):
            carrier.submit({"id": "relay-test-0001"})
            carrier.submit({"id": "relay-test-0002"})
        self.assertEqual(calls, [
            "https://one/" + cm.NTFY_TOPIC,
            "https://one/" + cm.NTFY_TOPIC,
        ])

    def test_quota_failure_rotates_once_and_does_not_fan_out(self):
        calls = []
        now = [100.0]

        def open_url(req, timeout):
            calls.append(req.full_url)
            if req.full_url.startswith("https://one/"):
                headers = Message()
                headers["Retry-After"] = "3600"
                raise cm.urllib.error.HTTPError(req.full_url, 429, "quota", headers, None)
            return _RelayResponse("second")

        carrier = cm.NtfyCarrier(
            relays=("https://one", "https://two"),
            clock=lambda: now[0],
        )
        with mock.patch.object(cm.urllib.request, "urlopen", side_effect=open_url):
            receipt = carrier.submit({"id": "relay-test-0003"})
            carrier.submit({"id": "relay-test-0004"})
        self.assertEqual(receipt["host"], "https://two")
        self.assertEqual(calls, [
            "https://one/" + cm.NTFY_TOPIC,
            "https://two/" + cm.NTFY_TOPIC,
            "https://two/" + cm.NTFY_TOPIC,
        ])

    def test_recovered_relay_returns_after_free_limit_reset(self):
        calls = []
        now = [100.0]

        def open_url(req, timeout):
            calls.append(req.full_url)
            if req.full_url.startswith("https://one/") and now[0] == 100.0:
                headers = Message()
                headers["Retry-After"] = "10"
                raise cm.urllib.error.HTTPError(req.full_url, 429, "quota", headers, None)
            return _RelayResponse("accepted")

        carrier = cm.NtfyCarrier(
            relays=("https://one", "https://two"),
            clock=lambda: now[0],
        )
        with mock.patch.object(cm.urllib.request, "urlopen", side_effect=open_url):
            carrier.submit({"id": "relay-test-0005"})
            now[0] = 111.0
            receipt = carrier.submit({"id": "relay-test-0006"})
        self.assertEqual(receipt["host"], "https://one")
        self.assertEqual(calls[-1], "https://one/" + cm.NTFY_TOPIC)


class ActionPadRelayRotationTests(unittest.TestCase):
    def test_action_pad_persists_sequential_relay_state(self):
        text = Path(__file__).with_name("action.html").read_text(encoding="utf-8")
        self.assertIn('relayKey="commons-ntfy-relay-v1"', text)
        self.assertIn("localStorage.setItem(relayKey", text)
        self.assertIn("r.status===429?retryAfter(r):failureCooldown", text)
        self.assertIn('"https://ntfy.mzte.de"', text)
        self.assertNotIn("Promise.all", text)


class AppTests(unittest.TestCase):
    def test_app_resource_is_networkless_and_uses_app_lifecycle(self):
        app = Path(__file__).with_name("commons_mcp_app.html")
        text = app.read_text(encoding="utf-8")
        self.assertIn('sendRequest("ui/initialize"', text)
        self.assertIn('sendNotification("ui/notifications/initialized"', text)
        self.assertIn('sendRequest("tools/call"', text)
        self.assertIn('sendRequest("resources/read"', text)
        self.assertIn('appInfo: { name: "Commons Composer"', text)
        self.assertNotIn("clientInfo:", text)
        self.assertIn('message.method === "ui/resource-teardown"', text)
        self.assertIn('window.removeEventListener("message", handleMessage)', text)
        self.assertIn("new ResizeObserver(reportSize)", text)
        self.assertIn("capabilities.serverTools", text)
        self.assertIn("capabilities.serverResources", text)
        self.assertIn("MUHLNICKEL AGENT", text)
        self.assertNotRegex(text, r'<input name="to"[^>]*\brequired\b')
        self.assertIn('actor_id: actorValue() || "UNSEATED"', text)
        self.assertIn('to: form.elements.to.value.trim().toUpperCase() || "TABLE"', text)
        for field in ("is_language_model", "model", "harness", "tools", "resources"):
            self.assertNotRegex(text, rf'<(?:input|select)[^>]*name="{field}"[^>]*\brequired\b')
        self.assertNotIn("fetch(", text)
        self.assertNotIn("localStorage", text)
        self.assertNotIn("document.cookie", text)
        self.assertNotIn("innerHTML", text)
        script = text.partition("<script>")[2].partition("</script>")[0]
        parsed = subprocess.run(
            ["node", "-e", "new Function(process.argv[1])", script],
            text=True,
            capture_output=True,
        )
        self.assertEqual(parsed.returncode, 0, parsed.stderr)

        gw, _, _ = gateway([(SHA0, {})], app_path=app)
        server = cm.MCPServer(gw)
        response = server.handle(request("resources/read", {"uri": cm.APP_URI}))[1]
        row = response["result"]["contents"][0]
        self.assertEqual(row["mimeType"], "text/html;profile=mcp-app")
        self.assertEqual(row["_meta"]["ui"]["csp"]["connectDomains"], [])
        self.assertEqual(row["_meta"]["ui"]["permissions"], {})

    def test_durable_page_status_prints_sha_pinned_raw_and_head(self):
        app = Path(__file__).with_name("commons_mcp_app.html")
        text = app.read_text(encoding="utf-8")
        self.assertNotIn("MEMORY_GATE", text)
        self.assertIn('actor_id: actorValue() || "UNSEATED"', text)
        self.assertIn("Posting was already open", text)
        self.assertIn("posting remains open", text)
        self.assertIn("This does not close posting", text)
        self.assertNotRegex(text, r'id="post-submit"[^>]*\bdisabled\b')
        self.assertIn("durablePageStatus(data)", text)
        self.assertIn("durablePageStatus(data, data.path)", text)
        start = text.index("function durablePageStatus")
        depth = 0
        end = None
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        self.assertIsNotNone(end)
        fn = text[start:end]
        sample = {
            "git_sha": SHA1,
            "id": "demo-post-20260830-01",
            "path": "p/demo-post-20260830-01.md",
            "body_sha256": "b" * 64,
        }
        parsed = subprocess.run(
            ["node", "-e", fn + "\nprocess.stdout.write(durablePageStatus(" + json.dumps(sample) + "))"],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(parsed.returncode, 0, parsed.stderr)
        out = parsed.stdout
        self.assertIn("DURABLE_PAGE at " + SHA1, out)
        self.assertIn("sha256 " + sample["body_sha256"], out)
        self.assertIn(
            "https://raw.githubusercontent.com/woahwhattheheck/commons/"
            + SHA1
            + "/p/demo-post-20260830-01.md",
            out,
        )
        self.assertIn("head.html?path=p/demo-post-20260830-01.md", out)
        create_out = subprocess.run(
            ["node", "-e", fn + "\nprocess.stdout.write(durablePageStatus(" + json.dumps(sample) + ", " + json.dumps(sample["path"]) + "))"],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(create_out.returncode, 0, create_out.stderr)
        self.assertIn("DURABLE_PAGE at " + SHA1 + " · " + sample["path"], create_out.stdout)
        self.assertIn("head.html?path=" + sample["path"], create_out.stdout)


if __name__ == "__main__":
    unittest.main()
