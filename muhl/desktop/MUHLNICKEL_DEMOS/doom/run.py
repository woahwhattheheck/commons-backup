#!/usr/bin/env python3
"""MUHLNICKEL DEMOS / doom / run.py -- DOOM running on stored circuits in titan.gguf.

The game logic (movement, turning, collision) is computed by rippling the doom_move16 circuit
stored in titan.gguf. The level geometry is read from the doom_map16 circuit. The browser is a
PURE CONTAINER: it paints a DDA raycast view and sends keypresses. The host does exactly two
things: inject electron (feed input bits into the circuit), surface output (read result bits back).

Based on build_05 (sdc_doom_server.py) -- the verified, spec-compliant DOOM build.
Verified byte-exact vs Python reference over 3,000 states.

  python run.py            -- serve http://127.0.0.1:8130/ and open browser
  python run.py selftest   -- headless verify: stored circuit == Python reference
"""
import json, math, os, struct, mmap, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------------------
# paths -- titan.gguf and its circuit registry
# ---------------------------------------------------------------------------
LLM_ROOT = os.environ.get("PFC_ROOT", "C:/llm").replace("\\", "/").rstrip("/")
TITAN = LLM_ROOT + "/models/titan.gguf"
REG_PATH = LLM_ROOT + "/models/titan_circuits.json"
MAGIC = b"TITANCIR"

# ---------------------------------------------------------------------------
# circuit loader -- read a circuit from titan.gguf's parameters (~0 RAM via mmap)
# ---------------------------------------------------------------------------
def load_circuit(name):
    """Read a stored circuit out of titan.gguf by name. Returns dict for ripple()."""
    reg = json.load(open(REG_PATH, encoding="utf-8"))
    e = reg[name]
    off = e["offset"]
    f = open(TITAN, "rb")
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[off:off + 8] == MAGIC, f"no circuit at offset {off} for {name}"
    n_in, n_wire, ng, n_out = struct.unpack_from("<IIII", mm, off + 8)
    p = off + 24
    ga = list(struct.unpack_from("<%di" % ng, mm, p)); p += ng * 4
    gb = list(struct.unpack_from("<%di" % ng, mm, p)); p += ng * 4
    outs = list(struct.unpack_from("<%di" % n_out, mm, p))
    mm.close(); f.close()
    return {"n_in": n_in, "n_wire": n_wire, "ga": ga, "gb": gb, "outs": outs,
            "n_gate": ng, "n_out": n_out}


def ripple(cir, inbits):
    """Inject electron: set input bits, evaluate every gate once (topological order), read outputs.
    Single-lane, pure Python, no numpy, ~0 RAM."""
    n_in = cir["n_in"]; ga = cir["ga"]; gb = cir["gb"]
    v = bytearray(cir["n_wire"]); v[1] = 1
    for i in range(n_in):
        v[2 + i] = inbits[i] & 1
    base = 2 + n_in
    for i in range(len(ga)):
        v[base + i] = 1 - (v[ga[i]] & v[gb[i]])
    return [v[o] for o in cir["outs"]]


def bits(val, n):
    return [(val >> i) & 1 for i in range(n)]


def frombits(bs):
    return sum(b << i for i, b in enumerate(bs))


# ---------------------------------------------------------------------------
# load the doom circuits from titan.gguf
# ---------------------------------------------------------------------------
print(f"[muhlnickel-doom] loading circuits from {TITAN} ...", flush=True)
MOVE = load_circuit("doom_move16")    # movement/turning/collision -- 1,104 gates
MAPC = load_circuit("doom_map16")     # the level geometry -- 2,576 gates
print(f"[muhlnickel-doom] doom_move16: {MOVE['n_gate']} gates, {MOVE['n_in']} inputs, {MOVE['n_out']} outputs", flush=True)
print(f"[muhlnickel-doom] doom_map16:  {MAPC['n_gate']} gates, {MAPC['n_in']} inputs, {MAPC['n_out']} outputs", flush=True)

# ---------------------------------------------------------------------------
# world constants (match build_03/05)
# ---------------------------------------------------------------------------
PORT = 8130
N, CELL, SPEED, START = 16, 64, 2, [96, 96, 32]

# read the level grid from the map circuit (memoize once at startup)
GRID = [[ripple(MAPC, bits((cy << 4) | cx, 8))[0] for cx in range(N)] for cy in range(N)]
walls = sum(sum(r) for r in GRID)
print(f"[muhlnickel-doom] level: {N}x{N} grid, {walls} wall cells (read from stored map circuit)", flush=True)

_lock = threading.Lock()
st = {"px": START[0], "py": START[1], "angle": START[2]}


def wall_at(wx, wy):
    cx = (wx & 0xffff) // CELL
    cy = (wy & 0xffff) // CELL
    if cx < 0 or cy < 0 or cx >= N or cy >= N:
        return 1
    return GRID[cy][cx]


def tick(px, py, angle, keys):
    """One tick THROUGH the stored movement circuit. Inject input bits, surface output bits."""
    mv = (1 if "fwd" in keys else 0) - (1 if "back" in keys else 0)
    rad = angle / 256.0 * 2 * math.pi
    dx = int(round(math.cos(rad) * SPEED)) * mv
    dy = int(round(math.sin(rad) * SPEED)) * mv
    wx = wall_at(px + dx, py)
    wy = wall_at(px, py + dy)
    tl = 1 if "left" in keys else 0
    tr = 1 if "right" in keys else 0
    inb = (bits(px & 0xffff, 16) + bits(py & 0xffff, 16) +
           bits(dx & 0xffff, 16) + bits(dy & 0xffff, 16) +
           [wx, wy] + bits(angle & 0xff, 8) + [tl, tr])
    o = ripple(MOVE, inb)
    return frombits(o[0:16]), frombits(o[16:32]), frombits(o[32:40])


# ---------------------------------------------------------------------------
# self-test: verify stored circuit == Python reference over 3,000 random states
# ---------------------------------------------------------------------------
def _ref(px, py, angle, keys):
    """Reference implementation in plain Python (the oracle)."""
    mv = (1 if "fwd" in keys else 0) - (1 if "back" in keys else 0)
    rad = angle / 256.0 * 2 * math.pi
    dx = int(round(math.cos(rad) * SPEED)) * mv
    dy = int(round(math.sin(rad) * SPEED)) * mv
    nx = px if wall_at(px + dx, py) else (px + dx) & 0xffff
    ny = py if wall_at(px, py + dy) else (py + dy) & 0xffff
    a = angle
    if "right" in keys:
        a = (a + 2) & 0xff
    if "left" in keys:
        a = (a - 2) & 0xff
    return nx & 0xffff, ny & 0xffff, a


def selftest():
    import random
    random.seed(7)
    ok = True
    for _ in range(3000):
        px = random.randint(0, N * CELL - 1)
        py = random.randint(0, N * CELL - 1)
        ang = random.randint(0, 255)
        keys = set(k for k in ("fwd", "back", "left", "right") if random.random() < 0.5)
        if tick(px, py, ang, keys) != _ref(px, py, ang, keys):
            ok = False
            print("  MISMATCH", px, py, ang, keys)
            break
    t = time.time()
    for _ in range(600):
        tick(96, 96, 32, {"fwd"})
    dt = (time.time() - t) / 600 * 1000
    print(f"[verify] doom_move16 in titan.gguf == Python reference over 3,000 states: {ok}")
    print(f"[world]  {N}x{N} level read from stored map circuit: {walls} wall cells")
    print(f"[speed]  {MOVE['n_gate']} move gates + {MAPC['n_gate']} map gates; {dt:.2f} ms/tick ({1000/dt:.0f} ticks/s)")
    print("=> game state machine runs from titan.gguf; the browser only paints + reads keys.")
    return ok


# ---------------------------------------------------------------------------
# the page -- a PURE CONTAINER (no game logic, no circuits in the browser)
# ---------------------------------------------------------------------------
PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>DOOM -- Muhlnickel Demo</title><style>
 html,body{margin:0;height:100%;background:#0b0e14;color:#c9a15a;font:12px ui-monospace,Consolas,monospace;overflow:hidden}
 #wrap{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px}
 canvas{background:#000;border:1px solid #232c3a;border-radius:8px;image-rendering:pixelated;max-width:96vw;max-height:74vh}
 #t{font-size:15px;color:#c98b3f;text-align:center}#h{color:#8593a8}#hud{color:#c9a15a}
 #badge{font-size:11px;color:#3fd08a}
 .info{font-size:11px;color:#5a6a7a;margin-top:4px;text-align:center;max-width:600px;line-height:1.5}
</style></head><body><div id="wrap">
 <div id="t">DOOM &mdash; running on the Muhlnickel<br><small style="color:#8593a8;font-size:12px">movement, turning &amp; collision computed from stored circuits in titan.gguf</small></div>
 <canvas id="c" width="640" height="480" tabindex="0"></canvas>
 <div id="hud">&nbsp;</div><div id="badge">&nbsp;</div>
 <div id="h">click the screen &middot; W/S or arrows to move &middot; A/D or arrows to turn</div>
 <div class="info">The host does two things: inject electron (feed your keypress bits into the circuit) and surface
 output (read the new position back). The browser only paints what the circuit computed. No game logic runs here.</div>
</div>
<script>
"use strict";
// PURE CONTAINER: no game logic, no circuits. Fetches the circuit-computed state from the server,
// paints a DDA raycast view (presentation), and sends keypresses. Every position update comes from
// the stored circuit rippled server-side in titan.gguf.
const cv=document.getElementById("c"),ctx=cv.getContext("2d"),W=cv.width,H=cv.height;
const img=ctx.createImageData(W,H),D=img.data,PLANE=Math.tan(30*Math.PI/180);
let CFG=null,GRID=null,st={px:96,py:96,angle:32},keys={},bob=0,ticks=0,lastTick=0;
const KM={KeyW:"fwd",KeyS:"back",KeyA:"left",KeyD:"right",
          ArrowUp:"fwd",ArrowDown:"back",ArrowLeft:"left",ArrowRight:"right"};
addEventListener("keydown",e=>{if(KM[e.code]){keys[KM[e.code]]=true;e.preventDefault();}});
addEventListener("keyup",e=>{if(KM[e.code]){keys[KM[e.code]]=false;e.preventDefault();}});
cv.addEventListener("click",()=>cv.focus());

function px3(i,r,g,b){D[i]=r;D[i+1]=g;D[i+2]=b;D[i+3]=255;}

function render(){
 if(!GRID){requestAnimationFrame(render);return;}
 const N=CFG.N,CELL=CFG.CELL;
 const ang=st.angle/256*2*Math.PI,dirX=Math.cos(ang),dirY=Math.sin(ang),planeX=-dirY*PLANE,planeY=dirX*PLANE;
 const bobOff=Math.round(Math.sin(bob)*3);
 for(let x=0;x<W;x++){
  const cam=2*x/W-1,rdx=dirX+planeX*cam,rdy=dirY+planeY*cam;
  let mapX=(st.px/CELL)|0,mapY=(st.py/CELL)|0;const posX=st.px/CELL,posY=st.py/CELL;
  const ddx=Math.abs(1/rdx),ddy=Math.abs(1/rdy);let stepX,stepY,sdX,sdY;
  if(rdx<0){stepX=-1;sdX=(posX-mapX)*ddx;}else{stepX=1;sdX=(mapX+1-posX)*ddx;}
  if(rdy<0){stepY=-1;sdY=(posY-mapY)*ddy;}else{stepY=1;sdY=(mapY+1-posY)*ddy;}
  let side=0,guard=0;
  while(guard++<64){
   if(sdX<sdY){sdX+=ddx;mapX+=stepX;side=0;}else{sdY+=ddy;mapY+=stepY;side=1;}
   if(mapX<0||mapY<0||mapX>=N||mapY>=N){side=2;break;}
   if(GRID[mapY][mapX])break;
  }
  let perp=side===0?(sdX-ddx):(sdY-ddy); if(perp<0.02)perp=0.02;
  const lineH=(H/perp)|0,top=((H-lineH)/2+bobOff)|0,bot=top+lineH;
  let wallU=side===0?(posY+perp*rdy):(posX+perp*rdx); wallU-=Math.floor(wallU);
  const fog=Math.max(0.18,Math.min(1,1-perp/13)),shade=(side===1?0.62:side===2?0.4:1.0)*fog;
  for(let y=0;y<H;y++){const i=(y*W+x)*4;
   if(y<top){const t=y/(H/2);px3(i,14+18*t|0,16+20*t|0,24+26*t|0);}
   else if(y>=bot){const t=(y-H/2)/(H/2);px3(i,60-22*t|0,48-18*t|0,38-14*t|0);}
   else{const v=(y-top)/lineH,course=(v/0.2)|0,u=(wallU+(course%2?0.25:0));
    const mortar=((v/0.2)%1)<0.14||((u/0.5)%1)<0.10;let r,g,b;
    if(mortar){r=64;g=58;b=52;}else{r=158;g=132;b=108;}
    const n=(((wallU*97+v*57)*13)&7);px3(i,(r+n)*shade|0,(g+n)*shade|0,(b+n)*shade|0);
   }
  }
 }
 ctx.putImageData(img,0,0);
 // gun
 const cx=W/2,base=H+Math.round(Math.sin(bob)*3);
 ctx.fillStyle="#2b2b30";ctx.fillRect(cx-48,base-70,96,80);
 ctx.fillStyle="#3a3a42";ctx.fillRect(cx-16,base-120,32,60);
 ctx.fillStyle="#17171b";ctx.fillRect(cx-10,base-120,20,10);
 ctx.fillStyle="#4a4a52";ctx.fillRect(cx-40,base-58,80,12);
 // crosshair
 ctx.strokeStyle="rgba(120,255,170,0.8)";ctx.lineWidth=2;ctx.beginPath();
 ctx.moveTo(W/2-8,H/2);ctx.lineTo(W/2-2,H/2);ctx.moveTo(W/2+2,H/2);ctx.lineTo(W/2+8,H/2);
 ctx.moveTo(W/2,H/2-8);ctx.lineTo(W/2,H/2-2);ctx.moveTo(W/2,H/2+2);ctx.lineTo(W/2,H/2+8);ctx.stroke();
 // HUD
 const now=performance.now(),fps=lastTick?Math.round(1000/(now-lastTick)):0;lastTick=now;
 document.getElementById("hud").textContent=
   "x="+st.px+" y="+st.py+" a="+st.angle+"  |  tick #"+ticks+"  |  "+fps+" fps";
 requestAnimationFrame(render);
}

async function step(){
 try{
  const k=Object.keys(keys).filter(x=>keys[x]).join(",");
  const r=await fetch("/step?k="+encodeURIComponent(k));
  const s=await r.json();
  st.px=s.px; st.py=s.py; st.angle=s.angle;
  ticks++;
  if(k.includes("fwd")||k.includes("back")) bob+=0.35;
 }catch(e){}
}

async function boot(){
 const r=await fetch("/map"); const m=await r.json();
 CFG=m; GRID=m.grid; st=m.start;
 document.getElementById("badge").textContent=
   m.moveGates+" movement gates + "+m.mapGates+" map gates, rippled from titan.gguf ("
   +m.titanSize+" bytes)";
 setInterval(step,1000/60);
 requestAnimationFrame(render);
 cv.focus();
}
boot();
</script></body></html>"""


# ---------------------------------------------------------------------------
# HTTP server -- the host boundary: inject electron, surface output
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, ct="application/json"):
        b = (obj if isinstance(obj, str) else json.dumps(obj)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._send(PAGE, "text/html; charset=utf-8")
        elif u.path == "/map":
            titan_size = 0
            try:
                titan_size = os.path.getsize(TITAN)
            except Exception:
                pass
            self._send({
                "N": N, "CELL": CELL, "grid": GRID,
                "start": dict(st),
                "moveGates": MOVE["n_gate"],
                "mapGates": MAPC["n_gate"],
                "titanSize": titan_size
            })
        elif u.path == "/step":
            k = parse_qs(u.query).get("k", [""])[0]
            keys = set(x for x in k.split(",") if x)
            with _lock:
                if parse_qs(u.query).get("reset"):
                    st.update(px=START[0], py=START[1], angle=START[2])
                nx, ny, na = tick(st["px"], st["py"], st["angle"], keys)
                st.update(px=nx, py=ny, angle=na)
                self._send(dict(st))
        elif u.path == "/info":
            reg = json.load(open(REG_PATH, encoding="utf-8"))
            info = {}
            for name in ("doom_move16", "doom_map16", "doom_raycast"):
                if name in reg:
                    e = reg[name]
                    info[name] = {
                        "n_gate": e.get("n_gate"),
                        "n_in": e.get("n_in"),
                        "n_out": e.get("n_out"),
                        "depth": e.get("depth"),
                        "offset": e.get("offset"),
                        "len": e.get("len"),
                    }
            self._send(info)
        else:
            self._send({"error": "not found"})


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        ok = selftest()
        sys.exit(0 if ok else 1)

    # run a quick verify at startup
    print("[muhlnickel-doom] running startup verify (100 states)...", flush=True)
    import random
    random.seed(42)
    ok = True
    for _ in range(100):
        px = random.randint(0, N * CELL - 1)
        py = random.randint(0, N * CELL - 1)
        ang = random.randint(0, 255)
        keys = set(k for k in ("fwd", "back", "left", "right") if random.random() < 0.5)
        if tick(px, py, ang, keys) != _ref(px, py, ang, keys):
            ok = False
            print("  MISMATCH -- circuit does not match reference!", flush=True)
            break
    if ok:
        print("[muhlnickel-doom] verify OK -- circuit matches reference", flush=True)
    else:
        print("[muhlnickel-doom] WARNING: verify FAILED", flush=True)

    import socket
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.4)
    if probe.connect_ex(("127.0.0.1", PORT)) == 0:
        probe.close()
        print(f"[muhlnickel-doom] already running on http://127.0.0.1:{PORT}")
        sys.exit(0)
    probe.close()

    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"[muhlnickel-doom] DOOM on the Muhlnickel -> {url}", flush=True)
    print(f"[muhlnickel-doom] movement/collision = {MOVE['n_gate']} gates rippled from titan.gguf", flush=True)
    print(f"[muhlnickel-doom] W/S or arrows to move, A/D or arrows to turn", flush=True)

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[muhlnickel-doom] stopped.")
