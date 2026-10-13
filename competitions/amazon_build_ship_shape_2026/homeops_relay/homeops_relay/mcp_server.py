from __future__ import annotations

import json
import os
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .homeops import HomeOpsLedger, ValidationError

MCP_PROTOCOL_VERSION = "2025-11-25"
SERVER_INFO = {"name": "homeops-relay", "version": "1.0.0"}
MAX_REQUEST_BYTES = 1_048_576
TOOL_CALL_WINDOW_SECONDS = 60.0
TOOL_CALLS_PER_WINDOW = 120


class DuplicateKeyError(ValueError):
    pass


def _strict_json_loads(raw: bytes) -> Any:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise DuplicateKeyError(f"duplicate key: {key}")
            out[key] = value
        return out

    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=pairs_hook,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite number: {value}")),
    )


def _json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be an object")
    return value


def _require_impl_info(value: Any, field: str) -> dict[str, Any]:
    value = _require_object(value, field)
    if not isinstance(value.get("name"), str) or not value["name"].strip():
        raise ValidationError(f"{field}.name must be a non-empty string")
    if not isinstance(value.get("version"), str) or not value["version"].strip():
        raise ValidationError(f"{field}.version must be a non-empty string")
    return value


class Dispatcher:
    def __init__(self, ledger: HomeOpsLedger | None = None) -> None:
        self.ledger = ledger or HomeOpsLedger()
        # ThreadingHTTPServer can dispatch concurrent tool calls. Serialize access
        # to the append-only in-memory ledger so sequence IDs and receipt chaining
        # cannot race.
        self._tool_lock = threading.RLock()

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict):
            return _rpc_error(None, -32600, "Invalid Request")
        if message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return _rpc_error(message.get("id"), -32600, "Invalid Request")
        allowed = {"jsonrpc", "id", "method", "params"}
        if set(message) - allowed:
            return _rpc_error(message.get("id"), -32600, "Invalid Request")
        request_id = message.get("id")
        is_notification = "id" not in message
        method = message["method"]
        params = message.get("params", {})
        if not isinstance(params, dict):
            return None if is_notification else _rpc_error(request_id, -32602, "Invalid params")

        try:
            if method == "initialize":
                result = self._initialize(params)
            elif method == "notifications/initialized":
                if params:
                    raise ValidationError("notifications/initialized does not accept parameters")
                return None
            elif method == "ping":
                if params:
                    raise ValidationError("ping does not accept parameters")
                result = {}
            elif method == "tools/list":
                unknown = set(params) - {"cursor", "_meta"}
                if unknown:
                    raise ValidationError("tools/list accepts only optional cursor metadata")
                cursor = params.get("cursor")
                if cursor not in (None, ""):
                    raise ValidationError("unknown pagination cursor")
                result = {"tools": HomeOpsLedger.tool_definitions()}
            elif method == "tools/call":
                with self._tool_lock:
                    result = self._tools_call(params)
            else:
                return None if is_notification else _rpc_error(request_id, -32601, "Method not found")
        except ValidationError as exc:
            return None if is_notification else _rpc_error(request_id, -32602, str(exc))
        except Exception:
            return None if is_notification else _rpc_error(request_id, -32603, "Internal error")
        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        unknown = set(params) - {"protocolVersion", "capabilities", "clientInfo", "_meta"}
        if unknown:
            raise ValidationError(f"initialize has unknown keys: {', '.join(sorted(unknown))}")
        missing = {"protocolVersion", "capabilities", "clientInfo"} - set(params)
        if missing:
            raise ValidationError(f"initialize is missing keys: {', '.join(sorted(missing))}")
        requested = params["protocolVersion"]
        if not isinstance(requested, str) or not requested:
            raise ValidationError("protocolVersion must be a non-empty string")
        _require_object(params["capabilities"], "capabilities")
        _require_impl_info(params["clientInfo"], "clientInfo")
        # MCP version negotiation requires the server to return the requested
        # version if supported; otherwise it returns a version it supports.
        negotiated = MCP_PROTOCOL_VERSION
        return {
            "protocolVersion": negotiated,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": "HomeOps Relay records evidence and proposes household actions. External effects remain owner-gated and are never executed by this server.",
        }

    def _tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        unknown = set(params) - {"name", "arguments", "_meta"}
        if unknown or "name" not in params:
            raise ValidationError("tools/call requires name and optional arguments only")
        if not isinstance(params["name"], str) or not params["name"]:
            raise ValidationError("tools/call name must be a non-empty string")
        arguments = params.get("arguments", {})
        try:
            payload = self.ledger.call_tool(params["name"], arguments)
            return {
                "content": [{"type": "text", "text": json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)}],
                "structuredContent": payload,
                "isError": False,
            }
        except ValidationError as exc:
            payload = {"error": str(exc)}
            return {
                "content": [{"type": "text", "text": json.dumps(payload, sort_keys=True)}],
                "structuredContent": payload,
                "isError": True,
            }


def _origin_allowed(origin: str | None) -> bool:
    if origin is None:
        return True
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return True
    configured = {item.strip() for item in os.environ.get("HOMEOPS_ALLOWED_ORIGINS", "").split(",") if item.strip()}
    return origin in configured


def _accept_types(raw: str | None) -> set[str]:
    if not raw:
        return set()
    values: set[str] = set()
    for item in raw.split(","):
        media = item.split(";", 1)[0].strip().lower()
        if media:
            values.add(media)
    return values


@dataclass
class SessionState:
    initialized: bool = False
    tool_calls: deque[float] = field(default_factory=deque)


class HomeOpsHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler: type[BaseHTTPRequestHandler], ledger: HomeOpsLedger | None = None) -> None:
        super().__init__(server_address, handler)
        self.dispatcher = Dispatcher(ledger)
        self.sessions: dict[str, SessionState] = {}
        self.session_lock = threading.RLock()

    def create_session(self) -> str:
        with self.session_lock:
            while True:
                session_id = secrets.token_urlsafe(24)
                if session_id not in self.sessions:
                    self.sessions[session_id] = SessionState()
                    return session_id

    def session_exists(self, session_id: str) -> bool:
        with self.session_lock:
            return session_id in self.sessions

    def mark_initialized(self, session_id: str) -> bool:
        with self.session_lock:
            state = self.sessions.get(session_id)
            if state is None:
                return False
            state.initialized = True
            return True

    def is_initialized(self, session_id: str) -> bool:
        with self.session_lock:
            state = self.sessions.get(session_id)
            return bool(state and state.initialized)

    def delete_session(self, session_id: str) -> bool:
        with self.session_lock:
            return self.sessions.pop(session_id, None) is not None

    def permit_tool_call(self, session_id: str, *, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self.session_lock:
            state = self.sessions.get(session_id)
            if state is None:
                return False
            cutoff = now - TOOL_CALL_WINDOW_SECONDS
            while state.tool_calls and state.tool_calls[0] <= cutoff:
                state.tool_calls.popleft()
            if len(state.tool_calls) >= TOOL_CALLS_PER_WINDOW:
                return False
            state.tool_calls.append(now)
            return True


class HomeOpsRequestHandler(BaseHTTPRequestHandler):
    server_version = "HomeOpsRelay/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover - intentionally quiet by default
        if os.environ.get("HOMEOPS_HTTP_LOG") == "1":
            super().log_message(fmt, *args)

    @property
    def app_server(self) -> HomeOpsHTTPServer:
        return self.server  # type: ignore[return-value]

    @property
    def dispatcher(self) -> Dispatcher:
        return self.app_server.dispatcher

    def _headers(self, status: int, content_type: str = "application/json", *, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _transport_error(self, status: int, message: str, *, request_id: Any = None) -> None:
        self._headers(status)
        self.wfile.write(_json(_rpc_error(request_id, -32600, message)))

    def _check_origin(self) -> bool:
        if _origin_allowed(self.headers.get("Origin")):
            return True
        self._transport_error(403, "Origin rejected")
        return False

    def _check_accept(self, *, post: bool) -> bool:
        accepts = _accept_types(self.headers.get("Accept"))
        required = {"application/json", "text/event-stream"} if post else {"text/event-stream"}
        if required.issubset(accepts):
            return True
        self._transport_error(406, "Accept header does not advertise required MCP response types")
        return False

    def _subsequent_session(self) -> str | None:
        session_id = self.headers.get("MCP-Session-Id")
        if not session_id:
            self._transport_error(400, "MCP-Session-Id is required after initialization")
            return None
        if not self.app_server.session_exists(session_id):
            self._transport_error(404, "MCP session not found")
            return None
        version = self.headers.get("MCP-Protocol-Version")
        if version != MCP_PROTOCOL_VERSION:
            self._transport_error(400, "Unsupported or missing MCP-Protocol-Version")
            return None
        return session_id

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._headers(200)
            with self.app_server.session_lock:
                sessions = len(self.app_server.sessions)
            self.wfile.write(
                _json(
                    {
                        "ok": True,
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "receipt": self.dispatcher.ledger.receipt,
                        "active_sessions": sessions,
                    }
                )
            )
            return
        if self.path == "/mcp":
            if not self._check_origin():
                return
            # This implementation deliberately uses JSON-only responses and no
            # unsolicited SSE stream. MCP explicitly allows 405 for GET here.
            self.send_response(405)
            self.send_header("Allow", "POST, DELETE")
            self.end_headers()
            return
        self._headers(404)
        self.wfile.write(_json({"error": "not found"}))

    def do_DELETE(self) -> None:
        if self.path != "/mcp":
            self._headers(404)
            self.wfile.write(_json({"error": "not found"}))
            return
        if not self._check_origin():
            return
        session_id = self.headers.get("MCP-Session-Id")
        if not session_id:
            self._transport_error(400, "MCP-Session-Id is required")
            return
        if not self.app_server.delete_session(session_id):
            self._transport_error(404, "MCP session not found")
            return
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self._headers(404)
            self.wfile.write(_json({"error": "not found"}))
            return
        if not self._check_origin() or not self._check_accept(post=True):
            return
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._transport_error(415, "Content-Type must be application/json")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_REQUEST_BYTES:
            self._transport_error(413, "request too large")
            return
        try:
            raw = self.rfile.read(length)
            message = _strict_json_loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError, ValueError):
            self._headers(400)
            self.wfile.write(_json(_rpc_error(None, -32700, "Parse error")))
            return
        if isinstance(message, list):
            self._headers(400)
            self.wfile.write(_json(_rpc_error(None, -32600, "Batch requests are not supported")))
            return
        if not isinstance(message, dict):
            self._headers(400)
            self.wfile.write(_json(_rpc_error(None, -32600, "Invalid Request")))
            return

        method = message.get("method")
        request_id = message.get("id")
        if method == "initialize":
            if self.headers.get("MCP-Session-Id"):
                self._transport_error(400, "initialize must not reuse an MCP session", request_id=request_id)
                return
            response = self.dispatcher.handle(message)
            if response is None or "error" in response:
                self._headers(200)
                self.wfile.write(_json(response or _rpc_error(request_id, -32603, "Internal error")))
                return
            session_id = self.app_server.create_session()
            self._headers(200, extra={"MCP-Session-Id": session_id})
            self.wfile.write(_json(response))
            return

        session_id = self._subsequent_session()
        if session_id is None:
            return
        if method == "notifications/initialized":
            response = self.dispatcher.handle(message)
            if response is not None:
                self._headers(200)
                self.wfile.write(_json(response))
                return
            self.app_server.mark_initialized(session_id)
            self.send_response(202)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return

        if not self.app_server.is_initialized(session_id) and method != "ping":
            self._headers(200)
            self.wfile.write(_json(_rpc_error(request_id, -32002, "Server not initialized")))
            return
        if method == "tools/call" and not self.app_server.permit_tool_call(session_id):
            self._headers(429)
            self.wfile.write(_json(_rpc_error(request_id, -32029, "Tool call rate limit exceeded")))
            return

        response = self.dispatcher.handle(message)
        if response is None:
            self.send_response(202)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self._headers(200)
        self.wfile.write(_json(response))


def make_server(host: str = "127.0.0.1", port: int = 8000, ledger: HomeOpsLedger | None = None) -> HomeOpsHTTPServer:
    return HomeOpsHTTPServer((host, port), HomeOpsRequestHandler, ledger)


def main() -> None:
    host = os.environ.get("HOMEOPS_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost", "::1"} and os.environ.get("HOMEOPS_ALLOW_REMOTE_BIND") != "1":
        raise SystemExit("Refusing non-loopback bind without HOMEOPS_ALLOW_REMOTE_BIND=1; terminate TLS/auth at a trusted reverse proxy.")
    port = int(os.environ.get("HOMEOPS_PORT", "8000"))
    server = make_server(host, port)
    print(f"HomeOps Relay MCP {MCP_PROTOCOL_VERSION} on http://{host}:{server.server_port}/mcp", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
