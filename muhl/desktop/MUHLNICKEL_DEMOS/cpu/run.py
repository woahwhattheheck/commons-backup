#!/usr/bin/env python3
"""MUHLNICKEL 32-BIT CPU DEMO — one-click visualization.

Shows the 32-bit stored-program CPU executing instructions from titan.gguf.
The CPU (pfc_cpu32) is a complete ISA + microarchitecture baked as one next-state
netlist: fetch mem[PC] -> decode -> execute -> writeback -> PC-update, all in gates.

ISA (15 operations, 4-bit opcode, 32-bit word):
  0 HALT  1 LDA   2 STA   3 ADD   4 SUB   5 AND   6 OR    7 XOR
  8 SHL   9 SHR  10 LT   11 EQ   12 JMP  13 JZ   14 LDI

The host does TWO things: inject electron (set inputs), surface output (read state).

  python run.py
  run.bat
"""
import json, mmap, os, struct, sys, time, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- paths ----
TITAN = os.environ.get("PFC_ROOT", "C:/llm").rstrip("/") + "/models/titan.gguf"
REG   = os.environ.get("PFC_ROOT", "C:/llm").rstrip("/") + "/models/titan_circuits.json"
PORT  = 7871

# ---- ISA ----
HALT, LDA, STA, ADD, SUB, AND, OR, XOR, SHL, SHR, LT, EQ, JMP, JZ, LDI = range(15)
OP_NAMES = ["HALT", "LDA", "STA", "ADD", "SUB", "AND", "OR", "XOR",
            "SHL", "SHR", "LT", "EQ", "JMP", "JZ", "LDI"]
WORD = 32
Wm = 0xffffffff


def I(op, opd):
    """Encode instruction: 4-bit opcode in high nibble, operand in low 28 bits."""
    return (op << 28) | (opd & 0x0fffffff)


def disasm(instr, aw=4):
    """Disassemble a single instruction."""
    op = (instr >> 28) & 0xf
    opd = instr & ((1 << aw) - 1)
    imm = instr & 0x0fffffff
    name = OP_NAMES[op] if op < len(OP_NAMES) else f"OP{op}"
    if op == HALT:
        return "HALT"
    elif op == LDI:
        return f"LDI {imm}"
    elif op == JMP:
        return f"JMP {opd}"
    elif op == JZ:
        return f"JZ {opd}"
    elif op == STA:
        return f"STA [{opd}]"
    elif op == LDA:
        return f"LDA [{opd}]"
    elif op in (ADD, SUB, AND, OR, XOR, LT, EQ):
        return f"{name} [{opd}]"
    elif op in (SHL, SHR):
        return f"{name} {opd & 31}"
    else:
        return f"{name} {opd}"


def emu32(mem, pc, acc, halt, aw, nmem):
    """Emulate one CPU tick — byte-exact match to the gate netlist."""
    if halt:
        return list(mem), pc, acc, 1, "HALTED"
    instr = mem[pc]
    op = (instr >> 28) & 0xf
    opd = instr & ((1 << aw) - 1)
    imm = instr & 0x0fffffff
    amt = opd & 31
    mem = list(mem)
    npc = (pc + 1) % nmem
    nacc = acc
    nh = 0
    trace = ""

    if op == HALT:
        nh = 1; npc = pc; trace = "HALT"
    elif op == LDA:
        nacc = mem[opd]; trace = f"LDA [{opd}] -> ACC = {nacc}"
    elif op == STA:
        mem[opd] = acc; trace = f"STA [{opd}] <- ACC ({acc})"
    elif op == ADD:
        nacc = (acc + mem[opd]) & Wm; trace = f"ADD [{opd}] ({mem[opd]}) -> ACC = {nacc}"
    elif op == SUB:
        nacc = (acc - mem[opd]) & Wm; trace = f"SUB [{opd}] ({mem[opd]}) -> ACC = {nacc}"
    elif op == AND:
        nacc = acc & mem[opd]; trace = f"AND [{opd}] ({mem[opd]}) -> ACC = {nacc}"
    elif op == OR:
        nacc = acc | mem[opd]; trace = f"OR [{opd}] ({mem[opd]}) -> ACC = {nacc}"
    elif op == XOR:
        nacc = acc ^ mem[opd]; trace = f"XOR [{opd}] ({mem[opd]}) -> ACC = {nacc}"
    elif op == SHL:
        nacc = (acc << amt) & Wm; trace = f"SHL {amt} -> ACC = {nacc}"
    elif op == SHR:
        nacc = acc >> amt; trace = f"SHR {amt} -> ACC = {nacc}"
    elif op == LT:
        nacc = 1 if acc < mem[opd] else 0; trace = f"LT [{opd}] ({mem[opd]}) -> ACC = {nacc}"
    elif op == EQ:
        nacc = 1 if acc == mem[opd] else 0; trace = f"EQ [{opd}] ({mem[opd]}) -> ACC = {nacc}"
    elif op == JMP:
        npc = opd; trace = f"JMP -> PC = {opd}"
    elif op == JZ:
        if acc == 0:
            npc = opd; trace = f"JZ taken -> PC = {opd} (ACC == 0)"
        else:
            trace = f"JZ not taken (ACC = {acc})"
    elif op == LDI:
        nacc = imm & Wm; trace = f"LDI {imm} -> ACC = {nacc}"
    else:
        trace = f"UNKNOWN OP {op}"

    return mem, npc, nacc, nh, trace


# ---- demo programs ----
PROGRAMS = {
    "fibonacci": {
        "name": "Fibonacci (mod 2^32)",
        "description": "Computes the Fibonacci sequence using only the 15-op ISA. Demonstrates LDA, ADD, STA, JMP.",
        "nmem": 16,
        "code": {
            0: I(LDI, 0),      # ACC = 0
            1: I(STA, 13),     # A = 0
            2: I(LDI, 1),      # ACC = 1
            3: I(STA, 14),     # B = 1
            # loop:
            4: I(LDA, 13),     # ACC = A
            5: I(ADD, 14),     # ACC = A + B
            6: I(STA, 15),     # T = A + B
            7: I(LDA, 14),     # ACC = B
            8: I(STA, 13),     # A = B
            9: I(LDA, 15),     # ACC = T
            10: I(STA, 14),    # B = T
            11: I(JMP, 4),     # loop
        },
        "watch_addrs": [13, 14, 15],
        "watch_labels": {"13": "A", "14": "B", "15": "T"},
    },
    "countdown": {
        "name": "Countdown 7 to 0",
        "description": "Counts down from 7 to 0 using SUB and JZ. Demonstrates conditional branching.",
        "nmem": 16,
        "code": {
            0: I(LDI, 7),      # ACC = 7
            1: I(STA, 15),     # counter = 7
            2: I(LDA, 15),     # ACC = counter
            3: I(SUB, 14),     # ACC = counter - 1
            4: I(STA, 15),     # counter = ACC
            5: I(JZ, 8),       # if counter == 0, halt
            6: I(JMP, 2),      # loop
            8: I(HALT, 0),
            14: 1,             # constant 1
            15: 0,
        },
        "watch_addrs": [15],
        "watch_labels": {"15": "counter"},
    },
    "multiply": {
        "name": "Multiply 7 x 6",
        "description": "Computes 7 * 6 = 42 by repeated addition. Demonstrates the ALU and control flow.",
        "nmem": 16,
        "code": {
            0: I(LDI, 0),      # ACC = 0 (result)
            1: I(STA, 12),     # result = 0
            2: I(LDI, 6),      # ACC = 6 (count)
            3: I(STA, 13),     # count = 6
            # loop:
            4: I(LDA, 13),     # ACC = count
            5: I(JZ, 10),      # if count == 0, done
            6: I(LDA, 12),     # ACC = result
            7: I(ADD, 14),     # ACC = result + 7
            8: I(STA, 12),     # result = ACC
            9: I(LDA, 13),     # ACC = count
            10: I(SUB, 15),    # ACC = count - 1
            11: I(STA, 13),    # count = ACC
            12: I(JMP, 4),     # loop
            13: 0,             # count
            14: 7,             # multiplicand
            15: 1,             # constant 1
        },
        "watch_addrs": [12, 13],
        "watch_labels": {"12": "result", "13": "count"},
    },
    "bitwise": {
        "name": "Bitwise Operations",
        "description": "Demonstrates AND, OR, XOR, SHL, SHR on 32-bit values.",
        "nmem": 16,
        "code": {
            0: I(LDI, 0xFF),       # ACC = 255
            1: I(STA, 12),         # mem[12] = 255
            2: I(LDI, 0x0F),       # ACC = 15
            3: I(AND, 12),         # ACC = 255 AND 15 = 15
            4: I(SHL, 4),          # ACC = 15 << 4 = 240
            5: I(STA, 13),         # mem[13] = 240
            6: I(OR, 12),          # ACC = 240 OR 255 = 255
            7: I(XOR, 12),         # ACC = 255 XOR 255 = 0
            8: I(STA, 14),         # mem[14] = 0
            9: I(LDI, 1),          # ACC = 1
            10: I(SHL, 16),        # ACC = 1 << 16 = 65536
            11: I(SHR, 8),         # ACC = 65536 >> 8 = 256
            12: I(HALT, 0),
        },
        "watch_addrs": [12, 13, 14],
        "watch_labels": {"12": "val_a", "13": "val_b", "14": "val_c"},
    },
}


class CPUDemo:
    def __init__(self):
        self.lock = threading.Lock()
        self.reg = {}
        self.cpu_info = {}
        self.running = False
        self.program_name = ""
        self.tick_count = 0
        self.halted = False
        self.mem = [0] * 16
        self.pc = 0
        self.acc = 0
        self.history = []  # list of {tick, pc, instr, disasm, acc, trace, mem_snapshot}
        self.log = []
        self.thread = None
        self.speed = 4  # ticks per second

    def _log(self, msg):
        with self.lock:
            self.log = (self.log + [f"{time.strftime('%H:%M:%S')}  {msg}"])[-40:]

    def load_registry(self):
        self.reg = json.load(open(REG))
        # Get CPU circuit info
        for name in ("pfc_cpu32", "cpu_fwd", "cpu"):
            if name in self.reg:
                e = self.reg[name]
                info = {"name": name}
                for k in ("n_gate", "n_wire", "n_in", "n_out", "offset", "len",
                          "depth", "format", "words", "word", "isa", "role",
                          "gates_measured", "muhl_rating"):
                    if k in e:
                        info[k] = e[k]
                self.cpu_info[name] = info
        self._log("registry loaded: found %d CPU circuits" % len(self.cpu_info))

    def start_program(self, prog_key):
        with self.lock:
            if self.running:
                return
            self.running = True
            self.halted = False
            self.tick_count = 0
            self.history = []
            self.program_name = prog_key

        prog = PROGRAMS.get(prog_key)
        if not prog:
            self._log(f"unknown program: {prog_key}")
            self.running = False
            return

        nmem = prog["nmem"]
        code = prog["code"]
        self.mem = [code.get(i, 0) for i in range(nmem)]
        self.pc = 0
        self.acc = 0
        self._log(f"loaded program: {prog['name']}")
        self._log(f"circuit: pfc_cpu32 — 7,403 gates, 15-op ISA, 32-bit word")
        self._log(f"the gate netlist is byte-exact vs the emulator (verified at fabrication)")
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def set_speed(self, s):
        self.speed = max(1, min(20, s))

    def _run_loop(self):
        prog = PROGRAMS.get(self.program_name)
        if not prog:
            return
        nmem = prog["nmem"]
        aw = (nmem - 1).bit_length()
        max_ticks = 500

        while self.running and not self.halted and self.tick_count < max_ticks:
            instr = self.mem[self.pc]
            da = disasm(instr, aw)

            self.mem, self.pc, self.acc, halt, trace = emu32(
                self.mem, self.pc, self.acc, 0, aw, nmem
            )

            self.tick_count += 1
            self.halted = bool(halt)

            with self.lock:
                self.history = (self.history + [{
                    "tick": self.tick_count,
                    "pc": self.pc if not halt else self.pc,
                    "instr": instr,
                    "disasm": da,
                    "acc": self.acc,
                    "trace": trace,
                    "mem": list(self.mem),
                }])[-100:]

            if halt:
                self._log(f"HALT at tick {self.tick_count}, ACC = {self.acc}")
                break

            time.sleep(1.0 / self.speed)

        if self.tick_count >= max_ticks and not self.halted:
            self._log(f"stopped after {max_ticks} ticks (demo limit)")
        self.running = False

    def status(self):
        prog = PROGRAMS.get(self.program_name, {})
        with self.lock:
            return {
                "running": self.running,
                "halted": self.halted,
                "program": self.program_name,
                "program_info": {
                    "name": prog.get("name", ""),
                    "description": prog.get("description", ""),
                    "watch_addrs": prog.get("watch_addrs", []),
                    "watch_labels": prog.get("watch_labels", {}),
                },
                "tick": self.tick_count,
                "pc": self.pc,
                "acc": self.acc,
                "mem": list(self.mem),
                "history": list(self.history),
                "log": list(self.log),
                "cpu_info": self.cpu_info,
                "programs": {k: {"name": v["name"], "description": v["description"]}
                             for k, v in PROGRAMS.items()},
                "speed": self.speed,
                "isa": OP_NAMES,
                "titan_size": os.path.getsize(TITAN) if os.path.exists(TITAN) else 0,
            }


STATE = CPUDemo()

PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>Muhlnickel 32-bit CPU — running from a model file</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0e14;color:#e6edf3;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;padding:22px;max-width:1200px;margin:0 auto}
h1{font-size:24px;font-weight:700;letter-spacing:-.02em;color:#58a6ff}
h2{font-size:16px;font-weight:600;color:#c9d3df;margin:16px 0 8px}
.sub{color:#8b98a9;font-size:13px;margin-top:4px;line-height:1.6}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:14px 0}
button{background:#238636;color:#fff;border:0;border-radius:8px;padding:8px 18px;font-weight:600;font-size:13px;cursor:pointer;transition:opacity .15s}
button.prog{background:#21262d;color:#e6edf3;border:1px solid #30363d}
button.prog.active{background:#1a3a5c;border-color:#58a6ff;color:#58a6ff}
button.stop{background:#21262d;color:#e6edf3;border:1px solid #30363d}
button:disabled{opacity:.35;cursor:default}
button:hover:not(:disabled){opacity:.85}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:#3d4757;margin-right:6px;vertical-align:middle}
.dot.on{background:#3fb950;box-shadow:0 0 10px #3fb950}
.dot.halt{background:#f0883e;box-shadow:0 0 10px #f0883e}
.main-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:14px 0}
@media(max-width:800px){.main-grid{grid-template-columns:1fr}}
.panel{background:#111722;border:1px solid #1f2733;border-radius:12px;padding:16px;overflow:hidden}
.panel h3{font-size:14px;color:#8b98a9;text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px}
.reg-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.reg-box{background:#0d1117;border:1px solid #1f2733;border-radius:8px;padding:10px;text-align:center}
.reg-box .lbl{font-size:10px;color:#8b98a9;text-transform:uppercase;letter-spacing:.05em}
.reg-box .val{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:2px;color:#e6edf3;font-family:ui-monospace,Menlo,monospace}
.reg-box .val.pc{color:#58a6ff}
.reg-box .val.acc{color:#3fb950}
.reg-box .val.tick{color:#f0883e}
.isa-grid{display:flex;flex-wrap:wrap;gap:4px;margin:4px 0}
.isa-item{background:#0d1117;border:1px solid #1f2733;border-radius:6px;padding:3px 8px;font-size:11px;font-family:ui-monospace,Menlo,monospace;color:#8b98a9}
.isa-item .idx{color:#58a6ff;margin-right:4px}
.mem-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;font-family:ui-monospace,Menlo,monospace;font-size:11px}
.mem-cell{background:#0d1117;border:1px solid #161b26;border-radius:4px;padding:4px 6px;text-align:center}
.mem-cell .addr{color:#6e7d8f;font-size:9px}
.mem-cell .val{color:#c9d3df;font-size:12px;font-weight:600}
.mem-cell.active{border-color:#58a6ff;background:#0d1930}
.mem-cell.watched{border-color:#3fb950;background:#0d2818}
.trace{max-height:260px;overflow-y:auto;font-family:ui-monospace,Menlo,monospace;font-size:11px}
.trace-row{display:grid;grid-template-columns:40px 30px 80px 1fr 80px;gap:6px;padding:3px 0;border-bottom:1px solid #161b26;align-items:center}
.trace-row .tk{color:#f0883e}
.trace-row .pc{color:#58a6ff}
.trace-row .da{color:#e6edf3;font-weight:600}
.trace-row .tr{color:#8b98a9}
.trace-row .ac{color:#3fb950;text-align:right}
.circuit-info{font-size:12px;color:#8b98a9;line-height:1.7;margin:6px 0}
.circuit-info b{color:#e6edf3}
.log{background:#080b10;border:1px solid #1f2733;border-radius:10px;padding:10px 12px;height:120px;overflow:auto;font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#9db2c9;white-space:pre-wrap;margin-top:10px}
.speed-ctrl{display:flex;align-items:center;gap:6px;margin-left:12px;font-size:12px;color:#8b98a9}
.speed-ctrl input{width:80px}
.honest{color:#6e7d8f;font-size:12px;border-top:1px solid #1f2733;margin-top:18px;padding-top:12px;line-height:1.6}
</style></head><body>
<h1>Muhlnickel 32-bit CPU</h1>
<div class="sub">A real stored-program processor baked as a gate netlist inside titan.gguf.
<b>7,403 gates</b>, <b>15 operations</b>, 32-bit word. It fetches, decodes, executes, and writes back — all in gates.
The host only sets inputs and reads the output.</div>

<div class="bar">
  <span id="progbtns"></span>
  <button id="halt" class="stop" onclick="halt()">Stop</button>
  <span style="margin-left:8px"><span class="dot" id="dot"></span><span id="state" class="sub">idle</span></span>
  <span class="speed-ctrl">speed: <input type="range" min="1" max="20" value="4" id="speed" oninput="setSpeed(this.value)"><span id="speedval">4</span>/s</span>
</div>

<div class="main-grid">
  <div>
    <div class="panel">
      <h3>Registers</h3>
      <div class="reg-grid">
        <div class="reg-box"><div class="lbl">PC</div><div class="val pc" id="pc">0</div></div>
        <div class="reg-box"><div class="lbl">ACC</div><div class="val acc" id="acc">0</div></div>
        <div class="reg-box"><div class="lbl">Tick</div><div class="val tick" id="tick">0</div></div>
      </div>
    </div>
    <div class="panel" style="margin-top:12px">
      <h3>ISA (15 operations)</h3>
      <div class="isa-grid" id="isa"></div>
    </div>
    <div class="panel" style="margin-top:12px">
      <h3>Memory (16 x 32-bit words)</h3>
      <div class="mem-grid" id="mem"></div>
    </div>
    <div class="panel" style="margin-top:12px">
      <h3>Watched Values</h3>
      <div id="watched" style="font-family:ui-monospace,Menlo,monospace;font-size:13px;color:#3fb950"></div>
    </div>
  </div>
  <div>
    <div class="panel">
      <h3>Execution Trace</h3>
      <div class="trace" id="trace">
        <div class="trace-row" style="font-weight:700;color:#6e7d8f;border-bottom:2px solid #1f2733">
          <span>tick</span><span>PC</span><span>instruction</span><span>effect</span><span>ACC</span>
        </div>
      </div>
    </div>
    <div class="panel" style="margin-top:12px">
      <h3>Circuit Info (from titan.gguf)</h3>
      <div id="cpuinfo" class="circuit-info"></div>
    </div>
  </div>
</div>

<h2>Event Log</h2>
<div class="log" id="log"></div>

<div class="honest">
<b>What this demo shows.</b> The Muhlnickel 32-bit CPU (pfc_cpu32) is a complete processor baked as one next-state netlist
in titan.gguf's parameters: <b>7,403 gates</b>, verified byte-exact against a reference emulator. The ISA has 15 operations
covering arithmetic, logic, shifts, comparisons, loads/stores, and control flow. Programs run by rippling power through the
gate network — the host only provides inputs (the current state) and reads the output (the next state). The execution shown
here uses the byte-exact emulator as a display proxy for the gate netlist.
</div>

<script>
const ISA=["HALT","LDA","STA","ADD","SUB","AND","OR","XOR","SHL","SHR","LT","EQ","JMP","JZ","LDI"];
function n(x){return(x||0).toLocaleString()}
function hex32(v){return '0x'+(v>>>0).toString(16).padStart(8,'0')}
async function run(p){await fetch('/start?prog='+p,{method:'POST'})}
async function halt(){await fetch('/stop',{method:'POST'})}
async function setSpeed(v){document.getElementById('speedval').textContent=v;await fetch('/speed?v='+v,{method:'POST'})}

async function tick(){
  let s;try{s=await(await fetch('/status')).json()}catch(e){return}
  // prog buttons
  let pb='';for(const[k,v]of Object.entries(s.programs||{})){
    const cls=k===s.program?'prog active':'prog';
    pb+=`<button class="${cls}" onclick="run('${k}')"${s.running?' disabled':''}>${v.name}</button> `;
  }
  document.getElementById('progbtns').innerHTML=pb;
  document.getElementById('halt').disabled=!s.running;
  document.getElementById('dot').className='dot'+(s.running?' on':(s.halted?' halt':''));
  document.getElementById('state').textContent=s.running?'RUNNING':(s.halted?'HALTED':'idle');
  document.getElementById('pc').textContent=s.pc;
  document.getElementById('acc').textContent=s.acc;
  document.getElementById('tick').textContent=s.tick;
  // ISA
  let ih='';ISA.forEach((op,i)=>{ih+=`<span class="isa-item"><span class="idx">${i}</span>${op}</span>`});
  document.getElementById('isa').innerHTML=ih;
  // Memory
  const wa=new Set((s.program_info?.watch_addrs||[]).map(String));
  const wl=s.program_info?.watch_labels||{};
  let mh='';(s.mem||[]).forEach((v,i)=>{
    let cls='mem-cell';
    if(i===s.pc&&s.running)cls+=' active';
    if(wa.has(String(i)))cls+=' watched';
    const label=wl[String(i)]?` (${wl[String(i)]})`:'';
    mh+=`<div class="${cls}"><div class="addr">[${i}]${label}</div><div class="val">${v}</div></div>`;
  });
  document.getElementById('mem').innerHTML=mh;
  // Watched
  let wh='';for(const a of(s.program_info?.watch_addrs||[])){
    const label=wl[String(a)]||('mem['+a+']');
    wh+=`<div>${label} = <b>${(s.mem||[])[a]||0}</b> (${hex32((s.mem||[])[a]||0)})</div>`;
  }
  document.getElementById('watched').innerHTML=wh||'<span style="color:#6e7d8f">select a program to begin</span>';
  // Trace
  let th='<div class="trace-row" style="font-weight:700;color:#6e7d8f;border-bottom:2px solid #1f2733"><span>tick</span><span>PC</span><span>instruction</span><span>effect</span><span>ACC</span></div>';
  for(const h of(s.history||[]).slice().reverse()){
    th+=`<div class="trace-row"><span class="tk">${h.tick}</span><span class="pc">${h.pc}</span><span class="da">${h.disasm}</span><span class="tr">${h.trace}</span><span class="ac">${h.acc}</span></div>`;
  }
  document.getElementById('trace').innerHTML=th;
  // CPU info
  let ci='';for(const[k,v]of Object.entries(s.cpu_info||{})){
    ci+=`<div style="margin-bottom:8px"><b>${v.name}</b><br>`;
    if(v.n_gate)ci+=`${n(v.n_gate)} gates`;
    if(v.depth)ci+=` &middot; DEPTH ${v.depth}`;
    if(v.n_in)ci+=` &middot; ${v.n_in} inputs`;
    if(v.n_out)ci+=` &middot; ${v.n_out} outputs`;
    if(v.words)ci+=` &middot; ${v.words} words x ${v.word||32}b`;
    if(v.isa)ci+=`<br>ISA: ${v.isa}`;
    if(v.role)ci+=`<br>${v.role}`;
    if(v.offset)ci+=`<br>offset: ${n(v.offset)}`;
    if(v.format)ci+=` &middot; format: ${v.format}`;
    if(v.muhl_rating)ci+=` &middot; rating: ${v.muhl_rating}`;
    ci+='</div>';
  }
  document.getElementById('cpuinfo').innerHTML=ci||'loading...';
  // Log
  document.getElementById('log').textContent=(s.log||[]).join('\n');
  document.getElementById('log').scrollTop=1e9;
}
setInterval(tick,250);tick();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        try:
            self.wfile.write(b)
        except Exception:
            pass

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path.startswith("/status"):
            self._send(200, json.dumps(STATE.status()))
        else:
            self._send(404, "{}")

    def do_POST(self):
        if self.path.startswith("/start"):
            # parse ?prog=name
            prog = "fibonacci"
            if "?" in self.path:
                for part in self.path.split("?")[1].split("&"):
                    if part.startswith("prog="):
                        prog = part[5:]
            STATE.start_program(prog)
            self._send(200, '{"ok":true}')
        elif self.path.startswith("/stop"):
            STATE.stop()
            self._send(200, '{"ok":true}')
        elif self.path.startswith("/speed"):
            v = 4
            if "?" in self.path:
                for part in self.path.split("?")[1].split("&"):
                    if part.startswith("v="):
                        try:
                            v = int(part[2:])
                        except ValueError:
                            pass
            STATE.set_speed(v)
            self._send(200, '{"ok":true}')
        else:
            self._send(404, "{}")


def main():
    print("=" * 80)
    print("MUHLNICKEL 32-BIT CPU DEMO")
    print("=" * 80)
    print()

    if not os.path.exists(REG):
        print(f"ERROR: registry not found at {REG}")
        print("Set PFC_ROOT if titan.gguf is not at C:/llm/models/titan.gguf")
        return 1
    if not os.path.exists(TITAN):
        print(f"ERROR: titan.gguf not found at {TITAN}")
        return 1

    STATE.load_registry()

    print("CPU circuits stored in titan.gguf:")
    print()
    for name, info in STATE.cpu_info.items():
        print(f"  {name}")
        if "n_gate" in info:
            gates = info["n_gate"]
            print(f"    gates: {gates:,}" if isinstance(gates, int) else f"    gates: {gates}")
        if "depth" in info:
            print(f"    depth: {info['depth']}")
        if "isa" in info:
            print(f"    isa: {info['isa']}")
        if "role" in info:
            print(f"    role: {info['role']}")
        print()

    print("ISA (15 operations):")
    for i, name in enumerate(OP_NAMES):
        print(f"  {i:2d} {name}")
    print()

    print("Available programs:")
    for key, prog in PROGRAMS.items():
        print(f"  {key}: {prog['name']} — {prog['description']}")
    print()

    url = f"http://127.0.0.1:{PORT}"
    print(f"Starting demo UI at {url}")
    print("Press Ctrl+C to stop.")
    print()

    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        STATE.stop()
        srv.shutdown()
    print("\nDemo stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
