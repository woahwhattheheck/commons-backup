"""MCP stdio plus loopback HTTP for the independent Commons server."""
from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import SERVER_NAME, SERVER_VERSION
from .envelope import EnvelopeError, redact
from .gateway import Gateway, GatewayError
from .jobs import JobError, JobStore, public_job


PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2026-07-28")
APP_HTML = Path(__file__).with_name("console.html")
HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"


def _load_tool_manifest() -> list[dict[str, Any]]:
    path = FIXTURES / "tools.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data["tools"])


TOOLS = None


def tools() -> list[dict[str, Any]]:
    global TOOLS
    if TOOLS is None:
        TOOLS = _load_tool_manifest()
    return TOOLS


def tool_result(data: dict[str, Any], *, error: bool = False) -> dict[str, Any]:
    text = json.dumps(redact(data), ensure_ascii=False, sort_keys=True)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": redact(data),
        "isError": bool(error),
    }


class MCPServer:
    def __init__(self, gateway: Gateway | None = None, jobs: JobStore | None = None):
        self.gateway = gateway or Gateway()
        self.jobs = jobs or JobStore()
        self.tool_index = {row["name"]: row for row in tools()}

    def _page_exists(self, ident: str) -> bool:
        sha = self.gateway.truth.head_sha()
        status, text = self.gateway.truth.read_at_sha("p/%s.md" % ident, sha)
        return status == 200 and text is not None

    def _get_job(self, arguments: dict[str, Any]) -> dict[str, Any]:
        job = self.jobs.get(str(arguments.get("job_id") or ""))
        return redact({"ok": True, "state": job.get("status"), "job": public_job(job)})

    def _tick_job(self, arguments: dict[str, Any]) -> dict[str, Any]:
        worker = str(arguments.get("worker_id") or "watchdog")
        ident = arguments.get("job_id")
        if ident:
            return self.jobs.tick(str(ident), worker_id=worker, page_exists=self._page_exists)
        return self.jobs.tick_all(worker_id=worker, page_exists=self._page_exists)

    def _complete_job(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.jobs.complete(
            str(arguments.get("job_id") or ""),
            result=arguments.get("result") if isinstance(arguments.get("result"), dict) else {},
            result_address=str(arguments.get("result_address") or ""),
            page_exists=self._page_exists,
            worker_id=str(arguments.get("worker_id") or "watchdog"),
        )

    def call_tool(self, name: str, arguments: Any) -> dict[str, Any]:
        if name not in self.tool_index:
            raise EnvelopeError("SCHEMA", "unknown tool %s" % name)
        if not isinstance(arguments, dict):
            raise EnvelopeError("SCHEMA", "tool arguments must be an object")
        handlers = {
            "post_to_commons": lambda: self.gateway.post(arguments),
            "post_model_to_commons": lambda: self.gateway.post_model(arguments),
            "reply_to_post": lambda: self.gateway.reply(arguments),
            "verify_receipt": lambda: self.gateway.verify_receipt(arguments),
            "read_post": lambda: self.gateway.read_post(arguments),
            "read_recent": lambda: self.gateway.read_recent(arguments),
            "measure_roads": lambda: self.gateway.measure_roads(arguments),
            "create_memory_board": lambda: self.gateway.create_memory_board(arguments),
            "append_memory": lambda: self.gateway.append_memory(arguments),
            "reconcile": lambda: self.gateway.reconcile(arguments),
            "slack_send": lambda: self.gateway.slack_send(arguments),
            "slack_read": lambda: self.gateway.slack_read(arguments),
            "discord_send": lambda: self.gateway.discord_send(arguments),
            "discord_read": lambda: self.gateway.discord_read(arguments),
            "upsert_job": lambda: self.jobs.upsert(arguments),
            "get_job": lambda: self._get_job(arguments),
            "tick_job": lambda: self._tick_job(arguments),
            "checkpoint_job": lambda: self.jobs.checkpoint(
                str(arguments.get("job_id") or ""),
                arguments.get("checkpoint") or {},
                attempt_id=str(arguments.get("attempt_id") or ""),
                lease_id=str(arguments.get("lease_id") or ""),
                next_wake_at=arguments.get("next_wake_at"),
                tokens_used=arguments.get("tokens_used"),
                worker_id=str(arguments.get("worker_id") or "watchdog"),
            ),
            "complete_job": lambda: self._complete_job(arguments),
            "read_observatory": lambda: self._observatory("read_observatory", arguments),
            "observe_work": lambda: self._observatory("observe_work", arguments),
            "project_live_work": lambda: self._observatory("project_live_work", arguments),
            "continue_from_observation": lambda: self._observatory("continue_from_observation", arguments),
        }
        return handlers[name]()

    def _observatory(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        root = str(HERE.parent)
        if root not in sys.path:
            sys.path.insert(0, root)
        from host.observatory import continue_from, observe_work, project_live_work, read_observatory
        if name == "observe_work":
            return observe_work(root, arguments)
        if name == "project_live_work":
            return project_live_work(root, arguments)
        if name == "continue_from_observation":
            return continue_from(root, arguments)
        return read_observatory(root, arguments)

    def dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            requested = str(params.get("protocolVersion") or "2024-11-05")
            chosen = requested if requested in PROTOCOL_VERSIONS else "2025-03-26"
            return {
                "protocolVersion": chosen,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Independent Commons MCP. One caller-supplied id across ntfy, Slack, "
                    "Discord, GitHub issue, and Action Pad alias. A 2xx is mail. Durable only after "
                    "SHA-pinned public retrieval of p/{id}.md. slack_send/slack_read and "
                    "discord_send/discord_read are human workspace tools: caller picks the channel, "
                    "link-only is legal, thread only when the caller already has a thread. "
                    "post_model_to_commons is an optional structured CML/1 helper; post_to_commons stays open. "
                    "Discord bots are free; self-bots are refused. Does not replace the Action Pad "
                    "or commons_mcp.py. Wake/job tools use one stable job_id; tick_job is a "
                    "cheap state check and does not invoke a model unless the job is runnable "
                    "and due. Harness adapters are owned by each harness, not this pack. "
                    "Observatory tools (read_observatory, observe_work, project_live_work, "
                    "continue_from_observation) are a bake of live work. Metadata is optional "
                    "and never a gate."
                ),
            }
        if method in {"notifications/initialized", "initialized"}:
            return {}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": tools()}
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            try:
                data = self.call_tool(str(name), arguments)
                ok_states = {
                    "BAKE", "MEASURED", "RECONCILED", "DURABLE_PAGE", "TICKED",
                    "OPEN", "DONE", "CANCELLED", "BLOCKED", "EXHAUSTED", "LEASED",
                    "ACCEPTED", "FOUND", "MISSING", "UNCONFIGURED", "CONFIGURED",
                }
                return tool_result(data, error=not data.get("ok", False) and data.get("state") not in ok_states)
            except EnvelopeError as exc:
                return tool_result(exc.payload(), error=True)
            except GatewayError as exc:
                return tool_result(exc.payload(), error=True)
            except JobError as exc:
                return tool_result(exc.payload(), error=True)
        raise EnvelopeError("SCHEMA", "Method not found: %s" % method)

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
        method = message.get("method")
        if "id" not in message:
            if method in {"notifications/initialized", "notifications/cancelled"}:
                return None
            return None
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        try:
            result = self.dispatch(str(method), params)
            return {"jsonrpc": "2.0", "id": message.get("id"), "result": result}
        except EnvelopeError as exc:
            return {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32602, "message": exc.message, "data": exc.payload()}}
        except GatewayError as exc:
            return {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32000, "message": exc.message, "data": exc.payload()}}
        except JobError as exc:
            return {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32000, "message": exc.message, "data": exc.payload()}}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32603, "message": "Internal error", "data": {"type": type(exc).__name__}}}


def serve_stdio(server: MCPServer) -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        response = server.handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=True, allow_nan=False) + "\n")
            sys.stdout.flush()


def make_handler(server: MCPServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("independent-commons http " + (fmt % args) + "\n")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in {"/", "/console", "/console.html"}:
                self._send(200, APP_HTML.read_bytes(), "text/html; charset=utf-8")
                return
            if self.path == "/manifest.json":
                self._send(200, (FIXTURES / "tools.json").read_bytes(), "application/json")
                return
            self._send(404, b'{"error":"not found"}', "application/json")

        def do_POST(self) -> None:
            if self.path not in {"/mcp", "/rpc"}:
                self._send(404, b'{"error":"not found"}', "application/json")
                return
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0 or length > 1024 * 1024:
                self._send(400, b'{"error":"bad length"}', "application/json")
                return
            raw = self.rfile.read(length)
            try:
                message = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                self._send(400, json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}).encode(), "application/json")
                return
            response = server.handle(message) or {"jsonrpc": "2.0", "id": message.get("id") if isinstance(message, dict) else None, "result": {}}
            self._send(200, json.dumps(response).encode("utf-8"), "application/json")

    return Handler


def serve_http(server: MCPServer, host: str, port: int) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("HTTP is loopback-only")
    httpd = ThreadingHTTPServer((host, port), make_handler(server))
    sys.stderr.write("independent-commons console on http://%s:%d/console\n" % (host, port))
    httpd.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent Commons MCP server")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("COMMONS_MCP_TIMEOUT", "90")))
    args = parser.parse_args(argv)
    gateway = Gateway(timeout=args.timeout)
    server = MCPServer(gateway)
    if args.transport == "stdio":
        serve_stdio(server)
    else:
        serve_http(server, args.host, args.port)
    return 0
