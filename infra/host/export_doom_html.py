#!/usr/bin/env python3
"""host/export_doom_html.py — export DOOM-from-the-SDC as ONE double-click HTML file (owner 07-16).

The tkinter window fought the console/focus on the owner's box. This removes every moving part: it reads the two stored
circuits OUT of titan.gguf's params (the 736-gate movement/turn/collision circuit + the 737-gate map circuit), embeds
their exact gate arrays into a self-contained HTML page, and the page RIPPLES those same gates in JavaScript. So the game
still runs the SDC's stored circuit — the world is read out of the params at load, and every move/turn/collision is the
stored gate-net evaluating — but it opens by double-click in the browser, where the keyboard just works. No Python at
run time, no server, no console, no focus quirk.

  python host/export_doom_html.py     # write "DOOM (double-click to play).html" to the Desktop (+ the build_02 folder)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
import titan_doom as D

DESK = "C:/Users/lucys/OneDrive/Desktop"
OUT  = os.path.join(DESK, "DOOM (double-click to play).html")
BUILD = os.path.join(DESK, "DOOM_builds", "build_02_playable-html")


def circuit_json(name):
    c = TC.load(name)
    return {"nin": c["n_in"], "nw": c["n_wire"], "ga": c["ga"], "gb": c["gb"], "outs": c["outs"]}


def main():
    # (re)build + store both circuits so they are definitely present, then read them back out of the params
    mv, outs = D.build_movement(); mi = TC.store("doom_move", mv, outs, slot=3)
    import sdc_doom as SD; SD.build_map()
    MOVE = circuit_json("doom_move"); MAP = circuit_json("doom_map")
    print(f"read stored circuits from titan.gguf: movement {len(MOVE['ga'])} gates, map {len(MAP['ga'])} gates.", flush=True)

    cfg = {"TURN": D.TURN, "SPEED": D.SPEED, "CELL": D.CELL, "MAP": D.MAP,
           "MOVE": MOVE, "MAP_CIR": MAP, "moveGates": len(MOVE["ga"]), "mapGates": len(MAP["ga"])}
    html = PAGE.replace("/*__DATA__*/", json.dumps(cfg))
    os.makedirs(BUILD, exist_ok=True)
    for p in (OUT, os.path.join(BUILD, "DOOM.html")):
        with open(p, "w", encoding="utf-8") as f: f.write(html)
    print(f"wrote {OUT}  ({len(html):,} bytes)", flush=True)
    print(f"also saved to {BUILD}\\DOOM.html", flush=True)
    print("double-click the Desktop file — it opens in your browser. Click the game, then W/A/S/D. Nothing else needed.", flush=True)


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>DOOM from the SDC</title>
<style>
 html,body{margin:0;height:100%;background:#0b0e14;color:#e7ecf5;font:14px ui-monospace,Consolas,monospace;overflow:hidden}
 #wrap{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px}
 canvas{background:#000;border:1px solid #232c3a;border-radius:8px;image-rendering:pixelated;max-width:96vw;max-height:74vh}
 #hud{color:#3fd08a;font-size:12px;letter-spacing:.02em}
 #help{color:#8593a8;font-size:12px}#help b{color:#f0a020}
 #title{font-size:16px}#title b{color:#3fd08a}
</style></head><body><div id="wrap">
 <div id="title">DOOM &mdash; <b>the game world + logic are stored circuits in titan.gguf</b></div>
 <canvas id="c" width="640" height="400" tabindex="0"></canvas>
 <div id="hud">&nbsp;</div>
 <div id="help"><b>W</b>/<b>S</b> move &nbsp; <b>A</b>/<b>D</b> turn &nbsp; arrows too &nbsp;&middot;&nbsp; click the screen if keys don't respond</div>
</div>
<script>
const CFG = /*__DATA__*/;
const {TURN, SPEED, CELL, MAP, MOVE, MAP_CIR, moveGates, mapGates} = CFG;

// ---- ripple a stored circuit exactly like titan_circuit.ripple (Python) ----
function ripple(cir, inbits){
  const v = new Uint8Array(cir.nw); v[1] = 1;
  for(let i=0;i<cir.nin;i++) v[2+i] = inbits[i] & 1;
  const base = 2 + cir.nin, ga = cir.ga, gb = cir.gb, ng = ga.length;
  for(let i=0;i<ng;i++) v[base+i] = 1 - (v[ga[i]] & v[gb[i]]);
  return cir.outs.map(o => o===0 ? 0 : (o===1 ? 1 : v[o]));
}
const bits = (val,n)=>{const a=[];for(let j=0;j<n;j++)a.push((val>>j)&1);return a;};
const frombits = a => a.reduce((s,b,i)=>s+(b<<i),0);

// ---- the WORLD, read out of the stored map circuit at load (64 addressed reads) ----
function wallFromCircuit(cx,cy){ return ripple(MAP_CIR, bits(((cy<<3)|cx),6))[0]; }
const GRID = [];
for(let cy=0;cy<8;cy++){ const row=[]; for(let cx=0;cx<8;cx++) row.push(wallFromCircuit(cx,cy)); GRID.push(row); }
function wallAt(wx,wy){ const cx=((wx&0xff)/CELL)|0, cy=((wy&0xff)/CELL)|0; return GRID[cy][cx]; }

// ---- one tick THROUGH the stored movement circuit (collision from the map circuit) ----
function step(px,py,angle,keys){
  const mv = (keys.fwd?1:0) - (keys.back?1:0);
  const rad = angle/256*2*Math.PI;
  const dx = Math.round(Math.cos(rad)*SPEED)*mv;
  const dy = Math.round(Math.sin(rad)*SPEED)*mv;
  const wallx = wallAt(px+dx, py), wally = wallAt(px, py+dy);        // collision read from the stored world
  const turnL = keys.left?1:0, turnR = keys.right?1:0;
  const inb = bits(px&0xff,8).concat(bits(py&0xff,8), bits(dx&0xff,8), bits(dy&0xff,8),
                    [wallx,wally], bits(angle&0xff,8), [turnL,turnR]);
  const o = ripple(MOVE, inb);                                       // the stored gate-net computes the next state
  return [frombits(o.slice(0,8)), frombits(o.slice(8,16)), frombits(o.slice(16,24))];
}

// ---- first-person ray-cast render ----
const cv = document.getElementById("c"), ctx = cv.getContext("2d");
const W = cv.width, H = cv.height, COLS = 320, CW = W/COLS, FOV = 60*Math.PI/180;
const st = {px:48, py:48, angle:32, keys:{}};
function render(){
  ctx.fillStyle = "#12121a"; ctx.fillRect(0,0,W,H/2);                // ceiling
  ctx.fillStyle = "#1b1b22"; ctx.fillRect(0,H/2,W,H/2);              // floor
  const rad = st.angle/256*2*Math.PI;
  for(let x=0;x<COLS;x++){
    const ra = rad - FOV/2 + FOV*x/COLS, sx=Math.cos(ra), sy=Math.sin(ra);
    let dist=0; while(dist<400){ dist+=3; if(wallAt((st.px+sx*dist)|0,(st.py+sy*dist)|0)) break; }
    dist *= Math.cos(ra-rad);                                        // fisheye fix
    const h = Math.min(H, (CELL*H/(dist+1))|0);
    const sh = Math.max(0, 255-(dist|0));
    ctx.fillStyle = `rgb(${(sh/3)|0},${sh},${(sh/2)|0})`;
    ctx.fillRect(x*CW, (H-h)/2, CW+1, h);
  }
}
function tick(){
  [st.px, st.py, st.angle] = step(st.px, st.py, st.angle, st.keys);
  render();
  document.getElementById("hud").textContent =
    `x=${st.px} y=${st.py} angle=${st.angle}  |  ${moveGates} movement gates + ${mapGates} world gates, from titan.gguf`;
  requestAnimationFrame(tick);
}

// ---- input (browser keydown/keyup: clean, no auto-repeat stutter) ----
const KM = {KeyW:"fwd",KeyS:"back",KeyA:"left",KeyD:"right",ArrowUp:"fwd",ArrowDown:"back",ArrowLeft:"left",ArrowRight:"right"};
addEventListener("keydown", e=>{ if(KM[e.code]){ st.keys[KM[e.code]]=true; e.preventDefault(); } });
addEventListener("keyup",   e=>{ if(KM[e.code]){ st.keys[KM[e.code]]=false; e.preventDefault(); } });
cv.focus(); addEventListener("click", ()=>cv.focus());
tick();
</script></body></html>"""


if __name__ == "__main__":
    main()
