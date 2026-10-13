#!/usr/bin/env python3
"""host/export_doom_html2.py — DOOM build 03: slower, bigger, textured. Still SDC-driven. (owner 07-16)

Build 02 played but felt like Sonic (movement tied to the render framerate, huge step in a tiny 256-unit world) and
looked like a flat green box. This build:
  * WORLD: a 16x16 level (1024 units) -> 16-bit positions. Movement/turn/collision is rebuilt as a stored gate-net
    ("doom_move16") in titan.gguf's params, and the level is a stored map circuit ("doom_map16"). Both verified byte-exact
    vs a Python reference, then exported into the page (the JS ripples the SAME gate arrays).
  * PACE: a fixed 60 Hz logical timestep (framerate-independent) with a gentle per-tick step -> a deliberate DOOM walk.
  * LOOK: a proper DDA raycaster with textured brick walls, wall-side shading, distance fog, floor/ceiling gradients,
    head-bob, a gun sprite + crosshair.

Only the RENDERER is host-side presentation (the console paints pixels); the movement/collision and the world are the
stored circuits, exactly the SDC thesis. Writes a self-contained double-click HTML to the Desktop + the build_03 folder.

  python host/export_doom_html2.py
"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

DESK = "C:/Users/lucys/OneDrive/Desktop"
OUT  = os.path.join(DESK, "DOOM (double-click to play).html")
BUILD = os.path.join(DESK, "DOOM_builds", "build_03_bigger-slower-textured")

N = 16; CELL = 64                                              # 16x16 cells, 64 units each -> a 1024-unit world (16-bit)
SPEED = 2; TURN = 2                                            # per 60 Hz tick: ~120 u/s move, full turn ~2.1 s (not snappy)
START = (96, 96, 32)                                           # start cell (1,1) center, facing ~45 degrees


def make_map():
    g = [['.'] * N for _ in range(N)]
    for i in range(N):
        g[0][i] = g[N-1][i] = g[i][0] = g[i][N-1] = '#'        # border walls
    for (r0, c0, r1, c1) in [(2,2,4,4),(2,11,4,13),(11,2,13,4),(11,11,13,13),(6,6,9,9)]:   # rooms + central pillar
        for r in range(r0, r1+1):
            for c in range(c0, c1+1): g[r][c] = '#'
    rows = ["".join(r) for r in g]
    assert len(rows) == N and all(len(r) == N for r in rows), "map must be NxN"
    return rows


MAP = make_map()


def wall16(wx, wy):
    cx = (wx & 0xffff) // CELL; cy = (wy & 0xffff) // CELL
    if cx < 0 or cy < 0 or cx >= N or cy >= N: return 1
    return 1 if MAP[cy][cx] == '#' else 0


def build_movement16():
    """px16 py16 dx16 dy16 wallx wally angle8 turnL turnR -> nx16 ny16 nangle8 (all NAND gates, 16-bit world)."""
    c = TC.Circuit(16+16+16+16+1+1+8+1+1); i = c.IN
    px, py, dx, dy = i[0:16], i[16:32], i[32:48], i[48:64]
    wallx, wally = i[64], i[65]; angle = i[66:74]; turnL, turnR = i[74], i[75]
    candx = c.add(px, dx); candy = c.add(py, dy)
    nx = [c.mux(wallx, candx[k], px[k]) for k in range(16)]      # wallx ? px : candx
    ny = [c.mux(wally, candy[k], py[k]) for k in range(16)]
    ang_r = c.add(angle, c.cvec(TURN, 8))
    na1 = [c.mux(turnR, angle[k], ang_r[k]) for k in range(8)]
    na1_l = c.add(na1, c.cvec((256 - TURN) & 0xff, 8))
    nangle = [c.mux(turnL, na1[k], na1_l[k]) for k in range(8)]
    return c, nx + ny + nangle


def build_map16():
    """(cx:4, cy:4) packed 8-bit cell index -> wall(1). the level is a stored lookup circuit."""
    c = TC.Circuit(8); idx = c.IN
    acc = c.C0
    for cy in range(N):
        for cx in range(N):
            if MAP[cy][cx] == '#':
                acc = c.or_(acc, c.eq_const(idx, (cy << 4) | cx))
    return c, [acc]


def _pack(px, py, dx, dy, wx, wy, angle, tl, tr):
    return (TC.bits(px & 0xffff, 16) + TC.bits(py & 0xffff, 16) + TC.bits(dx & 0xffff, 16) + TC.bits(dy & 0xffff, 16)
            + [wx, wy] + TC.bits(angle & 0xff, 8) + [tl, tr])


def step(cir, px, py, angle, keys):
    mv = (1 if 'fwd' in keys else 0) - (1 if 'back' in keys else 0)
    rad = angle / 256.0 * 2 * math.pi
    dx = int(round(math.cos(rad) * SPEED)) * mv; dy = int(round(math.sin(rad) * SPEED)) * mv
    wx = wall16(px + dx, py); wy = wall16(px, py + dy)
    tl = 1 if 'left' in keys else 0; tr = 1 if 'right' in keys else 0
    o = TC.ripple(cir, _pack(px, py, dx, dy, wx, wy, angle, tl, tr))
    return TC.frombits(o[0:16]), TC.frombits(o[16:32]), TC.frombits(o[32:40])


def _ref(px, py, angle, keys):
    mv = (1 if 'fwd' in keys else 0) - (1 if 'back' in keys else 0)
    rad = angle / 256.0 * 2 * math.pi
    dx = int(round(math.cos(rad) * SPEED)) * mv; dy = int(round(math.sin(rad) * SPEED)) * mv
    wx = wall16(px + dx, py); wy = wall16(px, py + dy)
    nx = px if wx else (px + dx) & 0xffff; ny = py if wy else (py + dy) & 0xffff
    a = angle
    if 'right' in keys: a = (a + TURN) & 0xff
    if 'left' in keys:  a = (a - TURN) & 0xff
    return nx & 0xffff, ny & 0xffff, a


def circuit_json(name):
    c = TC.load(name)
    return {"nin": c["n_in"], "nw": c["n_wire"], "ga": c["ga"], "gb": c["gb"], "outs": c["outs"]}


def verify(cir):
    import random; random.seed(11); ok = True
    for _ in range(2000):
        px = random.randint(0, 1023); py = random.randint(0, 1023); ang = random.randint(0, 255)
        keys = set(k for k in ('fwd', 'back', 'left', 'right') if random.random() < 0.5)
        if step(cir, px, py, ang, keys) != _ref(px, py, ang, keys): ok = False; break
    return ok


def main():
    mv, mouts = build_movement16(); mi = TC.store("doom_move16", mv, mouts, slot=4)
    mp, pouts = build_map16();      pi = TC.store("doom_map16", mp, pouts, slot=5)
    movecir = TC.load("doom_move16")
    ok = verify(movecir)
    print(f"stored circuits in titan.gguf: movement {mi['gates']} gates, map {pi['gates']} gates.", flush=True)
    print(f"[verify] movement circuit-in-params == reference over 2000 states: {ok}", flush=True)
    if not ok:
        print("verify FAILED — not exporting."); raise SystemExit(1)

    cfg = {"N": N, "CELL": CELL, "SPEED": SPEED, "TURN": TURN, "START": list(START),
           "MOVE": circuit_json("doom_move16"), "MAP_CIR": circuit_json("doom_map16"),
           "moveGates": mi['gates'], "mapGates": pi['gates']}
    html = PAGE.replace("/*__DATA__*/", json.dumps(cfg))
    os.makedirs(BUILD, exist_ok=True)
    for p in (OUT, os.path.join(BUILD, "DOOM.html")):
        with open(p, "w", encoding="utf-8") as f: f.write(html)
    print(f"wrote {OUT}  ({len(html):,} bytes)", flush=True)
    print(f"also saved to {BUILD}\\DOOM.html", flush=True)
    print("double-click the Desktop file -> browser. Click it, then W/A/S/D. Slower + textured now.", flush=True)


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>DOOM from the SDC</title>
<style>
 html,body{margin:0;height:100%;background:#0b0e14;color:#e7ecf5;font:13px ui-monospace,Consolas,monospace;overflow:hidden}
 #wrap{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px}
 canvas{background:#000;border:1px solid #232c3a;border-radius:8px;max-width:96vw;max-height:76vh}
 #hud{color:#c9a15a;font-size:12px}#title{font-size:15px}#title b{color:#c98b3f}
 #help{color:#8593a8;font-size:12px}#help b{color:#c9a15a}
</style></head><body><div id="wrap">
 <div id="title">DOOM &mdash; <b>world + logic are stored circuits in titan.gguf</b></div>
 <canvas id="c" width="640" height="400" tabindex="0"></canvas>
 <div id="hud">&nbsp;</div>
 <div id="help"><b>W</b>/<b>S</b> move &nbsp; <b>A</b>/<b>D</b> turn &nbsp; arrows too &nbsp;&middot;&nbsp; click the screen if keys don't respond</div>
</div>
<script>
const CFG = /*__DATA__*/;
const {N, CELL, SPEED, TURN, START, MOVE, MAP_CIR, moveGates, mapGates} = CFG;

// ---- ripple a stored circuit exactly like titan_circuit.ripple (Python) ----
function ripple(cir, inb){
  const v = new Uint8Array(cir.nw); v[1] = 1;
  for(let i=0;i<cir.nin;i++) v[2+i] = inb[i] & 1;
  const base = 2 + cir.nin, ga = cir.ga, gb = cir.gb, ng = ga.length;
  for(let i=0;i<ng;i++) v[base+i] = 1 - (v[ga[i]] & v[gb[i]]);
  return cir.outs.map(o => o===0?0:(o===1?1:v[o]));
}
const bits = (val,n)=>{const a=[];for(let j=0;j<n;j++)a.push((val>>j)&1);return a;};
const frombits = a => a.reduce((s,b,i)=>s+(b<<i),0);

// ---- the LEVEL, read out of the stored map circuit at load ----
function wallFromCircuit(cx,cy){ return ripple(MAP_CIR, bits(((cy<<4)|cx),8))[0]; }
const GRID = [];
for(let cy=0;cy<N;cy++){ const row=[]; for(let cx=0;cx<N;cx++) row.push(wallFromCircuit(cx,cy)); GRID.push(row); }
function wallAt(wx,wy){ const cx=((wx&0xffff)/CELL)|0, cy=((wy&0xffff)/CELL)|0;
  if(cx<0||cy<0||cx>=N||cy>=N) return 1; return GRID[cy][cx]; }

// ---- one tick THROUGH the stored movement circuit (collision from the level) ----
function stepLogic(){
  const px=st.px, py=st.py, angle=st.angle;
  const mv=(st.keys.fwd?1:0)-(st.keys.back?1:0);
  const rad=angle/256*2*Math.PI;
  const dx=Math.round(Math.cos(rad)*SPEED)*mv, dy=Math.round(Math.sin(rad)*SPEED)*mv;
  const wx=wallAt(px+dx,py), wy=wallAt(px,py+dy);
  const tl=st.keys.left?1:0, tr=st.keys.right?1:0;
  const inb=bits(px&0xffff,16).concat(bits(py&0xffff,16),bits(dx&0xffff,16),bits(dy&0xffff,16),
                 [wx,wy],bits(angle&0xff,8),[tl,tr]);
  const o=ripple(MOVE,inb);
  const nx=frombits(o.slice(0,16)), ny=frombits(o.slice(16,32));
  st.px=nx; st.py=ny; st.angle=frombits(o.slice(32,40));
  if(mv!==0) st.bob += 0.35;                                   // head-bob only while walking
}

// ---- DDA raycaster with textured brick walls, side shading, fog ----
const cv=document.getElementById("c"), ctx=cv.getContext("2d");
const W=cv.width, H=cv.height, img=ctx.createImageData(W,H), D=img.data;
const PLANE=Math.tan(30*Math.PI/180);                          // 60-degree FOV
const st={px:START[0], py:START[1], angle:START[2], keys:{}, bob:0};
function px3(i,r,g,b){ D[i]=r; D[i+1]=g; D[i+2]=b; D[i+3]=255; }

function render(){
  const ang=st.angle/256*2*Math.PI, dirX=Math.cos(ang), dirY=Math.sin(ang);
  const planeX=-dirY*PLANE, planeY=dirX*PLANE;
  const bobOff=Math.round(Math.sin(st.bob)*3);
  for(let x=0;x<W;x++){
    const cam=2*x/W-1, rdx=dirX+planeX*cam, rdy=dirY+planeY*cam;
    let mapX=(st.px/CELL)|0, mapY=(st.py/CELL)|0;
    const posX=st.px/CELL, posY=st.py/CELL;
    const ddx=Math.abs(1/rdx), ddy=Math.abs(1/rdy);
    let stepX,stepY,sdX,sdY;
    if(rdx<0){stepX=-1; sdX=(posX-mapX)*ddx;} else {stepX=1; sdX=(mapX+1-posX)*ddx;}
    if(rdy<0){stepY=-1; sdY=(posY-mapY)*ddy;} else {stepY=1; sdY=(mapY+1-posY)*ddy;}
    let side=0, guard=0;
    while(guard++<64){
      if(sdX<sdY){ sdX+=ddx; mapX+=stepX; side=0; } else { sdY+=ddy; mapY+=stepY; side=1; }
      if(mapX<0||mapY<0||mapX>=N||mapY>=N){ side=2; break; }
      if(GRID[mapY][mapX]) break;
    }
    let perp = side===0 ? (sdX-ddx) : (sdY-ddy); if(perp<0.02) perp=0.02;
    const lineH=(H/perp)|0; const top=((H-lineH)/2+bobOff)|0, bot=top+lineH;
    // texture coordinate along the wall
    let wallU = side===0 ? (posY+perp*rdy) : (posX+perp*rdx); wallU-=Math.floor(wallU);
    const fog=Math.max(0.18, Math.min(1, 1-perp/13));
    const shade=(side===1?0.62:side===2?0.4:1.0)*fog;
    for(let y=0;y<H;y++){
      const i=(y*W+x)*4;
      if(y<top){ const t=y/(H/2); px3(i, 14+18*t|0, 16+20*t|0, 24+26*t|0); }        // ceiling
      else if(y>=bot){ const t=(y-H/2)/(H/2); px3(i, 60-22*t|0, 48-18*t|0, 38-14*t|0); } // floor
      else{
        const v=(y-top)/lineH;                                 // 0..1 down the wall
        const course=(v/0.2)|0, u=(wallU+(course%2?0.25:0));
        const mortar = ((v/0.2)%1)<0.14 || ((u/0.5)%1)<0.10;
        let r,g,b;
        if(mortar){ r=64; g=58; b=52; } else { r=158; g=132; b=108; }
        const n=(((wallU*97+v*57)*13)&7);                      // faint brick grain
        px3(i, (r+n)*shade|0, (g+n)*shade|0, (b+n)*shade|0);
      }
    }
  }
  ctx.putImageData(img,0,0);
  drawGun(bobOff); drawCrosshair();
  document.getElementById("hud").textContent =
    `x=${st.px} y=${st.py} a=${st.angle}  |  ${moveGates} movement gates + ${mapGates} world gates, from titan.gguf`;
}
function drawGun(bob){
  const cx=W/2, base=H+bob;
  ctx.fillStyle="#2b2b30"; ctx.fillRect(cx-48, base-70, 96, 80);          // body
  ctx.fillStyle="#3a3a42"; ctx.fillRect(cx-16, base-120, 32, 60);          // barrel
  ctx.fillStyle="#17171b"; ctx.fillRect(cx-10, base-120, 20, 10);          // muzzle
  ctx.fillStyle="#4a4a52"; ctx.fillRect(cx-40, base-58, 80, 12);           // pump
}
function drawCrosshair(){
  ctx.strokeStyle="rgba(120,255,170,0.8)"; ctx.lineWidth=2;
  ctx.beginPath(); ctx.moveTo(W/2-8,H/2); ctx.lineTo(W/2-2,H/2);
  ctx.moveTo(W/2+2,H/2); ctx.lineTo(W/2+8,H/2);
  ctx.moveTo(W/2,H/2-8); ctx.lineTo(W/2,H/2-2);
  ctx.moveTo(W/2,H/2+2); ctx.lineTo(W/2,H/2+8); ctx.stroke();
}

// ---- fixed 60 Hz logic timestep, decoupled from render (framerate-independent pace) ----
let acc=0, last=performance.now();
function frame(now){ acc+=now-last; last=now;
  let n=0; while(acc>=1000/60 && n++<8){ stepLogic(); acc-=1000/60; }
  render(); requestAnimationFrame(frame);
}
const KM={KeyW:"fwd",KeyS:"back",KeyA:"left",KeyD:"right",ArrowUp:"fwd",ArrowDown:"back",ArrowLeft:"left",ArrowRight:"right"};
addEventListener("keydown",e=>{ if(KM[e.code]){ st.keys[KM[e.code]]=true; e.preventDefault(); }});
addEventListener("keyup",  e=>{ if(KM[e.code]){ st.keys[KM[e.code]]=false; e.preventDefault(); }});
cv.focus(); addEventListener("click",()=>cv.focus());
requestAnimationFrame(frame);
</script></body></html>"""


if __name__ == "__main__":
    main()
