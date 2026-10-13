#!/usr/bin/env python3
"""host/pfc_miner.py — host routing for the clocked miner.

Host may inject, address, read, and display published windows. Construction of
the next-state netlist stays available as build_statemachine() for fabrication
tools (host/pfc_fab_miner_clean.py). Offline bake: infra/host/pfc_miner.py.
Host does not import titan_circuit and does not ripple or evaluate the miner.

  python host/pfc_miner.py            # address published pfc_mine windows
  python host/pfc_miner.py inject F   # write 108-byte header|target into input_window
  python host/pfc_miner.py read       # read latch_reg (the answer)
  python host/pfc_miner.py revert     # restore titan.gguf from the genome
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_pfc_miner_genome.jsonl"
MAGIC = b"PFCSMACH"
INPUT_BYTES = 76 + 32                      # header(76) + target(32) = 108 B block-data window
# input-wire layout of the next-state netlist (928 in):
H_LO, H_HI = 0, 608                        # header W0..18  (input_window bits 0..607)
N_LO, N_HI = 608, 640                      # nonce  W19     (nonce_reg)
T_LO, T_HI = 640, 896                      # target        (input_window bits 608..863)
L_LO, L_HI = 896, 928                      # latch         (latch_reg)
KEYS = ("pfc_mine", "input_window", "nonce_reg", "latch_reg", "clk_bit")


def build_statemachine():
    """ONE next-state netlist: (header, nonce, target, latch) -> (nonce+1, win?nonce:latch). 64 outputs."""
    import sdc_cc as CC
    g = CC.CircuitCompiler(928)
    header = [list(g.IN[i * 32:(i + 1) * 32]) for i in range(19)]   # W0..18
    nonce = list(g.IN[N_LO:N_HI]); target = list(g.IN[T_LO:T_HI]); latch = list(g.IN[L_LO:L_HI])
    W = header + [nonce]                                            # 20 header words (W19 = nonce)
    mid = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], W[0:16])
    blk2 = [W[16], W[17], W[18], W[19], CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 10 + [CC.cword(g, 640)]
    d1 = CC.sha_block(g, mid, blk2)
    blk3 = d1 + [CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 6 + [CC.cword(g, 256)]
    d2 = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], blk3)
    A = [d2[(i // 8) // 4][8 * (3 - ((i // 8) % 4)) + (i % 8)] for i in range(256)]   # hash as LE 256-bit
    lt = g.C0; eq = g.C1
    for i in range(255, -1, -1):
        lt = g.OR(lt, g.AND(eq, g.AND(g.NOT(A[i]), target[i])))
        eq = g.AND(eq, g.NOT(g.XOR(A[i], target[i])))
    win = lt
    nn = []; carry = g.C1                                           # CLOCK: nonce + 1 (ripple-carry incrementer)
    for x in nonce:
        nn.append(g.XOR(x, carry)); carry = g.AND(x, carry)
    ln = [g.OR(g.AND(g.NOT(win), latch[i]), g.AND(win, nonce[i])) for i in range(32)]   # LATCH: win ? nonce : latch
    return g, nn + ln                                              # outs[0:32]=nonce', outs[32:64]=latch'


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    if os.path.exists(REG):
        reg = json.load(open(REG))
        for k in KEYS: reg.pop(k, None)
        json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: v = f.read(4) == b"GGUF" if os.path.exists(TITAN) else False
    print(f"reverted — titan.gguf byte-exact; clocked state machine removed. GGUF-valid: {v}.")
    return 0


def _reg():
    if not os.path.exists(REG):
        print("registry absent:", REG)
        return None
    return json.load(open(REG))


def address():
    """Display published miner windows. Host does not evaluate gates."""
    reg = _reg()
    if reg is None:
        return 1
    missing = [k for k in KEYS if k not in reg]
    if missing:
        print("unpublished:", ", ".join(missing))
        print("offline fabrication: infra/host/pfc_miner.py")
        print("host bake without eval: host/pfc_fab_miner_clean.py")
        return 0
    print("=== Muhlnickel miner windows (host address/read only) ===")
    for k in KEYS:
        row = reg[k]
        print(f"  {k}: offset={row.get('offset')} len={row.get('len')} { {x: row[x] for x in row if x not in ('offset', 'len', 'in_map', 'out_map')} }")
    return 0


def inject(path):
    """Write header|target bytes into the published input_window. Host does not evaluate."""
    reg = _reg()
    if not reg or "input_window" not in reg:
        print("input_window unpublished — nothing to inject.")
        return 1
    data = open(path, "rb").read()
    need = int(reg["input_window"]["len"])
    if len(data) != need:
        print(f"inject needs exactly {need} bytes, got {len(data)}")
        return 1
    off = int(reg["input_window"]["offset"])
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(data)
    print(f"injected {need} bytes at input_window offset {off}")
    return 0


def read_latch():
    """Read latch_reg (the answer). Host does not evaluate."""
    reg = _reg()
    if not reg or "latch_reg" not in reg:
        print("latch_reg unpublished — nothing to read.")
        return 1
    row = reg["latch_reg"]
    off, n = int(row["offset"]), int(row["len"])
    with open(TITAN, "rb") as f:
        f.seek(off); blob = f.read(n)
    nonce = struct.unpack_from("<I", blob + b"\x00\x00\x00\x00", 0)[0] if blob else 0
    print(f"latch_reg @ {off}: {blob.hex()}  nonce={nonce:#010x}")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "address"
    if cmd == "revert":
        return revert()
    if cmd == "inject":
        if len(sys.argv) < 3:
            print("usage: python host/pfc_miner.py inject <header+target.bin>")
            return 2
        return inject(sys.argv[2])
    if cmd == "read":
        return read_latch()
    return address()


if __name__ == "__main__":
    raise SystemExit(main())
