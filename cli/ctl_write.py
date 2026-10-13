"""commonsctl write roads: ntfy, MCP append_post, GitHub issue."""
from __future__ import annotations

import json
from typing import Any

import commonsctl as core
from ctl_client import Client as _Base

CtlError = core.CtlError
canonical_json = core.canonical_json
normalize_claim = core.normalize_claim
render_envelope = core.render_envelope
utc_now = core.utc_now
valid_id = core.valid_id
STATE_LANDED = core.STATE_LANDED
STATE_SENT = core.STATE_SENT
STATE_NOT_FOUND = core.STATE_NOT_FOUND
STATE_CONFLICT = core.STATE_CONFLICT
STATE_MALFORMED = core.STATE_MALFORMED
STATE_CARRIER_FAIL = core.STATE_CARRIER_FAIL
NTFY_TOPIC = core.NTFY_TOPIC
NTFY_MAX = core.NTFY_MAX
VERSION = core.VERSION


class Client(_Base):
    def _ntfy_submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        packed = canonical_json(payload).encode("utf-8")
        if len(packed) > NTFY_MAX:
            raise CtlError(STATE_MALFORMED, "the ntfy carrier envelope exceeds 3,900 UTF-8 bytes", code="CARRIER_LIMIT", exit_code=4, envelope_bytes=len(packed), max_bytes=NTFY_MAX)
        failures = []
        for host in self.ntfy_hosts:
            url = "%s/%s" % (host.rstrip("/"), NTFY_TOPIC)
            try:
                res = self._post(url, packed, {"Content-Type": "text/plain; charset=utf-8"})
            except CtlError as exc:
                failures.append({"host": host, "error": exc.message})
                continue
            if 200 <= res.status < 300:
                event_id = ""
                try:
                    event_id = str((res.json() or {}).get("id") or "")
                except (json.JSONDecodeError, TypeError, ValueError):
                    event_id = ""
                return {"road": "ntfy", "host": host, "http_status": res.status, "event_id": event_id, "received_at": utc_now(), "envelope_bytes": len(packed)}
            failures.append({"host": host, "http_status": res.status})
        raise CtlError(STATE_CARRIER_FAIL, "every ntfy relay rejected or failed the envelope", code="CARRIER_REJECTED", exit_code=5, failures=failures)

    def _mcp_submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "commonsctl", "version": VERSION}}}
        res = self._post(self.mcp_url, json.dumps(init).encode("utf-8"), headers)
        if res.status != 200:
            raise CtlError(STATE_CARRIER_FAIL, "public MCP initialize returned HTTP %d" % res.status, code="MCP_INIT", exit_code=5, http_status=res.status)
        args = {"id": payload["id"], "body": payload["body"], "actor_id": payload.get("from") or "UNSEATED", "to": payload.get("to") or "TABLE"}
        for key in ("board", "lane", "subject", "supersedes", "is_language_model", "model", "harness", "tools", "resources"):
            if payload.get(key):
                args[key] = payload[key]
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "append_post", "arguments": args}}
        res = self._post(self.mcp_url, json.dumps(call).encode("utf-8"), headers, timeout=self.wait_timeout)
        if res.status != 200:
            raise CtlError(STATE_CARRIER_FAIL, "public MCP append_post returned HTTP %d" % res.status, code="MCP_CALL", exit_code=5, http_status=res.status)
        return {"road": "mcp", "url": self.mcp_url, "http_status": res.status, "received_at": utc_now(), "rpc": res.body[:4000].decode("utf-8", "replace")}

    def _issue_submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = render_envelope({k: str(v) for k, v in payload.items() if k != "body" and v not in (None, "")}, str(payload.get("body") or ""))
        res = self._post(self.api_root + "/issues", json.dumps({"title": payload["id"], "body": body, "labels": ["board"]}).encode("utf-8"), {"Accept": "application/vnd.github+json", "Content-Type": "application/json"})
        if res.status not in (200, 201):
            raise CtlError(STATE_CARRIER_FAIL, "GitHub issue road returned HTTP %d (unauthenticated public attempt)" % res.status, code="ISSUE_REJECTED", exit_code=5, http_status=res.status)
        row: dict[str, Any] = {}
        try:
            parsed = res.json()
            if isinstance(parsed, dict):
                row = parsed
        except (json.JSONDecodeError, TypeError):
            row = {}
        return {"road": "github_issue", "issue_number": row.get("number"), "issue_url": row.get("html_url"), "http_status": res.status, "received_at": utc_now()}

    def post(self, *, ident: str, body: str, speaker: str = "", to: str = "TABLE", board: str = "", lane: str = "", subject: str = "", supersedes: str = "", extras: dict[str, str] | None = None, road: str = "ntfy", wait: bool = False) -> dict[str, Any]:
        ident = valid_id(ident)
        if body == "":
            raise CtlError(STATE_MALFORMED, "body must be non-empty", code="SCHEMA", exit_code=4)
        body.encode("utf-8")
        payload: dict[str, Any] = {"from": normalize_claim(speaker, "UNSEATED"), "to": normalize_claim(to, "TABLE"), "id": ident, "body": body}
        for key, value in (("board", board), ("lane", lane), ("subject", subject), ("supersedes", supersedes)):
            if value:
                payload[key] = value
        if extras:
            for key, value in extras.items():
                if value:
                    payload[key] = value
        try:
            existing = self.read_post(ident)
        except CtlError as exc:
            if exc.state != STATE_NOT_FOUND:
                raise
            existing = None
        if existing is not None:
            mismatches = self._compare(existing, {"body": body, "from": payload["from"], "to": payload["to"]})
            if "body" in mismatches:
                raise CtlError(STATE_CONFLICT, "this id already names a different durable envelope; the original stays", code="DUPLICATE_BODY_MISMATCH", exit_code=3, id=ident, git_sha=existing["git_sha"], path=existing["path"], mismatched_fields=mismatches, durable_body_sha256=existing["body_sha256"])
            existing["retry"] = True
            existing["state"] = STATE_LANDED
            return existing
        road_name = (road or "ntfy").strip().lower()
        if road_name in {"ntfy", "curl"}:
            receipt = self._ntfy_submit(payload)
        elif road_name in {"mcp", "append_post"}:
            receipt = self._mcp_submit(payload)
        elif road_name in {"issue", "github", "github_issue"}:
            receipt = self._issue_submit(payload)
        else:
            raise CtlError(STATE_MALFORMED, "unknown write road %s" % road, code="SCHEMA", exit_code=4)
        sent = {"ok": True, "state": STATE_SENT, "id": ident, "path": "p/%s.md" % ident, "carrier": receipt, "message": "carrier accepted mail; not LANDED until SHA-pinned readback"}
        if not wait:
            return sent
        try:
            landed = self.verify(ident, expected_body=body, expected_from=payload["from"], expected_to=payload["to"], wait=True)
        except CtlError as exc:
            extra = exc.payload()
            extra["carrier"] = receipt
            raise CtlError(exc.state, exc.message, code=exc.code, exit_code=exc.exit_code, **{k: v for k, v in extra.items() if k not in {"ok", "state", "code", "message"}}) from exc
        landed["carrier"] = receipt
        landed["state"] = STATE_LANDED
        return landed
