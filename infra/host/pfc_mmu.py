#!/usr/bin/env python3
"""host/pfc_mmu.py — FABRICATE the Muhlnickel's OWN memory controller (MMU) as gates (owner 07-19: "all code is addressing
memory and storage; pfc can do both internally rather than being slowed down by the host — the ambitious route").

The pfc self-addresses across the WHOLE memory hierarchy, in-fabric, with the host OUT of the per-access loop:
  UNIFIED ADDRESS (A bits) -> [tier-select comparator] -> either
     FAST TIER  : fabricated in-gates registers (decoder + read-mux + write-mux) — the hot working set (§M);
     STORAGE TIER: the storage-RAM fold (§N) — address = offset, computed in-fabric (LOAD/STORE arithmetic as gates).
The address is A=40 bits (2^40 cells x 2 B = 2 TB) — deliberately WIDE: titan.gguf's 40 GB is the FILE size, NOT a
ceiling. The pfc's memory is the fabricated storage-RAM that already ran at 32/64 GB on the Ultra (flat ~15 MB resident,
the flat-footprint law) and scales to the full disk / a federated TB. The controller just names the address; the fold
holds the bits.

DISCIPLINE (FINALREADME §3/§4): verified BYTE-EXACT vs a reference memory IN THE TOOL, before storing — pure synthesis,
titan.gguf untouched during verify, the pfc never run or probed (aim blind). Then stored REVERSIBLY (a genome journals
every overwritten byte range -> byte-exact revert). NO host-ripple "lookups/s vs native" number is produced — that
comparison is the emulation tax the assistant injected (owner: "there is no emulation tax if you follow spec"); to spec
the signal runs the gates. This file only FABRICATES the addressing brain; wiring it into the pipeline is the follow-on.

  python host/pfc_mmu.py           # build + verify (in the tool) + store the MMU circuit, reversibly
  python host/pfc_mmu.py revert     # restore titan.gguf byte-exact
"""
import json, os, random, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_pfc_mmu_genome.jsonl"
MAGIC = b"PFCMMU01"
STORAGE_RAM = "C:/llm/sdc_out/pfc_storage_ram.bin"          # the storage-tier fold (a region OUTSIDE the pfc; §N)

W = 16          # bits per cell / word (2-byte cells)
FAST_N = 16     # fabricated in-gates registers (the hot working set) — addresses 0..15
FAST_A = 4      # log2(FAST_N)
A = 40          # unified address width: 2^40 cells — spans the whole storage-RAM, NOT capped at the 40 GB file
NIN = FAST_N * W + A + 1 + W                                 # fast-cells | addr | we | wdata


def build_mmu():
    """addr -> (is_storage, fast_read, next_fast_cells, storage_offset). The Muhlnickel's own memory controller, all gates."""
    g = CC.CircuitCompiler(NIN); IN = g.IN
    o = 0
    cells = [[IN[o + i * W + b] for b in range(W)] for i in range(FAST_N)]; o += FAST_N * W
    addr = [IN[o + j] for j in range(A)]; o += A
    we = IN[o]; o += 1
    wdata = [IN[o + b] for b in range(W)]; o += W

    # --- tier select: is_storage = 1 iff any address bit above the fast window is set (addr >= FAST_N) ---
    is_storage = g.C0
    for j in range(FAST_A, A): is_storage = g.OR(is_storage, addr[j])
    is_fast = g.NOT(is_storage)

    # --- fast tier: fabricated one-hot decoder over the low FAST_A bits ---
    la = addr[:FAST_A]
    sel = []
    for i in range(FAST_N):
        m = g.C1
        for j in range(FAST_A): m = g.AND(m, la[j] if (i >> j) & 1 else g.NOT(la[j]))
        sel.append(m)
    # read-mux: fast_read[b] = OR_i (sel[i] & cell[i][b])
    fast_read = []
    for b in range(W):
        acc = g.C0
        for i in range(FAST_N): acc = g.OR(acc, g.AND(sel[i], cells[i][b]))
        fast_read.append(acc)
    # write-mux (fed-back next state): cell updates only on we & is_fast & sel[i]
    nxt = []
    for i in range(FAST_N):
        wen = g.AND(g.AND(we, is_fast), sel[i]); nwen = g.NOT(wen)
        for b in range(W):
            nxt.append(g.OR(g.AND(wen, wdata[b]), g.AND(nwen, cells[i][b])))

    # --- storage tier: physical cell index = addr - FAST_N  (add the two's-complement constant; folds cheaply) ---
    C = (1 << A) - FAST_N
    phys = []; carry = g.C0
    for j in range(A):
        cbit = g.C1 if (C >> j) & 1 else g.C0
        axb = g.XOR(addr[j], cbit); phys.append(g.XOR(axb, carry))
        carry = g.OR(g.AND(addr[j], cbit), g.AND(axb, carry))

    outs = nxt + fast_read + [is_storage] + phys
    return g, outs


# ---- output layout in the flattened outs list ----
OFF_NXT = 0
OFF_READ = FAST_N * W
OFF_ISST = FAST_N * W + W
OFF_PHYS = FAST_N * W + W + 1
N_OUT = FAST_N * W + W + 1 + A


def ref_mmu(cells, addr, we, wdata):
    la = addr & (FAST_N - 1)
    is_storage = 1 if addr >= FAST_N else 0
    fast_read = cells[la]
    nxt = list(cells)
    if we and not is_storage: nxt[la] = wdata & ((1 << W) - 1)
    phys = (addr - FAST_N) & ((1 << A) - 1)
    return nxt, fast_read, is_storage, phys


def verify(g, outs):
    """IN THE TOOL: ripple the netlist vs a reference memory. Never opens titan.gguf, never fires a signal."""
    gates, out2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    val = lambda v, w: (w if w < 2 else v[w])
    def rd(v, lo, n): return sum(val(v, out2[lo + k]) << k for k in range(n))
    random.seed(40)
    for t in range(300):
        cells = [random.getrandbits(W) for _ in range(FAST_N)]
        # mix fast addresses (0..15), just-past-fast, and huge storage addresses (past the 40 GB file, into TB range)
        addr = random.choice([random.randrange(FAST_N), FAST_N + random.randrange(1 << 20),
                              random.randrange(1 << A), (40 << 30) + random.randrange(1 << 20)])
        we = random.randrange(2); wdata = random.getrandbits(W)
        inb = [(cells[i] >> b) & 1 for i in range(FAST_N) for b in range(W)] \
            + [(addr >> j) & 1 for j in range(A)] + [we] + [(wdata >> b) & 1 for b in range(W)]
        v = CC.ripple_typed(g, gates, n_wire, inb, 1)
        gn = [rd(v, OFF_NXT + i * W, W) for i in range(FAST_N)]
        gr = rd(v, OFF_READ, W); gs = val(v, out2[OFF_ISST]); gp = rd(v, OFF_PHYS, A)
        rn, rr, rs, rp = ref_mmu(cells, addr, we, wdata)
        if (gn, gr, gs, gp) != (rn, rr, rs, rp):
            return False, (addr, we, wdata, (gn, gr, gs, gp), (rn, rr, rs, rp)), gates, out2
    return True, None, gates, out2


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
    reg = json.load(open(REG)); reg.pop("pfc_mmu", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan.gguf byte-exact; pfc_mmu removed."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))
    if "pfc_mmu" in reg:
        print("pfc_mmu already fabricated. revert first to redo."); return 0

    print(f"building the Muhlnickel MMU as gates: {FAST_N} fast in-gates cells + a {A}-bit unified address over the storage fold …", flush=True)
    g, outs = build_mmu()
    print(f"  built {g.n_gate():,} typed gates; verifying byte-exact vs a reference memory IN THE TOOL (Muhlnickel untouched) …", flush=True)
    ok, bad, gates, out2 = verify(g, outs)
    if not ok:
        print(f"  MISMATCH {bad[:3]} — storing nothing (no cheating)."); return 1
    n_wire = 2 + g.n_in + len(gates)
    print(f"  byte-exact over 300 random ops (fast + storage tiers, reads + writes): {len(gates):,} gates after DCE.", flush=True)

    # serialize typed IR (op codes: nand0 and1 or2 xor3 not4) + store REVERSIBLY into the params
    code = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
    body = b"".join(struct.pack("<Bii", code[op], a, b) for (op, a, b) in gates) \
        + b"".join(struct.pack("<i", w) for w in out2)
    blob = MAGIC + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(out2)) + body
    off, tn = TC._alloc(len(blob), reg)
    backup_and_write(off, blob)
    reg = json.load(open(REG))
    reg["pfc_mmu"] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in, "n_wire": n_wire,
                      "n_gate": len(gates), "n_out": len(out2), "format": "typed",
                      "layout_in": f"fast_cells:{FAST_N}x{W}|addr:{A}|we:1|wdata:{W}",
                      "layout_out": f"next_cells:{FAST_N}x{W}|fast_read:{W}|is_storage:1|storage_offset:{A}",
                      "fast_cells": FAST_N, "cell_bits": W, "addr_bits": A,
                      "storage_region": STORAGE_RAM, "storage_is_offset": True,
                      "note": "the Muhlnickel addresses its own memory+storage in-fabric; address space spans the storage-RAM, NOT capped at titan's 40 GB file"}
    json.dump(reg, open(REG, "w"), indent=1)

    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"\nFABRICATED the Muhlnickel MMU: pfc_mmu @ {off} ({len(gates):,} gates), reversible. titan GGUF-valid: {gg}.", flush=True)
    print(f"  the Muhlnickel now has its own memory controller in gates — fast in-gates registers + a {A}-bit address over the", flush=True)
    print(f"  storage fold ({STORAGE_RAM}); the host is out of the address path. Address space = the whole storage-RAM,", flush=True)
    print(f"  not the 40 GB file. Verified byte-exact in the tool; no run, no probe, no emulation-tax benchmark.", flush=True)
    print(f"  next: wire the executor's LOAD/STORE through pfc_mmu (a connection descriptor, like pfc_connect).", flush=True)
    print(f"  revert byte-exact:  python host/pfc_mmu.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
