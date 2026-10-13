from __future__ import annotations

import argparse
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

from .current import reconcile_current


def render_dashboard(receipt: dict) -> str:
    status_classes = {
        "HUMAN_CLOSING_READY": "ready",
        "COUNTEROFFER_REVIEW": "decision",
        "CLARIFICATION_REQUIRED": "decision",
        "EVIDENCE_CONFLICT": "danger",
        "LATE_RESPONSE_REVIEW": "danger",
        "REISSUE_REQUIRED": "decision",
    }
    cards = []
    for item in receipt["series"]:
        cls = status_classes.get(item["status"], "routine")
        interrupt = "SURFACE TO HUMAN" if item["status"] in status_classes else "QUIET / ROUTINE"
        cards.append(f"""
        <article class='card {cls}'>
          <div class='interrupt'>{escape(interrupt)}</div>
          <h2>{escape(item['series_id'])}</h2>
          <div class='status'>{escape(item['status'])}</div>
          <p>{escape(item['reason'])}</p>
          <dl><dt>Counterparty</dt><dd>{escape(item['counterparty_id'])}</dd>
          <dt>Offer</dt><dd>{escape(item['currency'])} {item['amount_minor']/100:,.2f}</dd>
          <dt>Version</dt><dd>{item['offer_version']}</dd></dl>
        </article>""")
    authority = " · ".join(f"{k}=false" for k in receipt["authority"])
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Commercial Decision Relay</title>
<style>
body{{font:16px system-ui;margin:0;background:#0e1116;color:#e8eef7}}header{{padding:2rem 4vw;border-bottom:1px solid #29313d}}
main{{padding:2rem 4vw}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem}}
.card{{background:#151b23;border:1px solid #2c3542;border-radius:14px;padding:1rem}}.ready{{border-color:#66d9a8}}.decision{{border-color:#e8b86d}}.danger{{border-color:#f07b7b}}.routine{{opacity:.72}}
.status{{font-weight:700;margin:.5rem 0}}.interrupt{{font-size:.72rem;letter-spacing:.08em;opacity:.8}}dl{{display:grid;grid-template-columns:auto 1fr;gap:.25rem .75rem}}dd{{margin:0}}code{{word-break:break-all}}footer{{padding:2rem 4vw;color:#9aa9bc}}
</style></head><body><header><h1>Commercial Decision Relay</h1><p>Quietly processes routine commercial evidence. Interrupts humans only for real decisions.</p>
<p>Trusted evaluation instant: <strong>{escape(receipt['evaluated_at'])}</strong></p>
<p><strong>{receipt['summary']['decision_count']}</strong> decisions · <strong>{receipt['summary']['routine_count']}</strong> routine · <strong>{receipt['summary']['quarantine_count']}</strong> quarantined</p></header>
<main><div class='grid'>{''.join(cards)}</div><h3>Deterministic receipt</h3><code>{escape(receipt['receipt_sha256'])}</code></main>
<footer>Authority boundary: {escape(authority)}</footer></body></html>"""


def serve(batch_path: str, port: int, evaluated_at: str) -> None:
    batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    receipt = reconcile_current(batch, evaluated_at=evaluated_at)
    page = render_dashboard(receipt).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in {"/", "/index.html"}:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, fmt, *args):
            pass

    print(f"Decision Relay demo: http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", default="fixtures/demo-batch.json")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--evaluated-at",
        required=True,
        help="trusted current ISO-8601 UTC instant supplied out-of-band",
    )
    args = parser.parse_args(argv)
    serve(args.batch, args.port, args.evaluated_at)


if __name__ == "__main__":
    main()
