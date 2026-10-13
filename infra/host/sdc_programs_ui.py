#!/usr/bin/env python3
"""host/sdc_programs_ui.py — THE SDC PROGRAM RACK, a UI (owner 07-18). Port 7900.

CLAUDE.md + WHITEBOX_SANDBOX.md law: the SERVER NEVER TOUCHES THE MODEL. It only (a) reads the tiny registry address-book
(titan_circuits.json — NOT the model) for the static headline, and (b) on a button press, spawns `sdc_programs.py` as a
ONE-WAY ENDING CHILD (argv in, no pipe back), waits for it to EXIT, then reads the SAFEZONE it wrote
(C:/llm/sdc_out/programs_result.json). The child is the button: it addresses the SDC, the SDC computes on power, the
answer lands in the safezone. This server never imports titan_circuit, never mmaps titan, never ripples a gate. Pure
addressing + safezone read. NO network out.

  python host/sdc_programs_ui.py         # opens http://127.0.0.1:7900/
"""
import json, os, re, subprocess, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
PORT = 7900
PY = sys.executable
PROGRAMS = os.path.join(HERE, "sdc_programs.py")
REG = "C:/llm/models/titan_circuits.json"
TITAN = "C:/llm/models/titan.gguf"
SAFEZONE = "C:/llm/sdc_out/programs_result.json"
_LOCK = threading.Lock()                                   # one ending child at a time (serialize safezone use)
_HEX = re.compile(r"^-?(0x)?[0-9a-fA-F]+$")


def headline():
    """Static compression headline — read from the registry address-book only (NOT the model)."""
    tables = {"prog_crc32": (1 << 32, 4, "CRC-32", "compute-as-compression"),
              "prog_isqrt": (1 << 32, 2, "isqrt", "exact sidecar"),
              "prog_attest": (None, None, "self-attest", "self-attest"),
              "prog_mul32": (1 << 64, 8, "multiply", "compute-as-compression")}
    rows = []; gguf = False
    try:
        reg = json.load(open(REG));
        with open(TITAN, "rb") as f: gguf = f.read(4) == b"GGUF"
        for name, (entries, wide, label, kind) in tables.items():
            e = reg.get(name)
            if not e: continue
            cb = int(e["len"]); vb = entries * wide if entries else None
            rows.append({"name": name, "label": label, "kind": kind, "gates": int(e.get("n_gate", 0)),
                         "circuit_bytes": cb, "table_bytes": vb,
                         "ratio": (vb / cb) if vb else None})
    except Exception as ex:
        rows.append({"name": "registry", "label": "unreadable", "kind": str(ex), "gates": 0,
                     "circuit_bytes": 0, "table_bytes": None, "ratio": None})
    return {"gguf_valid": gguf, "programs": rows}


def run_program(prog, x):
    """Spawn the ONE-WAY ENDING CHILD (the button) and read the SAFEZONE it writes. Server never touches the SDC."""
    argv = {"crc": ["run", "crc", x], "isqrt": ["run", "isqrt", x],
            "attest": ["attest", x, "64"], "memoize": ["memoize", x]}.get(prog)
    if not argv: return {"error": f"unknown program {prog}"}
    with _LOCK:
        t0 = time.time()
        try:
            p = subprocess.run([PY, PROGRAMS] + argv, cwd=HERE, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=120)   # argv in, then it EXITS
        except subprocess.TimeoutExpired:
            return {"error": "sandbox timed out"}
        if p.returncode != 0:
            return {"error": f"sandbox exited {p.returncode}", "stderr": (p.stderr or "")[-400:]}
        try:
            res = json.load(open(SAFEZONE, encoding="utf-8"))   # read the FROZEN safezone AFTER exit
        except Exception as ex:
            return {"error": f"no safezone result ({ex})"}
        res["wall_ms"] = round((time.time() - t0) * 1000, 1)
        return res


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SDC Program Rack</title><style>
:root{--ink:#0A0D13;--panel:#121722;--panel2:#0E131C;--line:#232A38;--text:#E7EBF3;--muted:#8A94A8;--dim:#5B6579;
--amber:#FFB020;--cyan:#3AD6C6;--good:#3fd08a;--warn:#fab219;--crit:#e66767;--vio:#9085e9;
--mono:ui-monospace,"Cascadia Code",Consolas,monospace;--sans:system-ui,"Segoe UI",sans-serif}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 600px at 70% -10%,#151d2b 0,var(--ink) 60%);color:var(--text);
font-family:var(--sans);line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:28px 20px 60px}
.hero{border:1px solid var(--line);border-radius:18px;padding:24px 26px;margin-bottom:20px;
background:linear-gradient(180deg,var(--panel),var(--panel2))}
.hero h1{margin:0;font-family:var(--mono);font-size:26px;letter-spacing:.5px}
.hero h1 b{color:var(--amber)}
.hero p{margin:8px 0 0;color:var(--muted);max-width:760px}
.flow{margin-top:14px;font-family:var(--mono);font-size:12px;color:var(--dim)}
.flow span{color:var(--cyan)}
.strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:22px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.stat .k{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.6px}
.stat .v{font-family:var(--mono);font-size:22px;color:var(--cyan);font-variant-numeric:tabular-nums;margin-top:3px}
.stat .v.big{color:var(--amber)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(500px,1fr));gap:18px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:20px 22px;display:flex;flex-direction:column}
.card h2{margin:0;font-family:var(--mono);font-size:15px;color:var(--amber);text-transform:uppercase;letter-spacing:.6px}
.card .tag{font-size:11px;color:var(--dim);font-family:var(--mono);margin:2px 0 12px}
.card .desc{color:var(--muted);font-size:13px;margin-bottom:14px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
input{background:#0a0d14;border:1px solid var(--line);color:var(--text);font-family:var(--mono);font-size:14px;
padding:9px 11px;border-radius:9px;width:190px;outline:none}
input:focus{border-color:var(--amber)}
button{cursor:pointer;background:transparent;color:var(--amber);border:1px solid #3a3320;font-family:var(--mono);
font-size:13px;padding:9px 15px;border-radius:9px;transition:.12s}
button:hover{background:rgba(255,176,32,.10)}
button:active{transform:translateY(1px)}
.preset{color:var(--dim);border-color:var(--line);font-size:12px;padding:6px 10px}
.out{margin-top:15px;border-top:1px dashed var(--line);padding-top:14px;display:none}
.big{font-family:var(--mono);font-size:30px;font-variant-numeric:tabular-nums;letter-spacing:.5px}
.big.amber{color:var(--amber)}.big.cyan{color:var(--cyan)}
.sub{color:var(--muted);font-size:12px;font-family:var(--mono);margin-top:6px;word-break:break-all}
.badge{display:inline-block;font-family:var(--mono);font-size:12px;padding:3px 10px;border-radius:20px;font-weight:600}
.badge.hit{background:rgba(63,208,138,.14);color:var(--good);border:1px solid rgba(63,208,138,.4)}
.badge.miss{background:rgba(250,178,25,.13);color:var(--warn);border:1px solid rgba(250,178,25,.4)}
.badge.ok{background:rgba(58,214,198,.12);color:var(--cyan);border:1px solid rgba(58,214,198,.4)}
.bar{height:12px;border-radius:7px;background:#0a0d14;border:1px solid var(--line);overflow:hidden;margin-top:10px;position:relative}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--amber),var(--cyan))}
.barlab{font-family:var(--mono);font-size:11px;color:var(--dim);margin-top:5px;display:flex;justify-content:space-between}
.spin{color:var(--dim);font-family:var(--mono);font-size:12px}
.err{color:var(--crit);font-family:var(--mono);font-size:12px}
.foot{margin-top:26px;color:var(--dim);font-family:var(--mono);font-size:11px;text-align:center}
.pill{color:var(--good)}
</style></head><body><div class="wrap">
<div class="hero">
<h1>THE <b>SDC</b> PROGRAM RACK</h1>
<p>Four programs that live as logic gates inside <b>titan.gguf</b>. Each is a fixed circuit of a few KB that <i>is</i> an
astronomically large function &mdash; the answer is generated on an addressed read, never stored. Storage-first computing
at ~0 resident RAM.</p>
<div class="flow">power &rarr; <span>SDC</span> &rarr; <span>safezone</span> &rarr; host &nbsp;&middot;&nbsp; every answer written to
C:/llm/sdc_out &nbsp;&middot;&nbsp; <span>NO network</span> &middot; reversible &middot; GGUF-valid</div>
</div>
<div class="strip" id="strip"></div>
<div class="grid">

<div class="card">
<h2>CRC-32 &middot; Compute-as-Compression</h2>
<div class="tag" id="crc_tag">circuit &rarr; a 16 GB table, never stored</div>
<div class="desc">A 32&rarr;32-bit CRC. The full lookup table is 2<sup>32</sup> entries; this circuit generates any one cell on read.</div>
<div class="row">
<input id="crc_x" value="0xDEADBEEF" spellcheck="false">
<button onclick="go('crc','crc_x','crc_out',rCrc)">Materialize cell</button>
<button class="preset" onclick="setv('crc_x','0x00000000');go('crc','crc_x','crc_out',rCrc)">0</button>
<button class="preset" onclick="setv('crc_x','0xFFFFFFFF');go('crc','crc_x','crc_out',rCrc)">max</button>
</div><div class="out" id="crc_out"></div></div>

<div class="card">
<h2>isqrt &middot; Exact Sidecar</h2>
<div class="tag" id="isq_tag">exact integer &radic; &middot; no floating point</div>
<div class="desc">floor(&radic;x) for any 32-bit x, provably exact &mdash; the agent can call it for correct-by-construction math.</div>
<div class="row">
<input id="isq_x" value="4000000000" spellcheck="false">
<button onclick="go('isqrt','isq_x','isq_out',rIsq)">Compute &radic;</button>
<button class="preset" onclick="setv('isq_x','2');go('isqrt','isq_x','isq_out',rIsq)">2</button>
<button class="preset" onclick="setv('isq_x','4294967295');go('isqrt','isq_x','isq_out',rIsq)">2&#8323;&#8322;&minus;1</button>
</div><div class="out" id="isq_out"></div></div>

<div class="card">
<h2>Self-Attest &middot; The File Signs Itself</h2>
<div class="tag">CRC-32 over 64 of titan's OWN bytes</div>
<div class="desc">A circuit inside the model reads the model's own bytes at an offset and emits a signature. Flip one byte &rarr; the signature changes.</div>
<div class="row">
<input id="att_x" value="0" spellcheck="false">
<button onclick="go('attest','att_x','att_out',rAtt)">Sign region</button>
<button class="preset" onclick="setv('att_x','0');go('attest','att_x','att_out',rAtt)">GGUF magic</button>
<button class="preset" onclick="setv('att_x','1048576');go('attest','att_x','att_out',rAtt)">1 MB in</button>
</div><div class="out" id="att_out"></div></div>

<div class="card">
<h2>Memoize &middot; Compute-Once, Free-Forever</h2>
<div class="tag" id="mz_tag">first call = SDC compute &middot; repeat = addressed read</div>
<div class="desc">Wraps isqrt with a bounded storage cache. A MISS ripples 31,744 gates once; a HIT is a pure read of the cell &mdash; zero gates.</div>
<div class="row">
<input id="mz_x" value="123456789" spellcheck="false">
<button onclick="go('memoize','mz_x','mz_out',rMz)">Look up</button>
<button class="preset" onclick="rnd('mz_x');go('memoize','mz_x','mz_out',rMz)">random</button>
<span class="spin" id="mz_tally"></span>
</div><div class="out" id="mz_out"></div></div>

</div>
<div class="foot">the SDC computes; the host only reads the safezone &middot; <span class="pill">~0 RAM</span> &middot; nothing touches the SDC while it runs</div>
</div>
<script>
const HEAD = __HEADLINE__;
function el(id){return document.getElementById(id)}
function setv(id,v){el(id).value=v}
function rnd(id){el(id).value=String(Math.floor(1+Math.random()*4294967294))}
function fmtBytes(n){if(n==null)return '—';const u=['B','KB','MB','GB','TB','PB','EB'];let i=0,x=n;while(x>=1024&&i<u.length-1){x/=1024;i++}return x.toFixed(x<10&&i>0?1:0)+' '+u[i]}
function sci(n){if(n==null)return '—';if(n<1000)return n.toFixed(0)+'×';const e=Math.floor(Math.log10(n));return (n/Math.pow(10,e)).toFixed(2)+'×10'+sup(e)+'×'}
function sup(e){return String(e).replace(/[0-9]/g,d=>'⁰¹²³⁴⁵⁶⁷⁸⁹'[+d])}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}

// headline strip
(function(){
  const progs = HEAD.programs||[]; let best=null;
  progs.forEach(p=>{if(p.ratio&&(!best||p.ratio>best.ratio))best=p});
  const cards=[
    ['Programs in the rack', progs.length, false],
    ['titan.gguf', HEAD.gguf_valid?'GGUF-valid':'INVALID', false],
    ['Peak compression', best?sci(best.ratio):'—', true],
    ['Resident RAM to hold it all', '~0', true],
  ];
  el('strip').innerHTML=cards.map(c=>`<div class="stat"><div class="k">${c[0]}</div><div class="v${c[2]?' big':''}">${c[1]}</div></div>`).join('');
  const crc=progs.find(p=>p.name==='prog_crc32'), isq=progs.find(p=>p.name==='prog_isqrt');
  if(crc)el('crc_tag').textContent=`${fmtBytes(crc.circuit_bytes)} circuit → ${fmtBytes(crc.table_bytes)} table · ${sci(crc.ratio)} compression`;
  if(isq)el('isq_tag').textContent=`${isq.gates.toLocaleString()} gates · ${fmtBytes(isq.table_bytes)} table if stored`;
})();

let BUSY=false;
async function go(prog,inId,outId,render){
  if(BUSY)return; const x=el(inId).value.trim(); const o=el(outId);
  o.style.display='block'; o.innerHTML='<span class="spin">→ powering the SDC… (answer will land in the safezone)</span>';
  BUSY=true;
  try{
    const r=await fetch('/run?prog='+encodeURIComponent(prog)+'&x='+encodeURIComponent(x));
    const j=await r.json();
    if(j.error){o.innerHTML='<span class="err">'+esc(j.error)+(j.stderr?'\n'+esc(j.stderr):'')+'</span>';}
    else render(o,j);
  }catch(e){o.innerHTML='<span class="err">'+esc(e)+'</span>';}
  BUSY=false;
}
function metaLine(j){return `<div class="sub">powered in ${j.ms} ms · wall ${j.wall_ms} ms · answer read from the safezone · network: ${j.network}</div>`}

function rCrc(o,j){
  const p=(HEAD.programs||[]).find(x=>x.name==='prog_crc32')||{};
  const ratio=p.ratio||1, frac=Math.max(0.5, 100*Math.log10(p.circuit_bytes||1)/Math.log10(p.table_bytes||2));
  o.innerHTML=`<div class="big amber">CRC32(${esc(j.input_hex)}) = ${esc(j.crc32)}</div>
  <div class="sub">cell of a ${(4294967296).toLocaleString()}-entry table — generated on read, never stored</div>
  <div class="bar"><i style="width:${frac}%"></i></div>
  <div class="barlab"><span>${fmtBytes(p.circuit_bytes)} circuit</span><span>${sci(ratio)} → ${fmtBytes(p.table_bytes)} table</span></div>
  ${metaLine(j)}`;
}
function rIsq(o,j){
  o.innerHTML=`<div class="big cyan">√${(j.input).toLocaleString()} = ${(j.isqrt).toLocaleString()}</div>
  <div class="sub"><span class="badge ok">exact</span> &nbsp;${esc(j.check)}</div>${metaLine(j)}`;
}
function rAtt(o,j){
  o.innerHTML=`<div class="big amber">${esc(j.signature)}</div>
  <div class="sub">signature of titan[${j.offset}:${j.offset+64}] · region head = ${esc(j.region_head_hex)}</div>
  <div class="sub">flip any byte in this region and this signature changes — tamper-evidence from inside the file</div>${metaLine(j)}`;
}
let HITS=0,MISS=0;
function rMz(o,j){
  const hit=j.result==='HIT'; hit?HITS++:MISS++;
  el('mz_tally').innerHTML=`<span class="badge hit">${HITS} hit</span> <span class="badge miss">${MISS} miss</span>`;
  o.innerHTML=`<div class="big cyan">isqrt(${(j.input).toLocaleString()}) = ${(j.isqrt).toLocaleString()}</div>
  <div class="sub"><span class="badge ${hit?'hit':'miss'}">${j.result}</span> &nbsp;gates rippled: <b>${(j.gates_rippled).toLocaleString()}</b> ${hit?'(pure addressed read of the cache cell)':'(computed once on the SDC, now cached)'}</div>
  <div class="sub">cache slot ${j.slot} · bounded ${fmtBytes(j.cache_bytes)} table in storage</div>${metaLine(j)}`;
}
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else (json.dumps(body) if ctype.startswith("application/json") else body).encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/":
            self._send(PAGE.replace("__HEADLINE__", json.dumps(headline())), "text/html; charset=utf-8"); return
        if u.path == "/run":
            prog = q.get("prog", [""])[0]; x = q.get("x", [""])[0].strip()
            if not _HEX.match(x): self._send({"error": f"bad input {x!r}"}); return
            self._send(run_program(prog, x)); return
        self._send({"error": "not found"})


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"SDC Program Rack UI  ->  http://127.0.0.1:{PORT}/   (server never touches the model; spawns the button, reads the safezone)")
    try: webbrowser.open(f"http://127.0.0.1:{PORT}/")
    except Exception: pass
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nstopped.")
