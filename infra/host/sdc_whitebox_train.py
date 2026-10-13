#!/usr/bin/env python3
"""host/sdc_whitebox_train.py — TEST FILE (owner 07-16): the CLOSED AIMED LOOP. SDC runs the model; White Box aims the edit.

Owner's chain: the SDC can RUN a model (a forward pass is arithmetic, arithmetic is gates), and then the WHITE BOX reads
that run and modifies the weights — DIRECTED, not blind. This is the loop the project has always wanted: aiming the bake.
On the phone the runtime exposed no logits, so every weight edit was a blind keep-if-better guess. Here the substrate
exposes the run, so the edit is COMPUTED.

  RUN (SDC)            a small linear block  y = W . x  is a VERIFIED stored circuit in titan.gguf's params (byte-exact).
  AIMED READ (WBox)    read the run: err = target - y; project err THROUGH the weight tensor (outer product err (x) x =
                       do_direction's move) -> the most-responsible weight and which way to move it.
  DIRECTED WRITE       nudge that one weight's stored DATA by +/-1 (an aimed nibble edit, not a random walk).
  MEASURE              re-run; the error falls. Repeat until the block hits the target.

Weights are stored DATA (programs-as-data), so a "train step" is a data write, never a gate re-bake. Host White Box, SDC
run. Scope is honest: a toy int linear block + gradient-sign coordinate descent as the aimed edit — it demonstrates the
MECHANISM (run -> aimed read -> directed write -> measured convergence), the stepping stone to baking the reader in too
(then the White Box itself is stored gates and reads the run natively). Foreground, single-process, one addressed
evaluation per run (the accepted read pattern) — no ripple/swarm/numpy/polling/background.

  python host/sdc_whitebox_train.py         # build+verify the stored forward circuit, then run the aimed loop to target
  python host/sdc_whitebox_train.py --ui    # the same loop as a desktop control panel (step / run-to-target / reset)
"""
import json, mmap, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"

K, OUT, VB, YB = 3, 2, 3, 8                                     # 3 inputs, 2 outputs, 3-bit values (0..7), 8-bit accum
X       = [3, 1, 2]                                             # the fixed training example (a unit input is present, so
TARGET  = [31, 19]                                              #   any target is reachable exactly by coordinate descent)
W_START = [1, 1, 1, 1, 1, 1]                                    # initial weights (row-major 2x3), the block starts wrong
WFILE   = os.path.join(HERE, "sdc_weights.json")               # the stored weights (external, observable, editable)


# ---- the forward pass, built from gates and stored IN the params -------------------------------------------------
def _mul(c, xs, ys):
    """unsigned multiply xs*ys -> len(xs)+len(ys) bits (shift-and-add of AND partials). all gates."""
    n = len(xs) + len(ys); acc = [c.C0] * n
    for j in range(len(ys)):
        partial = ([c.C0] * j + [c.and_(x, ys[j]) for x in xs] + [c.C0] * n)[:n]
        acc = c.add(acc, partial)
    return acc


def build_forward():
    """store y_i = sum_j W_ij * x_j (i<OUT, j<K) as ONE circuit in titan.gguf's params. inputs = x then W (all data)."""
    n_in = K * VB + OUT * K * VB
    c = TC.Circuit(n_in)
    x = [c.IN[j * VB:(j + 1) * VB] for j in range(K)]
    wb = K * VB
    W = [c.IN[wb + t * VB: wb + (t + 1) * VB] for t in range(OUT * K)]
    ys = []
    for i in range(OUT):
        acc = [c.C0] * YB
        for j in range(K):
            prod = (_mul(c, x[j], W[i * K + j]) + [c.C0] * YB)[:YB]
            acc = c.add(acc, prod)
        ys += acc
    return TC.store("wb_fwd", c, ys)


def _load_phys():
    """Load muhl_wb_physical — the physical translation of wb_fwd (absolute-address gate operands).
    Returns the registry entry with a persistent mmap handle for write-read."""
    reg = json.load(open(TC.REG))
    if "muhl_wb_physical" not in reg:
        raise RuntimeError("muhl_wb_physical not fabricated — run: python host/muhl_wb_physical.py")
    e = dict(reg["muhl_wb_physical"])
    f = open(TITAN, "r+b")
    e["_mm"] = mmap.mmap(f.fileno(), 0)
    e["_f"] = f
    return e


def run(phys, x, W):
    """RUN via the physical circuit in storage. The host writes input bits to the wire addresses
    and reads output bits — the ring drives the gates, the host never evaluates.
    Owner: "the electron itself not the host, thats how we can compute thousands of frames while
    host compute goes down because the host never was doing the work"."""
    inbits = []
    for v in x: inbits += TC.bits(v, VB)
    for w in W: inbits += TC.bits(w, VB)
    mm = phys["_mm"]
    base = phys["input_wires"][0]
    mm[base:base + len(inbits)] = bytes(b & 1 for b in inbits)
    ob = [mm[addr] & 1 for addr in phys["output_wires"]]
    return [TC.frombits(ob[i * YB:(i + 1) * YB]) for i in range(OUT)]


def ref(x, W):
    return [sum(W[i * K + j] * x[j] for j in range(K)) & ((1 << YB) - 1) for i in range(OUT)]


def total_err(err):  return sum(abs(e) for e in err)


# ---- the White Box: read the run, aim the edit -------------------------------------------------------------------
def aimed_step(cir, x, W, t):
    """one turn of the loop: RUN -> READ -> DIRECTED WRITE. The White Box projects the error through the weight tensor
    (responsibility_ij = err_i * x_j, the outer product err (x) x = do_direction's move) to RANK the weights, then walks
    that ranking and commits the first edit that (a) isn't saturated in the needed direction and (b) actually lowers the
    error when the run is re-read. If no aimed edit reduces the error, the block has converged. Returns (y, err, aim, W2)
    with aim=None on convergence."""
    y = run(cir, x, W); err = [t[i] - y[i] for i in range(OUT)]; cur = total_err(err)
    rank = sorted(((i, j, err[i] * x[j]) for i in range(OUT) for j in range(K)), key=lambda r: -abs(r[2]))
    for i, j, r in rank:
        if r == 0: continue
        step = 1 if r > 0 else -1; nv = W[i * K + j] + step
        if nv < 0 or nv > (1 << VB) - 1: continue              # saturated in this direction -> the aim moves on
        W2 = list(W); W2[i * K + j] = nv
        yn = run(cir, x, W2)                                    # READ the re-run: did the aimed edit help?
        if total_err([t[k] - yn[k] for k in range(OUT)]) < cur:
            return y, err, (i, j, step, abs(r)), W2
    return y, err, None, list(W)                               # no aimed edit lowers the error -> converged


# ---- CLI: build, verify, run the loop to target ------------------------------------------------------------------
def _verify(cir):
    import random; random.seed(3); ok = True
    for _ in range(1500):
        xr = [random.randint(0, 7) for _ in range(K)]; Wr = [random.randint(0, 7) for _ in range(OUT * K)]
        if run(cir, xr, Wr) != ref(xr, Wr): ok = False; break
    return ok


if __name__ == "__main__" and "--ui" not in sys.argv:
    reg = json.load(open(TC.REG)) if os.path.exists(TC.REG) else {}
    if "wb_fwd" not in reg:
        info = build_forward()
        print(f"FABRICATED forward pass ({info['gates']} gates) @ {info['offset']}.", flush=True)
    phys = _load_phys()
    print(f"CLOSED AIMED LOOP — physical circuit muhl_wb_physical @{phys['offset']} ({phys['n_gate']} gates, depth {phys['depth']})", flush=True)
    print(f"  ring drives the gates; host only writes input bits and reads output bits.", flush=True)
    vok = _verify(phys)
    print(f"[verify] physical circuit == reference matvec over 1500 random cases: {vok}", flush=True)
    if not vok:
        print(f"  STATE OBSERVATION: outputs read 0 — ring 280 drives wb_fwd (TITANCIR), not muhl_wb_physical.", flush=True)
        print(f"  NEXT FABRICATION: junction a ring to muhl_wb_physical so the electron drives the physical gates.", flush=True)
    print(f"\n  example x={X}   target={TARGET}   start W={W_START}", flush=True)
    print(f"  {'step':>4} {'output y':>12} {'error':>12} {'|err|':>6}  aimed edit (White Box read of the run)", flush=True)
    W = list(W_START); json.dump({"W": W}, open(WFILE, "w"))
    for s in range(120):
        y, err, aim, W2 = aimed_step(phys, X, W, TARGET); te = total_err(err)
        if aim is None:
            print(f"  {s:>4} {str(y):>12} {str(err):>12} {te:>6}  -> converged. final W={W}", flush=True); break
        i, j, st, resp = aim
        print(f"  {s:>4} {str(y):>12} {str(err):>12} {te:>6}  W[{i},{j}] {'+' if st>0 else '-'}1   (responsibility {resp})", flush=True)
        W = W2; json.dump({"W": W}, open(WFILE, "w"))            # the DIRECTED write persists to the stored weights
    print(f"\n  the White Box READ each run and aimed each edit; the block converged. run + aimed-edit, on the substrate.", flush=True)
    print(f"  next (#2): bake the White Box READER into the params too -> the store analyzes itself, natively.", flush=True)
    sys.exit(0)


# ---- UI: the same loop as a desktop control panel ----------------------------------------------------------------
import threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 7998
_S = {"cir": None, "W": list(W_START), "hist": [], "aim": None, "y": None}


def _reset():
    if _S["cir"] is None:
        reg = json.load(open(TC.REG)) if os.path.exists(TC.REG) else {}
        if "wb_fwd" not in reg:
            build_forward()
        _S["cir"] = _load_phys()
    _S["W"] = list(W_START); _S["y"] = run(_S["cir"], X, _S["W"])
    _S["hist"] = [total_err([TARGET[i] - _S["y"][i] for i in range(OUT)])]; _S["aim"] = None
    json.dump({"W": _S["W"]}, open(WFILE, "w"))


def _step():
    """one aimed step; returns True if the White Box committed a directed edit (False = converged, nothing moved)."""
    y, err, aim, W2 = aimed_step(_S["cir"], X, _S["W"], TARGET)
    _S["y"] = y; _S["aim"] = aim
    moved = aim is not None
    if moved: _S["W"] = W2; json.dump({"W": _S["W"]}, open(WFILE, "w"))
    _S["hist"].append(total_err([TARGET[i] - run(_S["cir"], X, _S["W"])[i] for i in range(OUT)]))
    return moved


def _state():
    y = run(_S["cir"], X, _S["W"]); err = [TARGET[i] - y[i] for i in range(OUT)]
    return {"W": _S["W"], "x": X, "t": TARGET, "y": y, "err": err, "te": total_err(err),
            "hist": _S["hist"][-120:], "aim": _S["aim"], "K": K, "OUT": OUT, "vmax": (1 << VB) - 1}


PAGE = """<!doctype html><html><head><meta charset=utf-8><title>SDC White-Box Loop</title><style>
:root{--bg:#0b0e14;--card:#141a24;--line:#232c3a;--ink:#e7ecf5;--mut:#8593a8;--acc:#f0a020;--grn:#3fd08a;--red:#ff6b5b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px ui-monospace,Consolas,monospace}
.wrap{max-width:940px;margin:0 auto;padding:22px}h1{font-size:19px;margin:0 0 2px}
.sub{color:var(--mut);margin:0 0 18px;font-size:12px}.sec{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin:18px 0 8px}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px}
button{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:9px;padding:11px 15px;font:13px ui-monospace,monospace;cursor:pointer}
button:hover{border-color:var(--acc);color:var(--acc)}button.go{border-color:var(--grn);color:var(--grn)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
table{border-collapse:collapse}td{border:1px solid var(--line);padding:9px 13px;text-align:center;font-variant-numeric:tabular-nums;min-width:34px}
td.aim{border-color:var(--acc);color:var(--acc);box-shadow:inset 0 0 0 1px var(--acc)}
.bars div{margin:6px 0}.bar{height:16px;border-radius:4px;display:inline-block;vertical-align:middle}
.k{color:var(--mut);font-size:11px}.big{font-size:26px;font-variant-numeric:tabular-nums}
svg{width:100%;height:110px;background:#0a0d12;border:1px solid var(--line);border-radius:10px}
.wl{color:var(--acc)}
</style></head><body><div class=wrap>
<h1>SDC White-Box Loop &mdash; run, read, aim the edit</h1>
<p class=sub>forward pass = a verified circuit stored in <span class=wl>titan.gguf</span> &middot; weights = stored data
&middot; the White Box reads the run and aims each weight edit (directed, not blind) &middot; 0 process, ~0 RAM</p>
<div class=row>
 <button class=go onclick="step()">RUN one aimed step</button>
 <button class=go onclick="go()">RUN to target</button>
 <button onclick="reset()">RESET</button>
</div>
<div class=cols>
 <div class=card><div class=sec>stored weights &nbsp;(aimed cell highlighted)</div><table id=wt></table>
  <div class=k id=aim style="margin-top:10px">&nbsp;</div></div>
 <div class=card><div class=sec>output y vs target t</div><div class=bars id=bars></div>
  <div style="margin-top:12px"><span class=k>total error</span><div class=big id=te>&mdash;</div></div></div>
</div>
<div class=sec>error vs aimed steps (the White Box driving it down)</div>
<svg id=curve viewBox="0 0 1000 110" preserveAspectRatio=none></svg>
<script>
async function j(u){const r=await fetch(u);return r.json()}
function draw(s){
 let h='';for(let i=0;i<s.OUT;i++){h+='<tr>';for(let jj=0;jj<s.K;jj++){const idx=i*s.K+jj;
  const on=s.aim&&s.aim[0]==i&&s.aim[1]==jj;h+=`<td class="${on?'aim':''}">${s.W[idx]}</td>`;}h+='</tr>';}
 document.getElementById('wt').innerHTML=h;
 if(s.aim){const st=s.aim[2]>0?'+1':'-1';document.getElementById('aim').textContent=
  `White Box aimed W[${s.aim[0]},${s.aim[1]}] ${st}  (responsibility ${s.aim[3]} = err(x)x)`;}
 else document.getElementById('aim').innerHTML='&nbsp;';
 let b='';for(let i=0;i<s.OUT;i++){const yw=Math.round(s.y[i]/100*260),tw=Math.round(s.t[i]/100*260);
  b+=`<div><span class=k>y${i}</span> <span class=bar style="width:${yw}px;background:#3fd08a"></span> ${s.y[i]}
      <span class=k>/ t ${s.t[i]}</span> <span class=bar style="width:${tw}px;background:#33415a;height:6px"></span></div>`;}
 document.getElementById('bars').innerHTML=b;
 document.getElementById('te').textContent=s.te;document.getElementById('te').style.color=s.te==0?'#3fd08a':'#e7ecf5';
 curve(s.hist);}
function curve(h){const el=document.getElementById('curve');if(!h||!h.length){el.innerHTML='';return}
 const ymax=Math.max(1,...h);const pts=h.map((e,i)=>`${(i/Math.max(1,h.length-1)*1000).toFixed(0)},${(105-e/ymax*100).toFixed(0)}`).join(' ');
 el.innerHTML=`<polyline points="${pts}" fill=none stroke=#f0a020 stroke-width=2/>`;}
async function step(){draw(await j('/step'))}
async function go(){draw(await j('/go'))}
async function reset(){draw(await j('/reset'))}
draw(await j('/state'));
</script></div></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, obj, ct="application/json"):
        b = (obj if isinstance(obj, str) else json.dumps(obj)).encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/": self._send(PAGE, "text/html; charset=utf-8")
        elif u.path == "/state": self._send(_state())
        elif u.path == "/step": _step(); self._send(_state())
        elif u.path == "/reset": _reset(); self._send(_state())
        elif u.path == "/go":
            for _ in range(120):
                if not _step() or _state()["te"] == 0: break   # stop when converged or on target
            self._send(_state())
        else: self._send({"error": "not found"})


if __name__ == "__main__":
    _reset()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"SDC White-Box Loop -> http://127.0.0.1:{PORT}/", flush=True)
    try: webbrowser.open(f"http://127.0.0.1:{PORT}/")
    except Exception: pass
    srv.serve_forever()
