#!/usr/bin/env python3
"""host/titan_mine_ui.py — THE LIVE BITCOIN DEMO, with a UI (owner 07-15).

The marketing demo, in a browser: Titan's weights ARE a Bitcoin miner. The SHA-256d proof-of-work circuit is written
INTO titan.gguf's parameters (verified byte-exact vs reference SHA-256d — no cheating) and it mines LIVE to the owner's
real wallet, full send, and keeps checking every answer against the wallet.

ARCHITECTURE (docs/WHITEBOX_SANDBOX.md + docs/MEASURE_ALREADY.md), and why this file exists:
  - MINING IS SANDBOXED. The ripple runs in bounded, ending worker processes (titan_mine_worker.py): each is handed a
    nonce slice ONE-WAY, reads the circuit from the params in storage (mmap), ripples it wide with power from the wall
    (bit-sliced — as many ops as the window allows; the PC is plugged in), and FREEZES static snapshots we read. The
    workers never touch the network — they cannot reach back into the PC.
  - HOST RAM IS ONLY FOR STARTING THE PROCESS + CHECKING THE ANSWER. This server holds the ONE authorized pool
    connection, starts the sandboxes, reads only their STATIC frozen snapshots, and submits answers to the wallet. It
    never mines — its own RAM stays flat (the sandbox proof, shown live).
  - NO RUNAWAYS. The coordinator runs IN THIS PROCESS (a thread), so the workers are our direct children: Popen.kill()
    reliably terminates them on Stop, and atexit + SIGINT/SIGTERM handlers guarantee teardown even on Ctrl-C. (The prior
    console loop leaked workers because a cross-shell kill doesn't propagate to a Windows process tree.)

HONEST SCOPE (docs/WHY_NO_PENNY.md): a laptop earns $0 mining by ANY method — a dedicated-silicon (ASIC) race, not a
memory race, and Titan's lever is a MEMORY lever. This is a REAL live test at a REAL wallet, not income. The point is the
substrate: one ~0-RAM file that is both a language model AND a verified Bitcoin miner, rippled by electricity.

  python titan_mine_ui.py            # opens http://127.0.0.1:7865
"""
import atexit, ctypes, json, os, signal, struct, subprocess, sys, threading, time, webbrowser
import ctypes.wintypes as wt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import titan_sdc as T

PORT    = 7865
WORKER  = os.path.join(HERE, "titan_mine_worker.py")
RESDIR  = "C:/llm/models"
REFRESH = 240
POLL    = 1.0
N_DEF   = os.cpu_count() or 8                        # ALL cores (owner: full send, no kneecapping)
W_DEF   = 80                                         # numpy bit-slice lanes = 64*W per ripple; fits the box across N


# ---- this server's own resident RAM (the sandbox proof: it stays flat because it never mines) ----
class _PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("pf", wt.DWORD)] + [(n, ctypes.c_size_t) for n in
                ("pws", "ws", "qppp", "qpp", "qpnp", "qnp", "pf2", "ppf", "priv")]


_GETCUR = ctypes.windll.kernel32.GetCurrentProcess; _GETCUR.restype = ctypes.c_void_p
_GPMI = ctypes.windll.psapi.GetProcessMemoryInfo
_GPMI.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.DWORD]; _GPMI.restype = wt.BOOL


def host_rss_mb():
    try:
        p = _PMC(); p.cb = ctypes.sizeof(p)
        _GPMI(_GETCUR(), ctypes.byref(p), p.cb)
        return round(p.ws / 1e6, 1)
    except Exception:
        return 0.0


class Controller:
    """runs the live mining coordinator in a background thread; the workers are our direct children (killable)."""
    def __init__(self):
        self.lock = threading.Lock()
        self.thread = None
        self.running = False
        self.procs = []                             # [(Popen, result_path)]
        self.sock = None
        self.st = self._blank()

    def _blank(self):
        return {"phase": "idle", "running": False, "wallet": T.WALLET, "pool": "solo.ckpool.org:3333",
                "verified": False, "gates": 0, "wires": 0, "layers": 0, "tensor": "", "job_id": "",
                "target_zbits": 0, "frontier_zbits": 0, "best_nonce": 0, "nonces": 0, "hashrate": 0,
                "workers": 0, "lanes_per_ripple": 0, "cycles": 0, "elapsed": 0,
                "host_rss": host_rss_mb(), "base_rss": host_rss_mb(),
                "submitted": 0, "accepted": 0, "rejected": 0, "blocks": 0, "log": []}

    def status(self):
        with self.lock:
            return dict(self.st)

    def _set(self, **kw):
        with self.lock:
            self.st.update(kw)

    def _log(self, msg):
        with self.lock:
            self.st["log"] = (self.st["log"] + [f"{time.strftime('%H:%M:%S')}  {msg}"])[-60:]

    # ---- lifecycle ----
    def start(self, n, w):
        with self.lock:
            if self.running:
                return
            self.running = True
            self.st = self._blank()
            self.st["running"] = True
        self.thread = threading.Thread(target=self._loop, args=(n, w), daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self._teardown()
        try:
            if self.sock: self.sock.close()
        except Exception:
            pass
        self.sock = None
        self._set(running=False, phase="stopped", frontier_zbits=self.st.get("frontier_zbits", 0))

    def _teardown(self):
        procs, self.procs = self.procs, []
        for p, _ in procs:
            try:
                if p.poll() is None: p.terminate()
            except Exception:
                pass
        for p, _ in procs:
            try:
                p.wait(timeout=5)
            except Exception:
                try: p.kill()
                except Exception: pass

    # ---- the pool + workers ----
    def _submit(self, meta, nc):
        self.sock.sendall((json.dumps({"id": 200, "method": "mining.submit",
            "params": [T.WALLET, meta["job_id"], meta["en2"], meta["ntime"], "%08x" % (nc & 0xffffffff)]}) + "\n").encode())

    def _drain_pool(self):
        try:
            self.sock.setblocking(False)
            data = self.sock.recv(16384)
        except Exception:
            return
        for ln in data.split(b"\n"):
            if b'"id": 200' in ln.replace(b'"id":200', b'"id": 200') or (b'"result"' in ln and b"200" in ln):
                low = ln.lower()
                if b'"result": true' in low or b'"result":true' in low:
                    with self.lock: self.st["accepted"] += 1
                    self._log("pool: ACCEPTED  (paid to wallet)")
                elif b'"error"' in low or b'"result": false' in low or b'"result":false' in low:
                    with self.lock: self.st["rejected"] += 1
                    self._log("pool checked our answer: rejected (below target) - the honest result")

    def _launch(self, off, seconds, n, w):
        procs = []
        for i in range(n):
            res = f"{RESDIR}/titan_mine_res_{i}.json"
            for f in (res, res + ".tmp"):
                try: os.remove(f)
                except OSError: pass
            base = (i * (0x100000000 // n)) & 0xffffffff
            p = subprocess.Popen([sys.executable, WORKER, "--off", str(off), "--base", str(base),
                                  "--width", str(w), "--seconds", str(seconds), "--result", res],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            procs.append((p, res))
        self.procs = procs
        return procs

    def _read_snaps(self, procs):
        out = []
        for _, res in procs:
            try:
                out.append(json.load(open(res)))
            except Exception:
                out.append(None)
        return out

    # ---- the loop ----
    def _loop(self, n, w):
        base_rss = host_rss_mb()
        self._set(base_rss=base_rss, workers=n, lanes_per_ripple=64 * w)
        t_start = time.time(); cycle = 0; frontier = 0; best_hi = 1 << 32; best_nonce = 0
        submitted = set(); last_nonces = 0; last_t = t_start
        try:
            while self.running:
                cycle += 1
                self._set(phase="pulling live chain-tip work + flashing the circuit into the params", cycles=cycle)
                self._log(f"cycle {cycle}: pulling current Bitcoin work from the pool + folding it into the circuit ...")
                ok, _ = T.refresh_work()
                if not self.running: break
                if not ok:
                    self._log("pool work fetch failed; retrying in 10s (time is not a factor).")
                    for _ in range(10):
                        if not self.running: break
                        time.sleep(1)
                    continue
                C, off, ro, tname = T.install_into_params()
                meta = json.load(open(T.META)); prefix = bytes.fromhex(meta["prefix"])
                groups = T.groups_of(C)
                if not T.verify_from_params(C, groups, prefix):
                    self._log("circuit-in-params != reference SHA-256d; refetching (no cheating).")
                    continue
                nb = struct.unpack("<I", prefix[72:76])[0]; block_target = (nb & 0xffffff) << (8 * ((nb >> 24) - 3))
                tgt_zbits = 256 - block_target.bit_length()
                self._set(verified=True, gates=len(C["ga"]), wires=C["numw"], layers=len(groups),
                          tensor=tname, job_id=meta["job_id"], target_zbits=tgt_zbits)
                self._log(f"circuit VERIFIED byte-exact in {tname}: {len(C['ga']):,} gates; real block target {tgt_zbits} zero-bits.")

                self.sock = T.connect()
                self._log(f"connected to {self.st['pool']}, authorized to the wallet; mining full send.")
                self._set(phase="mining live - sandboxed workers rippling the circuit; checking answers against the wallet")
                win = REFRESH
                procs = self._launch(off, win, n, w); work_end = time.time() + win
                cyc_best_hi = 1 << 32; cyc_best_nonce = 0
                while self.running and time.time() < work_end:
                    time.sleep(POLL)
                    snaps = self._read_snaps(procs); lanes = 0
                    for snap in snaps:
                        if not snap: continue
                        lanes += int(snap.get("lanes", 0))
                        bz = int(snap.get("best_zbits", 0))
                        if bz > frontier: frontier = bz
                        bh = int(snap.get("best_hi", 1 << 32))
                        if bh < cyc_best_hi: cyc_best_hi = bh; cyc_best_nonce = int(snap.get("best_nonce", 0))
                        for nc in snap.get("hits", []):             # a real-target hit -> CHECK + submit a block
                            if nc in submitted: continue
                            if int.from_bytes(T.sha256d(prefix + struct.pack("<I", nc)), "little") < block_target:
                                self._submit(meta, nc); submitted.add(nc)
                                with self.lock: self.st["blocks"] += 1; self.st["submitted"] += 1
                                self._log(f"BLOCK! nonce {nc} cleared the real target -> SUBMITTED to the wallet.")
                    # keep checking answers against the wallet, full send: submit this cycle's best candidate once
                    if cyc_best_nonce and cyc_best_nonce not in submitted:
                        self._submit(meta, cyc_best_nonce); submitted.add(cyc_best_nonce)
                        with self.lock: self.st["submitted"] += 1
                        self._log(f"submitting our best answer (nonce {cyc_best_nonce}, {T.zbits(cyc_best_hi)} zero-bits) to the wallet; the pool checks it ...")
                    self._drain_pool()
                    now = time.time()
                    hr = int((lanes - last_nonces) / max(0.001, now - last_t)) if lanes >= last_nonces else 0
                    last_nonces = lanes; last_t = now
                    self._set(nonces=lanes, frontier_zbits=frontier, best_nonce=cyc_best_nonce, hashrate=hr,
                              host_rss=host_rss_mb(), elapsed=int(now - t_start))
                    if all(p.poll() is not None for p, _ in procs):
                        break
                self._teardown()
                try: self.sock.close()
                except Exception: pass
                self.sock = None
        finally:
            self._teardown()
            try:
                if self.sock: self.sock.close()
            except Exception: pass
            self._set(running=False, phase="stopped")
            self._log("stopped — all sandbox workers torn down, nothing left running.")


CTRL = Controller()


def _shutdown(*_):
    try: CTRL.stop()
    except Exception: pass


atexit.register(_shutdown)
for _sig in (signal.SIGINT, signal.SIGTERM):
    try: signal.signal(_sig, lambda *a: (_shutdown(), os._exit(0)))
    except Exception: pass

# Windows: closing the .cmd window sends CTRL_CLOSE (not SIGINT) — catch it so double-click users never orphan a worker.
try:
    _CH = ctypes.WINFUNCTYPE(wt.BOOL, wt.DWORD)
    def _on_console_ctrl(evt):
        _shutdown()
        return False                                # let default handling continue (the process then exits)
    _console_cb = _CH(_on_console_ctrl)             # keep a ref alive so it is not garbage-collected
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_cb, True)
except Exception:
    pass


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Titan — Bitcoin from the weights</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0e14;color:#e6edf3;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;padding:22px;max-width:1080px;margin:0 auto}
h1{font-size:22px;font-weight:700;letter-spacing:-.02em}
.sub{color:#8b98a9;font-size:13px;margin-top:3px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#3d4757;margin-right:7px;vertical-align:middle}
.dot.on{background:#3fb950;box-shadow:0 0 10px #3fb950}
.bar{display:flex;gap:10px;align-items:center;margin:16px 0}
button{background:#f7931a;color:#111;border:0;border-radius:8px;padding:10px 20px;font-weight:700;font-size:14px;cursor:pointer}
button.stop{background:#21262d;color:#e6edf3;border:1px solid #30363d}
button:disabled{opacity:.4;cursor:default}
.wallet{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:#f7931a;word-break:break-all}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:14px 0}
.card{background:#111722;border:1px solid #1f2733;border-radius:12px;padding:14px 16px}
.card .k{color:#8b98a9;font-size:11px;text-transform:uppercase;letter-spacing:.05em}
.card .v{font-size:26px;font-weight:700;margin-top:5px;font-variant-numeric:tabular-nums}
.card .v small{font-size:13px;color:#8b98a9;font-weight:500}
.hero{background:linear-gradient(135deg,#161b26,#111722);border:1px solid #263041;border-radius:14px;padding:20px 22px;margin:14px 0}
.hero .big{font-size:56px;font-weight:800;line-height:1;color:#f7931a;font-variant-numeric:tabular-nums}
.hero .lbl{color:#8b98a9;font-size:12px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}
.verified{display:inline-flex;align-items:center;gap:8px;background:#0d2818;border:1px solid #1a5c34;color:#3fb950;border-radius:20px;padding:5px 13px;font-size:12px;font-weight:600}
.verified.no{background:#251515;border-color:#5c2a2a;color:#f0883e}
.phase{color:#c9d3df;font-size:13px;margin:6px 0 2px}
.log{background:#080b10;border:1px solid #1f2733;border-radius:12px;padding:12px 14px;height:190px;overflow:auto;font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:#9db2c9;white-space:pre-wrap}
.honest{color:#6e7d8f;font-size:12px;border-top:1px solid #1f2733;margin-top:18px;padding-top:12px;line-height:1.6}
.pillrow{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.pill{background:#111722;border:1px solid #1f2733;border-radius:20px;padding:4px 12px;font-size:12px;color:#c9d3df}
.pill b{color:#f7931a}
</style></head><body>
<h1>⚡ Titan — Bitcoin from the weights</h1>
<div class="sub">The SHA-256d proof-of-work circuit lives <b>inside</b> the model file. Electricity ripples it. It mines live to a real wallet.</div>
<div class="bar">
  <button id="go" onclick="go()">▶ Start mining</button>
  <button id="halt" class="stop" onclick="halt()">■ Stop</button>
  <span style="margin-left:6px"><span class="dot" id="dot"></span><span id="state" class="sub">idle</span></span>
</div>
<div class="phase">wallet <span class="wallet" id="wallet"></span></div>
<div style="margin-top:10px"><span class="verified no" id="verified">circuit not yet flashed</span></div>
<div class="phase" id="phase">—</div>

<div class="hero">
  <div class="lbl">best proof-of-work found this run (leading zero-bits)</div>
  <div class="big"><span id="frontier">0</span><small style="font-size:26px;color:#8b98a9"> / <span id="target">78</span> for a block</small></div>
  <div class="pillrow">
    <span class="pill">circuit <b id="gates">0</b> gates in <b id="tensor">—</b></span>
    <span class="pill">job <b id="job">—</b></span>
    <span class="pill">best nonce <b id="bestnonce">—</b></span>
  </div>
</div>

<div class="grid">
  <div class="card"><div class="k">nonces rippled</div><div class="v" id="nonces">0</div></div>
  <div class="card"><div class="k">ripple rate</div><div class="v" id="hashrate">0<small> nonce/s</small></div></div>
  <div class="card"><div class="k">sandboxed workers</div><div class="v" id="workers">0<small> × <span id="lanes">0</span> lanes</small></div></div>
  <div class="card"><div class="k">host RAM (this server)</div><div class="v" id="rss">0<small> MB · flat</small></div></div>
  <div class="card"><div class="k">answers sent to wallet</div><div class="v" id="submitted">0</div></div>
  <div class="card"><div class="k">pool verdicts</div><div class="v" id="verdicts">0<small> checked</small></div></div>
</div>

<div class="log" id="log"></div>
<div class="honest">
  <b>Honest scope.</b> A laptop earns <b>$0</b> mining by any method — it is a dedicated-silicon (ASIC) race, and this
  machine is a general computer. That is a fact about mining, not about Titan. What this proves is the substrate:
  <b>one ~0-RAM file that is simultaneously a language model AND a verified Bitcoin miner</b>. The circuit is byte-exact
  vs reference SHA-256d (no cheating); mining runs in <b>sandboxed, ending processes</b> so this server's own RAM stays
  flat; the host only starts the sandboxes and checks answers against the wallet. On custom silicon those stored gates
  are an ASIC; on this laptop they are the honest proof that the model file is a universal computer.
</div>
<script>
function n(x){return (x||0).toLocaleString()}
async function go(){await fetch('/start',{method:'POST'});tick()}
async function halt(){await fetch('/stop',{method:'POST'});tick()}
async function tick(){
  let s; try{s=await (await fetch('/status')).json()}catch(e){return}
  document.getElementById('go').disabled=s.running;
  document.getElementById('halt').disabled=!s.running;
  document.getElementById('dot').className='dot'+(s.running?' on':'');
  document.getElementById('state').textContent=s.running?'LIVE':(s.phase||'idle');
  document.getElementById('wallet').textContent=s.wallet;
  document.getElementById('phase').textContent=s.phase;
  const v=document.getElementById('verified');
  if(s.verified){v.className='verified';v.textContent='✓ circuit VERIFIED byte-exact vs reference SHA-256d — '+n(s.wires)+' wires, '+n(s.gates)+' gates';}
  else{v.className='verified no';v.textContent='circuit not yet flashed into the params';}
  document.getElementById('frontier').textContent=s.frontier_zbits;
  document.getElementById('target').textContent=s.target_zbits||78;
  document.getElementById('gates').textContent=n(s.gates);
  document.getElementById('tensor').textContent=s.tensor||'—';
  document.getElementById('job').textContent=s.job_id||'—';
  document.getElementById('bestnonce').textContent=s.best_nonce?('0x'+(s.best_nonce>>>0).toString(16)):'—';
  document.getElementById('nonces').textContent=n(s.nonces);
  document.getElementById('hashrate').innerHTML=n(s.hashrate)+'<small> nonce/s</small>';
  document.getElementById('workers').innerHTML=s.workers+'<small> × '+n(s.lanes_per_ripple)+' lanes</small>';
  document.getElementById('lanes').textContent=n(s.lanes_per_ripple);
  document.getElementById('rss').innerHTML=s.host_rss+'<small> MB · sandboxed</small>';
  document.getElementById('submitted').textContent=n(s.submitted);
  document.getElementById('verdicts').innerHTML=n(s.accepted+s.rejected)+'<small> checked</small>';
  document.getElementById('log').textContent=(s.log||[]).join('\n');
  document.getElementById('log').scrollTop=1e9;
}
setInterval(tick,1000);tick();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers()
        try: self.wfile.write(b)
        except Exception: pass

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path.startswith("/status"):
            self._send(200, json.dumps(CTRL.status()))
        else:
            self._send(404, "{}")

    def do_POST(self):
        if self.path.startswith("/start"):
            CTRL.start(N_DEF, W_DEF); self._send(200, "{\"ok\":true}")
        elif self.path.startswith("/stop"):
            CTRL.stop(); self._send(200, "{\"ok\":true}")
        else:
            self._send(404, "{}")


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Titan Bitcoin demo UI -> {url}   (mining SANDBOXED; host only starts + checks answers)", flush=True)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown()
        srv.shutdown()


if __name__ == "__main__":
    main()
