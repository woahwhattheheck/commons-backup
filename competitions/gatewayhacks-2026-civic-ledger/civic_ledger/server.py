from __future__ import annotations

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .core import ContractError, _strict_json_loads


def _load(path: Path) -> dict:
    obj = _strict_json_loads(path.read_text("utf-8"))
    if not isinstance(obj, dict) or "items" not in obj or "meeting_id" not in obj:
        raise ContractError("ledger.json is not a compiled ledger")
    return obj


def _matches(item: dict, q: str, state: str) -> bool:
    if state and item.get("state") != state:
        return False
    if not q:
        return True
    hay = " ".join(str(item.get(k) or "") for k in ("item_id", "title", "decision", "owner", "deadline", "action", "state")).casefold()
    return q.casefold() in hay


def _page(data: dict, q: str, state: str) -> bytes:
    items = [x for x in data["items"] if _matches(x, q, state)]
    states = sorted({x["state"] for x in data["items"]})
    rows = []
    for item in items:
        ev = item["title_evidence"]
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(item['item_id'])}</strong><br>{html.escape(item['title'])}</td>"
            f"<td>{html.escape(item['state'])}</td>"
            f"<td>{html.escape(item.get('decision') or '—')}</td>"
            f"<td>{html.escape(item.get('owner') or '—')}</td>"
            f"<td>{html.escape(item.get('deadline') or '—')}</td>"
            f"<td>{html.escape(item.get('action') or '—')}</td>"
            f"<td><a rel='noreferrer' href='{html.escape(ev['source_url'], quote=True)}'>{html.escape(ev['doc_id'])}:{ev['line']}</a></td>"
            "</tr>"
        )
    options = ["<option value=''>All states</option>"] + [f"<option {'selected' if s == state else ''} value='{html.escape(s, quote=True)}'>{html.escape(s)}</option>" for s in states]
    body = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Civic Action Ledger</title><style>
body{{font:16px system-ui,sans-serif;margin:0;background:#f8f8f6;color:#171717}}main{{max-width:1200px;margin:auto;padding:2rem}}.hero{{background:white;border:1px solid #ddd;border-radius:16px;padding:1.4rem;margin-bottom:1rem}}form{{display:flex;gap:.6rem;flex-wrap:wrap}}input,select,button{{font:inherit;padding:.65rem;border:1px solid #999;border-radius:8px}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{text-align:left;vertical-align:top;padding:.7rem;border-bottom:1px solid #ddd}}th{{position:sticky;top:0;background:#eee}}@media(max-width:850px){{table,thead,tbody,tr,td,th{{display:block}}thead{{display:none}}tr{{border:1px solid #ddd;margin:.8rem 0;border-radius:10px}}}} a{{color:#174ea6}}code{{word-break:break-all}}
</style></head><body><main><section class='hero'><h1>Civic Action Ledger</h1><p><strong>{html.escape(data['meeting_id'])}</strong> · source status {html.escape(data['freshness'])} · {len(data['items'])} tracked items.</p><p>Only source-backed facts are shown. Conflicts and missing decisions remain visible rather than inferred.</p><form method='get'><label>Search <input name='q' value='{html.escape(q, quote=True)}'></label><label>State <select name='state'>{''.join(options)}</select></label><button>Filter</button></form></section><table><thead><tr><th>Item</th><th>State</th><th>Decision</th><th>Owner</th><th>Deadline</th><th>Action</th><th>Evidence</th></tr></thead><tbody>{''.join(rows)}</tbody></table><p><a href='/api/ledger'>Canonical JSON</a> · <a href='/api/search?q={html.escape(q, quote=True)}&state={html.escape(state, quote=True)}'>Filtered JSON</a></p></main></body></html>"""
    return body.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    ledger_path: Path

    def _json(self, status: int, obj: object) -> None:
        raw = (json.dumps(obj, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        try:
            data = _load(self.ledger_path)
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query, keep_blank_values=True)
            q = qs.get("q", [""])[0][:200]
            state = qs.get("state", [""])[0][:80]
            if parsed.path == "/api/ledger":
                return self._json(200, data)
            if parsed.path == "/api/search":
                items = [x for x in data["items"] if _matches(x, q, state)]
                return self._json(200, {"meeting_id": data["meeting_id"], "query": q, "state": state, "count": len(items), "items": items})
            if parsed.path != "/":
                return self._json(404, {"error": "not found"})
            raw = _page(data, q, state)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(raw)
        except Exception as exc:
            self._json(500, {"error": type(exc).__name__})

    def log_message(self, fmt: str, *args: object) -> None:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        parser.error("server is intentionally loopback-only")
    handler = type("LedgerHandler", (Handler,), {"ledger_path": Path(args.ledger)})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Civic Action Ledger: http://{args.host}:{args.port}/")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
