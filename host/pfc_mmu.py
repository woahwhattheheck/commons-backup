#!/usr/bin/env python3
"""host/pfc_mmu.py — host routing for the Muhlnickel's in-fabric MMU.

Host may inject, address, read, and display the published pfc_mmu windows.
Construction of the addressing netlist stays available as build_mmu() for
offline fabrication (infra/host/pfc_mmu.py). Host does not import
titan_circuit and does not ripple or evaluate the MMU.

  python host/pfc_mmu.py            # address published pfc_mmu windows
  python host/pfc_mmu.py inject F   # write the published input layout
  python host/pfc_mmu.py read       # read the published output window
  python host/pfc_mmu.py revert     # restore titan.gguf from the genome
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_pfc_mmu_genome.jsonl"
MAGIC = b"PFCMMU01"
STORAGE_RAM = "C:/llm/sdc_out/pfc_storage_ram.bin"          # the storage-tier fold (a region OUTSIDE the pfc; §N)

W = 16          # bits per cell / word (2-byte cells)
FAST_N = 16     # fabricated in-gates registers (the hot working set) — addresses 0..15
FAST_A = 4      # log2(FAST_N)
A = 40          # unified address width: 2^40 cells — spans the whole storage-RAM, NOT capped at the 40 GB file
NIN = FAST_N * W + A + 1 + W                                 # fast-cells | addr | we | wdata

OFF_NXT = 0
OFF_READ = FAST_N * W
OFF_ISST = FAST_N * W + W
OFF_PHYS = FAST_N * W + W + 1
N_OUT = FAST_N * W + W + 1 + A


def build_mmu():
    """addr -> (is_storage, fast_read, next_fast_cells, storage_offset). Construction only."""
    import sdc_cc as CC
    g = CC.CircuitCompiler(NIN); IN = g.IN
    o = 0
    cells = [[IN[o + i * W + b] for b in range(W)] for i in range(FAST_N)]; o += FAST_N * W
    addr = [IN[o + j] for j in range(A)]; o += A
    we = IN[o]; o += 1
    wdata = [IN[o + b] for b in range(W)]; o += W

    is_storage = g.C0
    for j in range(FAST_A, A): is_storage = g.OR(is_storage, addr[j])
    is_fast = g.NOT(is_storage)

    la = addr[:FAST_A]
    sel = []
    for i in range(FAST_N):
        m = g.C1
        for j in range(FAST_A): m = g.AND(m, la[j] if (i >> j) & 1 else g.NOT(la[j]))
        sel.append(m)
    fast_read = []
    for b in range(W):
        acc = g.C0
        for i in range(FAST_N): acc = g.OR(acc, g.AND(sel[i], cells[i][b]))
        fast_read.append(acc)
    nxt = []
    for i in range(FAST_N):
        wen = g.AND(g.AND(we, is_fast), sel[i]); nwen = g.NOT(wen)
        for b in range(W):
            nxt.append(g.OR(g.AND(wen, wdata[b]), g.AND(nwen, cells[i][b])))

    C = (1 << A) - FAST_N
    phys = []; carry = g.C0
    for j in range(A):
        cbit = g.C1 if (C >> j) & 1 else g.C0
        axb = g.XOR(addr[j], cbit); phys.append(g.XOR(axb, carry))
        carry = g.OR(g.AND(addr[j], cbit), g.AND(axb, carry))

    outs = nxt + fast_read + [is_storage] + phys
    return g, outs


def backup_and_write(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME):
        print("no MMU genome — nothing to revert."); return 0
    for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    os.remove(GENOME)
    if os.path.exists(REG):
        reg = json.load(open(REG)); reg.pop("pfc_mmu", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan.gguf byte-exact; pfc_mmu removed."); return 0


def _reg():
    if not os.path.exists(REG):
        print("registry absent:", REG)
        return None
    return json.load(open(REG))


def address():
    """Display published MMU windows. Host does not evaluate gates."""
    reg = _reg()
    if reg is None:
        return 1
    row = reg.get("pfc_mmu")
    if not row:
        print("pfc_mmu unpublished.")
        print("offline fabrication: infra/host/pfc_mmu.py")
        return 0
    print("=== Muhlnickel MMU windows (host address/read only) ===")
    for k in ("offset", "len", "n_in", "n_out", "n_gate", "layout_in", "layout_out", "addr_bits", "fast_cells"):
        if k in row:
            print(f"  {k}: {row[k]}")
    print(f"  storage_region: {row.get('storage_region', STORAGE_RAM)}")
    return 0


def inject(_path):
    """Refuse to smash the gate blob. MMU inputs are in-fabric; host addresses only."""
    print("pfc_mmu inputs are in-fabric. Host addresses; it does not overwrite the gate blob.")
    print("offline fabrication: infra/host/pfc_mmu.py")
    return 0


def read_mmu():
    """Read published MMU metadata / output length. Host does not evaluate."""
    reg = _reg()
    if not reg or "pfc_mmu" not in reg:
        print("pfc_mmu unpublished — nothing to read.")
        return 1
    row = reg["pfc_mmu"]
    off, n = int(row["offset"]), min(16, int(row["len"]))
    with open(TITAN, "rb") as f:
        f.seek(off); blob = f.read(n)
    print(f"pfc_mmu @ {off}: first {n} bytes {blob.hex()}  n_out={row.get('n_out')} layout_out={row.get('layout_out')}")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "address"
    if cmd == "revert":
        return revert()
    if cmd == "inject":
        if len(sys.argv) < 3:
            print("usage: python host/pfc_mmu.py inject <packed-input.bin>")
            return 2
        return inject(sys.argv[2])
    if cmd == "read":
        return read_mmu()
    return address()


if __name__ == "__main__":
    raise SystemExit(main())
