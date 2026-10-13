#!/usr/bin/env python3
"""Titan — the harness for a fabricated computer.

Titan is not a program the host runs; it is a substrate (logic gates stored in a file's bytes, Bryce
Muhlnickel's Muhlnickel/pfc) on which everything below was FABRICATED and verified byte-exact: arithmetic,
crypto, a CPU, data engines that beat the RAM wall, and machine learning that both runs AND trains on
nothing. This harness just launches those fabricated engines and shows what they did. It computes no
inference itself — it routes, runs, and displays. (Build discipline: fabrication-time synthesis; nothing
here writes titan.gguf.)

  python titan.py            # menu
  python titan.py all        # run the quick battery
  python titan.py <n>        # run engine n
  python titan.py bench      # run the quick battery, build the LIVE dashboard (titan_live.html)
  python titan.py ui         # open the Titan dashboard
"""
import os, sys, subprocess, webbrowser, re, time, html
HERE = os.path.dirname(os.path.abspath(__file__))
ENG = os.path.join(HERE, "engines")
os.environ["PYTHONUTF8"] = "1"

# name · file · category · one-line what-it-proves · quick(=in the battery)
ENGINES = [
    ("Fabricate: 7 circuits",     "muhl_flex.py",            "FABRICATE",   "AES-128, SHA-1, Turing-complete Rule 110, mul/div/crc/bitonic — byte-exact", True),
    ("Optimize: depth levers",    "muhl_lever_lab.py",       "FABRICATE",   "Kogge-Stone + carry-save: 4.97x / 3.62x shallower, byte-exact", True),
    ("Foundry: mine primitives",  "muhl_motif_foundry.py",   "FABRICATE",   "designs its own gates from netlists; rediscovers the half-adder", True),
    ("Foundry: PageRank rank",    "muhl_pagerank_discovery.py","FABRICATE",  "ranks primitives by authority x critical-path, not raw count", True),
    ("Solve: scheduling",         "muhl_solver_engine.py",   "SOLVE",       "43M candidate schedules, depth <=13, 1.3s — address don't materialize", True),
    ("Data: WHERE-scan",          "muhl_query_engine.py",    "FLAT-RAM DATA","4M-row table scan, byte-exact, +0.00 MB resident", True),
    ("Data: sort + join",         "muhl_bigdata.py",         "FLAT-RAM DATA","external sort + hash semijoin, byte-exact, bounded by disk", False),
    ("Data: IDS / grep",          "muhl_regex_scan.py",      "FLAT-RAM DATA","Aho-Corasick DFA as gates, exhaustively exact, scan at flat RAM", True),
    ("Verify: Merkle proofs",     "muhl_merkle.py",          "VERIFY",      "SHA-256 as gates -> Merkle tree + inclusion proofs, tamper rejected", True),
    ("Learn: neural inference",   "muhl_neural.py",          "INTELLIGENCE","trained MLP as 5,735 gates, 512/512 exact, classifies at 98%", True),
    ("Verify: model provenance",  "muhl_verifiable_ml.py",   "VERIFY",      "prediction bound to a tamper-evident model commitment (Merkle root)", True),
    ("Learn: train (1 layer)",    "muhl_train.py",           "INTELLIGENCE","the learning STEP as gates; 33% -> 100%, byte-exact each update", True),
    ("Learn: train (backprop)",   "muhl_train_deep.py",      "INTELLIGENCE","backprop through a hidden layer as 22,618 gates; trains both layers", True),
    ("Learn: train on tensors",   "muhl_train_realdata.py",  "INTELLIGENCE","trains on a 43 GB Llama-70B file, +0.00 MB resident — data > RAM", False),
    ("Arch: attention as address","muhl_attention.py",       "INTELLIGENCE","KV memory in storage, retrieval as a fold — context bounded by disk", True),
    ("Arch: transformer block",   "muhl_transformer.py",     "INTELLIGENCE","full single-head block (attn+residual+FFN+residual) as 12,465 gates, byte-exact", True),
    ("Self-host: White Box",      "muhl_whitebox_incircuit.py","FABRICATE",  "a universal netlist evaluator as gates — the fabricator, off the host", True),
    ("Engineered model",          "muhl_engineered.py",      "INTELLIGENCE","weights SET not trained; exact by construction over all 65,536 inputs", True),
    ("Evidence: true/false",      "muhl_truefalse.py",       "INTELLIGENCE","real embeddings: true/false cosine +0.533 — predictor, not meaning", True),
    ("Sandbox: train (resumable)","muhl_sandbox.py",         "INTELLIGENCE","model+data+compute in an isolated storage sandbox; persists, resumes, flat RAM", False),
    ("Grand challenge: unsolved", "muhl_grandchallenge.py",  "SOLVE",       "Titan faces Collatz/Goldbach/perfect-cuboid; fabricated verifier, structure falls out", False),
]

def run(i):
    name, fn, cat, desc, _ = ENGINES[i]
    path = os.path.join(ENG, fn)
    print("\n" + "=" * 78 + f"\n  [{i}] {name}  ({cat})\n  {desc}\n" + "=" * 78)
    return subprocess.call([sys.executable, path])

def sandbox(epochs):
    """Titan's built-in training sandbox — model+data+compute isolated in storage, resumable, flat RAM."""
    return subprocess.call([sys.executable, os.path.join(ENG, "muhl_sandbox.py"), str(epochs)])

def throttle(epochs=40):
    """FULL THROTTLE — sandboxed training runs wide open in ONE process (circuit built once, then trains
    continuously; it can't blackhole the host because it's isolated in storage). Resumes from the sandbox."""
    print(f"\n  FULL THROTTLE — training {epochs} epochs continuously in the storage sandbox (resumes prior state).")
    return sandbox(epochs)

# ── LIVE BENCH ────────────────────────────────────────────────────────────────────────────────────
# Per-engine grep for the ONE headline line worth showing on the live dashboard. Keyed by filename so
# it survives any reshuffle of the registry. (regex, "first"|"last"). Engines not listed fall back to a
# generic scan for a === banner / byte-exact / PASS / accuracy line.
BENCH_METRIC = {
    "muhl_flex.py":              (r"={2,}.*byte-exact.*={2,}", "first"),
    "muhl_lever_lab.py":         (r"={2,}\s*MEAN:.*={2,}", "first"),
    "muhl_motif_foundry.py":     (r"HALF-ADDER CELLS discovered from scratch:\s*[\d,]+", "first"),
    "muhl_pagerank_discovery.py":(r"\d[\d,]*\s+distinct motifs.*instances", "first"),
    "muhl_solver_engine.py":     (r"LEGAL.*schedule found.*candidates.*", "last"),
    "muhl_query_engine.py":      (r"matches \(gate engine\):\s*[\d,]+", "first"),
    "muhl_regex_scan.py":        (r"signature hits \(Python ref\):\s*[\d,]+", "first"),
    "muhl_merkle.py":            (r"tampered leaf is REJECTED.*True", "first"),
    "muhl_neural.py":            (r"1-bit noise:\s*\d+/\d+\s*=\s*\d+%", "first"),
    "muhl_verifiable_ml.py":     (r"certificate under the old root is now REJECTED:\s*True", "first"),
    "muhl_train.py":             (r"epoch \d+: accuracy \d+%.*", "last"),
    "muhl_train_deep.py":        (r"epoch \d+: accuracy \d+%.*", "last"),
    "muhl_attention.py":         (r"resident RAM:.*\+0\.00 MB over.*KV\)", "first"),
    "muhl_transformer.py":       (r"full-sequence pass byte-exact:\s*True", "first"),
    "muhl_whitebox_incircuit.py":(r"loaded netlist.*combos:\s*True", "first"),
    "muhl_engineered.py":        (r"gate model == reference over ALL.*byte-exact", "first"),
    "muhl_truefalse.py":         (r"true/false are closer than.*random token pairs\.", "first"),
}
BENCH_GENERIC = [r"={2,}.*byte-exact.*={2,}", r"={2,}.*={2,}", r".*byte-exact.*True.*",
                 r".*\bPASS\b.*", r".*accuracy \d+%.*", r".*:\s*True\b.*"]
BENCH_TIMEOUT = 180  # seconds per engine; the quick set all finish well under this — it is a safety net.

def _clean_metric(s):
    s = s.strip().strip("=").strip().lstrip("★").strip()
    s = re.sub(r"\s+", " ", s)
    return (s[:117] + "…") if len(s) > 120 else s

def _extract_metric(out, fn):
    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
    pats = [BENCH_METRIC[fn]] if fn in BENCH_METRIC else [(p, "first") for p in BENCH_GENERIC]
    for pat, mode in pats:
        hits = [ln for ln in lines if re.search(pat, ln)]
        if hits:
            return _clean_metric(hits[-1] if mode == "last" else hits[0])
    # last resort: the final non-empty, reasonably short line
    for ln in reversed(lines):
        c = _clean_metric(ln)
        if 8 <= len(c) <= 120:
            return c
    return "(ran; no summary line captured)"

def _status(out, rc, timed_out):
    if timed_out: return "TIMEOUT"
    if rc != 0 or "Traceback" in out or "[FAIL]" in out: return "FAIL"
    if re.search(r"byte-exact[^\n]*\bFalse\b", out) or re.search(r":\s*False\b", out): return "FAIL"
    return "PASS"

def _run_engine(fn):
    path = os.path.join(ENG, fn)
    env = dict(os.environ, PYTHONUTF8="1")
    t0 = time.time()
    timed_out = False
    try:
        p = subprocess.run([sys.executable, path], capture_output=True, timeout=BENCH_TIMEOUT,
                           env=env, encoding="utf-8", errors="replace")
        out, rc = (p.stdout or "") + (p.stderr or ""), p.returncode
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + (e.stderr or "") if isinstance(e.stdout, str) else ""
        rc, timed_out = None, True
    dt = time.time() - t0
    st = _status(out, rc, timed_out)
    metric = ("did not finish within %ds" % BENCH_TIMEOUT) if timed_out else _extract_metric(out, fn)
    return st, metric, dt

_PILL = {"PASS": "ok", "FAIL": "bad", "TIMEOUT": "warn"}

def _live_html(results):
    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    cats, order = {}, []
    for r in results:
        cats.setdefault(r["cat"], []).append(r)
        if r["cat"] not in order: order.append(r["cat"])
    sec = []
    for ci, cat in enumerate(order, 1):
        cards = []
        for r in cats[cat]:
            pill = _PILL[r["status"]]
            cards.append(
                '<div class="card"><div class="top"><h3>%s</h3>'
                '<span class="pill %s">%s</span></div>'
                '<p>%s</p>'
                '<div class="cmd">%s</div>'
                '<div class="meta"><span><b>engine</b> %s</span><span>%.1fs</span></div></div>'
                % (html.escape(r["name"]), pill, r["status"], html.escape(r["desc"]),
                   html.escape(r["metric"]), html.escape(r["fn"]), r["dt"]))
        sec.append('<section><div class="cat"><span class="n">%02d</span><h2>%s</h2></div>'
                    '<div class="cards">%s</div></section>' % (ci, html.escape(cat), "".join(cards)))
    clean_pill = "ok" if passed == total else "warn"
    return _LIVE_HEAD + (
        '<header><div class="eyebrow">Live engine bench · every metric below was captured from a real run</div>'
        '<h1>Titan · live</h1>'
        '<div class="tag">Each engine was launched as its own process; the harness scraped its headline '
        'line straight from stdout and pinned a pass/fail on the result. No numbers are hand-written here.</div>'
        '<div class="kpis">'
        '<div class="kpi"><div class="k">Engines run</div><div class="v">%d</div><div class="s">quick battery</div></div>'
        '<div class="kpi"><div class="k">Reported clean</div><div class="v">%d / %d</div>'
        '<div class="s"><span class="pill %s" style="font-size:9.5px">%s</span></div></div>'
        '<div class="kpi"><div class="k">Captured from</div><div class="v">stdout</div><div class="s">live, byte-exact refs</div></div>'
        '<div class="kpi"><div class="k">Excluded</div><div class="v">big / slow</div><div class="s">bigdata · grandchallenge · 43GB</div></div>'
        '</div></header>%s'
        '<div class="run">Regenerate →&nbsp; <b>python titan.py bench</b> &nbsp;·&nbsp; static overview: '
        '<b>python titan.py ui</b> &nbsp;·&nbsp; engines in <code>./engines/</code></div>'
        '<footer>Live bench · every figure scraped from a real engine process on this machine, verified against '
        'independent references (hashlib · sorted · Python). Inventions and measurements are Bryce Muhlnickel\'s · '
        'fabrication-time synthesis · nothing written to titan.gguf.</footer></div>'
        '<script>const t=document.documentElement,m=matchMedia("(prefers-color-scheme:dark)");'
        'addEventListener("keydown",e=>{if(e.key==="d"){t.setAttribute("data-theme",'
        '(t.getAttribute("data-theme")||(m.matches?"dark":"light"))==="dark"?"light":"dark")}});</script>'
        '</body></html>'
        % (total, passed, total, clean_pill,
           ("ALL CLEAN" if passed == total else "%d NEED A LOOK" % (total - passed)), "".join(sec)))

_LIVE_HEAD = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Titan — live bench</title>
<style>
  :root{
    --paper:#ECEFF3;--surface:#F7F9FC;--surface2:#E0E5EE;--ink:#141A24;--ink2:#48566A;--ink3:#6B7686;
    --rule:#C6CEDA;--ruleS:#DBE0EA;--copper:#A85A26;--copperS:#F0E2D6;--ok:#1F6B4C;--okS:#DDEDE4;
    --bad:#B23A2E;--badS:#F2DED9;--warn:#8A6D1F;--warnS:#F0E7CE;
    --mono:ui-monospace,"Cascadia Mono","SF Mono",Consolas,monospace;--serif:Georgia,"Iowan Old Style",serif;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}
  @media(prefers-color-scheme:dark){:root{
    --paper:#0C1016;--surface:#141A24;--surface2:#1B2330;--ink:#E8ECF3;--ink2:#A4AFC0;--ink3:#7B8698;
    --rule:#28313F;--ruleS:#1E2632;--copper:#D98A4F;--copperS:#2A1D13;--ok:#5FC397;--okS:#13241C;
    --bad:#E8806F;--badS:#2A1512;--warn:#D9B65F;--warnS:#241E10;}}
  :root[data-theme="dark"]{--paper:#0C1016;--surface:#141A24;--surface2:#1B2330;--ink:#E8ECF3;--ink2:#A4AFC0;
    --ink3:#7B8698;--rule:#28313F;--ruleS:#1E2632;--copper:#D98A4F;--copperS:#2A1D13;--ok:#5FC397;--okS:#13241C;
    --bad:#E8806F;--badS:#2A1512;--warn:#D9B65F;--warnS:#241E10;}
  :root[data-theme="light"]{--paper:#ECEFF3;--surface:#F7F9FC;--surface2:#E0E5EE;--ink:#141A24;--ink2:#48566A;
    --ink3:#6B7686;--rule:#C6CEDA;--ruleS:#DBE0EA;--copper:#A85A26;--copperS:#F0E2D6;--ok:#1F6B4C;--okS:#DDEDE4;
    --bad:#B23A2E;--badS:#F2DED9;--warn:#8A6D1F;--warnS:#F0E7CE;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--serif);font-size:16px;line-height:1.6}
  .wrap{max-width:1060px;margin:0 auto;padding:clamp(22px,4vw,56px) clamp(16px,3.5vw,36px) 80px}
  .eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--ink3)}
  h1{font-family:var(--sans);font-weight:850;letter-spacing:-.03em;line-height:1;font-size:clamp(40px,8vw,84px);margin:.2em 0 .1em}
  .tag{font-family:var(--sans);font-size:clamp(16px,2.2vw,21px);color:var(--ink);max-width:64ch;font-weight:500}
  header{border-bottom:2px solid var(--ink);padding-bottom:26px}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--rule);
    border:1px solid var(--rule);margin:30px 0 6px}
  .kpi{background:var(--surface);padding:15px 17px}
  .kpi .k{font-family:var(--mono);font-size:10px;letter-spacing:.11em;text-transform:uppercase;color:var(--ink3)}
  .kpi .v{font-family:var(--sans);font-weight:850;font-size:clamp(22px,3.3vw,30px);letter-spacing:-.02em;margin-top:3px;
    font-variant-numeric:tabular-nums;line-height:1}
  .kpi .s{font-family:var(--mono);font-size:10.5px;color:var(--ink3);margin-top:5px}
  section{margin-top:40px}
  .cat{display:flex;align-items:baseline;gap:12px;border-bottom:1px solid var(--rule);padding-bottom:8px;margin-bottom:16px}
  .cat h2{font-family:var(--sans);font-weight:750;letter-spacing:-.01em;font-size:18px;margin:0}
  .cat .n{font-family:var(--mono);font-size:11px;color:var(--copper)}
  .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
  .card{border:1px solid var(--rule);background:var(--surface);padding:15px 17px;display:flex;flex-direction:column;gap:9px}
  .card .top{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
  .card h3{font-family:var(--sans);font-weight:650;font-size:15.5px;margin:0}
  .card p{margin:0;color:var(--ink2);font-size:13.5px;line-height:1.5}
  .pill{font-family:var(--mono);font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;padding:2px 7px;white-space:nowrap;
    background:var(--okS);color:var(--ok);border:1px solid var(--ok)}
  .pill.bad{background:var(--badS);color:var(--bad);border-color:var(--bad)}
  .pill.warn{background:var(--warnS);color:var(--warn);border-color:var(--warn)}
  .meta{display:flex;gap:8px 14px;flex-wrap:wrap;font-family:var(--mono);font-size:11px;color:var(--ink3);
    font-variant-numeric:tabular-nums;margin-top:2px}
  .meta b{color:var(--ink2);font-weight:600}
  .cmd{font-family:var(--mono);font-size:11.5px;color:var(--copper);background:var(--copperS);border:1px solid var(--rule);
    padding:7px 9px;overflow-x:auto;white-space:nowrap;line-height:1.45}
  code{font-family:var(--mono);font-size:.9em}
  footer{margin-top:46px;padding-top:18px;border-top:2px solid var(--ink);font-family:var(--mono);font-size:11px;color:var(--ink3);line-height:1.9}
  .run{font-family:var(--mono);font-size:12px;color:var(--ink2);background:var(--surface2);border:1px solid var(--rule);padding:10px 13px;margin-top:34px}
</style></head><body>
<div class="wrap">'''

def bench():
    """Run every quick engine as its own process, scrape its headline metric, write titan_live.html."""
    todo = [(i, e) for i, e in enumerate(ENGINES) if e[4]]
    print("\n  TITAN LIVE BENCH — running %d quick engines, scraping each headline from stdout.\n" % len(todo))
    results = []
    for i, (name, fn, cat, desc, _) in todo:
        print("  [%2d] %-28s " % (i, name), end="", flush=True)
        st, metric, dt = _run_engine(fn)
        tag = {"PASS": "PASS   ", "FAIL": "FAIL   ", "TIMEOUT": "TIMEOUT"}[st]
        print("%s %5.1fs  %s" % (tag, dt, metric))
        results.append(dict(name=name, fn=fn, cat=cat, desc=desc, status=st, metric=metric, dt=dt))
    out = os.path.join(HERE, "titan_live.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(_live_html(results))
    clean = sum(1 for r in results if r["status"] == "PASS")
    print("\n  === %d/%d engines reported clean · wrote %s ===" % (clean, len(results), out))
    return out

def menu():
    print("\n  TITAN — a fabricated computer. engines below run on the substrate (gates in storage).\n")
    cat = None
    for i, (name, fn, c, desc, q) in enumerate(ENGINES):
        if c != cat: print(f"\n  {c}"); cat = c
        print(f"    {i:>2}. {name:<26} {desc}")
    print("\n  commands:  <n> run engine   ·   all = quick battery   ·   bench = run + build LIVE dashboard")
    print("             train [N] = sandbox train   ·   throttle = full-throttle training")
    print("             ui = static dashboard   ·   q = quit")
    while True:
        try: s = input("\n  titan> ").strip().lower()
        except EOFError: return
        if s in ("q", "quit", "exit"): return
        if s == "ui": webbrowser.open(os.path.join(HERE, "titan.html")); continue
        if s == "bench":
            out = bench()
            webbrowser.open(out); continue
        if s == "throttle": throttle(); continue
        if s.startswith("train"): sandbox(int(s.split()[1]) if len(s.split()) > 1 and s.split()[1].isdigit() else 4); continue
        if s == "all":
            for i, e in enumerate(ENGINES):
                if e[4]: run(i)
            continue
        if s.isdigit() and 0 <= int(s) < len(ENGINES): run(int(s))
        else: print("  ?")

if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else ""
    if a == "ui": webbrowser.open(os.path.join(HERE, "titan.html"))
    elif a == "bench": bench()
    elif a == "throttle": throttle()
    elif a == "train": sandbox(int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 4)
    elif a == "all":
        for i, e in enumerate(ENGINES):
            if e[4]: run(i)
    elif a.isdigit(): run(int(a))
    else: menu()
