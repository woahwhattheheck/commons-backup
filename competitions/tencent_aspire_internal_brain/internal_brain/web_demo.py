"""Local browser interface for the InternalBrain demonstration bundle.

The server deliberately has no login and no token check. A person using the page
selects a declaration already present in the loaded bundle. That selection is
not authentication.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from internal_brain.assistant_context import build_context_packet
from internal_brain.core import (
    AuditError,
    AuthorizationError,
    InternalBrain,
    SchemaError,
    strict_loads,
    verify_audit,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_REQUEST_BODY_BYTES = 64 * 1024
MAX_QUESTION_CHARACTERS = 2_000
MAX_RESULTS_LIMIT = 20
SOCKET_TIMEOUT_SECONDS = 15.0


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Internal Brain Browser</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #07111e;
      --panel: #102039;
      --panel2: #142943;
      --line: #315071;
      --text: #eef6ff;
      --muted: #a9bfd7;
      --accent: #79dbff;
      --good: #8cf0b5;
      --bad: #ff939e;
      --warn: #ffda87;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at top left, #153b5d 0, transparent 35rem),
        var(--bg);
      color: var(--text);
      font: 15px/1.5 system-ui, sans-serif;
    }
    main { width: min(1240px, calc(100% - 32px)); margin: 28px auto 60px; }
    h1 { margin: 0; font-size: clamp(2rem, 4vw, 3.2rem); letter-spacing: -.04em; }
    h2, h3 { margin-top: 0; }
    h2 { font-size: 1.3rem; }
    h3 { margin-top: 20px; font-size: 1rem; color: var(--accent); }
    .muted, .subtitle { color: var(--muted); }
    .notice {
      margin: 18px 0;
      padding: 13px 15px;
      border: 1px solid #8b7549;
      border-radius: 12px;
      background: #302914;
      color: #ffeab8;
    }
    .grid { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(320px, .85fr); gap: 18px; align-items: start; }
    .panel {
      margin-bottom: 18px;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 15px;
      background: linear-gradient(150deg, var(--panel2), var(--panel));
      box-shadow: 0 18px 45px #0005;
    }
    label { display: block; margin: 12px 0 5px; color: var(--muted); font-weight: 700; font-size: .88rem; }
    input, select, textarea, button { width: 100%; border-radius: 9px; font: inherit; }
    input, select, textarea { padding: 10px 11px; border: 1px solid var(--line); background: #081525; color: var(--text); }
    textarea { min-height: 145px; resize: vertical; }
    input:focus, select:focus, textarea:focus, button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    button {
      margin-top: 14px;
      padding: 11px;
      border: 1px solid #6bd3fa;
      background: linear-gradient(135deg, #177cad, #19886a);
      color: white;
      font-weight: 800;
      cursor: pointer;
    }
    button:disabled { opacity: .65; cursor: wait; }
    .row { display: grid; grid-template-columns: 1fr 130px; gap: 12px; }
    .badge { display: inline-block; margin: 3px 5px 3px 0; padding: 3px 8px; border: 1px solid var(--line); border-radius: 999px; font-size: .78rem; }
    .badge.audit { color: var(--good); border-color: var(--good); }
    .decision { padding: 12px 14px; border-left: 4px solid var(--accent); border-radius: 8px; background: #112944; }
    .decision.allowed { border-color: var(--good); background: #143527; }
    .decision.denied { border-color: var(--bad); background: #3a1e26; }
    .card { margin-top: 11px; padding: 12px; border: 1px solid var(--line); border-radius: 10px; background: #071321b8; }
    pre { max-height: 420px; overflow: auto; margin: 7px 0 0; padding: 10px; border: 1px solid #2b4666; border-radius: 8px; background: #06101c; color: #e0efff; white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.5 ui-monospace, Consolas, monospace; }
    .status { min-height: 1.5rem; margin-top: 11px; color: var(--muted); }
    .status.error { color: var(--bad); }
    .status.success { color: var(--good); }
    .hidden { display: none; }
    .empty { padding: 11px; border: 1px dashed var(--line); border-radius: 8px; color: var(--muted); }
    dl { display: grid; grid-template-columns: max-content 1fr; gap: 5px 12px; }
    dt { color: var(--muted); }
    dd { margin: 0; overflow-wrap: anywhere; }
    @media (max-width: 850px) { .grid, .row { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<main>
  <header>
    <h1>Internal Brain Browser</h1>
    <p class="subtitle">Query the loaded evidence bundle and inspect authorization and audit receipts.</p>
  </header>
  <div class="notice"><strong>Identity boundary:</strong> identities on this page are selected by the operator from declarations in the loaded bundle. The server does not authenticate the person making a request.</div>
  <div class="grid">
    <section>
      <div class="panel">
        <h2>Evidence query</h2>
        <label for="query-actor">Declared actor</label>
        <select id="query-actor"></select>
        <div id="query-actor-summary" class="muted"></div>
        <label for="question">Question</label>
        <textarea id="question" maxlength="2000" placeholder="Enter a question for the loaded evidence bundle."></textarea>
        <div class="row">
          <div>
            <label for="document-ids">Document IDs, comma-separated (optional)</label>
            <input id="document-ids" type="text" autocomplete="off">
          </div>
          <div>
            <label for="max-results">Maximum results</label>
            <input id="max-results" type="number" min="1" max="20" value="5">
          </div>
        </div>
        <button id="query-button" type="button">Run authorized query</button>
        <div id="query-status" class="status" role="status" aria-live="polite"></div>
      </div>
      <div id="query-output" class="panel hidden">
        <h2>Query receipt</h2>
        <div id="decision-output"></div>
        <h3>Authorization decision</h3><pre id="authorization-output"></pre>
        <h3>Security boundary</h3><pre id="security-output"></pre>
        <h3>Audit event digest</h3><pre id="query-audit-digest"></pre>
        <h3>AI context packet</h3><pre id="context-packet-output"></pre>
        <h3>Results</h3><div id="results-output"></div>
        <h3>Citations</h3><div id="citations-output"></div>
        <h3>Digests</h3><div id="digests-output"></div>
        <h3>Instruction markers</h3><div id="markers-output"></div>
        <details><summary>Complete receipt</summary><pre id="receipt-output"></pre></details>
      </div>
    </section>
    <aside>
      <div class="panel">
        <h2>Loaded bundle</h2>
        <dl><dt>Tenant</dt><dd id="tenant-id">Loading…</dd><dt>Declared actors</dt><dd id="actor-count">—</dd><dt>Documents</dt><dd id="document-count">—</dd></dl>
        <div id="meta-status" class="status" role="status" aria-live="polite"></div>
      </div>
      <div class="panel">
        <h2>Audit chain</h2>
        <p class="muted">Select a declared actor whose roles include audit permission.</p>
        <label for="audit-actor">Declared audit actor</label>
        <select id="audit-actor"></select>
        <div id="audit-actor-summary" class="muted"></div>
        <button id="audit-button" type="button">Load and verify audit chain</button>
        <div id="audit-status" class="status" role="status" aria-live="polite"></div>
        <div id="audit-output" class="hidden"><h3>Verification</h3><pre id="audit-verification"></pre><h3>Events</h3><div id="audit-events"></div></div>
      </div>
    </aside>
  </div>
</main>
<script>
"use strict";
const state = { meta: null };
const byId = id => document.getElementById(id);
const pretty = value => JSON.stringify(value, null, 2);
const queryActor = byId("query-actor");
const auditActor = byId("audit-actor");

function status(element, message, kind = "") {
  element.textContent = message;
  element.className = "status" + (kind ? " " + kind : "");
}

async function jsonRequest(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let body;
  try { body = await response.json(); }
  catch { throw Object.assign(new Error(`Unreadable server response (${response.status}).`), { code: "invalid_response" }); }
  if (!response.ok) {
    const error = body && body.error || {};
    throw Object.assign(new Error(error.message || `HTTP ${response.status}`), { code: error.code || "request_failed" });
  }
  return body;
}

function actor(userId) {
  return state.meta && state.meta.actors.find(item => item.user_id === userId);
}

function describeActor(select, target) {
  const item = actor(select.value);
  target.replaceChildren();
  if (!item) { target.textContent = "No declared actor selected."; return; }
  const identity = document.createElement("p");
  identity.textContent = `Declared identity: ${item.user_id}`;
  const badges = document.createElement("div");
  item.roles.forEach(role => {
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = `${role.role_id} · clearance ${role.clearance}`;
    badges.append(badge);
  });
  if (item.audit_capable) {
    const badge = document.createElement("span");
    badge.className = "badge audit";
    badge.textContent = "audit-capable declaration";
    badges.append(badge);
  }
  const permissions = document.createElement("p");
  permissions.textContent = item.permissions.length ? `Permissions: ${item.permissions.join(", ")}` : "Permissions: none declared";
  target.append(identity, badges, permissions);
}

function fillActors(select, actors, preferred = null) {
  select.replaceChildren();
  actors.forEach(item => {
    const option = document.createElement("option");
    option.value = item.user_id;
    option.textContent = item.audit_capable ? `${item.user_id} — audit capable` : item.user_id;
    select.append(option);
  });
  if (preferred) select.value = preferred;
}

function findFields(value, names, path = "$", found = [], depth = 0) {
  if (depth > 16 || value === null || value === undefined) return found;
  if (Array.isArray(value)) {
    value.forEach((item, index) => findFields(item, names, `${path}[${index}]`, found, depth + 1));
    return found;
  }
  if (typeof value !== "object") return found;
  Object.entries(value).forEach(([key, item]) => {
    const child = `${path}.${key}`;
    if (names.has(key.toLowerCase())) found.push({ path: child, value: item });
    findFields(item, names, child, found, depth + 1);
  });
  return found;
}

function renderFields(target, fields) {
  target.replaceChildren();
  if (!fields.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No matching fields were returned.";
    target.append(empty);
    return;
  }
  fields.forEach(field => {
    const card = document.createElement("div");
    card.className = "card";
    const label = document.createElement("strong");
    label.textContent = field.path;
    const value = document.createElement("pre");
    value.textContent = pretty(field.value);
    card.append(label, value);
    target.append(card);
  });
}

function renderResults(results) {
  const target = byId("results-output");
  target.replaceChildren();
  const items = Array.isArray(results) ? results : results == null ? [] : [results];
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "The authorized query returned no result records.";
    target.append(empty);
    return;
  }
  items.forEach((item, index) => {
    const card = document.createElement("article");
    card.className = "card";
    const heading = document.createElement("h3");
    const id = item && typeof item === "object" && (item.document_id || item.id);
    heading.textContent = id ? `Result ${index + 1} · ${id}` : `Result ${index + 1}`;
    const body = document.createElement("pre");
    body.textContent = pretty(item);
    card.append(heading, body);
    target.append(card);
  });
}

function renderReceipt(receipt, contextPacket) {
  byId("query-output").classList.remove("hidden");
  const code = typeof receipt.decision_code === "string" ? receipt.decision_code : "unspecified";
  const normalized = code.toUpperCase();
  const box = document.createElement("div");
  box.className = "decision";
  if (normalized.startsWith("AUTHORIZED_")) box.classList.add("allowed");
  else if (normalized.includes("DENY") || normalized.includes("REJECT") || normalized.includes("FORBID")) box.classList.add("denied");
  const label = document.createElement("strong");
  label.textContent = `Decision: ${code}`;
  box.append(label);
  byId("decision-output").replaceChildren(box);
  byId("authorization-output").textContent = pretty(receipt.authorization ?? null);
  byId("security-output").textContent = pretty(receipt.security_boundary ?? null);
  byId("query-audit-digest").textContent = pretty(receipt.audit_event_digest ?? null);
  byId("receipt-output").textContent = pretty(receipt);
  byId("context-packet-output").textContent = pretty(contextPacket);
  renderResults(receipt.results);
  renderFields(byId("citations-output"), findFields(receipt.results, new Set(["citation", "citations", "source_citations"])));
  renderFields(byId("digests-output"), findFields(receipt, new Set([
    "digest", "content_digest", "document_digest", "chunk_digest",
    "audit_event_digest", "previous_digest", "previous_event_digest",
    "content_sha256", "document_sha256", "result_receipt_sha256", "query_sha256",
    "packet_sha256", "source_result_receipt_sha256",
  ])));
  renderFields(byId("markers-output"), findFields(receipt.results, new Set([
    "instruction_marker", "instruction_markers", "instruction_detection", "instruction_detections",
  ])));
}

function renderAudit(events, verification) {
  byId("audit-output").classList.remove("hidden");
  byId("audit-verification").textContent = pretty(verification);
  const target = byId("audit-events");
  target.replaceChildren();
  if (!events.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "The audit chain contains no events.";
    target.append(empty);
    return;
  }
  events.forEach((event, index) => {
    const card = document.createElement("article");
    card.className = "card";
    const heading = document.createElement("h3");
    const kind = event && typeof event === "object" && (event.event_type || event.action || event.type);
    heading.textContent = kind ? `Event ${index + 1} · ${kind}` : `Event ${index + 1}`;
    const body = document.createElement("pre");
    body.textContent = pretty(event);
    card.append(heading, body);
    target.append(card);
  });
}

async function loadMeta() {
  const target = byId("meta-status");
  status(target, "Loading bundle declarations…");
  try {
    state.meta = (await jsonRequest("/meta", { method: "GET", headers: {} })).meta;
    byId("tenant-id").textContent = state.meta.tenant_id;
    byId("actor-count").textContent = String(state.meta.actors.length);
    byId("document-count").textContent = String(state.meta.document_count);
    fillActors(queryActor, state.meta.actors);
    const preferred = (state.meta.actors.find(item => item.audit_capable) || state.meta.actors[0] || {}).user_id;
    fillActors(auditActor, state.meta.actors, preferred);
    describeActor(queryActor, byId("query-actor-summary"));
    describeActor(auditActor, byId("audit-actor-summary"));
    status(target, "Bundle metadata loaded.", "success");
  } catch (error) { status(target, `${error.code || "error"}: ${error.message}`, "error"); }
}

queryActor.addEventListener("change", () => describeActor(queryActor, byId("query-actor-summary")));
auditActor.addEventListener("change", () => describeActor(auditActor, byId("audit-actor-summary")));

byId("query-button").addEventListener("click", async () => {
  const button = byId("query-button");
  const target = byId("query-status");
  const question = byId("question").value.trim();
  const documentIds = byId("document-ids").value.split(",").map(value => value.trim()).filter(Boolean);
  const maxResults = Number(byId("max-results").value);
  if (!question) { status(target, "Enter a question before running the query.", "error"); return; }
  button.disabled = true;
  status(target, "Running query…");
  try {
    const response = await jsonRequest("/query", {
      method: "POST",
      body: JSON.stringify({ actor_user_id: queryActor.value, question, max_results: maxResults, document_ids: documentIds }),
    });
    renderReceipt(response.receipt, response.context_packet);
    status(target, "Query receipt returned.", "success");
  } catch (error) {
    byId("query-output").classList.add("hidden");
    status(target, `${error.code || "error"}: ${error.message}`, "error");
  } finally { button.disabled = false; }
});

byId("audit-button").addEventListener("click", async () => {
  const button = byId("audit-button");
  const target = byId("audit-status");
  button.disabled = true;
  status(target, "Loading audit chain…");
  try {
    const response = await jsonRequest("/audit", {
      method: "POST",
      body: JSON.stringify({ actor_user_id: auditActor.value }),
    });
    renderAudit(response.events, response.verification);
    status(target, `Loaded ${response.events.length} audit event(s).`, "success");
  } catch (error) {
    byId("audit-output").classList.add("hidden");
    status(target, `${error.code || "error"}: ${error.message}`, "error");
  } finally { button.disabled = false; }
});

loadMeta();
</script>
</body>
</html>
"""


class RequestProblem(Exception):
    """A request failure safe to describe to the HTTP client."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ApplicationState:
    engine: InternalBrain
    engine_lock: threading.RLock


def _default_bundle_path() -> Path:
    package_candidate = Path(__file__).resolve().with_name("demo_bundle.json")
    repository_candidate = Path(__file__).resolve().parent.parent / "demo_bundle.json"
    if package_candidate.is_file():
        return package_candidate
    return repository_candidate


def _permission_implies_audit(permission: str) -> bool:
    normalized = permission.strip().lower().replace("_", ":").replace("-", ":")
    return "audit" in normalized


def _public_meta(engine: InternalBrain) -> dict[str, Any]:
    actors: list[dict[str, Any]] = []
    for user_id, user in sorted(engine.users.items()):
        roles: list[dict[str, Any]] = []
        permissions: set[str] = set()
        for role_id in user.role_ids:
            role = engine.roles.get(role_id)
            if role is None:
                continue
            role_permissions = sorted(str(value) for value in role.permissions)
            permissions.update(role_permissions)
            roles.append(
                {
                    "role_id": role.role_id,
                    "clearance": role.clearance,
                    "permissions": role_permissions,
                }
            )
        sorted_permissions = sorted(permissions)
        actors.append(
            {
                "user_id": user_id,
                "role_ids": list(user.role_ids),
                "roles": roles,
                "permissions": sorted_permissions,
                "audit_capable": any(
                    _permission_implies_audit(permission)
                    for permission in sorted_permissions
                ),
            }
        )
    return {
        "tenant_id": engine.tenant_id,
        "actors": actors,
        "document_count": len(engine.documents),
        "identity_selection": {
            "mode": "operator_selected_declaration",
            "authenticated": False,
            "notice": (
                "Declared identities are selected by the operator and are "
                "not authenticated by this server."
            ),
        },
    }


class InternalBrainRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "InternalBrainWebDemo/1"
    sys_version = ""
    application_state: ApplicationState

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(SOCKET_TIMEOUT_SECONDS)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; connect-src 'self'; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; "
            "frame-ancestors 'none'",
        )
        super().end_headers()

    def log_message(self, format_string: str, *args: Any) -> None:
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.address_string(), self.log_date_time_string(), format_string % args)
        )

    def _send_bytes(self, status: int, body: bytes, *, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        self._send_bytes(status, body, content_type="application/json; charset=utf-8")

    def _send_problem(self, problem: RequestProblem) -> None:
        self._send_json(
            problem.status,
            {"ok": False, "error": {"code": problem.code, "message": problem.message}},
        )

    def _read_json_object(self) -> dict[str, Any]:
        if self.headers.get("Transfer-Encoding"):
            self.close_connection = True
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "unsupported_transfer_encoding",
                "Chunked or encoded request bodies are not accepted.",
            )
        media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise RequestProblem(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "content_type_required",
                "Content-Type must be application/json.",
            )
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            self.close_connection = True
            raise RequestProblem(
                HTTPStatus.LENGTH_REQUIRED,
                "content_length_required",
                "Content-Length is required.",
            )
        try:
            content_length = int(raw_length, 10)
        except ValueError as exc:
            self.close_connection = True
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "invalid_content_length",
                "Content-Length must be a non-negative integer.",
            ) from exc
        if content_length < 0:
            self.close_connection = True
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "invalid_content_length",
                "Content-Length must be a non-negative integer.",
            )
        if content_length > MAX_REQUEST_BODY_BYTES:
            self.close_connection = True
            raise RequestProblem(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "request_body_too_large",
                f"Request body must not exceed {MAX_REQUEST_BODY_BYTES} bytes.",
            )
        try:
            raw_body = self.rfile.read(content_length)
        except (TimeoutError, socket.timeout) as exc:
            self.close_connection = True
            raise RequestProblem(
                HTTPStatus.REQUEST_TIMEOUT,
                "request_timeout",
                "The request body was not received in time.",
            ) from exc
        if len(raw_body) != content_length:
            self.close_connection = True
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "incomplete_request_body",
                "The request body ended before Content-Length bytes were received.",
            )
        try:
            text = raw_body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "invalid_utf8",
                "Request body must be valid UTF-8.",
            ) from exc
        try:
            value = strict_loads(text)
        except (json.JSONDecodeError, SchemaError, ValueError) as exc:
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "invalid_json",
                "Request body must be one valid JSON object.",
            ) from exc
        if not isinstance(value, dict):
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "json_object_required",
                "Request body must be a JSON object.",
            )
        return value

    @staticmethod
    def _reject_unknown_fields(
        payload: dict[str, Any], allowed_fields: frozenset[str]
    ) -> None:
        unknown = sorted(set(payload) - allowed_fields)
        if unknown:
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "unknown_field",
                f"Unsupported request field: {unknown[0]}",
            )

    def _declared_actor(self, payload: dict[str, Any]) -> str:
        actor = payload.get("actor_user_id")
        if not isinstance(actor, str) or not actor.strip():
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "actor_user_id_required",
                "actor_user_id must name a declared actor.",
            )
        actor = actor.strip()
        if actor not in self.application_state.engine.users:
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "unknown_declared_actor",
                "actor_user_id does not name an actor declared in the loaded bundle.",
            )
        return actor

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path == "/":
                self._send_bytes(
                    HTTPStatus.OK,
                    INDEX_HTML.encode("utf-8"),
                    content_type="text/html; charset=utf-8",
                )
                return
            if path == "/healthz":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "status": "healthy",
                        "tenant_id": self.application_state.engine.tenant_id,
                    },
                )
                return
            if path == "/meta":
                with self.application_state.engine_lock:
                    meta = _public_meta(self.application_state.engine)
                self._send_json(HTTPStatus.OK, {"ok": True, "meta": meta})
                return
            raise RequestProblem(
                HTTPStatus.NOT_FOUND,
                "not_found",
                "The requested endpoint does not exist.",
            )
        except RequestProblem as problem:
            self._send_problem(problem)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            self._send_problem(
                RequestProblem(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "internal_error",
                    "The server could not complete the request.",
                )
            )

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path == "/query":
                self._handle_query()
                return
            if path == "/audit":
                self._handle_audit()
                return
            raise RequestProblem(
                HTTPStatus.NOT_FOUND,
                "not_found",
                "The requested endpoint does not exist.",
            )
        except RequestProblem as problem:
            self._send_problem(problem)
        except AuthorizationError as exc:
            code = getattr(exc, "code", None)
            self._send_problem(
                RequestProblem(
                    HTTPStatus.FORBIDDEN,
                    str(code) if code else "scope_mismatch",
                    "The selected declaration cannot complete this request.",
                )
            )
        except SchemaError:
            self._send_problem(
                RequestProblem(
                    HTTPStatus.BAD_REQUEST,
                    "schema_error",
                    "The request did not satisfy the Internal Brain schema.",
                )
            )
        except AuditError:
            self._send_problem(
                RequestProblem(
                    HTTPStatus.CONFLICT,
                    "audit_error",
                    "The audit chain could not be read or verified.",
                )
            )
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            self._send_problem(
                RequestProblem(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "internal_error",
                    "The server could not complete the request.",
                )
            )

    def _handle_query(self) -> None:
        payload = self._read_json_object()
        self._reject_unknown_fields(
            payload,
            frozenset({"actor_user_id", "question", "max_results", "document_ids"}),
        )
        actor = self._declared_actor(payload)
        question = payload.get("question")
        if not isinstance(question, str) or not question.strip():
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "question_required",
                "question must be a non-empty string.",
            )
        question = question.strip()
        if len(question) > MAX_QUESTION_CHARACTERS:
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "question_too_long",
                f"question must not exceed {MAX_QUESTION_CHARACTERS} characters.",
            )
        max_results = payload.get("max_results", 5)
        if (
            isinstance(max_results, bool)
            or not isinstance(max_results, int)
            or not 1 <= max_results <= MAX_RESULTS_LIMIT
        ):
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "invalid_max_results",
                f"max_results must be an integer from 1 to {MAX_RESULTS_LIMIT}.",
            )
        document_ids = payload.get("document_ids", [])
        if not isinstance(document_ids, list) or any(
            not isinstance(document_id, str) or not document_id.strip()
            for document_id in document_ids
        ):
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "invalid_document_ids",
                "document_ids must be an array of non-empty strings.",
            )
        normalized_ids = [document_id.strip() for document_id in document_ids]
        if len(normalized_ids) != len(set(normalized_ids)):
            raise RequestProblem(
                HTTPStatus.BAD_REQUEST,
                "duplicate_document_id",
                "document_ids must not contain duplicates.",
            )
        engine = self.application_state.engine
        query = {
            "schema": "internal-brain-query/v1",
            "tenant_id": engine.tenant_id,
            "actor_user_id": actor,
            "question": question,
            "max_results": max_results,
            "document_ids": normalized_ids,
        }
        with self.application_state.engine_lock:
            receipt = engine.query(query)
            context_packet = build_context_packet(receipt)
        self._send_json(HTTPStatus.OK, {
            "ok": True,
            "receipt": receipt,
            "context_packet": context_packet,
        })

    def _handle_audit(self) -> None:
        payload = self._read_json_object()
        self._reject_unknown_fields(payload, frozenset({"actor_user_id"}))
        actor = self._declared_actor(payload)
        engine = self.application_state.engine
        with self.application_state.engine_lock:
            events = engine.audit_events(
                tenant_id=engine.tenant_id,
                actor_user_id=actor,
            )
            verification = verify_audit(events)
        self._send_json(
            HTTPStatus.OK,
            {"ok": True, "events": events, "verification": verification},
        )


class InternalBrainHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _handler_for(state: ApplicationState) -> type[InternalBrainRequestHandler]:
    class BoundInternalBrainRequestHandler(InternalBrainRequestHandler):
        application_state = state

    return BoundInternalBrainRequestHandler


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve a local browser interface over an InternalBrain bundle."
    )
    parser.add_argument(
        "bundle_path",
        nargs="?",
        type=Path,
        help="Optional positional path to demo_bundle.json.",
    )
    parser.add_argument(
        "--bundle",
        dest="bundle_option",
        type=Path,
        help="Path to demo_bundle.json.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Listen address (default: {DEFAULT_HOST}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Listen port (default: {DEFAULT_PORT}).",
    )
    arguments = parser.parse_args(argv)
    if arguments.bundle_path is not None and arguments.bundle_option is not None:
        parser.error("provide the bundle either positionally or with --bundle, not both")
    arguments.bundle = (
        arguments.bundle_option or arguments.bundle_path or _default_bundle_path()
    )
    return arguments


def main(argv: list[str] | None = None) -> int:
    arguments = _parse_arguments(argv)
    if not 1 <= arguments.port <= 65535:
        print("error: --port must be between 1 and 65535", file=sys.stderr)
        return 2
    bundle_path = arguments.bundle.expanduser().resolve()
    try:
        bundle_text = bundle_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: could not read bundle: {exc}", file=sys.stderr)
        return 2
    try:
        engine = InternalBrain.from_json(bundle_text)
    except (SchemaError, ValueError) as exc:
        print(f"error: bundle validation failed: {exc}", file=sys.stderr)
        return 2
    state = ApplicationState(engine=engine, engine_lock=threading.RLock())
    try:
        server = InternalBrainHTTPServer(
            (arguments.host, arguments.port),
            _handler_for(state),
        )
    except OSError as exc:
        print(f"error: could not start server: {exc}", file=sys.stderr)
        return 2
    address, port = server.server_address[:2]
    print(f"Internal Brain Browser: http://{address}:{port}/")
    print(f"Bundle: {bundle_path}")
    print(
        "Identity note: declarations are selected by the operator; "
        "this server does not authenticate them."
    )
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
