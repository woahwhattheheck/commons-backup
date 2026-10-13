from __future__ import annotations

import argparse
import html
import json
import secrets
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from studio import CreatorConfig, StudioError, StudioStore, canonical_json_bytes, load_config

MAX_BODY = 64_000
SUPPORTED_BIND_HOSTS = frozenset({"127.0.0.1", "localhost"})


def loopback_browser_authorities(bind_host: str, port: int) -> tuple[frozenset[str], frozenset[str]]:
    """Return exact browser Host/Origin values for the configured loopback listener.

    Host validation is deliberately lexical rather than DNS based: an attacker-controlled
    hostname that happens to resolve to loopback must never become an application origin.
    The stdlib server used here is IPv4-only, so IPv6 loopback is rejected rather than
    advertised as a runnable listener.
    """
    if bind_host not in SUPPORTED_BIND_HOSTS:
        raise StudioError("browser app supports IPv4 loopback only")
    if type(port) is not int or not (1 <= port <= 65535):
        raise StudioError("invalid browser port")

    if bind_host == "localhost":
        names = ("localhost", "127.0.0.1")
    else:
        names = ("127.0.0.1", "localhost")

    hosts = {f"{name}:{port}" for name in names}
    if port == 80:
        hosts.update(names)
    return frozenset(hosts), frozenset(f"http://{host}" for host in hosts)


def page(cfg: CreatorConfig, body: str, csrf: str) -> bytes:
    title = html.escape(cfg.app_name)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
body{{font:16px system-ui,sans-serif;max-width:1080px;margin:0 auto;padding:24px;background:#fafafa;color:#171717}}
nav{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}} a{{color:#0645ad}} .card{{background:white;border:1px solid #ddd;border-radius:12px;padding:18px;margin:12px 0}}
label{{display:block;margin:8px 0 3px}} input,select,textarea{{width:100%;max-width:680px;padding:8px;box-sizing:border-box}} button{{padding:9px 14px;margin-top:10px}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}} .muted{{color:#555}} .error{{background:#fff0f0;border:1px solid #d99;padding:12px}} code{{word-break:break-word}}
</style></head><body>
<header><h1>{title}</h1><p>{html.escape(cfg.promise)}</p><p class="muted">Built for {html.escape(cfg.audience_label)} · creator: {html.escape(cfg.creator_label)}</p></header>
<nav><a href="/">Planner</a><a href="/onboarding">Onboarding</a><a href="/pricing">Pricing</a><a href="/support">Support</a><a href="/export.json">Export JSON</a><a href="/export.csv">Export CSV</a></nav>
{body}<input type="hidden" id="csrf-token" value="{html.escape(csrf)}"></body></html>""".encode("utf-8")


def _v(form: dict[str, list[str]], key: str, default: str = "") -> str:
    values = form.get(key)
    return default if not values else values[-1]


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "CreatorNicheStudio/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    @property
    def store(self) -> StudioStore:
        return self.server.store  # type: ignore[attr-defined]

    @property
    def cfg(self) -> CreatorConfig:
        return self.store.config

    @property
    def csrf(self) -> str:
        return self.server.csrf  # type: ignore[attr-defined]

    @property
    def allowed_hosts(self) -> frozenset[str]:
        return self.server.allowed_hosts  # type: ignore[attr-defined]

    @property
    def allowed_origins(self) -> frozenset[str]:
        return self.server.allowed_origins  # type: ignore[attr-defined]

    def _send(self, code: int, content_type: str, data: bytes, *, disposition: str | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        if disposition:
            self.send_header("Content-Disposition", disposition)
        self.end_headers()
        self.wfile.write(data)

    def _plain_refusal(self, code: int, message: str) -> None:
        data = (message + "\n").encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(data)

    def _trusted_host(self) -> bool:
        values = self.headers.get_all("Host", [])
        return len(values) == 1 and values[0] in self.allowed_hosts

    def _trusted_origin(self) -> bool:
        values = self.headers.get_all("Origin", [])
        return len(values) == 1 and values[0] in self.allowed_origins

    def _html(self, body: str, code: int = 200) -> None:
        self._send(code, "text/html; charset=utf-8", page(self.cfg, body, self.csrf))

    def _error(self, message: str, code: int = 400) -> None:
        self._html(f'<div class="error"><strong>Could not complete that action.</strong><p>{html.escape(message)}</p><p><a href="/">Return to planner</a></p></div>', code)

    def _form(self) -> dict[str, list[str]]:
        if self.headers.get("Transfer-Encoding"):
            raise StudioError("Transfer-Encoding is not supported")
        raw_len = self.headers.get("Content-Length")
        if raw_len is None or not raw_len.isdigit():
            raise StudioError("Content-Length is required")
        length = int(raw_len)
        if length > MAX_BODY:
            raise StudioError("request body too large")
        raw = self.rfile.read(length)
        return urllib.parse.parse_qs(raw.decode("utf-8"), keep_blank_values=True, strict_parsing=False)

    def _check_csrf(self, form: dict[str, list[str]]) -> None:
        if not secrets.compare_digest(_v(form, "csrf"), self.csrf):
            raise StudioError("invalid form token")

    def do_GET(self) -> None:
        if not self._trusted_host():
            self._plain_refusal(HTTPStatus.MISDIRECTED_REQUEST, "untrusted browser host")
            return
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path == "/":
                self._planner()
            elif path == "/onboarding":
                self._onboarding()
            elif path == "/pricing":
                self._pricing()
            elif path == "/support":
                self._support()
            elif path == "/export.json":
                plan = self.store.compute_plan()
                self._send(200, "application/json; charset=utf-8", canonical_json_bytes(plan), disposition='attachment; filename="supply-plan.json"')
            elif path == "/export.csv":
                plan = self.store.compute_plan()
                self._send(200, "text/csv; charset=utf-8", self.store.export_csv(plan), disposition='attachment; filename="supply-plan.csv"')
            else:
                self._error("not found", 404)
        except StudioError as exc:
            self._error(str(exc), 400)

    def do_POST(self) -> None:
        if not self._trusted_host():
            self._plain_refusal(HTTPStatus.MISDIRECTED_REQUEST, "untrusted browser host")
            return
        if not self._trusted_origin():
            self._plain_refusal(HTTPStatus.FORBIDDEN, "untrusted browser origin")
            return
        path = urllib.parse.urlsplit(self.path).path
        try:
            form = self._form()
            self._check_csrf(form)
            if path == "/class/save":
                self.store.upsert_class(
                    _v(form, "class_id"), _v(form, "label"), int(_v(form, "rostered")), int(_v(form, "expected")), _v(form, "notes")
                )
                self.send_response(303); self.send_header("Location", "/"); self.end_headers()
            elif path == "/item/save":
                self.store.upsert_item(
                    _v(form, "item_id"), _v(form, "label"), _v(form, "mode"),
                    units_per_attendee=int(_v(form, "units_per_attendee", "0") or "0"),
                    units_per_class=int(_v(form, "units_per_class", "0") or "0"),
                    program_units=int(_v(form, "program_units", "0") or "0"),
                    package_size=int(_v(form, "package_size", "1") or "1"), notes=_v(form, "notes"),
                )
                self.send_response(303); self.send_header("Location", "/"); self.end_headers()
            elif path == "/plan/save":
                self.store.save_plan(_v(form, "plan_id"))
                self.send_response(303); self.send_header("Location", "/"); self.end_headers()
            elif path == "/support/packet":
                packet = self.store.create_support_packet(_v(form, "topic"), _v(form, "details"))
                self._send(200, "application/json; charset=utf-8", packet, disposition='attachment; filename="support-request.json"')
            else:
                self._error("not found", 404)
        except (StudioError, ValueError) as exc:
            self._error(str(exc), 400)

    def _onboarding(self) -> None:
        b = f"""<div class="card"><h2>Start in three steps</h2>
<ol><li>Add each class with both <strong>rostered</strong> and <strong>expected</strong> attendance.</li>
<li>Add supplies and choose whether each is a per-attendee consumable, shared per class, or shared across the whole program.</li>
<li>Generate/export the plan. Shared tools are never multiplied by attendance.</li></ol>
<p>This first niche workflow exists because real ceramics-class planning has different roster and show-up counts, and many tools are reusable rather than one-per-student.</p></div>
<div class="card"><h2>Limits in this build</h2><pre>{html.escape(json.dumps(dict(self.cfg.limits), indent=2))}</pre></div>"""
        self._html(b)

    def _pricing(self) -> None:
        price = self.cfg.mvp_sprint_price_cents / 100
        self._html(f"""<div class="card"><h2>Creator MVP Sprint</h2><p><strong>${price:,.2f} fixed scoped MVP sprint.</strong></p>
<p>The sprint includes creator brief/configuration, one audience-specific workflow, onboarding, usage limits, support handoff, runnable source, and launch assets.</p>
<p>This page is the configured offer; it does not process payment or imply a sale.</p></div>""")

    def _support(self) -> None:
        self._html(f"""<div class="card"><h2>Support handoff</h2><p>Configured route: <code>{html.escape(self.cfg.support_route)}</code></p>
<p>The app does not send messages. It creates a support packet you can inspect and send yourself.</p>
<form method="post" action="/support/packet"><input type="hidden" name="csrf" value="{html.escape(self.csrf)}">
<label>Topic<input name="topic" required maxlength="120"></label><label>Details<textarea name="details" required maxlength="1200"></textarea></label>
<button>Create support packet</button></form></div>""")

    def _planner(self) -> None:
        snap = self.store.snapshot()
        classes = "".join(
            f"<tr><td>{html.escape(c['class_id'])}</td><td>{html.escape(c['label'])}</td><td>{c['rostered']}</td><td>{c['expected']}</td><td>{html.escape(c['notes'])}</td></tr>"
            for c in snap["classes"]
        ) or '<tr><td colspan="5" class="muted">No classes yet.</td></tr>'
        items = "".join(
            f"<tr><td>{html.escape(i['item_id'])}</td><td>{html.escape(i['label'])}</td><td>{html.escape(i['mode'])}</td><td>{i['units_per_attendee'] or i['units_per_class'] or i['program_units']}</td><td>{i['package_size']}</td></tr>"
            for i in snap["items"]
        ) or '<tr><td colspan="5" class="muted">No supply items yet.</td></tr>'
        try:
            plan = self.store.compute_plan()
            rows = "".join(
                f"<tr><td>{html.escape(r['label'])}</td><td>{html.escape(r['mode'])}</td><td>{r['needed_units']}</td><td>{r['packages_to_prepare']}</td><td>{html.escape(r['basis'])}</td></tr>"
                for r in plan["supply_plan"]
            )
            plan_html = f"""<div class="card"><h2>Current supply plan</h2><p>Expected attendance {plan['summary']['expected_total']} vs rostered {plan['summary']['rostered_total']}.</p>
<table><tr><th>Supply</th><th>Mode</th><th>Units</th><th>Packages</th><th>Basis</th></tr>{rows}</table>
<p><a href="/export.json">JSON export</a> · <a href="/export.csv">CSV export</a></p>
<form method="post" action="/plan/save"><input type="hidden" name="csrf" value="{html.escape(self.csrf)}"><label>Save as plan ID<input name="plan_id" required pattern="[a-z0-9_-]+"></label><button>Save immutable plan snapshot</button></form></div>"""
        except StudioError as exc:
            plan_html = f'<div class="card"><h2>Current supply plan</h2><p class="muted">{html.escape(str(exc))}</p></div>'
        b = f"""
<div class="card"><h2>Classes</h2><table><tr><th>ID</th><th>Label</th><th>Rostered</th><th>Expected</th><th>Notes</th></tr>{classes}</table>
<form method="post" action="/class/save"><input type="hidden" name="csrf" value="{html.escape(self.csrf)}">
<label>Class ID<input name="class_id" required pattern="[a-z0-9_-]+"></label><label>Label<input name="label" required></label>
<label>Rostered<input name="rostered" type="number" min="0" max="10000" required></label><label>Expected attendance<input name="expected" type="number" min="0" max="10000" required></label>
<label>Notes<textarea name="notes"></textarea></label><button>Add/update class</button></form></div>
<div class="card"><h2>Supplies</h2><table><tr><th>ID</th><th>Label</th><th>Mode</th><th>Units basis</th><th>Package size</th></tr>{items}</table>
<form method="post" action="/item/save"><input type="hidden" name="csrf" value="{html.escape(self.csrf)}">
<label>Item ID<input name="item_id" required pattern="[a-z0-9_-]+"></label><label>Label<input name="label" required></label>
<label>Mode<select name="mode"><option>per_attendee_consumable</option><option>per_class_shared</option><option>program_shared</option></select></label>
<label>Units per attendee<input name="units_per_attendee" type="number" min="0" value="0"></label><label>Units per class<input name="units_per_class" type="number" min="0" value="0"></label>
<label>Program units<input name="program_units" type="number" min="0" value="0"></label><label>Package size<input name="package_size" type="number" min="1" value="1"></label>
<label>Notes<textarea name="notes"></textarea></label><button>Add/update supply</button></form></div>{plan_html}"""
        self._html(b)


def serve(config_path: str, db_path: str, host: str = "127.0.0.1", port: int = 8765) -> None:
    cfg, cfg_sha = load_config(config_path)
    store = StudioStore(db_path, cfg, cfg_sha)
    if host not in SUPPORTED_BIND_HOSTS:
        store.close()
        raise StudioError("browser app supports IPv4 loopback only")
    server = ThreadingHTTPServer((host, port), StudioHandler)
    actual_port = int(server.server_address[1])
    server.allowed_hosts, server.allowed_origins = loopback_browser_authorities(host, actual_port)  # type: ignore[attr-defined]
    server.store = store  # type: ignore[attr-defined]
    server.csrf = secrets.token_urlsafe(24)  # type: ignore[attr-defined]
    try:
        server.serve_forever()
    finally:
        store.close()
        server.server_close()


def main() -> None:
    p = argparse.ArgumentParser(description="Creator-backed niche app studio — local browser product")
    p.add_argument("--config", required=True)
    p.add_argument("--db", default="creator-app.sqlite3")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    serve(args.config, args.db, args.host, args.port)


if __name__ == "__main__":
    main()
