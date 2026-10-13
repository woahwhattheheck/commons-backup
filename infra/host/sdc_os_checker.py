#!/usr/bin/env python3
"""host/sdc_os_checker.py — the RESIDENT orchestrator checker (Phase 4). A completely separate process with ONE job:
read the orchestrator's safezone and push whatever the SDC deposited there to the screen. It never touches the running
SDC, never routes, never computes — it reads the safezone only and feeds the UI (owner 07-18; FINALREADME §3/§12).

Same no-hammer discipline as the forward-pass checker: push-on-change + a slow keepalive that drops dead connections, so
it never pings the network in a tight loop.

  python host/sdc_os_checker.py     # http://127.0.0.1:7905/   (resident feed for the orchestrator UI)
"""
import struct, sys, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.stdout.reconfigure(encoding="utf-8")
SAFEZONE = "C:/llm/sdc_out/os_safezone.bin"            # the orchestrator's external read-out window (RAW output bits)
PORT = 7905
SYM = {1: "*", 2: "+", 3: "-", 4: ">"}                 # orchestrator opcode -> display symbol (host renders raw bits)


def read_output():
    """read the SDC's RAW output window and RENDER it for display (host reads raw bits, never writes them — §5.8)."""
    try:
        with open(SAFEZONE, "rb") as fh: raw = fh.read()
    except OSError:
        return ""
    if len(raw) < 19: return ""
    status, grounded, opcode, a, b, result = struct.unpack_from("<BBBIIQ", raw)
    if status != 1: return ""
    if not grounded:
        return "→ REFUSED. no verified circuit grounds this request — not fabricated (GROUND: unknown ⇔ not provable)."
    sym = SYM.get(opcode, "?")
    if opcode == 4:                                     # GT -> a boolean
        return f"is {a} > {b}  =  {bool(result)}   [grounded on the SDC by the baked gate circuit]"
    if opcode == 3 and result >= (1 << 63):            # SUB -> render two's-complement 64-bit as signed
        result -= (1 << 64)
    return f"{a} {sym} {b}  =  {result}   [grounded on the SDC by the baked gate circuit 'sdc_os_circuit']"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")     # the separate UI page consumes this feed
            self.end_headers()
            last = None; last_beat = time.time()
            while True:
                out = read_output()                          # read the safezone
                try:
                    if out != last:                          # push each NEW output (nothing filtered)
                        msg = "".join(f"data: {ln}\n" for ln in out.split("\n")) + "\n"
                        self.wfile.write(msg.encode("utf-8")); self.wfile.flush(); last = out
                    elif time.time() - last_beat > 10:       # slow keepalive: drops DEAD connections, never hammers
                        self.wfile.write(b": beat\n\n"); self.wfile.flush(); last_beat = time.time()
                except (BrokenPipeError, ConnectionError, OSError):
                    return                                   # dead connection -> exit its loop (no pile-up)
                time.sleep(0.5)
        else:
            b = b"<!doctype html><meta charset=utf-8><title>orch feed</title><pre id=o>waiting</pre>" \
                b"<script>new EventSource('/stream').onmessage=e=>o.textContent=e.data</script>"
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"orchestrator checker -> http://127.0.0.1:{PORT}/  (resident; reads the safezone only, feeds the UI; nothing else)")
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nstopped.")
