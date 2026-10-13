#!/usr/bin/env python3
"""host/sdc_gamestudio_server.py — the SDC Generative Game Studio. The model runs ONLY on the SDC; the game runs ON THE
SDC. No numpy. No presets. No host game-logic harness. (rewritten 07-16 to the owner's spec.)

The container is a browser tab with two things: a DISPLAY and a TEXT FIELD for the game DESCRIPTION. Nothing else.
  - GENERATION: you describe a game in words. The server runs a bounded, ending, gated-sandbox forward-pass READ of
    titan.gguf's real trained weights (sdc_gen_once -> sdc_read, PURE PYTHON) and the trained weights decide which
    mechanics your words mean (cosine over the model's own geometry) -> a game spec. No lexicon, no word-catch.
  - GAMEPLAY: the game's logic is stored logic CIRCUITS in titan.gguf -- a bounded-move circuit, a collision-select
    circuit, and a lane-rotate circuit. Every tick the SERVER (the SDC) ripples those stored circuits to advance the
    world, move the player, and resolve collisions. The browser tab only DRAWS the board and reads the KEYBOARD.
    There is no game logic, no circuit, and no preset in the page.

  python host/sdc_gamestudio_server.py            # serve http://127.0.0.1:8110/  (SDCGameStudio.cmd opens it)
  python host/sdc_gamestudio_server.py selftest   # headless: build+store circuits, verify vs reference, tick a game
"""
import json, math, os, subprocess, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as tc
import sdc_safe

PORT = 8110
PY = sys.executable
BOARD = 13                                                      # sdc_gen_once emits a 13x13 board
WB = lambda n: max(1, math.ceil(math.log2(n)))                 # address-bit width for n cells


# ------------------------------------------------------------------ the engine's stored circuits (game-agnostic) -----
def build_move(WW, HW, N, M):
    """(cx[WW], cy[HW], U, D, L, R, B) -> (nx[WW], ny[HW]). Bounded to the board, held in place when blocked (B)."""
    c = tc.Circuit(WW + HW + 5); I = c.IN
    cx = I[0:WW]; cy = I[WW:WW + HW]; U, D, L, R, B = I[WW + HW], I[WW + HW + 1], I[WW + HW + 2], I[WW + HW + 3], I[WW + HW + 4]
    atL = c.eq_const(cx, 0); atR = c.eq_const(cx, N - 1); atT = c.eq_const(cy, 0); atB = c.eq_const(cy, M - 1)
    cxp = c.add(cx, c.cvec(1, WW)); cxm = c.add(cx, c.cvec((1 << WW) - 1, WW))
    cyp = c.add(cy, c.cvec(1, HW)); cym = c.add(cy, c.cvec((1 << HW) - 1, HW))
    gR = c.and_(R, c.not_(atR)); gL = c.and_(L, c.not_(atL)); gD = c.and_(D, c.not_(atB)); gU = c.and_(U, c.not_(atT))
    cX = [c.mux(gR, c.mux(gL, cx[k], cxm[k]), cxp[k]) for k in range(WW)]     # gR ? cxp : (gL ? cxm : cx)
    cY = [c.mux(gD, c.mux(gU, cy[k], cym[k]), cyp[k]) for k in range(HW)]
    nx = [c.mux(B, cX[k], cx[k]) for k in range(WW)]                          # B ? cx : cX  (blocked -> stay)
    ny = [c.mux(B, cY[k], cy[k]) for k in range(HW)]
    return c, nx + ny


def build_sel(length, aw):
    """(vec[length], addr[aw]) -> vec[addr]. A MUX tree: addressing the occupancy line reads the cell's bit."""
    c = tc.Circuit(length + aw); vec = c.IN[0:length]; ad = c.IN[length:length + aw]
    cur = [vec[i] if i < length else c.C0 for i in range(1 << aw)]
    for a in ad:
        cur = [c.mux(a, cur[k], cur[k + 1]) for k in range(0, len(cur), 2)]
    return c, [cur[0]]


def build_rotate(length, direction):
    """rotate a bit-line one cell (moving tiles = a rotating occupancy line). Pure routing: out[i] = in[(i-dir) mod L]."""
    c = tc.Circuit(length)
    outs = [c.IN[((i - direction) % length + length) % length] for i in range(length)]
    return c, outs


def load_engine():
    """Ensure the four engine circuits are stored in titan.gguf (once, reversibly) and return them loaded."""
    WWb = WB(BOARD)
    E = {
        "move": sdc_safe.ensure(f"gg_move_{BOARD}x{BOARD}", lambda: build_move(WWb, WWb, BOARD, BOARD)),
        "sel":  sdc_safe.ensure(f"gg_sel_{BOARD}",          lambda: build_sel(BOARD, WWb)),
        "rotp": sdc_safe.ensure(f"gg_rot_{BOARD}_p",        lambda: build_rotate(BOARD, +1)),
        "rotm": sdc_safe.ensure(f"gg_rot_{BOARD}_m",        lambda: build_rotate(BOARD, -1)),
    }
    return E, WWb


# ------------------------------------------------------------------ the game state, advanced BY the stored circuits --
class Game:
    """Holds one generated game's state. Every tick advances it by RIPPLING the stored circuits (the SDC computes);
    the render just reads the resulting occupancy. Ported 1:1 from the universal engine -- no game is built in."""
    def __init__(self, spec, E, WWb):
        self.E = E; self.WW = WWb; self.W = spec["W"]; self.H = spec["H"]
        self.sym = {ch: {"roles": set(s["roles"]), "dir": s.get("dir"), "speed": s.get("speed") or 1}
                    for ch, s in spec["sym"].items()}
        grid = [list(r) for r in spec["grid"]]
        self.start = (1, self.H - 2)
        chg = {ch: [0] * self.H for ch in self.sym}
        for y in range(self.H):
            for x in range(self.W):
                ch = grid[y][x]; s = self.sym.get(ch)
                if not s: continue
                if "player" in s["roles"]: self.start = (x, y)
                else: chg[ch][y] |= (1 << x)
        self.layers = []
        for ch, s in self.sym.items():
            if "player" in s["roles"]: continue
            vert = "move" in s["roles"] and s["dir"] in ("up", "down")
            if vert:
                lines = []
                for x in range(self.W):
                    col = 0
                    for y in range(self.H):
                        if (chg[ch][y] >> x) & 1: col |= (1 << y)
                    lines.append(col)
            else:
                lines = list(chg[ch])
            self.layers.append({"ch": ch, "kind": "v" if vert else "h", "lines": lines, "dir": s["dir"],
                                "speed": s.get("speed") or 2, "moving": "move" in s["roles"], "solid": "solid" in s["roles"],
                                "deadly": "deadly" in s["roles"], "goal": "goal" in s["roles"], "pushable": "pushable" in s["roles"]})
        pl = next((c for c, s in self.sym.items() if "player" in s["roles"]), None)
        self.hop = ("hop" in self.sym[pl]["roles"]) if pl else True
        self.px, self.py = self.start; self.sx, self.sy = self.start
        self.score = 0; self.lives = 3; self.msg = ""; self.frame = 0; self.prev = set()

    def occ(self, L, x, y):
        """Is layer L occupied at (x,y)? Read by ADDRESSING the stored select circuit (the SDC generates the answer)."""
        if L["kind"] == "v":
            return tc.ripple(self.E["sel"], tc.bits(L["lines"][x], self.H) + tc.bits(y, self.WW))[0]
        return tc.ripple(self.E["sel"], tc.bits(L["lines"][y], self.W) + tc.bits(x, self.WW))[0]

    def any_role(self, x, y, role):
        for L in self.layers:
            if L[role] and self.occ(L, x, y): return L
        return None

    def tick_world(self):
        self.frame += 1
        for L in self.layers:
            if not L["moving"]: continue
            if self.frame % max(1, 7 - L["speed"]) != 0: continue
            direction = 1 if L["dir"] in ("right", "down") else -1
            length = self.H if L["kind"] == "v" else self.W
            rc = self.E["rotp"] if direction == 1 else self.E["rotm"]
            L["lines"] = [tc.frombits(tc.ripple(rc, tc.bits(ln, length))) for ln in L["lines"]]

    def try_move(self, u, d, l, r):
        tx = min(self.W - 1, max(0, self.px + (1 if r else 0) - (1 if l else 0)))
        ty = min(self.H - 1, max(0, self.py + (1 if d else 0) - (1 if u else 0)))
        pu = self.any_role(tx, ty, "pushable")
        if pu:
            bx = tx + (1 if r else 0) - (1 if l else 0); by = ty + (1 if d else 0) - (1 if u else 0)
            if 0 <= bx < self.W and 0 <= by < self.H and not self.any_role(bx, by, "solid") and not self.any_role(bx, by, "pushable"):
                if pu["kind"] == "v":
                    pu["lines"][tx] &= ~(1 << ty); pu["lines"][bx] |= (1 << by)
                else:
                    pu["lines"][ty] &= ~(1 << tx); pu["lines"][by] |= (1 << bx)
            else:
                return
        blk = 1 if self.any_role(tx, ty, "solid") else 0
        o = tc.ripple(self.E["move"], tc.bits(self.px, self.WW) + tc.bits(self.py, self.WW)
                      + [1 if u else 0, 1 if d else 0, 1 if l else 0, 1 if r else 0, blk])
        self.px = tc.frombits(o[0:self.WW]); self.py = tc.frombits(o[self.WW:2 * self.WW]); self.resolve()

    def resolve(self):
        if self.any_role(self.px, self.py, "deadly"):
            self.lives -= 1; self.px, self.py = self.sx, self.sy
            self.msg = "game over - Generate again" if self.lives <= 0 else "hit!"
            if self.lives <= 0: self.lives = 3; self.score = 0
        elif self.any_role(self.px, self.py, "goal"):
            self.score += 1; self.px, self.py = self.sx, self.sy; self.msg = "reached! +1"

    def tick(self, keys):
        self.tick_world()
        cur = set(keys)
        if self.hop:                                            # discrete: move once on each rising edge
            for k in cur - self.prev:
                self.try_move(k == "up", k == "down", k == "left", k == "right")
        else:                                                   # continuous: one step per tick while held
            if cur & {"up", "down", "left", "right"}:
                self.try_move("up" in cur, "down" in cur, "left" in cur, "right" in cur)
            else:
                self.resolve()
        self.prev = cur

    def board(self):
        """The drawable state: per-cell color of the top occupying layer (read straight from state for painting)."""
        col = {"goal": "#e6c34a", "deadly": "#e0554b", "solid": "#3a4152", "pushable": "#c9853f", "move": "#4a5568"}
        grid = [["" for _ in range(self.W)] for _ in range(self.H)]
        for L in self.layers:
            role = "goal" if L["goal"] else "deadly" if L["deadly"] else "solid" if L["solid"] else "pushable" if L["pushable"] else "move"
            for y in range(self.H):
                for x in range(self.W):
                    bit = (L["lines"][x] >> y) & 1 if L["kind"] == "v" else (L["lines"][y] >> x) & 1
                    if bit: grid[y][x] = col[role]
        return {"W": self.W, "H": self.H, "grid": grid, "px": self.px, "py": self.py,
                "score": self.score, "lives": self.lives, "msg": self.msg, "hop": self.hop, "layers": len(self.layers)}


# ------------------------------------------------------------------ generation on the SDC (unchanged path) ----------
def generate(desc):
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([PY, os.path.join(HERE, "sdc_gen_once.py"), desc or "a maze to explore"],
                           capture_output=True, text=True, timeout=120, env=env)
        line = (r.stdout or "").strip().splitlines()[-1] if r.stdout.strip() else ""
        return json.loads(line) if line else {"error": r.stderr[-300:] or "no output"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


_ENGINE, _WW = load_engine()
_lock = threading.Lock()
_state = {"game": None}


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>SDC Generative Game Studio</title><style>
 html,body{margin:0;height:100%;background:#0b0e14;color:#e7ecf5;font:13px ui-monospace,Consolas,monospace;overflow:hidden}
 #app{position:absolute;inset:0;display:flex;gap:12px;padding:12px;box-sizing:border-box}
 #left{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;min-width:0}
 #right{width:360px;display:flex;flex-direction:column;gap:8px}
 canvas{background:#000;border:1px solid #232c3a;border-radius:8px;image-rendering:pixelated;max-width:100%;max-height:64vh}
 #t{font-size:15px;color:#c98b3f;text-align:center}#hud{color:#c9a15a;font-size:12px}#hint{color:#8593a8;font-size:12px}
 textarea{height:90px;background:#0a0d12;color:#cbd5e6;border:1px solid #232c3a;border-radius:8px;padding:10px;font:13px ui-monospace,monospace;resize:none;line-height:1.4}
 button{background:#141a24;color:#e7ecf5;border:1px solid #232c3a;border-radius:8px;padding:10px 13px;cursor:pointer;font:13px ui-monospace,monospace}
 button:hover{border-color:#c9a15a;color:#c9a15a}button.go{border-color:#3fd08a;color:#3fd08a;font-weight:bold}
 .k{color:#8593a8;font-size:11px;line-height:1.5}#badge{font-size:11px}#badge.ok{color:#3fd08a}#badge.bad{color:#ff6b5b}
 h3{margin:2px 0;font-size:13px;color:#c98b3f}#meta{color:#c9a15a;font-size:11px;white-space:pre-wrap}
</style></head><body><div id="app">
 <div id="left"><div id="t">SDC GENERATIVE GAME STUDIO &mdash; the model reads your meaning off the SDC; stored circuits play it</div>
  <canvas id="c" width="520" height="520" tabindex="0"></canvas><div id="hud">&nbsp;</div>
  <div id="hint">click the game &middot; arrows / WASD &middot; describe a game, then Generate</div></div>
 <div id="right"><h3>describe a game (any words &mdash; the meaning drives it)</h3>
  <textarea id="spec">hop across the busy road to reach the safe side</textarea>
  <div><button class="go" id="gen">Generate &#9654;</button></div>
  <div class="k">generation = a forward-pass READ of titan.gguf's real weights (pure python, no numpy). the trained model
   decides which mechanics your words mean. gameplay = stored logic circuits rippled on the server (the SDC). this tab
   only draws the board and reads keys &mdash; no circuit, no game logic, no presets live here.</div>
  <div id="badge" class="k">&nbsp;</div><div id="meta"></div></div></div>
<script>
"use strict";
// PURE CONTAINER. No Circuit, no ripple, no game rules. It POSTs the description to /gen and the pressed keys to /tick,
// and paints whatever board the SDC returns. Every world update / move / collision is computed server-side.
const cv=document.getElementById("c"),ctx=cv.getContext("2d");let B=null,keys={},running=false;
const KM={KeyW:"up",ArrowUp:"up",KeyS:"down",ArrowDown:"down",KeyA:"left",ArrowLeft:"left",KeyD:"right",ArrowRight:"right"};
addEventListener("keydown",e=>{if(document.activeElement!==cv)return;const a=KM[e.code];if(!a)return;e.preventDefault();keys[a]=true;});
addEventListener("keyup",e=>{const a=KM[e.code];if(a)keys[a]=false;});
cv.addEventListener("click",()=>cv.focus());
function draw(){
 if(!B){return;} const W=B.W,H=B.H,s=Math.min(cv.width/W,cv.height/H),ox=(cv.width-s*W)/2,oy=(cv.height-s*H)/2;
 ctx.fillStyle="#05070c";ctx.fillRect(0,0,cv.width,cv.height);
 for(let y=0;y<H;y++)for(let x=0;x<W;x++){ctx.fillStyle="#0e1420";ctx.fillRect(ox+x*s|0,oy+y*s|0,Math.ceil(s),Math.ceil(s));}
 for(let y=0;y<H;y++)for(let x=0;x<W;x++){const c=B.grid[y][x];if(c){ctx.fillStyle=c;ctx.fillRect(ox+x*s+1|0,oy+y*s+1|0,Math.ceil(s-2),Math.ceil(s-2));}}
 ctx.fillStyle="#3fd08a";ctx.beginPath();ctx.arc(ox+B.px*s+s/2,oy+B.py*s+s/2,s*0.35,0,7);ctx.fill();
 document.getElementById("hud").textContent="score "+B.score+"  lives "+B.lives+"  "+B.msg+"  |  "+B.layers+" tile-layers, all state from stored circuits";
}
async function tick(){
 if(!B||!running){return;}
 try{const k=Object.keys(keys).filter(x=>keys[x]).join(",");
  const r=await fetch("/tick?k="+encodeURIComponent(k));B=await r.json();draw();}catch(e){}
}
async function generate(){const b=document.getElementById("badge");b.textContent="reading your meaning off the SDC...";b.className="k";
 try{const desc=document.getElementById("spec").value;const r=await fetch("/gen?desc="+encodeURIComponent(desc));const j=await r.json();
  if(j.error){b.textContent="x "+j.error;b.className="k bad";return;}
  B=j.board;const m=j.meta||{},sc=m.scores||{};const rank=Object.keys(sc).sort((a,c)=>sc[c]-sc[a]);
  b.textContent="move "+j.gates.move+" + select "+j.gates.sel+" + rotate(routing) gates in titan.gguf, rippled server-side";b.className="k ok";
  document.getElementById("meta").textContent="words read: "+(m.words||[]).join(" ")+"\nmeaning -> mechanics (cosine on the trained weights):\n"+rank.map(k=>"  "+k+"  "+sc[k]).join("\n");
  running=true;draw();cv.focus();
 }catch(e){b.textContent="x "+e;b.className="k bad";}}
document.getElementById("gen").onclick=generate;setInterval(tick,1000/15);generate();
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
        elif u.path == "/gen":
            spec = generate(parse_qs(u.query).get("desc", [""])[0])
            if "error" in spec: self._send(spec); return
            with _lock:
                g = Game(spec, _ENGINE, _WW); _state["game"] = g
                gates = {"move": len(_ENGINE["move"]["ga"]), "sel": len(_ENGINE["sel"]["ga"]),
                         "rot": len(_ENGINE["rotp"]["ga"])}
                self._send({"board": g.board(), "meta": spec.get("meta", {}), "gates": gates})
        elif u.path == "/tick":
            k = parse_qs(u.query).get("k", [""])[0]
            keys = [x for x in k.split(",") if x]
            with _lock:
                g = _state["game"]
                if g is None: self._send({"error": "no game"}); return
                g.tick(keys); self._send(g.board())
        else:
            self._send({"error": "not found"})


def selftest():
    E, WWb = _ENGINE, _WW
    import random; random.seed(5)
    ok_sel = all(tc.ripple(E["sel"], tc.bits(v, BOARD) + tc.bits(a, WWb))[0] == ((v >> a) & 1)
                 for v, a in [(random.randint(0, (1 << BOARD) - 1), random.randint(0, BOARD - 1)) for _ in range(500)])
    ok_rot = all(tc.frombits(tc.ripple(E["rotp"], tc.bits(v, BOARD))) == (((v << 1) | (v >> (BOARD - 1))) & ((1 << BOARD) - 1))
                 for v in [random.randint(0, (1 << BOARD) - 1) for _ in range(200)])
    ok_mv = True
    for _ in range(500):
        cx, cy = random.randint(0, BOARD - 1), random.randint(0, BOARD - 1)
        u, d, l, r, b = (random.random() < 0.5 for _ in range(5))
        o = tc.ripple(E["move"], tc.bits(cx, WWb) + tc.bits(cy, WWb) + [int(u), int(d), int(l), int(r), int(b)])
        # the circuit is edge-gated with R>L and D>U priority (not net r-l) -- the reference matches THAT
        ex = cx if b else (cx + 1 if (r and cx < BOARD - 1) else (cx - 1 if (l and cx > 0) else cx))
        ey = cy if b else (cy + 1 if (d and cy < BOARD - 1) else (cy - 1 if (u and cy > 0) else cy))
        if (tc.frombits(o[0:WWb]), tc.frombits(o[WWb:2 * WWb])) != (ex, ey): ok_mv = False
    print(f"[verify] select circuit  == vec[addr] over 500 cases: {ok_sel}")
    print(f"[verify] rotate circuit  == rotl over 200 cases: {ok_rot}")
    print(f"[verify] move circuit    == bounded move over 500 cases: {ok_mv}")
    print(f"[store]  move {len(E['move']['ga'])} + select {len(E['sel']['ga'])} + rotate {len(E['rotp']['ga'])} gates in titan.gguf")
    spec = generate("hop across the busy road to reach the safe side")
    if "error" in spec: print("[gen] ERROR", spec); return
    g = Game(spec, E, WWb)
    for i in range(40): g.tick(["up"] if i % 3 == 0 else [])
    b = g.board()
    print(f"[play]  generated '{spec['meta']['desc']}' -> {b['layers']} layers; ran 40 ticks; player at ({b['px']},{b['py']}) score {b['score']}")
    print("=> generation = model on the SDC; every tick = stored circuits rippled server-side; browser only draws.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest(); sys.exit(0)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"SDC Generative Game Studio -> http://127.0.0.1:{PORT}/", flush=True)
    try: webbrowser.open(f"http://127.0.0.1:{PORT}/")
    except Exception: pass
    srv.serve_forever()
