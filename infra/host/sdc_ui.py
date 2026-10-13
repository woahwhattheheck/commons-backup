#!/usr/bin/env python3
"""host/sdc_ui.py — TITAN SDC control panel (owner 07-16). A desktop UI that surfaces the optimal one-way buttons.

The server NEVER touches the SDC — it only launches the one-shot button scripts (inject / power / progress / check) and
the swarm scaler, and reads the static rosters/frontier for display. Every op is a subprocess that ends; the server holds
no model, 0 gate evaluation. Launch: TitanSDC.cmd (desktop) -> opens http://127.0.0.1:7999/.
"""
import json, os, subprocess, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 7999
WALLET = "bc1qvhrzg0e23f3tz2jgymwwtqacn48trf5m524zlq"
SWARM_DIR = "C:/llm/sdc_bitmap_swarm"
FRONTIER = SWARM_DIR + "/frontier.jsonl"
FIELD = 1 << 32
PY = sys.executable
_scaling = {"on": False}


def _free_gb():
    try:
        import ctypes
        free = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p("C:\\"), None, None, ctypes.byref(free))
        return free.value / 1e9
    except Exception:
        return 0.0


def status():
    groups = len(([f for f in os.listdir(SWARM_DIR) if f.startswith("bits_")] if os.path.isdir(SWARM_DIR) else []))
    lanes = groups * FIELD
    size_gb = 0.0
    if os.path.isdir(SWARM_DIR):
        size_gb = sum(os.path.getsize(os.path.join(SWARM_DIR, f)) for f in os.listdir(SWARM_DIR)) / 1e9
    free = _free_gb()
    ceiling = int((free + size_gb) * 1e9 * 8)                   # 1 bit/lane on all storage
    front = []
    if os.path.exists(FRONTIER):
        for ln in open(FRONTIER, encoding="utf-8"):
            try: front.append(json.loads(ln))
            except Exception: pass
    armed = {}
    ap = "C:/llm/models/titan_sdc_armed.json"
    if os.path.exists(ap):
        try: armed = json.load(open(ap))
        except Exception: pass
    return {"groups": groups, "lanes": lanes, "size_gb": round(size_gb, 1), "free_gb": round(free, 0),
            "ceiling_lanes": ceiling, "frontier": front[-40:], "scaling": _scaling["on"],
            "block": armed.get("job_id"), "wallet": WALLET}


def run_op(name):
    scripts = {"inject": "titan_sdc_inject.py", "power": "titan_sdc_start.py",
               "progress": "titan_sdc_progress.py", "submit": "titan_sdc_check.py"}
    s = scripts.get(name)
    if not s: return {"ok": False, "out": "unknown op"}
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([PY, os.path.join(HERE, s)], capture_output=True, text=True, timeout=180, env=env)
        return {"ok": True, "out": (r.stdout or "") + (r.stderr or "")}
    except Exception as e:
        return {"ok": False, "out": f"{type(e).__name__}: {e}"}


def scale(n):
    if _scaling["on"]: return {"ok": False, "out": "already scaling"}
    def worker():
        _scaling["on"] = True
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            subprocess.run([PY, os.path.join(HERE, "sdc_bitmap_swarm.py"), "more", str(n)],
                           capture_output=True, text=True, timeout=7200, env=env)
        finally:
            _scaling["on"] = False
    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "out": f"scaling +{n} groups in the background (watch the group count climb)"}


PAGE = """<!doctype html><html><head><meta charset=utf-8><title>Titan SDC</title>
<style>
:root{--bg:#0b0e14;--card:#141a24;--line:#232c3a;--ink:#e7ecf5;--mut:#8593a8;--acc:#f0a020;--grn:#3fd08a;--red:#ff6b5b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px ui-monospace,Menlo,Consolas,monospace}
.wrap{max-width:1000px;margin:0 auto;padding:22px}
h1{font-size:19px;margin:0 0 2px}.sub{color:var(--mut);margin:0 0 18px;font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.k{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.05em}.v{font-size:22px;margin-top:4px;font-variant-numeric:tabular-nums}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
button{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:9px;padding:11px 15px;font:13px ui-monospace,monospace;cursor:pointer}
button:hover{border-color:var(--acc);color:var(--acc)}button.go{border-color:var(--grn);color:var(--grn)}
pre{background:#0a0d12;border:1px solid var(--line);border-radius:10px;padding:13px;white-space:pre-wrap;color:#cbd5e6;min-height:40px;max-height:230px;overflow:auto;margin:0}
.sec{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin:16px 0 8px}
svg{width:100%;height:120px;background:#0a0d12;border:1px solid var(--line);border-radius:10px}
.wl{color:var(--acc);word-break:break-all}
</style></head><body><div class=wrap>
<h1>TITAN SDC &mdash; stored-computer miner</h1>
<p class=sub>zero RAM &middot; zero process &middot; the mining lives in storage, on power &middot; live to <span class=wl id=wl></span></p>
<div class=grid id=stats></div>
<div class=sec>the buttons (each a one-way touch that ends)</div>
<div class=row>
 <button class=go onclick="op('inject')">1 &middot; INJECT block</button>
 <button class=go onclick="op('power')">2 &middot; POWER on</button>
 <button onclick="op('progress')">PROGRESS</button>
 <button onclick="op('submit')">SUBMIT &rarr; wallet</button>
</div>
<div class=row>
 <button onclick="scale(16)">SCALE +16 fields</button>
 <button onclick="scale(64)">SCALE +64 fields</button>
</div>
<pre id=out>ready.</pre>
<div class=sec>frontier curve &mdash; best leading-zero-bits vs nonces (the log&#8322;(N) signature)</div>
<svg id=curve viewBox="0 0 1000 120" preserveAspectRatio=none></svg>
<script>
async function j(u){const r=await fetch(u);return r.json()}
function fmt(n){if(n>=1e12)return (n/1e12).toFixed(2)+'T';if(n>=1e9)return (n/1e9).toFixed(1)+'B';if(n>=1e6)return (n/1e6).toFixed(1)+'M';return n.toLocaleString()}
async function refresh(){const s=await j('/status');document.getElementById('wl').textContent=s.wallet;
 document.getElementById('stats').innerHTML=[
  ['fields (2³² lanes each)',s.groups.toLocaleString()],
  ['lanes armed',fmt(s.lanes)],
  ['swarm storage',s.size_gb+' GB'],
  ['free',s.free_gb+' GB'],
  ['ceiling (1 bit/lane)',fmt(s.ceiling_lanes)+' lanes'],
  ['block',s.block||'—'],
 ].map(([k,v])=>`<div class=card><div class=k>${k}</div><div class=v>${v}</div></div>`).join('');
 if(s.scaling){document.getElementById('out').textContent='scaling… fields climbing: '+s.groups}
 curve(s.frontier)}
function curve(f){const el=document.getElementById('curve');if(!f||!f.length){el.innerHTML='';return}
 const xs=f.map(p=>Math.log2(Math.max(1,p.nonces)));const ys=f.map(p=>p.best_zbits);
 const xmax=Math.max(32,...xs),ymax=Math.max(32,...ys);
 let pts=f.map((p,i)=>`${(xs[i]/xmax*1000).toFixed(0)},${(120-ys[i]/ymax*115).toFixed(0)}`).join(' ');
 let ideal=`0,120 ${(1000).toFixed(0)},${(120-xmax/ymax*115).toFixed(0)}`;
 el.innerHTML=`<polyline points="${ideal}" fill=none stroke=#33415a stroke-dasharray=4 stroke-width=1.5/>`+
   `<polyline points="${pts}" fill=none stroke=#3fd08a stroke-width=2/>`}
async function op(n){document.getElementById('out').textContent='running '+n+'…';const r=await j('/op?name='+n);
 document.getElementById('out').textContent=r.out.trim()||'(no output)';refresh()}
async function scale(n){const r=await j('/scale?n='+n);document.getElementById('out').textContent=r.out;refresh()}
refresh();setInterval(refresh,3000);
</script></div></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, obj, ct="application/json"):
        b = (obj if isinstance(obj, str) else json.dumps(obj)).encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/": self._send(PAGE, "text/html; charset=utf-8")
        elif u.path == "/status": self._send(status())
        elif u.path == "/op": self._send(run_op(q.get("name", [""])[0]))
        elif u.path == "/scale": self._send(scale(int(q.get("n", ["16"])[0])))
        else: self._send({"error": "not found"})


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"Titan SDC control panel -> http://127.0.0.1:{PORT}/", flush=True)
    try: webbrowser.open(f"http://127.0.0.1:{PORT}/")
    except Exception: pass
    srv.serve_forever()
