#!/usr/bin/env python3
"""Component implementation and operation."""
import http.server, json, os, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "C:/llm/sdc_sandbox")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

import devour

PORT = 7867

PAGE = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>The Field</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Consolas','Courier New',monospace;background:#0b0f14;color:#d7e3ee;
     display:flex;flex-direction:column;align-items:center;min-height:100vh;padding:32px 16px}
h1{color:#54d6a0;font-size:28px;margin-bottom:4px}
.sub{color:#6b7f92;font-size:12px;margin-bottom:24px}
textarea{width:100%;max-width:720px;height:200px;background:#111820;color:#d7e3ee;border:1px solid #1e2a38;
         font-family:inherit;font-size:14px;padding:12px;resize:vertical;border-radius:4px}
textarea:focus{outline:none;border-color:#54d6a0}
.row{display:flex;gap:10px;margin-top:12px;width:100%;max-width:720px}
button{padding:10px 24px;font-family:inherit;font-size:14px;font-weight:bold;border:none;
       border-radius:4px;cursor:pointer}
#devour{background:#54d6a0;color:#04150e;flex:1}
#devour:hover{background:#6de8b4}
#undo{background:#1e2a38;color:#d7e3ee}
#undo:hover{background:#2a3a4e}
#log{background:#1e2a38;color:#d7e3ee}
#log:hover{background:#2a3a4e}
#out{width:100%;max-width:720px;margin-top:16px;padding:12px;background:#070a0e;
     border:1px solid #1e2a38;border-radius:4px;font-size:13px;white-space:pre-wrap;
     min-height:60px;color:#6b7f92;overflow-x:auto}
.ok{color:#54d6a0}.err{color:#ef6b6b}
</style></head><body>
<h1>THE FIELD</h1>
<div class="sub">paste source &middot; type text &middot; enter a file path &mdash; Devour eats it into Titan's weights</div>
<textarea id="src" placeholder="paste code, text, or a file path here"></textarea>
<div class="row">
<button id="devour" onclick="go()">DEVOUR</button>
<button id="undo" onclick="undo()">UNDO</button>
<button id="log" onclick="log()">LOG</button>
</div>
<div id="out">ready. every edit is reversible via the genome.</div>
<script>
async function post(path, body) {
  const o = document.getElementById('out');
  o.textContent = 'working...';
  try {
    const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    const j = await r.json();
    o.innerHTML = '';
    if (j.error) { o.className = 'err'; o.textContent = 'ERROR: ' + j.error; }
    else { o.className = 'ok'; o.textContent = JSON.stringify(j, null, 2); }
  } catch(e) { o.className = 'err'; o.textContent = 'request failed: ' + e; }
}
function go() { post('/devour', {source: document.getElementById('src').value}); }
function undo() { post('/undo', {}); }
function log() { post('/log', {}); }
</script>
</body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE.encode())

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(ln)) if ln else {}
        if self.path == "/devour":
            result = devour.devour(body.get("source", ""))
        elif self.path == "/undo":
            result = devour.undevour()
        elif self.path == "/log":
            result = devour.devour_log()
        else:
            result = {"error": "unknown path"}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result, default=str).encode())

    def log_message(self, fmt, *args):
        pass


def main():
    print("THE FIELD — Devour interface")
    print("  http://127.0.0.1:%d" % PORT)
    print("  paste source, text, or a file path. every edit is reversible.")
    httpd = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
