#!/usr/bin/env python3
"""host/titan_lab.py — TITAN TEST BENCH: click a button, run a test, watch it live (owner 07-14, "make me a button").

A tiny self-contained server (stdlib only) that serves a page with buttons for the Titan tests, runs the chosen test as
a subprocess, and streams its output back live. So the owner runs the tests himself - no tokens.

Tests:
  - Bitcoin via Titan's gates  (titan_mine.py)      : genesis-hash proof + mine on the model's NAND switches
  - Real pool mine -> wallet   (titan_pool_miner.py) : live Stratum solo mine to the owner's wallet (choose seconds)
  - Run a billion Titans       (titan_swarm.py)      : scale the population to 1e9 at 0 model RAM, limit = time

Run:  python host/titan_lab.py   ->  http://127.0.0.1:7866
"""
import http.server, json, os, subprocess, sys, threading, urllib.parse

HOST_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 7866

TESTS = {
    "mine":  ("Bitcoin via Titan's gates",   "titan_mine.py"),
    "pool":  ("Real pool mine -> wallet",     "titan_pool_miner.py"),
    "swarm": ("Run a billion Titans",         "titan_swarm.py"),
}

state = {"proc": None, "lines": [], "running": None}
lock = threading.Lock()


def _reader(proc, label):
    for line in iter(proc.stdout.readline, ""):
        with lock:
            state["lines"].append(line.rstrip("\n"))
    with lock:
        state["lines"].append(f"[done] {label} finished.")
        if state["proc"] is proc:
            state["proc"] = None; state["running"] = None


def start(test, secs):
    with lock:
        if state["proc"] and state["proc"].poll() is None:
            return False
        label, script = TESTS[test]
        args = [sys.executable, "-u", os.path.join(HOST_DIR, script)]
        if test == "pool":
            args.append(str(secs))
        state["lines"] = [f"[start] {label} ..."]
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1, cwd=HOST_DIR,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        state["proc"] = p; state["running"] = label
    threading.Thread(target=_reader, args=(p, label), daemon=True).start()
    return True


def stop():
    with lock:
        if state["proc"] and state["proc"].poll() is None:
            state["proc"].terminate()
            state["lines"].append("[stopped by user]")
            state["running"] = None
            return True
    return False


PAGE = """<!doctype html><html><head><meta charset=utf-8><title>Titan Test Bench</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
 :root{--bg:#0b0e14;--panel:#131823;--ink:#e6edf3;--dim:#8b97a7;--acc:#f7a41d;--acc2:#37c98b;--line:#232b3a}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);
   font:15px/1.5 "Segoe UI",system-ui,sans-serif}
 .wrap{max-width:960px;margin:0 auto;padding:28px 20px 60px}
 h1{font-size:24px;margin:0 0 4px;letter-spacing:.3px}
 h1 span{color:var(--acc)}
 .sub{color:var(--dim);margin:0 0 22px;font-size:13px}
 .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin-bottom:18px}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}
 .card h3{margin:0 0 6px;font-size:16px}
 .card p{margin:0 0 14px;color:var(--dim);font-size:12.5px;min-height:34px}
 button{cursor:pointer;border:0;border-radius:9px;padding:11px 16px;font-size:14px;font-weight:600;
   color:#0b0e14;background:var(--acc);width:100%;transition:filter .15s}
 button:hover{filter:brightness(1.08)} button:disabled{opacity:.45;cursor:not-allowed}
 .row{display:flex;gap:10px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
 input[type=number]{width:110px;background:#0b0e14;color:var(--ink);border:1px solid var(--line);
   border-radius:8px;padding:9px 10px;font-size:14px}
 label{color:var(--dim);font-size:13px}
 .stop{background:#e5534b;color:#fff;width:auto;padding:11px 22px}
 .pill{display:inline-block;padding:4px 12px;border-radius:20px;font-size:12.5px;font-weight:600}
 .idle{background:#1b2130;color:var(--dim)} .live{background:#123024;color:var(--acc2)}
 pre{background:#05070b;border:1px solid var(--line);border-radius:12px;padding:16px;margin:0;
   min-height:340px;max-height:60vh;overflow:auto;font:12.5px/1.55 "Cascadia Code",Consolas,monospace;
   color:#c9d4e0;white-space:pre-wrap}
 .note{color:var(--dim);font-size:12px;margin-top:14px}
 code{color:var(--acc)}
</style></head><body><div class=wrap>
 <h1>Titan <span>Test Bench</span></h1>
 <p class=sub>Click a test. It runs on the model's own gates / shared storage &mdash; watch it live below. Zero model RAM.</p>
 <div class=grid>
  <div class=card><h3>&#9935; Bitcoin via gates</h3>
    <p>Reproduces the real Bitcoin genesis hash on Titan's NAND switches, then mines. Proof the gates compute SHA-256.</p>
    <button onclick="run('mine')">Run gate proof + mine</button></div>
  <div class=card><h3>&#127760; Mine to my wallet</h3>
    <p>Real Stratum solo mine to your wallet on the live network. No payout expected at CPU speed &mdash; real data.</p>
    <button onclick="run('pool')">Mine to wallet</button></div>
  <div class=card><h3>&#128043; A billion Titans</h3>
    <p>Scales the population to 1,000,000,000 in parallel over shared storage. Model RAM stays 0; limit = time.</p>
    <button onclick="run('swarm')">Run a billion</button></div>
 </div>
 <div class=row>
   <label>pool mine seconds</label><input id=secs type=number value=600 min=10 max=86400>
   <button class=stop onclick="stop()">&#9632; Stop</button>
   <span id=status class="pill idle">idle</span>
 </div>
 <pre id=out>ready.</pre>
 <p class=note>Wallet for pool mining is set in <code>host/titan_pool_miner.py</code>. One test at a time. Closing the
   minimized server window shuts the bench down.</p>
</div>
<script>
let since=0;
function run(t){since=0;document.getElementById('out').textContent='';
  fetch('/run?test='+t+'&secs='+document.getElementById('secs').value).then(r=>r.json()).then(j=>{
    if(!j.ok)flash('a test is already running - stop it first');});}
function stop(){fetch('/stop').then(()=>{});}
function flash(m){document.getElementById('out').textContent=m;}
function poll(){fetch('/out?since='+since).then(r=>r.json()).then(j=>{
  since=j.n; const o=document.getElementById('out');
  if(j.lines.length){o.textContent+=(o.textContent?'\\n':'')+j.lines.join('\\n');o.scrollTop=o.scrollHeight;}
  const s=document.getElementById('status');
  if(j.running){s.className='pill live';s.textContent='running: '+j.running;}
  else{s.className='pill idle';s.textContent='idle';}});}
setInterval(poll,900);poll();
</script></body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, body, ct="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(200); self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(b))); self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path == "/" or u.path == "/index.html":
            return self._send(PAGE, "text/html; charset=utf-8")
        if u.path == "/run":
            test = q.get("test", [""])[0]
            secs = q.get("secs", ["600"])[0]
            try: secs = max(10, min(86400, int(secs)))
            except Exception: secs = 600
            ok = start(test, secs) if test in TESTS else False
            return self._send(json.dumps({"ok": ok}))
        if u.path == "/stop":
            return self._send(json.dumps({"ok": stop()}))
        if u.path == "/out":
            since = int(q.get("since", ["0"])[0])
            with lock:
                lines = state["lines"][since:]
                n = len(state["lines"])
                running = state["running"]
            return self._send(json.dumps({"lines": lines, "n": n, "running": running}))
        self.send_response(404); self.end_headers()


if __name__ == "__main__":
    print(f"Titan Test Bench -> http://127.0.0.1:{PORT}")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
