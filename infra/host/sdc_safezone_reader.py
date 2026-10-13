#!/usr/bin/env python3
"""host/sdc_safezone_reader.py — the RESIDENT safezone checker. Reads the safezone and pushes ANY output to the screen.
Nothing more, nothing less. (owner 07-18)

  python host/sdc_safezone_reader.py     # http://127.0.0.1:7903/
"""
import struct, sys, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.stdout.reconfigure(encoding="utf-8")
SAFEZONE = "C:/llm/sdc_out/safezone.bin"                 # the SDC's external read-out window (raw output bits)
OPS = ["ADD", "SUB", "MUL", "SILU", "EXP", "RSQRT", "GT", "MOV"]
PORT = 7903

PAGE = """<!doctype html><meta charset="utf-8"><title>SDC output</title>
<body style="margin:0;background:#0A0D13;color:#E7EBF3;font-family:system-ui;padding:26px">
<pre id="o" style="white-space:pre-wrap;font-size:15px;line-height:1.55">waiting&hellip;</pre>
<script>new EventSource('/stream').onmessage=function(e){document.getElementById('o').textContent=e.data;};</script>
"""


def read_output():
    try: raw = open(SAFEZONE, "rb").read()                # read the SDC's raw output window
    except OSError: return ""
    if len(raw) < 8: return ""
    status, op, A, B, result = struct.unpack_from("<BBHHH", raw)   # decode the circuit's output bits for display
    return f"{OPS[op & 7]}({A}, {B}) = {result}" if status == 1 else ""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")     # so the separate UI page can consume the feed
            self.end_headers()
            last = None; last_beat = time.time()
            while True:
                out = read_output()                          # read the safezone
                try:
                    if out != last:                          # push each NEW output (every output still surfaces — NOT filtering)
                        msg = "".join(f"data: {ln}\n" for ln in out.split("\n")) + "\n"
                        self.wfile.write(msg.encode("utf-8")); self.wfile.flush(); last = out
                    elif time.time() - last_beat > 10:       # slow keepalive: drops DEAD connections, never hammers the network
                        self.wfile.write(b": beat\n\n"); self.wfile.flush(); last_beat = time.time()
                except (BrokenPipeError, ConnectionError, OSError):
                    return                                   # dead connection -> exit its loop (no lingering ping, no pile-up)
                time.sleep(0.5)
        else:
            b = PAGE.encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"safezone checker -> http://127.0.0.1:{PORT}/  (resident; pushes ANY safezone output to the screen; nothing else)")
    try: webbrowser.open(f"http://127.0.0.1:{PORT}/")
    except Exception: pass
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nstopped.")
