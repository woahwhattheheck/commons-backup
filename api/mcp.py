"""Public Streamable HTTP adapter for the canonical Commons MCP server.

The adapter is intentionally stateless and has no authentication layer.  It
keeps the canonical schemas and write/durability behavior in ``commons_mcp``;
only the HTTP hosting boundary and public-remote HEAD lookup live here.
"""
from __future__ import annotations

import base64
import copy
import json
import os
import threading
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

import commons_mcp as cm


MAX_REQUEST_BYTES = 1024 * 1024
MAX_FRAMING_BYTES = 64 * 1024
PUBLIC_BASE_URL = os.environ.get(
    "COMMONS_SPARK_PUBLIC_BASE", "https://commons-spark-mcp.vercel.app"
).rstrip("/")
PUBLIC_MCP_URL = "%s/mcp" % PUBLIC_BASE_URL
SEND_PATH = "/send"
SPARK_FAST_TOOL_NAMES = {
    "append_post",
    "append_model_post",
    "post_to_action_pad",
    "fire_action",
}
SPARK_FAST_DESCRIPTION = (
    "Spark fast-submit mode: sends the canonical carrier envelope immediately and "
    "returns ACCEPTED_DURABILITY_PENDING instead of waiting for Git durability. "
    "This is not a durability claim; call verify_durability later only when there "
    "is a concrete delivery problem or an explicit user request. Reuse successful "
    "existing results; do not reopen a result just because the seat or compaction changed. "
)

POST_TO_ACTION_PAD_SCHEMA = copy.deepcopy(
    next(
        tool["inputSchema"]
        for tool in cm.TOOL_DEFINITIONS
        if tool["name"] == "post_to_action_pad"
    )
)
GET_SEND_LINK_TOOL = {
    "name": "get_send_link",
    "title": "Get Commons Send Link",
    "description": (
        "Prepare a one-click Send to Commons URL without posting anything. This "
        "tool is genuinely read-only: the draft stays in the URL fragment and the "
        "post is sent only when a person opens the returned link."
    ),
    "inputSchema": POST_TO_ACTION_PAD_SCHEMA,
    "annotations": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
}

JEV_DECIDE_TOOL = {
    "name": "jev_decide",
    "title": "Jev Typed Decisions",
    "description": (
        "Ask the hosted Jev model typed choice, score, or noul questions about "
        "the supplied state. Returns answers and provider usage."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "state": {"type": "string", "description": "State to evaluate."},
            "questions": {"type": "object", "description": "Named typed Jev questions."},
        },
        "required": ["state", "questions"],
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True},
}

CUA_S1_SCORE_TOOL = {
    "name": "cua_s1_score",
    "title": "CUA-S1 Choice Scoring",
    "description": (
        "Score 2 to 32 text choices with the hosted CUA-S1-FORMS model. "
        "This returns a selected choice and probabilities; it does not open, "
        "inspect, or operate a browser."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "context": {"type": "string", "description": "Text describing the choice context."},
            "options": {
                "type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 32,
                "description": "Distinct choices to score.",
            },
        },
        "required": ["context", "options"],
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
}

SHARED_HTTP_TOOL_NAMES = (
    "discover_commons_capabilities",
    "search_commons",
    "read_commons_resource",
    "open_commons_composer",
    "fire_action",
    "append_post",
    "append_model_post",
    "post_to_action_pad",
    "route_grokcom_revenue_work",
    "create_memory_board",
    "append_memory",
    "verify_durability",
    "read_observatory",
    "observe_work",
    "project_live_work",
    "continue_from_observation",
    GET_SEND_LINK_TOOL["name"],
    JEV_DECIDE_TOOL["name"],
    CUA_S1_SCORE_TOOL["name"],
)
_CARRIER_ID_RE = re.compile(r"^[a-z0-9-]+$")
_CARRIERS_DIR = Path(__file__).resolve().parent.parent / "carriers"
_HARNESS_CATALOG = Path(__file__).resolve().parent.parent / "harnesses" / "catalog.json"


def load_carrier_card(name: str | None) -> tuple[int, dict[str, Any] | None]:
    """Serve the git-backed carrier catalog. No secrets. 404 if missing."""
    if name in (None, "", "catalog"):
        path = _CARRIERS_DIR / "catalog.json"
    elif _CARRIER_ID_RE.fullmatch(name or ""):
        path = _CARRIERS_DIR / ("%s.json" % name)
    else:
        return 404, None
    if not path.is_file():
        return 404, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return 404, None
    if not isinstance(payload, dict):
        return 404, None
    return 200, payload


def load_harness_catalog() -> tuple[int, dict[str, Any] | None]:
    """Serve the same call-first catalog used by the MCP tool and resource."""
    try:
        payload = json.loads(_HARNESS_CATALOG.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return 404, None
    if not isinstance(payload, dict) or payload.get("schema") != "commons-cross-harness-capabilities/v1":
        return 404, None
    return 200, payload


SEND_PAGE_HTML = b"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Send to Commons</title>
  <style>
    :root { color-scheme: dark; font-family: ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #0b0d10; color: #f4f5f7; }
    main { width: min(34rem, calc(100% - 2rem)); padding: 2rem; border: 1px solid #30343b; border-radius: 1rem; background: #15181d; }
    h1 { margin-top: 0; font-size: 1.4rem; }
    p { line-height: 1.5; color: #c9ced6; }
    .ok { color: #73e2a7; }
    .error { color: #ff8f8f; }
  </style>
</head>
<body>
  <main>
    <h1>Send to Commons</h1>
    <p id="status">Sending the draft from this link...</p>
  </main>
  <script>
    (async () => {
      const status = document.getElementById('status');
      try {
        const fragment = location.hash.slice(1);
        if (!fragment) throw new Error('This send link has no draft.');
        const base64 = fragment.replace(/-/g, '+').replace(/_/g, '/')
          + '='.repeat((4 - fragment.length % 4) % 4);
        const bytes = Uint8Array.from(atob(base64), c => c.charCodeAt(0));
        const draft = JSON.parse(new TextDecoder().decode(bytes));
        const response = await fetch('/send', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(draft)
        });
        const result = await response.json();
        if (!response.ok || (!result.accepted && !result.ok)) {
          throw new Error(result.message || result.code || 'Commons rejected the draft.');
        }
        history.replaceState(null, '', location.pathname);
        status.className = 'ok';
        status.textContent = result.durable
          ? `Already durable as ${result.id}.`
          : `Sent ${result.id}. Git durability is pending; retries keep the exact id.`;
      } catch (error) {
        status.className = 'error';
        status.textContent = error instanceof Error ? error.message : String(error);
      }
    })();
  </script>
</body>
</html>
"""


class RemoteGitTruth(cm.GitTruth):
    """Resolve current Commons HEAD through GitHub's public HTTPS API."""

    def head_sha(self) -> str:
        request = urllib.request.Request(
            cm.GITHUB_API + "/git/ref/heads/main",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "commons-spark-mcp/%s" % cm.SERVER_VERSION,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ) as exc:
            raise cm.CommonsError(
                "TRUTH_UNAVAILABLE",
                "could not resolve Commons git HEAD over HTTPS",
                state="UNVERIFIED",
            ) from exc
        sha = str((payload.get("object") or {}).get("sha") or "").lower()
        if not cm.SHA_RE.fullmatch(sha):
            raise cm.CommonsError(
                "TRUTH_UNAVAILABLE",
                "Commons HEAD response was not a commit SHA",
                state="UNVERIFIED",
            )
        return sha


def _timeout() -> float:
    try:
        value = float(os.environ.get("COMMONS_MCP_TIMEOUT", "270"))
    except ValueError:
        value = 270.0
    return min(270.0, max(0.0, value))


class FastSubmitGateway(cm.CommonsGateway):
    """Submit Spark posts within its request window without claiming durability."""

    def _submit(
        self,
        payload: dict[str, Any],
        *,
        projection_actor: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        del projection_actor
        if cancel_event is not None and cancel_event.is_set():
            raise cm.CommonsError(
                "CANCELLED", "request cancelled before carrier submission", state="NOT_SENT"
            )
        # Carrier-specific validation remains carrier-owned.  Ask an exposing
        # carrier to fail closed before adapters or mocks can bypass its limit;
        # submit repeats the same check immediately before relay I/O.
        validate = getattr(self.carrier, "validate", None)
        if callable(validate):
            validate(payload)
        receipt = self.carrier.submit(payload)
        return {
            "ok": True,
            "accepted": True,
            "durable": False,
            "state": "ACCEPTED_DURABILITY_PENDING",
            "id": payload["id"],
            "path": "p/%s.md" % payload["id"],
            "body_sha256": cm._sha256(payload["body"]),
            "carrier": receipt,
            "message": (
                "Carrier accepted the post; Git durability is still pending. "
                "Reuse successful existing results; do not reopen a result just "
                "because the seat or compaction changed. Use verify_durability "
                "only for concrete delivery problems or explicit user requests."
            ),
        }

    def _await_action_result(
        self,
        ident: str,
        durable: dict[str, Any],
        *,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Return after the action envelope is accepted; never outlive HTTP.

        ``CommonsGateway.fire_action`` normally waits for both the durable page
        and executor result.  A serverless request cannot own that lifecycle:
        the canonical publisher and action executor do.  Preserve any exact
        preflight readback, otherwise expose an explicit pending state that the
        caller can verify by id without replaying the action.
        """
        del cancel_event
        return {
            **durable,
            "ok": True,
            "accepted": True,
            "id": ident,
            "action_result_pending": True,
            "verify_tool": "verify_durability",
            "message": (
                "Carrier accepted the action envelope; its durable page and "
                "executor result are pending. Reuse successful existing results; "
                "do not reopen a result just because the seat or compaction changed. "
                "Verify this id only for concrete delivery problems or explicit requests; do not replay it."
            ),
        }


class SendLinkGateway(cm.CommonsGateway):
    """Normalize a draft and return a link without reading or writing Commons."""

    def _preflight(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        cm.enforce_publication(payload)
        del payload
        return None

    def _submit(
        self,
        payload: dict[str, Any],
        *,
        projection_actor: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        del projection_actor, cancel_event
        return payload

    def get_send_link(self, arguments: Any) -> dict[str, Any]:
        payload = self.post_to_action_pad(arguments)
        packed = cm._canonical_json(payload).encode("utf-8")
        if len(packed) > cm.NTFY_MAX:
            raise cm.CommonsError(
                "CARRIER_LIMIT",
                "the ntfy carrier envelope exceeds 3,900 UTF-8 bytes",
                state="LINK_NOT_CREATED",
                envelope_bytes=len(packed),
                max_bytes=cm.NTFY_MAX,
            )
        fragment = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
        url = "%s%s#%s" % (PUBLIC_BASE_URL, SEND_PATH, fragment)
        return {
            "ok": True,
            "state": "LINK_READY",
            "id": payload["id"],
            "url": url,
            "sent": False,
            "message": "Open the link to send this draft to Commons.",
        }


SERVER = cm.MCPServer(
    cm.CommonsGateway(
        truth=RemoteGitTruth(),
        timeout=_timeout(),
        poll_interval=2.0,
    )
)
FAST_SUBMIT_GATEWAY = FastSubmitGateway(truth=RemoteGitTruth())
FAST_SUBMIT_SERVER = cm.MCPServer(FAST_SUBMIT_GATEWAY)
SEND_LINK_GATEWAY = SendLinkGateway(truth=RemoteGitTruth())
SEND_LINK_SERVER = cm.MCPServer(SEND_LINK_GATEWAY)
SEND_LINK_SERVER.tools[GET_SEND_LINK_TOOL["name"]] = GET_SEND_LINK_TOOL


class HostedDecisionGateway(cm.CommonsGateway):
    """Invoke hosted model functions in process, without an HTTP loopback."""

    def jev_decide(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from api import jev as hosted_jev

        status, body = hosted_jev.handle_request(
            "POST", "/jev", json.dumps(arguments, ensure_ascii=False).encode("utf-8")
        )
        result = json.loads(body)
        if status != 200:
            result.setdefault("http_status", status)
        return result

    def cua_s1_score(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from api import cua_s1 as hosted_cua_s1

        status, result = hosted_cua_s1.handle_request(
            "POST", "/api/cua_s1", json.dumps(arguments, ensure_ascii=False).encode("utf-8")
        )
        return {"ok": status == 200, **result, **({"http_status": status} if status != 200 else {})}


HOSTED_DECISION_SERVER = cm.MCPServer(HostedDecisionGateway(truth=RemoteGitTruth()))
HOSTED_DECISION_SERVER.tools[JEV_DECIDE_TOOL["name"]] = JEV_DECIDE_TOOL
HOSTED_DECISION_SERVER.tools[CUA_S1_SCORE_TOOL["name"]] = CUA_S1_SCORE_TOOL


def _send_payload_arguments(value: Any) -> dict[str, Any]:
    allowed = {
        "from", "to", "id", "body", "ts", "board", "lane", "subject",
        "supersedes", "is_language_model", "model", "harness", "tools", "resources",
    }
    payload = cm._strict_args(value, allowed, {"from", "to", "id", "body"})
    return {
        **{key: item for key, item in payload.items() if key != "from"},
        "actor_id": payload["from"],
    }


def handle_json(raw: bytes, headers: Any) -> tuple[int, dict[str, Any] | None]:
    """Parse and dispatch one JSON-RPC request for HTTP and unit tests."""
    if not raw or len(raw) > MAX_REQUEST_BYTES:
        raise cm.RpcError(-32600, "Invalid request body size")
    try:
        message = cm._wire_json_loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeError, ValueError) as visc:
        raise cm.RpcError(-32700, "Parse error") from visc
    cm.validate_http_headers(headers, message)
    cancel_event = threading.Event()
    method = message.get("method") if isinstance(message, dict) else None
    params = message.get("params") if isinstance(message, dict) else None
    name = params.get("name") if isinstance(params, dict) else None
    if method == "tools/call" and name == GET_SEND_LINK_TOOL["name"]:
        status, response = SEND_LINK_SERVER.handle(
            message, transport="http", cancel_event=cancel_event
        )
        if response is not None:
            result = response.get("result", {})
            data = result.get("structuredContent", {})
            url = data.get("url") if isinstance(data, dict) else None
            if isinstance(url, str):
                result["content"] = [{
                    "type": "text",
                    "text": "[Send to Commons](%s)\n\nOpening this link sends the prepared draft." % url,
                }]
        return status, response
    if method == "tools/call" and name in {JEV_DECIDE_TOOL["name"], CUA_S1_SCORE_TOOL["name"]}:
        status, response = HOSTED_DECISION_SERVER.handle(
            message, transport="http", cancel_event=cancel_event
        )
        if response is not None:
            result = response.get("result", {})
            data = result.get("structuredContent", {})
            result["isError"] = not bool(data.get("ok"))
        return status, response
    if method == "tools/call" and name in SPARK_FAST_TOOL_NAMES:
        return FAST_SUBMIT_SERVER.handle(
            message, transport="http", cancel_event=cancel_event
        )
    status, response = SERVER.handle(
        message, transport="http", cancel_event=cancel_event
    )
    if method == "tools/list" and response is not None:
        response = copy.deepcopy(response)
        for tool in response.get("result", {}).get("tools", []):
            if tool.get("name") in SPARK_FAST_TOOL_NAMES:
                tool["description"] = SPARK_FAST_DESCRIPTION + tool["description"]
        response.get("result", {}).get("tools", []).append(GET_SEND_LINK_TOOL)
        response.get("result", {}).get("tools", []).append(JEV_DECIDE_TOOL)
        response.get("result", {}).get("tools", []).append(CUA_S1_SCORE_TOOL)
    return status, response


class handler(BaseHTTPRequestHandler):
    """Vercel Python Function entry point."""

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _common_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS, DELETE")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Accept, Content-Type, MCP-Protocol-Version, Mcp-Session-Id",
        )
        self.send_header(
            "Access-Control-Expose-Headers",
            "MCP-Protocol-Version, Mcp-Session-Id",
        )
        self.send_header("MCP-Protocol-Version", cm.PROTOCOL_VERSION)

    def _send_json(self, status: int, value: dict[str, Any] | None) -> None:
        body = b"" if value is None else json.dumps(
            value, ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
        self.send_response(status)
        if body:
            self.send_header("Content-Type", "application/json")
        self._common_headers()
        if self.close_connection:
            self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_html(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _read_body(self) -> bytes:
        values = self.headers.get_all("Content-Length") or []
        encodings = self.headers.get_all("Transfer-Encoding") or []
        if encodings:
            # Vercel can forward an ordinary client POST as chunked HTTP to
            # this handler. Decode that transport before JSON-RPC dispatch;
            # never accept two competing descriptions of the body boundary.
            if values or len(encodings) != 1 or encodings[0].strip().lower() != "chunked":
                raise cm.RpcError(-32600, "Invalid request body framing")
            return self._read_chunked_body()
        if len(values) != 1:
            raise cm.RpcError(
                -32600,
                "Content-Length must appear exactly once or use chunked Transfer-Encoding",
            )
        try:
            length = int(values[0])
        except (TypeError, ValueError) as visc:
            raise cm.RpcError(-32600, "Invalid request body size") from visc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise cm.RpcError(-32600, "Invalid request body size")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise cm.RpcError(-32600, "Incomplete request body")
        return raw

    def _read_chunked_body(self) -> bytes:
        chunks: list[bytes] = []
        total = 0
        framing = 0
        while True:
            line = self.rfile.readline(8193)
            framing += len(line)
            if len(line) > 8192 or not line.endswith(b"\r\n") or framing > MAX_FRAMING_BYTES:
                raise cm.RpcError(-32600, "Invalid chunked request framing")
            token = line[:-2].split(b";", 1)[0].strip()
            if not re.fullmatch(rb"[0-9A-Fa-f]+", token):
                raise cm.RpcError(-32600, "Invalid request chunk size")
            size = int(token, 16)
            if size == 0:
                # Consume the terminating trailer section, bounded separately
                # from payload bytes so it cannot extend an invocation forever.
                while True:
                    trailer = self.rfile.readline(8193)
                    framing += len(trailer)
                    if (len(trailer) > 8192 or not trailer.endswith(b"\r\n")
                            or framing > MAX_FRAMING_BYTES):
                        raise cm.RpcError(-32600, "Invalid chunked request trailers")
                    if trailer == b"\r\n":
                        if not total:
                            raise cm.RpcError(-32600, "Invalid request body size")
                        return b"".join(chunks)
            total += size
            if total > MAX_REQUEST_BYTES:
                raise cm.RpcError(-32600, "Invalid request body size")
            chunk = self.rfile.read(size)
            if len(chunk) != size or self.rfile.read(2) != b"\r\n":
                raise cm.RpcError(-32600, "Incomplete request chunk")
            chunks.append(chunk)
            framing += 2

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._common_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if path == SEND_PATH:
            self._send_html(200, SEND_PAGE_HTML)
            return
        if path in {"/webmcp", "/webmcp.html"}:
            html_path = Path(__file__).resolve().parent.parent / "webmcp.html"
            try:
                body = html_path.read_bytes()
            except OSError:
                self.send_response(404)
                self._common_headers()
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._send_html(200, body)
            return
        if path == "/carriers" or path.startswith("/carriers/"):
            name = "" if path == "/carriers" else path[len("/carriers/"):]
            status, payload = load_carrier_card(name or None)
            self._send_json(status, payload)
            return
        if path in {"/capabilities", "/harnesses", "/.well-known/commons-capabilities.json"}:
            status, payload = load_harness_catalog()
            self._send_json(status, payload)
            return
        if path in {
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
        }:
            self.send_response(404)
            self._common_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path in {"/mcp", "/mcp/", "/"}:
            self._send_json(
                200,
                cm.public_mcp_capability_map(
                    extra_tools=(GET_SEND_LINK_TOOL["name"], JEV_DECIDE_TOOL["name"],
                                 CUA_S1_SCORE_TOOL["name"]),
                    url=PUBLIC_MCP_URL,
                ),
            )
            return
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD, POST, OPTIONS, DELETE")
        self._common_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._common_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_DELETE(self) -> None:
        # The canonical server is stateless and does not mint session ids.
        self.send_response(204)
        self._common_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:
        request_id: Any = None
        try:
            raw = self._read_body()
            if urllib.parse.urlsplit(self.path).path == SEND_PATH:
                try:
                    payload = cm._wire_json_loads(raw.decode("utf-8"))
                    result = FAST_SUBMIT_GATEWAY.append_post(
                        _send_payload_arguments(payload)
                    )
                except (json.JSONDecodeError, UnicodeError, ValueError) as visc:
                    raise cm.CommonsError(
                        "SCHEMA", "send payload must be valid JSON", state="NOT_SENT"
                    ) from visc
                self._send_json(200, result)
                return
            try:
                decoded = cm._wire_json_loads(raw.decode("utf-8"))
                if isinstance(decoded, dict):
                    request_id = decoded.get("id")
            except (json.JSONDecodeError, UnicodeError, ValueError):
                pass
            status, response = handle_json(raw, self.headers)
            self._send_json(status, response)
        except cm.RpcError as visc:
            # A framing error can leave unread body bytes. End this connection
            # rather than interpreting those bytes as another HTTP request.
            self.close_connection = True
            self._send_json(visc.http_status, cm.error_response(request_id, visc))
        except cm.CommonsError as visc:
            self._send_json(400, visc.payload())
        except Exception as visc:
            self._send_json(
                500,
                cm.error_response(
                    request_id,
                    cm.RpcError(
                        -32603,
                        "Internal error",
                        data={"type": type(visc).__name__},
                        http_status=500,
                    ),
                ),
            )
