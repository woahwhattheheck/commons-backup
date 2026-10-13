#!/usr/bin/env python3
"""host/jevchat_demo.py — local-only JEVCHAT browser demo.

Loopback chat surface for the external-autoregression experiment: the page
posts a prompt, the server runs host/jevchat.py's baseline loop and streams
each emitted symbol over SSE. The TypeSafe key stays server-side inside
jev.py's resolver — nothing secret reaches the browser.

  python3 host/jevchat_demo.py --port 8765
  # open http://127.0.0.1:8765/

Guards: binds 127.0.0.1 only (any other host raises); DOM renders generated
text via textContent, never HTML; no cloud deploy, no public endpoint, no
key in JS. Symbols are JSON-encoded per SSE frame — the wire is escaped by
construction.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
import jevchat  # noqa: E402

LOOPBACKS = {"127.0.0.1", "localhost", "::1"}

PAGE = """<!doctype html>
<meta charset="utf-8"><title>jevchat — external autoregression demo</title>
<style>
 body{font:14px/1.5 system-ui;margin:2em auto;max-width:52em}
 #out{white-space:pre-wrap;border:1px solid #999;padding:1em;min-height:8em}
 #in{width:100%;box-sizing:border-box} button{margin:.5em 0}
 #meta{color:#666;font-size:12px}
</style>
<h1>jevchat</h1>
<p id="meta">Jev chooses one symbol per API call. Local demo, loopback only.</p>
<textarea id="in" rows="3" placeholder="Say hello in one short sentence."></textarea>
<br><button id="go">generate</button>
<pre id="out"></pre><div id="stat"></div>
<script>
const out = document.getElementById('out');
const stat = document.getElementById('stat');
document.getElementById('go').onclick = () => {
  out.textContent = ''; stat.textContent = '';
  const p = encodeURIComponent(document.getElementById('in').value);
  const es = new EventSource('/stream?prompt=' + p);
  es.onmessage = ev => {                       // 'symbol' frames
    const d = JSON.parse(ev.data);
    out.textContent += d.symbol;               // textContent: never HTML
  };
  es.addEventListener('done', ev => {
    stat.textContent = ev.data; es.close();
  });
  es.addEventListener('error', ev => {
    stat.textContent = 'stream ended'; es.close();
  });
};
</script>
"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "jevchat-demo/1.0"

    def log_message(self, fmt, *a):  # quiet; diagnostics go nowhere public
        pass

    def _send(self, code, ctype, body):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE)
        elif parsed.path == "/stream":
            self._stream(parsed)
        else:
            self._send(404, "text/plain", "not found")

    def _stream(self, parsed):
        params = urllib.parse.parse_qs(parsed.query)
        prompt = (params.get("prompt") or [""])[0][:4096]
        max_chars = int((params.get("max_chars") or ["256"])[0])
        max_chars = max(1, min(max_chars, jevchat.MAX_CHARS_HARD))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def send(event, obj):
            payload = f"event: {event}\ndata: {json.dumps(obj)}\n\n"
            self.wfile.write(payload.encode("utf-8"))
            self.wfile.flush()

        def on_symbol(sym):
            try:
                send("message", {"symbol": sym})
            except (BrokenPipeError, ConnectionResetError):
                pass

        try:
            result = jevchat.generate(prompt, max_chars=max_chars,
                                      on_symbol=on_symbol)
            send("done", {"stop_reason": result["stop_reason"],
                          "chars": len(result["text"]),
                          "steps": result["steps"]})
        except Exception as err:  # typed JevError or unexpected — surface code
            send("done", {"stop_reason": str(err), "chars": 0, "steps": 0})
        self.close_connection = True


def serve(host="127.0.0.1", port=8765, dry=False):
    if host not in LOOPBACKS:
        raise ValueError("jevchat demo binds loopback only; refused " + str(host))
    if dry:
        return None
    httpd = ThreadingHTTPServer((host, port), _Handler)
    print(f"jevchat demo on http://{host}:{httpd.server_address[1]}/",
          file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="jevchat loopback demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    serve(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
