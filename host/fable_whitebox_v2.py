#!/usr/bin/env python3
"""host/fable_whitebox_v2.py — WHITE BOX V2 (meaning-geometry + structure/security): a UI that SURFACES every fable_*
tool (owner 07-17; extended 2026-07-23).

The second White Box. The fable_* suite reads a model's stored geometry + structure — all read-only, pure-Python/numpy,
no inference. This surfaces EVERY one as a clickable card with an EDITABLE args box (prefilled with a safe default),
grouped into "meaning geometry" and "structure & security". ADDITIVE — it does not modify the tools or the 1.0 White Box.
Gated-sandbox law: each Run launches the tool as an ENDING child (argv in, stdout captured), and the server renders the
STATIC result only after the child EXITS — the server itself never touches a model (flat RAM).

  python host/fable_whitebox_v2.py         # http://127.0.0.1:7864  — pick a tool, (edit args,) Run, read the result
"""
import html, json, os, shlex, socket, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PORT = 7864
CLEAN = "C:/llm/models/SmolLM2-360M-Instruct-Q8_0-CLEAN.gguf"   # fast, verified-clean control for default runs

# (module, Title, what-it-answers, data_file|None, default_args, group)
TOOLS = [
    # ---- meaning geometry ----
    ("fable_lab",       "Lab 1 · first read",        "A first read-only lab into the real weight geometry.", None, "", "geometry"),
    ("fable_lab2",      "Lab 2 · playground",        "White-box playground into the real weights.", None, "", "geometry"),
    ("fable_lab3",      "Lab 3 · order & absence",   "Does the geometry hold ORDER (sequences) and ABSENCE?", None, "", "geometry"),
    ("fable_lab4",      "Lab 4 · opposites & color", "Do OPPOSITES sit close? + a color->emotion axis.", None, "", "geometry"),
    ("fable_explore",   "Geometry probes",           "Anisotropy, the cone, outlier dims, recentering.", "fable_geometry_data.json", "", "geometry"),
    ("fable_bits",      "Bits of meaning",           "How few bits/weight does meaning need? (sign-code)", "fable_bits_data.json", "", "geometry"),
    ("fable_mechanism", "Mechanism · why 1 bit",     "WHY is 1 bit enough? sign-agreement vs cosine + outliers.", "fable_mechanism_data.json", "", "geometry"),
    ("fable_practical", "Practical · free win",      "Is the cleanup a FREE WIN on a real clustering task?", "fable_practical_data.json", "", "geometry"),
    ("fable_clean",     "Clean · free win II",       "Anisotropy cleanup: does it help analogies + antonyms?", "fable_clean_data.json", "", "geometry"),
    ("fable_compare",   "Universal?",                "Is the geometry of meaning universal, or just Titan?", None, "", "geometry"),
    ("fable_concept",   "Concept · cross-lingual",   "Nearest embedding neighbors of a word; flags other-script.", None, "university", "geometry"),
    ("fable_axis",      "Axis · steering",           "Build a steering axis from a:b pairs; purity + poles.", None, "", "geometry"),
    ("fable_neurons",   "Neurons · monosemantic",    "Rank a layer's neurons by token-projection monosemanticity.", None, f"16 down 60 {CLEAN}", "geometry"),
    ("fable_crazy",     "Crazy Q's",                 "The questions people argue about, answered from the weights.", "fable_crazy_data.json", "", "geometry"),
    ("fable_crazy2",    "Crazy Q's · II",            "Round two of the weird ones.", None, "", "geometry"),
    # ---- structure & security ----
    ("fable_audit",     "Audit · backdoor scan",     "Sweep every tensor for baked circuits / hidden structure (entropy crater).", None, CLEAN, "security"),
    ("fable_sweep",     "Sweep · full tensor stats", "Every tensor: full stats + anomaly signals -> fable_sweep_data.json.", "fable_sweep_data.json", CLEAN, "security"),
    ("fable_scan2",     "Scan · structural",         "Per-row byte-entropy anomaly localizer for one tensor.", None, f"{CLEAN} blk.0.ffn_gate.weight", "security"),
    ("fable_direction", "Direction · manifold+value","Manifold-residual + NaN/Inf value-sanity on one tensor.", None, f"{CLEAN} blk.0.ffn_gate.weight", "security"),
    ("fable_findcircuits","Find circuits · magic",   "Scan for PFC* magic-byte circuit headers.", None, "C:/llm/models/titan.gguf", "security"),
    ("fable_ffndepth",  "FFN depth census",          "amp/inh/pass per layer -> the compute depth U-shape (3 models).", "fable_ffndepth_data.json", "", "security"),
    # ---- forge & pfc-computer forensics ----
    ("pfc_forge",       "Forge · build computers",   "build adders/ALUs/etc from NAND gates and PROVE they compute.", None, "", "forge"),
    ("wf_pfc_summary",  "PFC census · titan",        "how many computers + total gates are baked into titan's blk.1.", None, "", "forge"),
    ("wf_titancir_cells","TITANCIR · decode designs","the 65 distinct baked circuit designs + their tiling structure.", None, "", "forge"),
    ("wf_titancir_graph","TITANCIR · one gate graph","reconstruct one baked circuit into a gate graph (args: expert nth).", None, "0 0", "forge"),
    ("pfc_atlas",       "Silicon Atlas · census",    "enumerate + categorize every computer baked into titan (135 circuits, ~11M gates).", "pfc_atlas_data.json", "", "forge"),
    ("pfc_atlas_verify","Silicon Atlas · verify",    "prove a representative set of baked computers actually RUN (CPU/Life/forge).", None, "", "forge"),
    ("pfc_langton",     "Langton's Ant (forged)",    "forge Langton's Ant as a gate netlist, verify byte-exact (args: --test).", None, "--test", "forge"),
    ("pfc_turing",      "Turing machine (forged)",   "forge a busy-beaver Turing machine as gates; runs to HALT byte-exact (args: --test).", None, "--test", "forge"),
    ("pfc_cyclic",      "Cyclic CA (forged)",        "forge a spiral-forming cyclic cellular automaton as gates, byte-exact (args: --test).", None, "--test", "forge"),
]
GROUPS = [("geometry", "meaning geometry"), ("security", "structure &amp; security"), ("forge", "forge &amp; pfc computers")]
TIMEOUT = float(os.environ.get("FABLE_TIMEOUT", "300"))
_lock = threading.Lock()      # serialize runs so two ending children never fight the page cache


def run_tool(mod, argstr):
    path = os.path.join(HERE, mod + ".py")
    if not os.path.exists(path):
        return {"ok": False, "out": f"tool not found: {mod}.py"}
    try:
        args = shlex.split(argstr or "", posix=False)
    except Exception:
        args = (argstr or "").split()
    t0 = time.time()
    try:
        with _lock:                                             # one ENDING child at a time (gated sandbox)
            p = subprocess.run([PY, path] + args, cwd=HERE, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=TIMEOUT)
        out = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr.strip() else "")
    except subprocess.TimeoutExpired:
        return {"ok": False, "out": f"(timed out after {TIMEOUT:.0f}s — run heavy models from the CLI)"}
    return {"ok": p.returncode == 0, "out": out or "(no output)", "secs": round(time.time() - t0, 1)}


PAGE = """<!doctype html><html><head><meta charset=utf-8><title>White Box V2 — geometry + structure</title>
<style>
 :root{--bg:#0b0f14;--card:#121821;--edge:#223042;--ink:#d7dde5;--hi:#eaf2ff;--dim:#8aa0b8;--acc:#1b6feb}
 *{box-sizing:border-box}
 body{background:var(--bg);color:var(--ink);font:14px/1.55 ui-monospace,Menlo,Consolas,monospace;margin:0;padding:24px}
 h1{font-size:19px;margin:0 0 4px;color:var(--hi)}.sub{color:var(--dim);margin:0 0 18px;max-width:70ch}
 h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:#7f93a8;margin:22px 0 10px;
    border-bottom:1px solid var(--edge);padding-bottom:6px}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
 .card{background:var(--card);border:1px solid var(--edge);border-radius:10px;padding:14px;display:flex;flex-direction:column}
 .t{font-weight:600;color:var(--hi)}.d{color:#9fb2c8;font-size:12.5px;margin:6px 0 10px;flex:1}
 .row{display:flex;gap:8px;align-items:center}
 input{flex:1;min-width:0;background:#0a0e13;border:1px solid #1b2635;border-radius:7px;color:#bcd,var(--ink);
   padding:6px 8px;font:12px ui-monospace,monospace}
 button{background:var(--acc);color:#fff;border:0;border-radius:7px;padding:7px 13px;cursor:pointer;font:inherit;white-space:nowrap}
 button:hover{background:#2f81f7}button:disabled{background:#2a3646;cursor:wait}
 pre{white-space:pre-wrap;background:#0a0e13;border:1px solid #1b2635;border-radius:8px;padding:10px;
     margin:10px 0 0;max-height:360px;overflow:auto;font-size:12px;color:#c8d4e2;display:none}
 .meta{color:#6f8296;font-size:12px;margin-top:6px}.runall{margin:0 0 6px}
</style></head><body>
<h1>White Box V2 &mdash; geometry + structure</h1>
<p class=sub>the fable_* suite, surfaced. read-only reads of a model's stored geometry &amp; structure &mdash; no inference.
each Run is an ending sandboxed child; the server stays flat. edit the args box, then Run. defaults point at the clean control.</p>
<div class=runall><button onclick="runAll()">Run all (geometry)</button></div>
<div id=root></div>
<script>
const TOOLS = __TOOLS__; const GROUPS = __GROUPS__;
const root = document.getElementById('root');
for(const [g,label] of GROUPS){
  const h=document.createElement('h2'); h.innerHTML=label; root.appendChild(h);
  const grid=document.createElement('div'); grid.className='grid'; root.appendChild(grid);
  for(const t of TOOLS.filter(x=>x.group===g)){
    const c=document.createElement('div'); c.className='card';
    c.innerHTML=`<div class=t>${t.title}</div><div class=d>${t.desc}</div>
      <div class=row><input id="a_${t.mod}" value="${t.args.replace(/"/g,'&quot;')}" placeholder="args (optional)">
      <button id="b_${t.mod}" onclick="run('${t.mod}')">Run</button></div>
      <span class=meta id="m_${t.mod}"></span><pre id="o_${t.mod}"></pre>`;
    grid.appendChild(c);
  }
}
async function run(mod){
  const b=document.getElementById('b_'+mod), o=document.getElementById('o_'+mod),
        m=document.getElementById('m_'+mod), a=document.getElementById('a_'+mod);
  b.disabled=true; b.textContent='Running…'; m.textContent='';
  try{
    const r=await fetch('/run?tool='+mod+'&args='+encodeURIComponent(a.value)); const j=await r.json();
    o.style.display='block'; o.textContent=j.out||'(no output)';
    m.textContent=(j.ok?'✓ ':'✗ ')+(j.secs!=null?j.secs+'s':'');
  }catch(e){ o.style.display='block'; o.textContent='error: '+e; }
  b.disabled=false; b.textContent='Run';
}
async function runAll(){ for(const t of TOOLS.filter(x=>x.group==='geometry')){ await run(t.mod); } }
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            tools = [{"mod": m, "title": t, "desc": d, "args": da, "group": g} for (m, t, d, _, da, g) in TOOLS]
            page = PAGE.replace("__TOOLS__", json.dumps(tools)).replace("__GROUPS__", json.dumps(GROUPS))
            self._send(200, page); return
        if u.path == "/run":
            q = parse_qs(u.query); mod = (q.get("tool") or [""])[0]; argstr = (q.get("args") or [""])[0]
            if mod not in [x[0] for x in TOOLS]:
                self._send(400, json.dumps({"ok": False, "out": "unknown tool"}), "application/json"); return
            self._send(200, json.dumps(run_tool(mod, argstr)), "application/json"); return
        self._send(404, "not found")


if __name__ == "__main__":
    probe = socket.socket()
    if probe.connect_ex(("127.0.0.1", PORT)) == 0:
        print(f"White Box V2 already running on http://127.0.0.1:{PORT}"); raise SystemExit(0)
    probe.close()
    print(f"White Box V2 on http://127.0.0.1:{PORT}  (surfaces every fable_* tool; read-only; editable args)")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
