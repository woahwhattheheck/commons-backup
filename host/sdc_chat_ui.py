#!/usr/bin/env python3
"""host/sdc_chat_ui.py — THE UI. Text field + Send + output area. (owner 07-18)

Serves the page and the SEND endpoint (POST /send fires the send button — sdc_prompt_button.py — which routes the prompt
to the SDC and dies). It does NOT read the safezone: the output area is fed directly by the SEPARATE checker
(sdc_safezone_reader.py, 7903) over its own feed. The checker and the send are entirely separate; this UI just shows the
one and triggers the other.

  python host/sdc_chat_ui.py     # http://127.0.0.1:7906/   (needs the checker running on 7903)
"""
import json, os, subprocess, sys, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8")
BUTTON = os.path.join(HERE, "sdc_prompt_button.py")
STAGING = "C:/llm/sdc_out/chat_pending.json"
PORT = 7906
CHECKER_FEED = "http://127.0.0.1:7903/stream"           # the separate checker's feed (isolated, read-only)

PAGE = """<!doctype html><meta charset="utf-8"><title>SDC</title>
<body style="margin:0;background:#0A0D13;color:#E7EBF3;font-family:system-ui;padding:26px">
<div style="font-family:ui-monospace,monospace;font-size:13px;color:#FFB020">SDC &middot; output fed by the checker (7903)</div>
<pre id="o" style="white-space:pre-wrap;font-size:15px;line-height:1.55;margin:14px 0 20px;min-height:60px">waiting for the checker&hellip;</pre>
<div style="display:flex;gap:10px;max-width:820px">
<textarea id="box" placeholder="prompt&hellip; (Enter to send)" rows="1"
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
        with open(STAGING, "w", encoding="utf-8") as f:
            json.dump({"messages": [{"role": "user", "content": prompt}]}, f)
        subprocess.Popen([sys.executable, BUTTON, STAGING],                         # SEND: route prompt -> SDC, then die
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.send_response(200); self.send_header("Content-Length", "0"); self.end_headers()


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"SDC UI -> http://127.0.0.1:{PORT}/  (text field + send fires the button; output fed by the separate checker on 7903)")
    try: webbrowser.open(f"http://127.0.0.1:{PORT}/")
    except Exception: pass
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nstopped.")
