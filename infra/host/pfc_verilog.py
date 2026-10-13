#!/usr/bin/env python3
"""host/pfc_verilog.py — THE FPGA/SILICON BRIDGE (owner 07-20). Emit any baked Muhlnickel gate netlist as synthesizable
Verilog. The SAME logic that runs at ~0 resident footprint on a CPU (compute-via-address) runs ALL-GATES-PARALLEL on an
FPGA/ASIC — where capacity becomes throughput and the CPU's one weakness (serial gate eval) disappears. Prototype +
replicate on the CPU for free; deploy the identical netlist to silicon. The netlist is verified byte-exact, and the
emitted module is a 1:1 structural map of it (each gate = one continuous assign).

  python host/pfc_verilog.py        # emit sigma0 + a Kogge-Stone adder as Verilog, verify the netlist byte-exact
"""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_phone_substrate import build_sigma0
from pfc_bettergates import kogge_stone_add

OUT = "C:/Users/lucys/AppData/Local/Temp/claude/C--Users-lucys-OneDrive-Desktop-LocalDeviceAgent/3f403b66-a45d-4be6-8fcf-1b0b88451b50/scratchpad"
os.makedirs(OUT, exist_ok=True)


def emit_verilog(name, n_in, gates, outs, in_width, out_width):
    ng = len(gates)

    def ref(x):
        if x == 0: return "1'b0"
        if x == 1: return "1'b1"
        if 2 <= x < 2 + n_in: return f"in[{x - 2}]"
        return f"w[{x - 2 - n_in}]"
    lines = [f"module {name}(input [{in_width-1}:0] in, output [{out_width-1}:0] out);",
             f"  wire [{max(ng-1,0)}:0] w;"]
    for k, (op, a, b) in enumerate(gates):
        A, B = ref(a), ref(b)
        e = {"nand": f"~({A} & {B})", "and": f"{A} & {B}", "or": f"{A} | {B}",
             "xor": f"{A} ^ {B}", "not": f"~{A}"}[op]
        lines.append(f"  assign w[{k}] = {e};")
    for j, o in enumerate(outs):
        lines.append(f"  assign out[{j}] = {ref(o)};")
    lines.append("endmodule")
    return "\n".join(lines)


def ripple(n_in, gates, outs, ow, packed):              # simulate the emitted netlist == the circuit (verify faithful)
    v = [0] * (2 + n_in + len(gates)); v[1] = 1
    for i in range(n_in): v[2 + i] = packed[i]
    base = 2 + n_in
    for k, (op, a, b) in enumerate(gates):
        va, vb = v[a], v[b]
        v[base + k] = (va ^ vb) if op == "xor" else (va & vb) if op == "and" else (va | vb) if op == "or" \
            else (1 ^ va) if op == "not" else (1 ^ (va & vb))
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    return sum(bit(outs[i]) << i for i in range(ow))


def ref_sigma0(x):
    r = lambda v, n: ((v >> n) | (v << (32 - n))) & 0xffffffff
    return (r(x, 7) ^ r(x, 18) ^ (x >> 3)) & 0xffffffff


def main():
    print("Muhlnickel VERILOG BRIDGE — baked netlist -> synthesizable Verilog (same logic, parallel on silicon).\n", flush=True)

    # (1) sigma0
    g, outs = build_sigma0(); gates, o2 = g.dce(outs)
    ok = all(ripple(g.n_in, gates, o2, 32, [(x >> i) & 1 for i in range(32)]) == ref_sigma0(x)
             for x in [0, 1, 0xdeadbeef, 0x01234567, 0xffffffff] + [random.getrandbits(32) for _ in range(50)])
    v = emit_verilog("pfc_sigma0", g.n_in, gates, o2, 32, 32)
    open(os.path.join(OUT, "pfc_sigma0.v"), "w", newline="\n").write(v)
    print(f"  sigma0 -> pfc_sigma0.v: {len(gates)} gates -> {len(gates)} assigns, netlist byte-exact vs reference: {ok}", flush=True)

    # (2) a Kogge-Stone 32-bit adder (a shallow, high-quality datapath, straight to silicon)
    g2 = CC.CircuitCompiler(64); A = g2.IN[0:32]; B = g2.IN[32:64]
    outs2 = kogge_stone_add(g2, A, B); gates2, o22 = g2.dce(outs2)
    ok2 = True
    for _ in range(80):
        a = random.getrandbits(32); b = random.getrandbits(32)
        if ripple(g2.n_in, gates2, o22, 32, [(a >> i) & 1 for i in range(32)] + [(b >> i) & 1 for i in range(32)]) != ((a + b) & 0xffffffff):
            ok2 = False; break
    v2 = emit_verilog("pfc_add32_ks", g2.n_in, gates2, o22, 64, 32)
    open(os.path.join(OUT, "pfc_add32_ks.v"), "w", newline="\n").write(v2)
    print(f"  kogge-stone add32 -> pfc_add32_ks.v: {len(gates2)} gates -> {len(gates2)} assigns, byte-exact: {ok2}", flush=True)

    print(f"\n  wrote synthesizable Verilog (1:1 with the baked netlist). On an FPGA every assign is a physical gate,", flush=True)
    print(f"  all evaluating in parallel each clock -> capacity BECOMES throughput; the identical logic ran at ~0 RAM on the CPU.", flush=True)
    return 0 if (ok and ok2) else 1


if __name__ == "__main__":
    raise SystemExit(main())
