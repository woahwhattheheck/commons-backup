from __future__ import annotations

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

from workspace import FieldServiceWorkspace, WorkspaceError

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _one(form: Mapping[str, list[str]], name: str, *, max_len: int = 512) -> str:
    values = form.get(name)
    if values is None or len(values) != 1:
        raise WorkspaceError(f"form field {name} is required exactly once")
    value = values[0]
    if not value or value != value.strip() or len(value) > max_len:
        raise WorkspaceError(f"form field {name} is invalid")
    return value


def _money(cents: int, currency: str) -> str:
    return f"{currency} {cents // 100:,}.{cents % 100:02d}"


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _page(title: str, body: str) -> bytes:
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_escape(title)}</title>
<style>
body{{font:16px system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;color:#171717}}
.card{{border:1px solid #ddd;border-radius:12px;padding:1rem;margin:1rem 0}} table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:.45rem;border-bottom:1px solid #eee}} button{{padding:.6rem 1rem;margin:.2rem}}
.ok{{background:#eefbf0}} .warn{{background:#fff7df}} code{{overflow-wrap:anywhere}}</style></head><body>
<h1>{_escape(title)}</h1>{body}
<footer><p><small>Local customer workspace. No payment, invoice send, or external messaging occurs here.</small></p></footer>
</body></html>"""
    return doc.encode("utf-8")


def _hidden(name: str, value: str) -> str:
    return f'<input type="hidden" name="{_escape(name)}" value="{_escape(value)}">'


def _render_quote(snapshot: dict[str, Any], token: str) -> bytes:
    quote_id = snapshot["quote_id"]
    currency = snapshot["currency"]
    rows = "".join(
        f"<tr><td>{_escape(item['description'])}</td><td>{item['quantity']}</td><td>{_escape(_money(item['unit_cents'], currency))}</td><td>{_escape(_money(item['total_cents'], currency))}</td></tr>"
        for item in snapshot["items"]
    )
    body = (
        f'<section class="card"><p><strong>Quote:</strong> <code>{_escape(quote_id)}</code></p>'
        f'<p><strong>Status:</strong> {_escape(snapshot["state"])}</p>'
        f'<table><thead><tr><th>Scope</th><th>Qty</th><th>Unit</th><th>Total</th></tr></thead><tbody>{rows}</tbody></table>'
        f'<p><strong>Base total:</strong> {_escape(_money(snapshot["total_cents"], currency))}</p>'
        f'<p><small>Scope fingerprint: <code>{_escape(snapshot["quote_digest"])}</code></small></p></section>'
    )
    if snapshot["state"] == "OPEN":
        body += '<section class="card"><h2>Quote decision</h2><form method="post" action="/customer/quote-decision">'
        body += _hidden("quote_id", quote_id) + _hidden("token", token) + _hidden("expected_quote_digest", snapshot["quote_digest"])
        body += '<label>Decision time (UTC) <input name="decided_at" required placeholder="2026-09-13T15:00:00Z"></label><br>'
        body += '<label>Request key <input name="request_key" required placeholder="customer-approval-1"></label><br>'
        body += '<button name="decision" value="APPROVE">Approve quote</button><button name="decision" value="DECLINE">Decline</button></form></section>'
    if snapshot["job"]:
        body += f'<section class="card"><h2>Job</h2><p><code>{_escape(snapshot["job"]["job_id"])}</code> — {_escape(snapshot["job"]["state"])}</p></section>'
    if snapshot["changes"]:
        body += '<section class="card"><h2>Change orders</h2>'
        for change in snapshot["changes"]:
            change_rows = "".join(
                f"<tr><td>{_escape(item['description'])}</td><td>{item['quantity']}</td><td>{_escape(_money(item['unit_cents'], currency))}</td><td>{_escape(_money(item['total_cents'], currency))}</td></tr>"
                for item in change["items"]
            )
            body += (
                f'<div><p><strong>{_escape(change["change_id"])}</strong> — {_escape(change["state"])} — {_escape(_money(change["total_cents"], currency))}</p>'
                f'<table><thead><tr><th>Change scope</th><th>Qty</th><th>Unit</th><th>Total</th></tr></thead><tbody>{change_rows}</tbody></table>'
                f'<p><small>Change fingerprint: <code>{_escape(change["change_digest"])}</code></small></p>'
            )
            if change["state"] == "PENDING" and snapshot["job"]:
                body += '<form method="post" action="/customer/change-decision">'
                body += _hidden("job_id", snapshot["job"]["job_id"]) + _hidden("change_id", change["change_id"]) + _hidden("token", token) + _hidden("expected_change_digest", change["change_digest"])
                body += '<label>Decision time (UTC) <input name="decided_at" required placeholder="2026-09-13T16:00:00Z"></label> '
                body += '<label>Request key <input name="request_key" required></label> '
                body += '<button name="decision" value="APPROVE">Approve change</button><button name="decision" value="DECLINE">Decline</button></form>'
            body += "</div>"
        body += "</section>"
    return _page("Field Service Customer Workspace", body)


def handler_for(workspace: FieldServiceWorkspace):
    class PortalHandler(BaseHTTPRequestHandler):
        server_version = "HiveFieldServicePortal/1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            # Deliberately suppress standard request logging so customer capability
            # values from POST bodies are never accidentally recorded by this app.
            return

        def _security_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")

        def _respond(self, status: int, body: bytes, content_type: str = "text/html; charset=utf-8") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)

        def _loopback_request(self) -> bool:
            host_header = self.headers.get("Host", "")
            try:
                host = (urlparse("http://" + host_header).hostname or "").lower()
            except ValueError:
                host = ""
            if host not in LOOPBACK_HOSTS:
                return False
            origin = self.headers.get("Origin")
            if origin:
                parsed = urlparse(origin)
                if parsed.scheme != "http" or (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
                    return False
            return True

        def _form(self) -> dict[str, list[str]]:
            if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                raise WorkspaceError("form content type required")
            raw_len = self.headers.get("Content-Length")
            if raw_len is None or not raw_len.isdigit():
                raise WorkspaceError("bounded Content-Length required")
            length = int(raw_len)
            if not 0 <= length <= 8192:
                raise WorkspaceError("request body too large")
            raw = self.rfile.read(length)
            try:
                text = raw.decode("utf-8", "strict")
            except UnicodeDecodeError as exc:
                raise WorkspaceError("form must be UTF-8") from exc
            return parse_qs(text, keep_blank_values=True, strict_parsing=True, max_num_fields=20)

        def do_GET(self) -> None:  # noqa: N802
            if not self._loopback_request():
                self._respond(403, _page("Denied", "<p>Loopback requests only.</p>"))
                return
            path = urlparse(self.path).path
            if path == "/health":
                body = json.dumps({"ok": True, "external_send_authorized": False, "payment_authorized": False}, sort_keys=True).encode()
                self._respond(200, body, "application/json; charset=utf-8")
                return
            if path == "/":
                body = _page(
                    "Field Service Customer Workspace",
                    '<section class="card"><h2>Open your quote</h2><form method="post" action="/customer/view">'
                    '<label>Quote reference <input name="quote_id" required></label><br>'
                    '<label>Customer access token <input name="token" type="password" required></label><br>'
                    '<button>Open quote</button></form></section>',
                )
                self._respond(200, body)
                return
            self._respond(404, _page("Not found", "<p>Not found.</p>"))

        def do_POST(self) -> None:  # noqa: N802
            if not self._loopback_request():
                self._respond(403, _page("Denied", "<p>Loopback requests only.</p>"))
                return
            try:
                form = self._form()
                path = urlparse(self.path).path
                if path == "/customer/view":
                    quote_id = _one(form, "quote_id", max_len=128)
                    token = _one(form, "token", max_len=256)
                    snapshot = workspace.customer_quote(quote_id=quote_id, customer_token=token)
                    self._respond(200, _render_quote(snapshot, token))
                    return
                if path == "/customer/quote-decision":
                    quote_id = _one(form, "quote_id", max_len=128)
                    token = _one(form, "token", max_len=256)
                    workspace.customer_decide_quote(
                        quote_id=quote_id,
                        customer_token=token,
                        expected_quote_digest=_one(form, "expected_quote_digest", max_len=64),
                        decision=_one(form, "decision", max_len=16),
                        decided_at=_one(form, "decided_at", max_len=20),
                        request_key=_one(form, "request_key", max_len=128),
                    )
                    snapshot = workspace.customer_quote(quote_id=quote_id, customer_token=token)
                    self._respond(200, _render_quote(snapshot, token))
                    return
                if path == "/customer/change-decision":
                    job_id = _one(form, "job_id", max_len=128)
                    change_id = _one(form, "change_id", max_len=128)
                    token = _one(form, "token", max_len=256)
                    workspace.customer_decide_change(
                        job_id=job_id,
                        change_id=change_id,
                        customer_token=token,
                        expected_change_digest=_one(form, "expected_change_digest", max_len=64),
                        decision=_one(form, "decision", max_len=16),
                        decided_at=_one(form, "decided_at", max_len=20),
                        request_key=_one(form, "request_key", max_len=128),
                    )
                    with workspace._conn() as conn:
                        quote_id = conn.execute("SELECT quote_id FROM jobs WHERE job_id=?", (job_id,)).fetchone()
                    if quote_id is None:
                        raise WorkspaceError("job not found")
                    snapshot = workspace.customer_quote(quote_id=quote_id["quote_id"], customer_token=token)
                    self._respond(200, _render_quote(snapshot, token))
                    return
                self._respond(404, _page("Not found", "<p>Not found.</p>"))
            except WorkspaceError as exc:
                self._respond(409, _page("Request not accepted", f"<p>{_escape(exc)}</p>"))
            except (ValueError, UnicodeError):
                self._respond(400, _page("Bad request", "<p>Malformed request.</p>"))

    return PortalHandler


def make_server(workspace: FieldServiceWorkspace, host: str = "127.0.0.1", port: int = 8086) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "::1"}:
        raise WorkspaceError("portal may bind only to an explicit loopback address")
    return ThreadingHTTPServer((host, port), handler_for(workspace))


def main() -> int:
    parser = argparse.ArgumentParser(description="Loopback-only customer quote/change approval portal")
    parser.add_argument("--db", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8086)
    args = parser.parse_args()
    workspace = FieldServiceWorkspace(args.db)
    server = make_server(workspace, args.host, args.port)
    print(f"field-service portal listening on http://{args.host}:{server.server_port} (loopback only)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
