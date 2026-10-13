#!/usr/bin/env python3
"""host/sdc_os_ui.py — THE ORCHESTRATOR UI (Phase 4). Text field + Send + output area, all in the page.

Send routes the prompt to the orchestrator and DIES: POST /send fires `sdc_os_run.py` detached (which routes the request
through the grounded orchestrator — exact/verifiable -> a verified circuit on the SDC, else refuse — and deposits the
result to the safezone), then this endpoint returns immediately. It does NOT read the safezone: the output area is fed by
the SEPARATE checker (sdc_os_checker.py, 7905). Send and checker are entirely separate processes (owner 07-18).

  python host/sdc_os_ui.py     # http://127.0.0.1:7904/   (needs the checker running on 7905)
"""
import json, os, subprocess, sys, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8")
BUTTON = os.path.join(HERE, "sdc_os_button.py")         # PRESS START: routes the request into the SDC + fires power, exits
PORT = 7904
CHECKER_FEED = "http://127.0.0.1:7905/stream"           # the separate checker's feed (isolated, read-only)

PAGE = """<!doctype html><meta charset="utf-8"><title>SDC OS</title>
<body style="margin:0;background:#0A0D13;color:#E7EBF3;font-family:system-ui;padding:26px">
<div style="font-family:ui-monospace,monospace;font-size:13px;color:#FFB020">SDC OS &middot; grounded orchestrator &middot; output fed by the checker (7905)</div>
<pre id="o" style="white-space:pre-wrap;font-size:15px;line-height:1.55;margin:14px 0 20px;min-height:60px">waiting for the checker&hellip;</pre>
<div style="display:flex;gap:10px;max-width:820px">
<textarea id="box" placeholder="e.g.  9094 * 40496   &middot;   is 31537 &gt; 30968   (Enter to send)" rows="1"
 style="flex:1;background:#0a0d14;border:1px solid #232A38;color:#E7EBF3;font-family:system-ui;font-size:14px;padding:11px 13px;border-radius:11px;outline:none;resize:none"></textarea>
<button onclick="send()"
 style="cursor:pointer;background:#FFB020;color:#1a1204;border:none;font-family:ui-monospace,monospace;font-weight:700;font-size:14px;padding:12px 20px;border-radius:11px">Send</button></div>
<script>
function send(){var b=document.getElementById('box');var t=b.value.trim();if(!t)return;
 fetch('/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:t})});b.value='';}
document.getElementById('box').addEventListener('keydown',function(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}});
new EventSource('__FEED__').onmessage=function(e){document.getElementById('o').textContent=e.data;};
</script>
""".replace("__FEED__", CHECKER_FEED)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        b = PAGE.encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_POST(self):
        if self.path != "/send":
            self.send_response(404); self.end_headers(); return
        try:
            n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        prompt = str(body.get("prompt", ""))
        subprocess.Popen([sys.executable, BUTTON, prompt],                          # SEND: press start (routes + fires), dies
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.send_response(200); self.send_header("Content-Length", "0"); self.end_headers()


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"SDC OS UI -> http://127.0.0.1:{PORT}/  (text field + send fires the orchestrator; output fed by the checker on 7905)")
    if "--no-open" not in sys.argv:                          # the launcher opens the tab once (checker-first); don't double-open
        try: webbrowser.open(f"http://127.0.0.1:{PORT}/")
        except Exception: pass
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nstopped.")
