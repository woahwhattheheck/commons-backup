#!/usr/bin/env python3
"""host/sdc_playground_ui.py — THE SDC PLAYGROUND, interactive (owner 07-18). Port 7901.

A LIVE DEMO, not a video: you paint Life cells, orbit the tesseract, draw the automaton's seed — your input is DATA.
Each chunk of steps is a fresh ONE-TIME BUTTON THAT DIES (CLAUDE.md): the server spawns `sdc_playground.py step TOY K
STATEHEX` (one-way argv: the current state routed in), the child powers the stored gates K steps (output→input each
step = the SDC computing successive moments), writes frames + the final state to the SAFEZONE, and EXITS. The browser
reads the safezone and paints. The SERVER NEVER TOUCHES THE MODEL — it never imports titan_circuit, never mmaps titan.
NO network out. Nothing touches the SDC while it runs.

  python host/sdc_playground_ui.py     # opens http://127.0.0.1:7901/
"""
import json, os, re, subprocess, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
PORT = 7901
PY = sys.executable
PLAY = os.path.join(HERE, "sdc_playground.py")
SAFEZONE = "C:/llm/sdc_out/playground_result.json"
_LOCK = threading.Lock()
_HEXRE = re.compile(r"^[0-9a-fA-F]*$")
_TOYS = {"tess": 36, "life": 16, "ca90": 80, "ca30": 80, "ca110": 80}   # toy -> default steps per button press


def run_step(toy, n, state):
    """Press the button: spawn the ONE-WAY ENDING child, wait for it to EXIT, read the SAFEZONE it wrote."""
    if toy not in _TOYS: return {"error": f"unknown toy {toy}"}
    if not _HEXRE.match(state or "") or len(state) > 300: return {"error": "bad state"}
    argv = [PY, PLAY, "step", toy, str(n)] + ([state] if state else [])
    with _LOCK:
        try:
            p = subprocess.run(argv, cwd=HERE, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=120)
        except subprocess.TimeoutExpired:
            return {"error": "sandbox timed out"}
        if p.returncode != 0:
            return {"error": f"sandbox exited {p.returncode}", "stderr": (p.stderr or "")[-400:]}
        try:
            return json.load(open(SAFEZONE, encoding="utf-8"))
        except Exception as ex:
            return {"error": f"no safezone result ({ex})"}


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SDC Playground</title><style>
:root{--ink:#05070d;--panel:#0d1320;--panel2:#0a0f1a;--line:#1d2636;--text:#EAF0FA;--muted:#8493ac;--dim:#566079;
--amber:#FFB020;--cyan:#39E0D6;--vio:#9b8cff;--pink:#ff6ac1;--good:#49e6a0;--mono:ui-monospace,"Cascadia Code",Consolas,monospace;
--sans:system-ui,"Segoe UI",sans-serif}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 700px at 72% -12%,#101a2e 0,var(--ink) 62%);color:var(--text);font-family:var(--sans);
-webkit-font-smoothing:antialiased;overflow-x:hidden}
.wrap{max-width:1120px;margin:0 auto;padding:22px 20px 56px}
.hero{border:1px solid var(--line);border-radius:18px;padding:18px 22px;margin-bottom:14px;background:linear-gradient(180deg,var(--panel),var(--panel2))}
.hero h1{margin:0;font-family:var(--mono);font-size:22px;letter-spacing:.4px}
.hero h1 b{color:var(--cyan)}
.hero p{margin:6px 0 0;color:var(--muted);max-width:820px;font-size:13.5px}
.flow{margin-top:9px;font-family:var(--mono);font-size:11px;color:var(--dim)}.flow span{color:var(--cyan)}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 14px}
.tab{font-family:var(--mono);font-size:13px;padding:9px 15px;border:1px solid var(--line);border-radius:11px;color:var(--muted);
cursor:pointer;background:var(--panel);transition:.12s;user-select:none}
.tab:hover{color:var(--text)}
.tab.on{color:var(--ink);background:linear-gradient(180deg,var(--cyan),#22b9b0);border-color:transparent;font-weight:600}
.stage{position:relative;border:1px solid var(--line);border-radius:16px;overflow:hidden;background:#04060b;aspect-ratio:16/10;touch-action:none}
canvas{display:block;width:100%;height:100%;cursor:crosshair}
.hint{position:absolute;left:12px;bottom:10px;font-family:var(--mono);font-size:11px;color:rgba(160,180,210,.55);pointer-events:none}
.busy{position:absolute;right:12px;top:10px;font-family:var(--mono);font-size:11px;color:var(--amber);opacity:0;transition:.2s;pointer-events:none}
.busy.on{opacity:.9}
.load{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;
background:rgba(4,6,11,.86);text-align:center;padding:20px}
.load .ring{width:44px;height:44px;border:3px solid #1c2740;border-top-color:var(--cyan);border-radius:50%;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.load .t{font-family:var(--mono);font-size:13px;color:var(--text)}
.load .s{font-family:var(--mono);font-size:11px;color:var(--dim);max-width:460px}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:12px}
.bar .meta{font-family:var(--mono);color:var(--dim);font-size:11.5px}
button{cursor:pointer;background:transparent;color:var(--cyan);border:1px solid #204a48;font-family:var(--mono);font-size:12.5px;
padding:7px 13px;border-radius:9px;transition:.12s}
button:hover{background:rgba(57,224,214,.10)}
button.sec{color:var(--muted);border-color:var(--line)}
button.on{color:var(--ink);background:var(--cyan);border-color:transparent}
input[type=range]{accent-color:var(--cyan);width:110px}
label{font-family:var(--mono);font-size:11.5px;color:var(--muted);display:flex;gap:7px;align-items:center}
.foot{margin-top:20px;color:var(--dim);font-family:var(--mono);font-size:11px;text-align:center}
.foot b{color:var(--good)}
</style></head><body><div class="wrap">
<div class="hero">
<h1>THE <b>SDC</b> PLAYGROUND <span style="color:var(--dim);font-size:13px">&nbsp;· interactive</span></h1>
<p>Everything here is computed by <b>logic gates stored inside titan.gguf</b> — and you can reach in: paint living cells,
grab the hypercube, reseed the automaton. Your input is routed into the stored circuit, the SDC computes what happens
next, and the browser draws what it wrote to the safezone.</p>
<div class="flow">your input &rarr; <span>SDC</span> &rarr; <span>safezone</span> &rarr; drawn here &nbsp;&middot;&nbsp; <span>NO network</span> &middot; reversible &middot; GGUF-valid</div>
</div>
<div class="tabs" id="tabs"></div>
<div class="stage" id="stage"><canvas id="cv"></canvas>
  <div class="hint" id="hint"></div>
  <div class="busy" id="busy">&#9679; SDC computing&hellip;</div>
  <div class="load" id="load"><div class="ring"></div><div class="t" id="loadt">powering the SDC…</div><div class="s" id="loads"></div></div>
</div>
<div class="bar" id="controls"></div>
<div class="foot">a live demo — every step is a fresh button press into the stored gates &middot; <b>~0 RAM</b> &middot; nothing touches the SDC while it runs</div>
</div>
<script>
const TOYS=[
 {id:'tess',label:'✦ Tesseract (4D)'},
 {id:'life',label:'☘ Game of Life'},
 {id:'ca110',label:'▦ Rule 110'},
 {id:'ca90',label:'△ Sierpinski'},
 {id:'ca30',label:'⚡ Chaos'},
];
const el=id=>document.getElementById(id);
const cv=el('cv'), ctx=cv.getContext('2d');
let DPR=Math.min(2,window.devicePixelRatio||1);
let CUR=null, TIMER=null, FETCHING=false;

function fitCanvas(){const r=cv.getBoundingClientRect();cv.width=Math.round(r.width*DPR);cv.height=Math.round(r.height*DPR);}
window.addEventListener('resize',()=>{fitCanvas(); if(T[CUR]&&T[CUR].onResize)T[CUR].onResize();});
function tabs(){el('tabs').innerHTML=TOYS.map(t=>`<div class="tab${t.id==CUR?' on':''}" onclick="pick('${t.id}')">${t.label}</div>`).join('');}
function setLoad(on,t,s){el('load').style.display=on?'flex':'none';if(t)el('loadt').textContent=t;if(s!==undefined)el('loads').textContent=s;}
function busy(on){el('busy').classList.toggle('on',!!on);}

async function fetchStep(toy,n,state){
  FETCHING=true; busy(true);
  try{
    const r=await fetch('/step?toy='+toy+'&n='+n+'&state='+(state||''));
    return await r.json();
  }catch(e){return {error:String(e)};}
  finally{FETCHING=false; busy(false);}
}

function pick(id){
  if(CUR===id)return;
  if(CUR&&T[CUR].exit)T[CUR].exit();
  CUR=id;tabs();fitCanvas();
  ctx.fillStyle='#04060b';ctx.fillRect(0,0,cv.width,cv.height);
  T[id].enter();
}

// THE DRIVER — vsync-aligned rAF when visible (no timer judder), watchdog interval when rAF is throttled/occluded.
let _lastStep=0,_lastRaf=0;
function stepFrame(){
  const t=performance.now();const dt=Math.min(0.1,(_lastStep?(t-_lastStep):16)/1000);_lastStep=t;
  if(CUR&&T[CUR])T[CUR].tick(dt);
}
(function rafLoop(){requestAnimationFrame(rafLoop);_lastRaf=performance.now();stepFrame();})();
setInterval(()=>{if(performance.now()-_lastRaf>300)stepFrame();},100);   // keeps it alive when rAF is starved

function controls(html){el('controls').innerHTML=html;}
function hint(t){el('hint').textContent=t;}
function meta(t){const m=el('meta');if(m)m.textContent=t;}

// pointer plumbing (mouse + touch)
let PTR={down:false,x:0,y:0,px:0,py:0};
function evPos(e){const r=cv.getBoundingClientRect();const p=e.touches?e.touches[0]:e;
  return {x:(p.clientX-r.left)*DPR, y:(p.clientY-r.top)*DPR};}
for(const[ev,h]of[['pointerdown','down'],['pointermove','move'],['pointerup','up'],['pointerleave','up']]){
  cv.addEventListener(ev,e=>{const p=evPos(e);
    if(h=='down'){PTR.down=true;PTR.x=PTR.px=p.x;PTR.y=PTR.py=p.y;cv.setPointerCapture&&e.pointerId!==undefined&&cv.setPointerCapture(e.pointerId);}
    else if(h=='move'){PTR.px=PTR.x;PTR.py=PTR.y;PTR.x=p.x;PTR.y=p.y;}
    else PTR.down=false;
    if(T[CUR]&&T[CUR].pointer)T[CUR].pointer(h,p.x,p.y,e);e.preventDefault();});}
cv.addEventListener('wheel',e=>{if(T[CUR]&&T[CUR].wheel)T[CUR].wheel(e.deltaY);e.preventDefault();},{passive:false});

// ======================================================================= TESSERACT — grab it, spin it, zoom it
const tess={
  q:[],state:'',edges:null,scale:8192,gates:0,total:0,
  cur:null,nxt:null,frac:0,speed:9,zoom:1,yaw:0.5,pitch:-0.25,vyaw:0.004,vpitch:0,playing:true,
  enter(){
    controls(`<span class="meta" id="meta">loading…</span><span style="flex:1"></span>
      <button id="pp" onclick="tess.playing=!tess.playing;this.textContent=tess.playing?'❚❚ pause':'▶ play'">❚❚ pause</button>
      <label>4D speed <input type="range" min="2" max="30" value="9" oninput="tess.speed=+this.value"></label>
      <button class="sec" onclick="tess.reset()">↻ reset</button>`);
    hint('drag to orbit · scroll to zoom — the 4D tumble itself is the SDC');
    setLoad(true,'powering the SDC…','477,184 gates settle per step of 4D rotation — buffering the first moments…');
    this.q=[];this.state='';this.cur=null;this.total=0;this.pump(true);
  },
  exit(){},
  reset(){this.q=[];this.state='';this.cur=null;this.nxt=null;this.total=0;this.zoom=1;this.pump(true);},
  async pump(first){
    if(FETCHING)return;
    const j=await fetchStep('tess',36,this.state);
    if(j.error){setLoad(true,'sandbox error',j.error);return;}
    this.edges=j.edges;this.scale=j.scale;this.gates=j.gates;this.state=j.state;
    this.q.push(...j.frames);this.total+=j.frames.length;
    if(first){setLoad(false);}
    meta(`${this.gates.toLocaleString()} gates/step · ${this.total.toLocaleString()} steps computed · buffer ${this.q.length}`);
  },
  tick(dt){
    if(this.q.length<20&&!FETCHING)this.pump(false);
    if(PTR.down){this.vyaw=(PTR.x-PTR.px)*0.004/DPR;this.vpitch=(PTR.y-PTR.py)*0.004/DPR;}
    this.yaw+=this.vyaw;this.pitch=Math.max(-1.2,Math.min(1.2,this.pitch+this.vpitch));
    if(!PTR.down){this.vyaw*=0.97;this.vpitch*=0.92;if(Math.abs(this.vyaw)<0.0006)this.vyaw=0.0006;}
    if(this.playing){this.frac+=dt*this.speed;
      while(this.frac>=1&&this.q.length>1){this.frac-=1;this.cur=this.q.shift();}
      if(!this.cur&&this.q.length)this.cur=this.q.shift();
      this.nxt=this.q[0]||this.cur;}
    if(!this.cur)return;
    this.draw();
    meta(`${this.gates.toLocaleString()} gates/step · ${this.total.toLocaleString()} steps computed · buffer ${this.q.length}`);
  },
  wheel(dy){this.zoom=Math.max(0.4,Math.min(2.6,this.zoom*(dy>0?0.92:1.08)));},
  draw(){
    const W=cv.width,H=cv.height,S=this.scale,f=this.frac%1;
    ctx.fillStyle='rgba(4,6,11,0.30)';ctx.fillRect(0,0,W,H);
    const cx=W/2,cy=H/2,R=Math.min(W,H)*0.30*this.zoom;
    const cy1=Math.cos(this.yaw),sy1=Math.sin(this.yaw),cp=Math.cos(this.pitch),sp=Math.sin(this.pitch);
    const a=this.cur,b=this.nxt||this.cur;
    const pts=[];
    for(let i=0;i<16;i++){
      let x=(a[i][0]+(b[i][0]-a[i][0])*f)/S, y=(a[i][1]+(b[i][1]-a[i][1])*f)/S,
          z=(a[i][2]+(b[i][2]-a[i][2])*f)/S, w=(a[i][3]+(b[i][3]-a[i][3])*f)/S;
      const k4=1.9/(2.7-w);x*=k4;y*=k4;z*=k4;                       // 4D -> 3D
      let X=x*cy1-z*sy1, Z=x*sy1+z*cy1;                              // your orbit (camera)
      let Y=y*cp-Z*sp;   Z=y*sp+Z*cp;
      const k3=2.6/(3.2-Z);
      pts.push({sx:cx+X*k3*R, sy:cy+Y*k3*R, d:(Z+1)/2, w:(w+1)/2});
    }
    ctx.lineCap='round';
    for(const[i,j]of this.edges){
      const p=pts[i],q=pts[j];const wm=(p.w+q.w)/2,dm=(p.d+q.d)/2;const hue=200+wm*130;
      ctx.strokeStyle=`hsla(${hue},90%,${44+dm*26}%,${0.35+dm*0.6})`;
      ctx.lineWidth=(0.6+dm*2.4)*DPR;ctx.shadowBlur=14*DPR;ctx.shadowColor=`hsla(${hue},95%,60%,.85)`;
      ctx.beginPath();ctx.moveTo(p.sx,p.sy);ctx.lineTo(q.sx,q.sy);ctx.stroke();
    }
    ctx.shadowBlur=0;
    for(const p of pts){const r=(1.3+p.d*2.5)*DPR;const hue=200+p.w*130;
      ctx.fillStyle=`hsla(${hue},95%,${60+p.d*20}%,${0.5+p.d*0.5})`;
      ctx.beginPath();ctx.arc(p.sx,p.sy,r,0,7);ctx.fill();}
  },
  pointer(){}
};

// ======================================================================= LIFE — paint cells into a living world
const life={
  G:32,grid:null,prev:null,q:[],state:'',gates:0,total:0,acc:0,speed:8,playing:true,sprite:null,dirty:false,
  enter(){
    controls(`<span class="meta" id="meta">loading…</span><span style="flex:1"></span>
      <button id="pp" onclick="life.playing=!life.playing;this.textContent=life.playing?'❚❚ pause':'▶ play'">❚❚ pause</button>
      <label>speed <input type="range" min="1" max="20" value="8" oninput="life.speed=+this.value"></label>
      <button class="sec" onclick="life.seed('soup')">soup</button>
      <button class="sec" onclick="life.seed('pento')">R-pentomino</button>
      <button class="sec" onclick="life.seed('clear')">clear</button>`);
    hint('click / drag on the grid to PAINT LIVING CELLS — the physics is the SDC');
    setLoad(true,'powering the SDC…','518,144 gates settle per generation — growing the first moments…');
    this.grid=null;this.q=[];this.state='';this.total=0;this.makeSprite();this.pump(true);
  },
  exit(){},
  makeSprite(){
    const cs=Math.floor(Math.min(cv.width,cv.height)/this.G);
    const s=document.createElement('canvas');s.width=s.height=cs*2;const c2=s.getContext('2d');
    const g=c2.createRadialGradient(cs,cs,0,cs,cs,cs);
    g.addColorStop(0,'rgba(190,255,235,1)');g.addColorStop(0.35,'rgba(73,230,160,0.9)');
    g.addColorStop(0.75,'rgba(45,170,150,0.25)');g.addColorStop(1,'rgba(45,170,150,0)');
    c2.fillStyle=g;c2.fillRect(0,0,cs*2,cs*2);this.sprite=s;
  },
  onResize(){this.makeSprite();},
  bitsToHex(bits){const nb=(bits.length+7)>>3;const b=new Uint8Array(nb);
    bits.forEach((v,i)=>{if(v)b[i>>3]|=1<<(i&7);});
    return Array.from(b).map(x=>x.toString(16).padStart(2,'0')).join('');},
  seed(kind){
    const G=this.G,g=new Array(G*G).fill(0);
    if(kind=='soup'){for(let i=0;i<G*G;i++)if(Math.random()<0.33)g[i]=1;}
    else if(kind=='pento'){for(const[r,k]of[[0,1],[0,2],[1,0],[1,1],[2,1]])g[(r+15)*G+(k+15)]=1;}
    this.grid=g;this.prev=null;this.restartFrom(g);
  },
  restartFrom(g){this.q=[];this.state=this.bitsToHex(g);this.dirty=false;this.pump(false);},
  async pump(first){
    if(FETCHING)return;
    const st=this.dirty&&this.grid?this.bitsToHex(this.grid):this.state;
    if(this.dirty){this.q=[];this.dirty=false;}
    const j=await fetchStep('life',16,st);
    if(j.error){setLoad(true,'sandbox error',j.error);return;}
    this.gates=j.gates;this.state=j.state;this.q.push(...j.frames);this.total+=j.frames.length;
    if(first){setLoad(false);this.grid=j.frames[0]?j.frames[0].slice():this.grid;}
    meta(`${this.gates.toLocaleString()} gates/gen · gen ${this.total.toLocaleString()} · alive ${this.grid?this.grid.reduce((a,b)=>a+b,0):0} · buffer ${this.q.length}`);
  },
  tick(dt){
    if(this.q.length<8&&!FETCHING)this.pump(false);
    if(this.playing&&this.q.length){this.acc+=dt*this.speed;
      while(this.acc>=1&&this.q.length){this.acc-=1;this.prev=this.grid;this.grid=this.q.shift();}}
    if(!this.grid)return;
    this.draw();
  },
  cellAt(x,y){const G=this.G;const cs=Math.min(cv.width,cv.height)/G;
    const ox=(cv.width-cs*G)/2,oy=(cv.height-cs*G)/2;
    const k=Math.floor((x-ox)/cs),r=Math.floor((y-oy)/cs);
    return (r>=0&&r<G&&k>=0&&k<G)?r*G+k:-1;},
  pointer(kind,x,y){
    if(kind!='down'&&!(kind=='move'&&PTR.down))return;
    const i=this.cellAt(x,y);if(i<0||!this.grid)return;
    if(kind=='down'&&this.grid[i]&&!PTR.paintMode){PTR.paintVal=0;}else if(kind=='down'){PTR.paintVal=1;}
    if(this.grid[i]!==PTR.paintVal){this.grid[i]=PTR.paintVal;this.dirty=true;}
  },
  draw(){
    const W=cv.width,H=cv.height,G=this.G;
    ctx.fillStyle='rgba(4,7,12,0.38)';ctx.fillRect(0,0,W,H);
    const cs=Math.min(W,H)/G,ox=(W-cs*G)/2,oy=(H-cs*G)/2;
    ctx.strokeStyle='rgba(60,80,110,0.10)';ctx.lineWidth=1;
    for(let i=0;i<=G;i++){ctx.beginPath();ctx.moveTo(ox+i*cs,oy);ctx.lineTo(ox+i*cs,oy+G*cs);ctx.stroke();
      ctx.beginPath();ctx.moveTo(ox,oy+i*cs);ctx.lineTo(ox+G*cs,oy+i*cs);ctx.stroke();}
    const sp=this.sprite,ss=sp.width;
    for(let r=0;r<G;r++)for(let k=0;k<G;k++){const i=r*G+k;if(!this.grid[i])continue;
      const born=this.prev&&!this.prev[i];
      const x=ox+k*cs+cs/2,y=oy+r*cs+cs/2;
      ctx.globalAlpha=born?1:0.85;
      ctx.drawImage(sp,x-ss/2,y-ss/2);
      if(born){ctx.globalAlpha=0.9;ctx.fillStyle='rgba(220,255,245,0.9)';ctx.beginPath();ctx.arc(x,y,cs*0.18,0,7);ctx.fill();}
    }
    ctx.globalAlpha=1;
  }
};

// ======================================================================= CA — draw the seed, watch the universe fall
function makeCA(id,rule,palette){
  return {
    id,rule,palette,W:127,rows:[],q:[],state:'',seedRow:null,gates:0,total:0,acc:0,speed:26,wf:null,wfRow:0,playing:true,
    enter(){
      controls(`<span class="meta" id="meta">loading…</span><span style="flex:1"></span>
        <button id="pp" onclick="T['${id}'].playing=!T['${id}'].playing;this.textContent=T['${id}'].playing?'❚❚ pause':'▶ play'">❚❚ pause</button>
        <label>speed <input type="range" min="4" max="60" value="26" oninput="T['${id}'].speed=+this.value"></label>
        <button class="sec" onclick="T['${id}'].seed('dot')">single dot</button>
        <button class="sec" onclick="T['${id}'].seed('rand')">random</button>`);
      hint('click the BRIGHT TOP STRIP to edit the seed — each falling row is one press of the button');
      setLoad(false);
      this.seedRow=new Array(this.W).fill(0);this.seedRow[(this.W/2)|0]=1;
      this.restart();
    },
    exit(){},
    onResize(){this.rebuildWf();},
    bitsToHex(bits){const nb=(bits.length+7)>>3;const b=new Uint8Array(nb);
      bits.forEach((v,i)=>{if(v)b[i>>3]|=1<<(i&7);});
      return Array.from(b).map(x=>x.toString(16).padStart(2,'0')).join('');},
    seed(kind){this.seedRow=new Array(this.W).fill(0);
      if(kind=='dot')this.seedRow[(this.W/2)|0]=1;else for(let i=0;i<this.W;i++)this.seedRow[i]=Math.random()<0.5?1:0;
      this.restart();},
    restart(){this.rows=[this.seedRow.slice()];this.q=[];this.total=0;this.state=this.bitsToHex(this.seedRow);this.rebuildWf();this.pump();},
    rebuildWf(){this.wf=document.createElement('canvas');this.wf.width=cv.width;this.wf.height=cv.height*2;this.wfRow=0;
      const c2=this.wf.getContext('2d');c2.fillStyle='#04060b';c2.fillRect(0,0,this.wf.width,this.wf.height);
      for(const r of this.rows)this.paintRow(r,true);},
    async pump(){
      if(FETCHING)return;
      const j=await fetchStep(this.id,80,this.state);
      if(j.error){setLoad(true,'sandbox error',j.error);return;}
      this.gates=j.gates;this.state=j.state;this.q.push(...j.rows);
      meta(`rule ${this.rule} · ${this.gates.toLocaleString()} gates/row · row ${this.total.toLocaleString()} · buffer ${this.q.length}`);
    },
    paintRow(row,init){
      const c2=this.wf.getContext('2d');const cw=cv.width/this.W;const ch=Math.max(3*DPR,cw*0.9);
      const y=this.wfRow*ch;
      if(y+ch>this.wf.height){                                  // scroll the waterfall up by half
        const half=(this.wf.height/2)|0;
        c2.drawImage(this.wf,0,half,this.wf.width,this.wf.height-half,0,0,this.wf.width,this.wf.height-half);
        c2.fillStyle='#04060b';c2.fillRect(0,this.wf.height-half,this.wf.width,half);
        this.wfRow=Math.ceil((this.wf.height-half)/ch);}
      const yy=this.wfRow*ch;const hue=this.palette(this.total);
      for(let k=0;k<this.W;k++){if(!row[k])continue;
        c2.fillStyle=`hsl(${hue+(k/this.W)*18},92%,${52+((k*7)%13)}%)`;
        c2.fillRect(k*cw,yy,Math.ceil(cw)-1,Math.ceil(ch)-1);}
      this.wfRow++;if(!init)this.total++;
    },
    tick(dt){
      if(this.q.length<40&&!FETCHING)this.pump();
      if(this.playing){this.acc+=dt*this.speed;
        while(this.acc>=1&&this.q.length){this.acc-=1;const r=this.q.shift();this.rows.push(r);if(this.rows.length>400)this.rows.shift();this.paintRow(r);}}
      // blit: seed strip on top, waterfall under it
      const W=cv.width,H=cv.height;const cw=W/this.W;const stripH=Math.max(16*DPR,cw*1.6);
      ctx.fillStyle='#04060b';ctx.fillRect(0,0,W,H);
      const ch=Math.max(3*DPR,cw*0.9);const visRows=Math.floor((H-stripH)/ch);
      const srcY=Math.max(0,(this.wfRow-visRows))*ch;
      ctx.drawImage(this.wf,0,srcY,W,visRows*ch,0,stripH,W,visRows*ch);
      // seed strip
      ctx.fillStyle='rgba(20,28,46,0.95)';ctx.fillRect(0,0,W,stripH);
      for(let k=0;k<this.W;k++){
        ctx.fillStyle=this.seedRow[k]?'#FFB020':'rgba(70,86,116,0.35)';
        ctx.fillRect(k*cw+1,3*DPR,cw-2,stripH-6*DPR);}
      ctx.fillStyle='rgba(255,176,32,0.8)';ctx.font=`${10*DPR}px monospace`;
      ctx.fillText('SEED — click to edit',6*DPR,stripH-5*DPR);
    },
    pointer(kind,x,y){
      const W=cv.width;const cw=W/this.W;const stripH=Math.max(16*DPR,cw*1.6);
      if(y>stripH)return;
      if(kind!='down'&&!(kind=='move'&&PTR.down))return;
      const k=Math.floor(x/cw);if(k<0||k>=this.W)return;
      if(kind=='down')PTR.caVal=this.seedRow[k]?0:1;
      if(this.seedRow[k]!==PTR.caVal){this.seedRow[k]=PTR.caVal;this.restart();}
    }
  };
}

const T={tess,life,
  ca110:makeCA('ca110',110,t=>36+ (t*0.05)%40),
  ca90:makeCA('ca90',90,t=>175+(t*0.06)%120),
  ca30:makeCA('ca30',30,t=>200+(t*0.05)%100)};

tabs();fitCanvas();pick('tess');
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
            self._send(PAGE, "text/html; charset=utf-8"); return
        if u.path == "/step":
            toy = q.get("toy", [""])[0]; state = q.get("state", [""])[0]
            n = q.get("n", ["0"])[0]; n = min(int(n), 200) if n.isdigit() and int(n) > 0 else _TOYS.get(toy, 30)
            self._send(run_step(toy, n, state)); return
        self._send({"error": "not found"})


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"SDC Playground (interactive)  ->  http://127.0.0.1:{PORT}/   (server never touches the model; presses the button, reads the safezone)")
    try: webbrowser.open(f"http://127.0.0.1:{PORT}/")
    except Exception: pass
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nstopped.")
