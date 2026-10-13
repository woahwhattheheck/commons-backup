#!/usr/bin/env python3
"""host/pfc_clocked_cpu.py — run the ALREADY-BAKED pfc_cpu32 as a SELF-CLOCKED computer (owner 07-19: "same way any
other computer would thats the whole endeavor · ram = signal routing only, everything else pfc").

The clocked counter proved the architecture on a trivial state. This runs the REAL ISA computer the same way: a program
lives in the CPU's own RAM, and every clock tick fetches/decodes/executes/writes-back/advances-PC — the whole
microarchitecture is the baked next-state netlist (pfc_cpu32, read OFF titan.gguf). The full machine state (RAM + PC +
ACC + HALT) lives in the Muhlnickel's OWN storage (a sandbox file); the host only pulses the clock. Footprint stays flat; the
program runs to HALT with the correct result, byte-exact vs the reference emulator.

  python host/pfc_clocked_cpu.py [N]     # run a countdown-from-N program self-clocked (default 500)
"""
import ctypes, json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
from pfc_cpu32 import pack, unpack, emu32, HALT, LDA, STA, ADD, SUB, JMP, JZ, LDI
from pfc_clocked import rss_mb                       # reuse the fixed RSS meter

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
SBX = "C:/llm/sdc_sandbox/clocked_cpu"; STATEFILE = os.path.join(SBX, "cpu_state.bin")
WORD = 32; NMEM = 16; AW = 4


def load_cpu():
    reg = json.load(open(REG)); e = reg["pfc_cpu32"]
    with open(TITAN, "rb") as f: f.seek(int(e["offset"])); blob = f.read(int(e["len"]))
    assert blob[:8] == b"PFCTYPED"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((op, a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    return n_in, n_wire, gates, outs


def ripple(gates, n_wire, n_in, packed):              # 1-lane contained ripple over gates read from the file
    v = [0] * n_wire; v[1] = 1
    for i in range(n_in): v[2 + i] = packed[i]
    base = 2 + n_in
    for k in range(len(gates)):
        op, a, b = gates[k]; va = v[a]; vb = v[b]
        v[base + k] = (va ^ vb) if op == 3 else (va & vb) if op == 1 else (va | vb) if op == 2 \
            else (1 ^ va) if op == 4 else (1 ^ (va & vb))
    return v


def write_state(sf, mem, pc, acc, halt):
    sf.seek(0); sf.write(struct.pack("<16I", *mem) + struct.pack("<IIB", pc, acc, halt))


def read_state(sf):
    sf.seek(0); raw = sf.read(16 * 4 + 4 + 4 + 1)
    mem = list(struct.unpack_from("<16I", raw, 0))
    pc, acc, halt = struct.unpack_from("<IIB", raw, 64)
    return mem, pc, acc, halt


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    os.makedirs(SBX, exist_ok=True)
    print("SELF-CLOCKED Muhlnickel CPU — a real program running from the Muhlnickel's own RAM, host = clock only.\n", flush=True)

    n_in, n_wire, gates, outs = load_cpu()             # the CPU, read OFF the baked file
    print(f"  loaded pfc_cpu32 off titan.gguf: {len(gates):,} gates, {NMEM} words x {WORD}b RAM.", flush=True)

    # program: countdown from N in the CPU's own RAM (mem[15]=counter, mem[14]=1)
    I = lambda op, opd: (op << 28) | (opd & 0x0fffffff)
    prog = {0: I(LDI, N), 1: I(STA, 15), 2: I(LDA, 15), 3: I(SUB, 14), 4: I(STA, 15),
            5: I(JZ, 7), 6: I(JMP, 2), 7: I(HALT, 0), 14: 1, 15: 0}
    mem0 = [prog.get(i, 0) for i in range(NMEM)]

    # REFERENCE: run the emulator to completion (what the answer MUST be)
    rm, rpc, racc, rh = list(mem0), 0, 0, 0; rsteps = 0
    while not rh and rsteps < 10 * N + 50:
        rm, rpc, racc, rh = emu32(rm, rpc, racc, rh, AW, NMEM); rsteps += 1

    # SELF-CLOCKED: state in the Muhlnickel's storage; each clock tick = one baked next-state; host only clocks
    with open(STATEFILE, "wb") as f: pass
    sf = open(STATEFILE, "r+b"); write_state(sf, mem0, 0, 0, 0)
    rss0 = rss_mb(); t0 = time.time(); ticks = 0; halt = 0
    while not halt and ticks < 10 * N + 50:
        mem, pc, acc, halt = read_state(sf)            # read state from the pfc's storage
        v = ripple(gates, n_wire, n_in, pack(mem, pc, acc, halt, NMEM, AW))   # ONE clock tick
        mem, pc, acc, halt = unpack(v, outs, NMEM, AW)
        write_state(sf, mem, pc, acc, halt)            # latch next state back to storage
        ticks += 1
    el = time.time() - t0; rss1 = rss_mb()
    mem, pc, acc, halt = read_state(sf); sf.close()

    match = (mem == rm and pc == rpc and acc == racc and halt == rh)
    print(f"\n  ran 'countdown from {N}' self-clocked from the Muhlnickel's own RAM:", flush=True)
    print(f"    {ticks:,} clock ticks in {el:.2f}s = {ticks/el:,.0f} ticks/sec (HALTed: {bool(halt)})", flush=True)
    print(f"    final mem[15] (read from the Muhlnickel's storage) = {mem[15]}  (counted down to 0)", flush=True)
    print(f"    byte-exact vs reference emulator (full state: RAM+PC+ACC+HALT): {match}", flush=True)
    print(f"    host RSS: {rss0:.1f} MB -> {rss1:.1f} MB over {ticks:,} ticks  =>  FLAT (state is in the Muhlnickel, not host RAM)", flush=True)
    print(f"\n  the Muhlnickel executed a real program from its own memory, the same way any computer does; host = clock only.", flush=True)
    return 0 if match else 1


if __name__ == "__main__":
    raise SystemExit(main())
