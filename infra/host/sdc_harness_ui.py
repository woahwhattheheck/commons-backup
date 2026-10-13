#!/usr/bin/env python3
"""host/sdc_harness_ui.py — CHAT UI for the 3 SDC inference harnesses, with a MODEL SELECTOR (owner 07-18). Port 7902.

Type a message, hit Send; the model replies AS LONG AS IT WANTS (until it emits its end-of-turn token). Multi-turn.

Containment law: the SERVER NEVER TOUCHES A MODEL. On Send it fires the one-time BUTTON — writes the conversation to the
sandbox and spawns `sdc_harness.py --chatfile ...` as an ending child; the forward pass runs in the STORAGE sandbox and
the reply is written to the SAFEZONE (C:/llm/sdc_out/harness_result.json); the server READS the safezone. No model in the
server, no network out.

  python host/sdc_harness_ui.py     # opens http://127.0.0.1:7902/
"""
import glob, json, os, subprocess, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
PORT = 7902
PY = sys.executable
BUTTON = os.path.join(HERE, "sdc_prompt_button.py")   # the one-time gated one-way prompt button (mirrors sdc_button.py)
MODELS_DIR = "C:/llm/models"
OUT = "C:/llm/sdc_out"
PENDING = OUT + "/chat_pending.json"                  # host-side handoff to the button (NOT the sandbox, NOT the SDC)
SAFEZONE = OUT + "/harness_result.json"               # the ONE spot the display reads
_LOCK = threading.Lock()


def list_models():
    out = []
    for p in sorted(glob.glob(MODELS_DIR + "/*.gguf")):
        try: gb = os.path.getsize(p) / 1e9
        except OSError: gb = 0
        out.append({"path": p.replace("\\", "/"), "name": os.path.basename(p), "gb": round(gb, 2)})
    return out


def run_chat(harness, model, keep, messages):
    """THE SERVER NEVER TOUCHES THE SDC. On Send it does two things only:
      (1) FIRE THE ONE-TIME BUTTON — spawn sdc_prompt_button.py (fire-and-forget); it beams the prompt ONE-WAY into the
          SDC and DIES. The server does NOT wait on it, hold it, or read anything back from it — no bridge, no short.
      (2) READ ONLY the safezone and push it to the chat.
    No inference here, no host forward pass, no float math. The button injects one-way; the SDC computes and writes the
    safezone; the display reads that one spot."""
    with _LOCK:
        os.makedirs(OUT, exist_ok=True)
        if messages:                                                              # hand the prompt to the button (host-side staging)
            try:
                with open(PENDING, "w", encoding="utf-8") as fh:
                    json.dump({"harness": harness, "model": model, "keep": keep, "messages": messages}, fh)
                subprocess.Popen([PY, BUTTON, PENDING], cwd=HERE,                  # (1) the button beams it in and dies
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception: pass
        try:                                                                      # (2) READ the one spot: the safezone
            res = dict(json.load(open(SAFEZONE, encoding="utf-8")))
        except Exception:
            res = {"generated": "", "stopped": "no safezone yet",
                   "note": "the harness only reads the safezone; the SDC has not written a reply there yet"}
    res.setdefault("harness", harness); res.setdefault("model", os.path.basename(model) if model else "")
    res.setdefault("generated", ""); res.setdefault("tokens", 0); res.setdefault("stopped", "")
    res.setdefault("working_state_in_storage_mb", 0); res.setdefault("network", "NONE"); res["wall_s"] = 0
    return res


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SDC Chat</title><style>
:root{--ink:#0A0D13;--panel:#121722;--panel2:#0E131C;--line:#232A38;--text:#E7EBF3;--muted:#8A94A8;--dim:#5B6579;
--amber:#FFB020;--cyan:#3AD6C6;--good:#3fd08a;--vio:#9b8cff;--mono:ui-monospace,"Cascadia Code",Consolas,monospace;--sans:system-ui,"Segoe UI",sans-serif}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:radial-gradient(1100px 560px at 72% -10%,#151d2b 0,var(--ink) 60%);color:var(--text);font-family:var(--sans);display:flex;flex-direction:column;height:100vh}
.bar{border-bottom:1px solid var(--line);background:linear-gradient(180deg,var(--panel),var(--panel2));padding:12px 18px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.bar h1{margin:0;font-family:var(--mono);font-size:15px}.bar h1 b{color:var(--amber)}
select{background:#0a0d14;border:1px solid var(--line);color:var(--text);font-family:var(--mono);font-size:12px;padding:7px 9px;border-radius:8px;outline:none;max-width:280px}
.harn{display:flex;gap:6px}
.hbtn{cursor:pointer;border:1px solid var(--line);border-radius:8px;padding:6px 11px;background:#0a0d14;font-family:var(--mono);font-size:12px;color:var(--muted)}
.hbtn.on{border-color:var(--amber);color:var(--amber);background:rgba(255,176,32,.08)}
.keep{display:flex;gap:7px;align-items:center;font-family:var(--mono);font-size:11px;color:var(--muted)}
input[type=range]{accent-color:var(--amber);width:90px}
.newc{margin-left:auto;cursor:pointer;background:transparent;color:var(--muted);border:1px solid var(--line);font-family:var(--mono);font-size:12px;padding:6px 11px;border-radius:8px}
.chat{flex:1;overflow-y:auto;padding:22px 18px}
.wrap{max-width:820px;margin:0 auto;display:flex;flex-direction:column;gap:14px}
.msg{display:flex;gap:10px;max-width:88%}
.msg.u{align-self:flex-end;flex-direction:row-reverse}
.av{width:30px;height:30px;border-radius:8px;flex:0 0 30px;display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:12px;font-weight:700}
.msg.u .av{background:rgba(255,176,32,.15);color:var(--amber);border:1px solid rgba(255,176,32,.4)}
.msg.a .av{background:rgba(58,214,198,.13);color:var(--cyan);border:1px solid rgba(58,214,198,.4)}
.bub{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:11px 14px;white-space:pre-wrap;word-break:break-word;line-height:1.55;font-size:14.5px}
.msg.u .bub{background:rgba(255,176,32,.06);border-color:rgba(255,176,32,.25)}
.meta{font-family:var(--mono);font-size:10.5px;color:var(--dim);margin-top:5px}
.dots span{display:inline-block;width:6px;height:6px;margin:0 2px;border-radius:50%;background:var(--cyan);animation:b 1.2s infinite}
.dots span:nth-child(2){animation-delay:.2s}.dots span:nth-child(3){animation-delay:.4s}
@keyframes b{0%,80%,100%{opacity:.25}40%{opacity:1}}
.err{color:#e66767;font-family:var(--mono);font-size:12px;white-space:pre-wrap}
.foot{border-top:1px solid var(--line);background:var(--panel2);padding:12px 18px}
.foot .in{max-width:820px;margin:0 auto;display:flex;gap:10px;align-items:flex-end}
textarea{flex:1;background:#0a0d14;border:1px solid var(--line);color:var(--text);font-family:var(--sans);font-size:14px;padding:11px 13px;border-radius:11px;outline:none;resize:none;min-height:46px;max-height:180px}
textarea:focus{border-color:var(--amber)}
.send{cursor:pointer;background:linear-gradient(180deg,var(--amber),#e0980f);color:#1a1204;border:none;font-family:var(--mono);font-weight:700;font-size:14px;padding:12px 20px;border-radius:11px;height:46px}
.send:disabled{opacity:.5;cursor:default}
.tag{max-width:820px;margin:6px auto 0;font-family:var(--mono);font-size:10.5px;color:var(--dim);text-align:center}
.tag span{color:var(--cyan)}
</style></head><body>
<div class="bar">
<h1>SDC <b>CHAT</b></h1>
<select id="model"></select>
<div class="harn">
<div class="hbtn on" data-h="h1" onclick="pickH('h1')">H1 dense</div>
<div class="hbtn" data-h="h2" onclick="pickH('h2')">H2 routed</div>
<div class="hbtn" data-h="h3" onclick="pickH('h3')">H3 coding</div>
</div>
<div class="keep" id="keepwrap" style="display:none">keep <span id="keepv">0.25</span><input id="keep" type="range" min="0.05" max="1" step="0.05" value="0.25" oninput="keepv.textContent=this.value"></div>
<button class="newc" onclick="newChat()">＋ new chat</button>
</div>
<div class="chat" id="chat"><div class="wrap" id="wrap"></div></div>
<div class="foot">
<div class="in"><textarea id="box" placeholder="Message the model on the SDC…  (Enter to send · Shift+Enter for newline)" rows="1"></textarea>
<button class="send" id="send" onclick="send()">Send</button></div>
<div class="tag">your message &rarr; <span>SDC (storage sandbox)</span> &rarr; <span>safezone</span> &rarr; here · the model replies as long as it wants · no host RAM/CPU/GPU compute · no network</div>
</div>
<script>
const MODELS = __MODELS__; let H='h1', BUSY=false; const MSGS=[];
const el=id=>document.getElementById(id);
el('model').innerHTML=MODELS.map(m=>`<option value="${m.path}"${m.name.indexOf('SmolLM2')>=0?' selected':''}>${m.name} · ${m.gb} GB</option>`).join('');
function pickH(h){H=h;document.querySelectorAll('.hbtn').forEach(b=>b.classList.toggle('on',b.dataset.h===h));el('keepwrap').style.display=(h==='h1')?'none':'flex';}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function newChat(){MSGS.length=0;el('wrap').innerHTML='';}
function scroll(){const c=el('chat');c.scrollTop=c.scrollHeight;}
function addMsg(role,text,meta){
  const w=el('wrap');const d=document.createElement('div');d.className='msg '+(role==='user'?'u':'a');
  d.innerHTML=`<div class="av">${role==='user'?'you':'sdc'}</div><div><div class="bub">${text}</div>${meta?`<div class="meta">${meta}</div>`:''}</div>`;
  w.appendChild(d);scroll();return d;
}
const box=el('box');
box.addEventListener('input',()=>{box.style.height='auto';box.style.height=Math.min(180,box.scrollHeight)+'px';});
box.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}});
async function send(){
  if(BUSY)return; const text=box.value.trim(); if(!text)return;
  BUSY=true; el('send').disabled=true; box.value=''; box.style.height='auto';
  MSGS.push({role:'user',content:text}); addMsg('user',esc(text));
  const pend=addMsg('assistant','<span class="dots"><span></span><span></span><span></span></span>','powering the SDC…');
  try{
    const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({harness:H,model:el('model').value,keep:parseFloat(el('keep').value),messages:MSGS})});
    const j=await r.json();
    if(j.error){pend.querySelector('.bub').innerHTML='<span class="err">'+esc(j.error)+(j.stderr?'\n\n'+esc(j.stderr):'')+'</span>';pend.querySelector('.meta').textContent='';MSGS.pop();}
    else{
      const reply=j.generated&&j.generated.length?j.generated:'(no text)';
      MSGS.push({role:'assistant',content:reply});
      pend.querySelector('.bub').innerHTML=esc(reply);
      pend.querySelector('.meta').textContent=`${j.harness} · ${j.model} · ${j.tokens} tok · stopped: ${j.stopped} · ${j.wall_s}s · state ${j.working_state_in_storage_mb}MB in storage · net ${j.network}`;
    }
  }catch(e){pend.querySelector('.bub').innerHTML='<span class="err">'+esc(String(e))+'</span>';MSGS.pop();}
  scroll(); BUSY=false; el('send').disabled=false; box.focus();
}
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else (json.dumps(body) if ctype.startswith("application/json") else body).encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if urlparse(self.path).path == "/":
            self._send(PAGE.replace("__MODELS__", json.dumps(list_models())), "text/html; charset=utf-8"); return
        self._send({"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/chat":
            self._send({"error": "not found"}); return
        try:
            n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        except Exception as ex:
            self._send({"error": f"bad body ({ex})"}); return
        msgs = [{"role": m.get("role", "user"), "content": str(m.get("content", ""))[:4000]}
                for m in (body.get("messages") or [])][-20:]
        try: keep = min(max(float(body.get("keep", 0.25)), 0.05), 1.0)
        except (TypeError, ValueError): keep = 0.25
        self._send(run_chat(body.get("harness", "h1"), body.get("model", ""), keep, msgs))


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"SDC Chat UI  ->  http://127.0.0.1:{PORT}/   (server never touches a model; fires the button, reads the safezone)")
    try: webbrowser.open(f"http://127.0.0.1:{PORT}/")
    except Exception: pass
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nstopped.")
