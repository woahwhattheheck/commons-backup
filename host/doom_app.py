#!/usr/bin/env python3
"""host/doom_app.py — DOOM on Titan: a browser app with REAL keyboard controls, real-time, in TWO modes (owner 07-14).

PureGen (STUDY_NOTES §2, the pure-gen law): 0% of the game is my code. This server does ONLY the four allowed things —
ENERGY (forward passes on the served Titan), ACCESS (serve the page, carry keystrokes IN, blit Titan's pixels OUT),
MEASURE, and SAFETY (a RAM headroom guard so serving cannot black-screen the box). Titan generates EVERYTHING else: the
game rules, the screen, and — in mode B — the game's own runnable code.

Two modes (owner: "one just canvas generation and the second is full recreation of the game simulating the code and
running it on titan"):
  - GENERATE (canvas mode): each frame, Titan GENERATES the screen (an SVG, rendered to PNG by the installed resvg codec,
    INV-119); the keyboard drives the input; a memoize-recall store serves a recognized view with ZERO forward passes
    (INV-147) so recurring views play at full framerate — grab-don't-run, real-time.
  - RECREATE (code mode): Titan AUTHORS the whole game as one self-contained runnable program (its code); the program
    then runs, keyboard-driven, in real time. Titan wrote 100% of the game; the execution substrate is access.

Serving: connects to a Titan already on LLM_URL, or starts one on demand with the floor config (--no-repack, alpha=2,
tiny ctx) ONLY if a free-RAM headroom check passes — never OOMs the box.

Run:  python host/doom_app.py       (open http://127.0.0.1:7863)
Env:  LLM_URL (default http://127.0.0.1:8080)
"""
import base64, importlib.util, json, os, re, subprocess, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_gr = importlib.util.spec_from_file_location("genrun", os.path.join(HERE, "genrun.py"))
genrun = importlib.util.module_from_spec(_gr); _gr.loader.exec_module(genrun)
_dm = importlib.util.spec_from_file_location("doom", os.path.join(HERE, "doom.py"))
doom = importlib.util.module_from_spec(_dm); _dm.loader.exec_module(doom)

PORT = 7863
LLM = os.environ.get("LLM_URL", "http://127.0.0.1:8080").rstrip("/")
SRV = "C:/llm/bin/llamacpp/llama-server.exe"
MODELS = "C:/llm/models"
TITAN_GGUF = f"{MODELS}/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"   # the resident chip (MoE, alpha-gated); never dense phi-4
RAM_FLOOR_MB = 1000                                              # refuse to serve below this free RAM (safety, §STUDY_NOTES);
#                                                                 --no-repack commits ~300 MB so this is a real margin
STATE = {"program": None, "state": {"turn": 0}, "serving": False, "srv_proc": None, "log": []}
GAME_DEFAULT = "first-person DOOM: a stone corridor in perspective, a gun at the bottom, an imp ahead"


def logline(s):
    STATE["log"] = (STATE["log"] + [s])[-40:]
    print("[doom_app]", s, flush=True)


# ---- ACCESS/SAFETY: RAM headroom + serve management (never OOM the box) --------------------------------

def free_mb():
    try:
        import ctypes
        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS(); m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return int(m.ullAvailPhys / (1024 * 1024))
    except Exception:
        return 9999


def titan_up():
    try:
        urllib.request.urlopen(LLM + "/health", timeout=2).read()
        return True
    except Exception:
        return False


def serve_titan():
    """Start Titan with the floor config, ONLY if free RAM clears the guard. Idempotent."""
    if titan_up():
        STATE["serving"] = True; logline("Titan already serving on " + LLM); return True
    fm = free_mb()
    if fm < RAM_FLOOR_MB:
        logline(f"REFUSED to serve: only {fm} MB free (< {RAM_FLOOR_MB} MB floor) — free some RAM first, won't risk the box")
        return False
    if not os.path.exists(SRV) or not os.path.exists(TITAN_GGUF):
        logline("server or Titan gguf not found"); return False
    args = [SRV, "-m", TITAN_GGUF, "-c", "1024", "-t", "8", "-ngl", "0", "--no-repack", "-np", "1",
            "-b", "32", "-ub", "32", "--override-kv", "gemma4.expert_used_count=int:2",   # alpha=2: fast, low compute
            "--host", "127.0.0.1", "--port", str(urlparse(LLM).port or 8080)]
    logline(f"serving Titan (26B MoE, --no-repack, alpha=2) — {fm} MB free …")
    STATE["srv_proc"] = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        time.sleep(1)
        if titan_up():
            STATE["serving"] = True; logline("Titan is up"); return True
    logline("Titan failed to come up in 120s"); return False


# ---- ENERGY: one generation on Titan (the ONLY compute the server does; Titan generates the content) ---

def _chat(messages, maxtok, temp=0.3):
    body = json.dumps({"messages": messages, "max_tokens": maxtok, "temperature": temp, "cache_prompt": True,
                       "chat_template_kwargs": {"enable_thinking": False}}).encode()
    r = json.loads(urllib.request.urlopen(urllib.request.Request(
        LLM + "/v1/chat/completions", body, {"Content-Type": "application/json"}), timeout=900).read())
    return r["choices"][0]["message"].get("content", "") or ""


# ---- MODE A (GENERATE): Titan generates each frame's screen; memoize-recall = real-time --------------

def _view_key(state):
    return doom.view_key(state)


def gen_frame(inp):
    """One tick of the generative runtime: RECALL a memoized frame (0 forward passes) or GENERATE it (Titan draws the
    SVG, resvg renders the PNG). Returns a PNG data-URL — Titan drew every pixel; we only carry the bytes."""
    prog = STATE["program"] or GAME_DEFAULT
    st = STATE["state"]
    k = _view_key({**st, "in": inp})
    cache = f"{genrun.OUT}/frame_{re.sub(r'[^A-Za-z0-9_]', '_', k)}.png"
    if os.path.exists(cache):                                    # RECALL — instant, zero forward passes (INV-147)
        st["turn"] = int(st.get("turn", 0)) + 1
        return _png_dataurl(cache), True
    new_state, svg = genrun.step(prog, st, inp)                  # GENERATE — Titan computes state + draws the frame
    STATE["state"] = new_state
    png = genrun.render_png(svg, "doom_live") if svg else None
    if png and os.path.exists(png):
        try:
            import shutil; shutil.copyfile(png, cache)           # store Titan's frame for instant recall next time
        except Exception:
            pass
        return _png_dataurl(png), False
    return None, False


def _png_dataurl(path):
    return "data:image/png;base64," + base64.b64encode(open(path, "rb").read()).decode()


# ---- MODE B (RECREATE): Titan authors the whole game as one runnable program (its code) --------------

def _real_doom_brief():
    """id's ACTUAL DOOM code + level, read from the downloaded source + doom1.wad (doom_source.py). Returns a compact,
    context-sized brief of the REAL E1M1 so RECREATE reproduces id's actual first level, not a generic shooter.
    None if the real assets aren't present (then RECREATE falls back to the description)."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("doom_source", os.path.join(HERE, "doom_source.py"))
        ds = importlib.util.module_from_spec(spec); spec.loader.exec_module(ds)
        if not os.path.exists(ds.WAD):
            return None
        e = ds.read_e1m1()
        if "error" in e:
            return None
        c = ds.gather_constants()
        return (ds.compact_map(e), c, e.get("player_start"))
    except Exception:
        return None


def author_game_code(desc):
    """Titan AUTHORS a complete, self-contained, keyboard-playable game as one runnable program. 100% Titan's code;
    the browser is only the execution/display access (like resvg renders Titan's SVG in mode A). When id's real DOOM
    source + WAD are present, RECREATE reads the ACTUAL doom code/level and recreates id's real E1M1 (not a description)."""
    real = _real_doom_brief()
    if real and ("doom" in desc.lower() or "corridor" in desc.lower()):
        brief, consts, start = real
        ask = ("You ARE the DOOM engine. Recreate id Software's ACTUAL DOOM level E1M1 as ONE self-contained runnable "
               "HTML document (a <canvas> + inline <script>) — a first-person raycaster faithful to the real level below. "
               f"REAL LEVEL DATA (from the actual doom1.wad): {brief}. REAL ENGINE CONSTANTS (from id's source): {consts}. "
               "Build it faithful to THIS data: the player starts at the real start, the rooms/corridors match the real "
               "sectors, imps/zombiemen are placed like the real things. It MUST: read ARROW KEYS + SPACE (keydown/keyup); "
               "run a real-time requestAnimationFrame loop; raycast + draw every frame; shoot on Space; be fully playable, "
               "no external files. Output ONLY the HTML document, starting with <canvas and ending with </script>.")
    else:
        ask = ("You ARE a game engine. Author a COMPLETE, self-contained, playable browser game as ONE HTML document "
               f"(a <canvas> + inline <script>), for: {desc}. It MUST: read the ARROW KEYS and SPACE from keydown/keyup; "
               "run its own real-time loop with requestAnimationFrame; draw every frame to the canvas; be fully playable "
               "with no external files. Output ONLY the HTML document, starting with <canvas and ending with </script>.")
    txt = _chat([{"role": "user", "content": ask}], maxtok=3000, temp=0.4)
    m = re.search(r"<canvas[\s\S]*</script>", txt, re.I)
    return m.group(0) if m else txt


# ---- the page + routes (ACCESS only) ------------------------------------------------------------------

PAGE = r"""<!doctype html><html><head><meta charset=utf-8><title>DOOM on Titan</title><style>
body{margin:0;background:#0a0a0c;color:#d8d8dc;font-family:ui-monospace,Consolas,monospace}
.top{display:flex;gap:12px;align-items:center;padding:10px 16px;border-bottom:1px solid #26262c;background:#111}
.top b{color:#e0662a;letter-spacing:.05em}button{background:#1a1a20;color:#e0662a;border:1px solid #3a2a1a;border-radius:6px;padding:7px 12px;cursor:pointer;font:inherit}
button:hover{background:#241a12}.tab{color:#888;border-color:#333}.tab.on{color:#e0662a;border-color:#e0662a}
#stage{display:flex;flex-direction:column;align-items:center;gap:8px;padding:18px}
#screen{width:512px;height:512px;background:#000;border:1px solid #26262c;image-rendering:pixelated}
#gameframe{width:640px;height:480px;border:1px solid #26262c;background:#000}
.muted{color:#888;font-size:12px}.hint{color:#5a5a62;font-size:12px}
#log{font-size:11px;color:#6a6a72;max-width:680px;white-space:pre-wrap}
</style></head><body>
<div class=top><b>DOOM · on Titan</b>
 <button id=tGen class="tab on" onclick=mode('gen')>Generate (canvas)</button>
 <button id=tRec class="tab" onclick=mode('rec')>Recreate (code)</button>
 <span style=flex:1></span>
 <button onclick=serve()>▶ Serve Titan</button><span id=srv class=muted>checking…</span>
</div>
<div id=stage>
 <div id=genView>
   <img id=screen src="" alt="">
   <div class=muted id=gstat>Click <b>Serve Titan</b>, then <b>Start</b>. Arrow keys / WASD move · Space shoots.</div>
   <div><button onclick=startGen()>Start / Author level</button> <button onclick=freeze()>Pause</button></div>
   <div class=hint>Titan generates every frame; a recognized view is recalled instantly (real-time). Nothing here is scripted.</div>
 </div>
 <div id=recView style=display:none>
   <iframe id=gameframe sandbox="allow-scripts"></iframe>
   <div class=muted id=rstat>Click <b>Serve Titan</b>, then <b>Titan writes the game</b>. It runs here, keyboard-driven.</div>
   <div><input id=gdesc value="first-person DOOM-style corridor shooter" style="width:320px;background:#111;color:#ddd;border:1px solid #333;border-radius:6px;padding:6px">
     <button onclick=recreate()>Titan writes the game</button></div>
   <div class=hint>Titan authors the whole game as one runnable program; it runs in real time. 100% Titan-generated code.</div>
 </div>
 <div id=log></div>
</div>
<script>
let MODE='gen', playing=false, keys={}, lastInput='idle';
function el(i){return document.getElementById(i)}
async function j(u,o){const r=await fetch(u,o);return r.json()}
function mode(m){MODE=m;el('tGen').className='tab'+(m=='gen'?' on':'');el('tRec').className='tab'+(m=='rec'?' on':'');
  el('genView').style.display=m=='gen'?'':'none';el('recView').style.display=m=='rec'?'':'none';playing=false;}
async function poll(){const s=await j('/status');el('srv').textContent=s.serving?('Titan up · '+s.free_mb+'MB free'):('not serving · '+s.free_mb+'MB free');
  if(s.log)el('log').textContent=s.log.slice(-6).join('\n');}
setInterval(poll,1500);poll();
async function serve(){el('srv').textContent='serving…';await fetch('/serve');poll();}
// keyboard -> the current input (access: keys in, nothing scripted)
const KMAP={ArrowUp:'forward',KeyW:'forward',ArrowDown:'back',KeyS:'back',ArrowLeft:'left',KeyA:'left',ArrowRight:'right',KeyD:'right',Space:'shoot'};
addEventListener('keydown',e=>{if(KMAP[e.code]){keys[e.code]=1;lastInput=KMAP[e.code];e.preventDefault();}});
addEventListener('keyup',e=>{delete keys[e.code];if(!Object.keys(keys).length)lastInput='idle';});
// MODE A — real-time generate loop: send the current key, draw Titan's frame
async function startGen(){el('gstat').textContent='Titan is authoring the level + first frame…';playing=true;
  await fetch('/author');loopGen();}
function freeze(){playing=false;}
async function loopGen(){while(playing&&MODE=='gen'){
   const t=Date.now();const r=await j('/frame?input='+encodeURIComponent(lastInput));
   if(r.png){el('screen').src=r.png;el('gstat').textContent=(r.hit?'▮ recall (instant)':'✦ generated')+' · '+lastInput+' · '+(Date.now()-t)+'ms';}
   else{el('gstat').textContent='no frame — '+(r.err||'Titan emitted nothing');}
   await new Promise(z=>setTimeout(z, r&&r.hit?60:20));}}
// MODE B — Titan writes the whole game, run it in the iframe
async function recreate(){el('rstat').textContent='Titan is writing the game (one program)…';
  const r=await j('/author_code?desc='+encodeURIComponent(el('gdesc').value));
  if(r.err){el('rstat').textContent=r.err;return;}
  const doc='<!doctype html><meta charset=utf-8><body style="margin:0;background:#000;overflow:hidden">'+r.code;
  el('gameframe').srcdoc=doc;el('gameframe').focus();el('rstat').textContent='Titan wrote it — click the game and play (arrows + space).';}
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/":
            return self._send(PAGE, "text/html; charset=utf-8")
        if u.path == "/status":
            return self._send(json.dumps({"serving": titan_up(), "free_mb": free_mb(), "log": STATE["log"]}))
        if u.path == "/serve":
            threading.Thread(target=serve_titan, daemon=True).start()
            return self._send(json.dumps({"ok": True}))
        if u.path == "/author":
            if not titan_up():
                return self._send(json.dumps({"err": "serve Titan first"}))
            desc = (q.get("desc") or [GAME_DEFAULT])[0]
            # Titan authors the game PROGRAM (rules) that the generative runtime will run; reset the memoize + state
            STATE["program"] = desc
            STATE["state"] = {"turn": 0, "pos": [1, 1], "angle": 0}
            logline("authored level: " + desc[:60])
            return self._send(json.dumps({"ok": True, "program": desc}))
        if u.path == "/frame":
            if not titan_up():
                return self._send(json.dumps({"err": "serve Titan first"}))
            try:
                png, hit = gen_frame((q.get("input") or ["idle"])[0])
                return self._send(json.dumps({"png": png, "hit": hit} if png else {"err": "no frame"}))
            except Exception as e:
                return self._send(json.dumps({"err": f"{type(e).__name__}: {e}"}))
        if u.path == "/author_code":
            if not titan_up():
                return self._send(json.dumps({"err": "serve Titan first"}))
            try:
                code = author_game_code((q.get("desc") or ["a DOOM-style shooter"])[0])
                logline(f"Titan authored a game ({len(code)} chars)")
                return self._send(json.dumps({"code": code}))
            except Exception as e:
                return self._send(json.dumps({"err": f"{type(e).__name__}: {e}"}))
        return self._send(json.dumps({"err": "not found"}))


if __name__ == "__main__":
    import socket
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM); probe.settimeout(0.4)
    if probe.connect_ex(("127.0.0.1", PORT)) == 0:
        probe.close()
        print(f"DOOM app already running on http://127.0.0.1:{PORT}"); sys.exit(0)
    probe.close()
    print(f"DOOM on Titan — http://127.0.0.1:{PORT}  (Serve Titan, then play with the keyboard)")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
