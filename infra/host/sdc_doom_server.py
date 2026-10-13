#!/usr/bin/env python3
"""host/sdc_doom_server.py — DOOM where the game logic runs ON THE SDC (owner 07-16). No numpy.

The correction over the HTML builds (02/03/04): those exported the gate arrays into the page and rippled them in the
BROWSER (a host harness). Here the browser is a PURE CONTAINER — it draws pixels and reads keys, nothing else. Every
movement/turn/collision tick is computed by rippling the movement circuit stored IN titan.gguf, server-side (the SDC),
and the world map is read out of the stored map circuit. Per BARE_METAL.md the host only feeds input (your keys) and
paints (the raycaster is presentation); the COMPUTE — where can I move, did I hit a wall — is the stored circuit.

  python host/sdc_doom_server.py            # serve http://127.0.0.1:8120/  (SDCDoom.cmd opens it)
  python host/sdc_doom_server.py selftest   # headless: verify the stored circuit == a Python reference + time it
"""
import json, math, os, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as tc

PORT = 8120
N, CELL, SPEED, START = 16, 64, 2, [96, 96, 32]                 # build_03 world constants (TURN lives in the circuit)

MOVE = tc.load("doom_move16")                                   # movement/turn/collision — 1104 gates in titan.gguf
MAPC = tc.load("doom_map16")                                    # the level — 2576 gates in titan.gguf
GRID = [[tc.ripple(MAPC, tc.bits((cy << 4) | cx, 8))[0] for cx in range(N)] for cy in range(N)]  # memoized once (5.5)

_lock = threading.Lock()
st = {"px": START[0], "py": START[1], "angle": START[2]}


def wall_at(wx, wy):
    cx = (wx & 0xffff) // CELL; cy = (wy & 0xffff) // CELL
    if cx < 0 or cy < 0 or cx >= N or cy >= N: return 1
    return GRID[cy][cx]


def tick(px, py, angle, keys):
    """One tick THROUGH the stored movement circuit. keys = set of {'fwd','back','left','right'}. Returns (nx,ny,na)."""
    mv = (1 if "fwd" in keys else 0) - (1 if "back" in keys else 0)
    rad = angle / 256.0 * 2 * math.pi
    dx = int(round(math.cos(rad) * SPEED)) * mv
    dy = int(round(math.sin(rad) * SPEED)) * mv
    wx = wall_at(px + dx, py); wy = wall_at(px, py + dy)
    tl = 1 if "left" in keys else 0; tr = 1 if "right" in keys else 0
    inb = (tc.bits(px & 0xffff, 16) + tc.bits(py & 0xffff, 16) + tc.bits(dx & 0xffff, 16) + tc.bits(dy & 0xffff, 16)
           + [wx, wy] + tc.bits(angle & 0xff, 8) + [tl, tr])
    o = tc.ripple(MOVE, inb)
    return tc.frombits(o[0:16]), tc.frombits(o[16:32]), tc.frombits(o[32:40])


def _ref(px, py, angle, keys):                                  # the same logic in plain Python (self-test oracle)
    mv = (1 if "fwd" in keys else 0) - (1 if "back" in keys else 0)
    rad = angle / 256.0 * 2 * math.pi
    dx = int(round(math.cos(rad) * SPEED)) * mv; dy = int(round(math.sin(rad) * SPEED)) * mv
    nx = px if wall_at(px + dx, py) else (px + dx) & 0xffff
    ny = py if wall_at(px, py + dy) else (py + dy) & 0xffff
    a = angle
    if "right" in keys: a = (a + 2) & 0xff
    if "left" in keys:  a = (a - 2) & 0xff
    return nx & 0xffff, ny & 0xffff, a


def selftest():
    import random; random.seed(7); ok = True
    for _ in range(3000):
        px, py = random.randint(0, N * CELL - 1), random.randint(0, N * CELL - 1)
        ang = random.randint(0, 255)
        keys = set(k for k in ("fwd", "back", "left", "right") if random.random() < 0.5)
        if tick(px, py, ang, keys) != _ref(px, py, ang, keys):
            ok = False; print("  MISMATCH", px, py, ang, keys); break
    t = time.time()
    for _ in range(600): tick(96, 96, 32, {"fwd"})
    dt = (time.time() - t) / 600 * 1000
    walls = sum(sum(r) for r in GRID)
    print(f"[verify] doom_move16-in-titan.gguf == Python reference over 3000 states: {ok}")
    print(f"[world]  {N}x{N} level read from the stored map circuit: {walls} wall cells")
    print(f"[speed]  {MOVE['n_wire']-2-MOVE['n_in']} move gates + {MAPC['n_wire']-2-MAPC['n_in']} world gates; "
          f"{dt:.2f} ms per SDC tick ({1000/dt:.0f} ticks/s)")
    print("=> the game state machine runs from titan.gguf's params; the browser only paints + reads keys.")


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>DOOM — running on the SDC</title><style>
 html,body{margin:0;height:100%;background:#0b0e14;color:#c9a15a;font:12px ui-monospace,Consolas,monospace;overflow:hidden}
 #wrap{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px}
 canvas{background:#000;border:1px solid #232c3a;border-radius:8px;image-rendering:pixelated;max-width:96vw;max-height:74vh}
 #t{font-size:15px;color:#c98b3f}#h{color:#8593a8}#hud{color:#c9a15a}#badge{font-size:11px;color:#3fd08a}
</style></head><body><div id="wrap">
 <div id="t">DOOM &mdash; movement, turning &amp; collision computed on the SDC (stored circuits in titan.gguf)</div>
 <canvas id="c" width="512" height="384" tabindex="0"></canvas>
 <div id="hud">&nbsp;</div><div id="badge">&nbsp;</div>
 <div id="h">click the screen &middot; W/S move &middot; A/D turn &middot; the browser only paints + sends keys</div>
</div>
<script>
"use strict";
// PURE CONTAINER: no game logic, no circuits here. It fetches the SDC-computed map once, paints a raycast view of the
// state, and sends key presses to the SDC each tick. Every position update comes back from the server's stored circuit.
const cv=document.getElementById("c"),ctx=cv.getContext("2d"),W=cv.width,H=cv.height;
const img=ctx.createImageData(W,H),D=img.data,PLANE=Math.tan(30*Math.PI/180);
let CFG=null,GRID=null,st={px:96,py:96,angle:32},keys={},bob=0;
const KM={KeyW:"fwd",KeyS:"back",KeyA:"left",KeyD:"right",ArrowUp:"fwd",ArrowDown:"back",ArrowLeft:"left",ArrowRight:"right"};
addEventListener("keydown",e=>{if(KM[e.code]){keys[KM[e.code]]=true;e.preventDefault();}});
addEventListener("keyup",e=>{if(KM[e.code]){keys[KM[e.code]]=false;e.preventDefault();}});
cv.addEventListener("click",()=>cv.focus());
function px3(i,r,g,b){D[i]=r;D[i+1]=g;D[i+2]=b;D[i+3]=255;}
function render(){
 if(!GRID){return;} const N=CFG.N,CELL=CFG.CELL;
 const ang=st.angle/256*2*Math.PI,dirX=Math.cos(ang),dirY=Math.sin(ang),planeX=-dirY*PLANE,planeY=dirX*PLANE;
 const bobOff=Math.round(Math.sin(bob)*3);
 for(let x=0;x<W;x++){
  const cam=2*x/W-1,rdx=dirX+planeX*cam,rdy=dirY+planeY*cam;
  let mapX=(st.px/CELL)|0,mapY=(st.py/CELL)|0;const posX=st.px/CELL,posY=st.py/CELL;
  const ddx=Math.abs(1/rdx),ddy=Math.abs(1/rdy);let stepX,stepY,sdX,sdY;
  if(rdx<0){stepX=-1;sdX=(posX-mapX)*ddx;}else{stepX=1;sdX=(mapX+1-posX)*ddx;}
  if(rdy<0){stepY=-1;sdY=(posY-mapY)*ddy;}else{stepY=1;sdY=(mapY+1-posY)*ddy;}
  let side=0,guard=0;
  while(guard++<64){ if(sdX<sdY){sdX+=ddx;mapX+=stepX;side=0;}else{sdY+=ddy;mapY+=stepY;side=1;}
   if(mapX<0||mapY<0||mapX>=N||mapY>=N){side=2;break;} if(GRID[mapY][mapX])break; }
  let perp=side===0?(sdX-ddx):(sdY-ddy); if(perp<0.02)perp=0.02;
  const lineH=(H/perp)|0,top=((H-lineH)/2+bobOff)|0,bot=top+lineH;
  let wallU=side===0?(posY+perp*rdy):(posX+perp*rdx); wallU-=Math.floor(wallU);
  const fog=Math.max(0.18,Math.min(1,1-perp/13)),shade=(side===1?0.62:side===2?0.4:1.0)*fog;
  for(let y=0;y<H;y++){ const i=(y*W+x)*4;
   if(y<top){const t=y/(H/2);px3(i,14+18*t|0,16+20*t|0,24+26*t|0);}
   else if(y>=bot){const t=(y-H/2)/(H/2);px3(i,60-22*t|0,48-18*t|0,38-14*t|0);}
   else{const v=(y-top)/lineH,course=(v/0.2)|0,u=(wallU+(course%2?0.25:0));
    const mortar=((v/0.2)%1)<0.14||((u/0.5)%1)<0.10;let r,g,b;
    if(mortar){r=64;g=58;b=52;}else{r=158;g=132;b=108;}
    const n=(((wallU*97+v*57)*13)&7);px3(i,(r+n)*shade|0,(g+n)*shade|0,(b+n)*shade|0);}}}
 ctx.putImageData(img,0,0);
 const cx=W/2,base=H+bobOff;
 ctx.fillStyle="#2b2b30";ctx.fillRect(cx-48,base-70,96,80);ctx.fillStyle="#3a3a42";ctx.fillRect(cx-16,base-120,32,60);
 ctx.fillStyle="#17171b";ctx.fillRect(cx-10,base-120,20,10);ctx.fillStyle="#4a4a52";ctx.fillRect(cx-40,base-58,80,12);
 ctx.strokeStyle="rgba(120,255,170,0.8)";ctx.lineWidth=2;ctx.beginPath();
 ctx.moveTo(W/2-8,H/2);ctx.lineTo(W/2-2,H/2);ctx.moveTo(W/2+2,H/2);ctx.lineTo(W/2+8,H/2);
 ctx.moveTo(W/2,H/2-8);ctx.lineTo(W/2,H/2-2);ctx.moveTo(W/2,H/2+2);ctx.lineTo(W/2,H/2+8);ctx.stroke();
 document.getElementById("hud").textContent=`x=${st.px} y=${st.py} a=${st.angle}`;
 requestAnimationFrame(render);
}
async function step(){
 try{ const k=Object.keys(keys).filter(x=>keys[x]).join(",");
  const r=await fetch("/step?k="+encodeURIComponent(k)); const s=await r.json();
  st.px=s.px;st.py=s.py;st.angle=s.angle; if(k.includes("fwd")||k.includes("back"))bob+=0.35;
 }catch(e){}
}
async function boot(){
 const r=await fetch("/map"); const m=await r.json(); CFG=m; GRID=m.grid; st=m.start;
 document.getElementById("badge").textContent=m.moveGates+" movement gates + "+m.mapGates+" world gates, rippled server-side from titan.gguf";
 setInterval(step,1000/60); requestAnimationFrame(render); cv.focus();
}
boot();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, obj, ct="application/json"):
        b = (obj if isinstance(obj, str) else json.dumps(obj)).encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._send(PAGE, "text/html; charset=utf-8")
        elif u.path == "/map":
            self._send({"N": N, "CELL": CELL, "grid": GRID, "start": dict(st),
                        "moveGates": MOVE["n_wire"] - 2 - MOVE["n_in"], "mapGates": MAPC["n_wire"] - 2 - MAPC["n_in"]})
        elif u.path == "/step":
            k = parse_qs(u.query).get("k", [""])[0]
            keys = set(x for x in k.split(",") if x)
            with _lock:
                if parse_qs(u.query).get("reset"): st.update(px=START[0], py=START[1], angle=START[2])
                nx, ny, na = tick(st["px"], st["py"], st["angle"], keys)
                st.update(px=nx, py=ny, angle=na)
                self._send(dict(st))
        else:
            self._send({"error": "not found"})


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest(); sys.exit(0)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"DOOM on the SDC -> http://127.0.0.1:{PORT}/  (movement/collision = stored circuits in titan.gguf)", flush=True)
    try: webbrowser.open(f"http://127.0.0.1:{PORT}/")
    except Exception: pass
    srv.serve_forever()
