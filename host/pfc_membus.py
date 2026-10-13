#!/usr/bin/env python3
"""host/pfc_membus.py — HOOK the Muhlnickel MMU into the pipeline: the MEMORY BUS (owner 07-19: "just hook it up, dont do it
piecemeal"). One complete fabrication — no partial wiring.

The pfc's compute now reaches ALL its working memory through its own controller (`pfc_mmu`, §S), via shared-address
SEND/RECEIVE junctions (§1E — a junction IS the same physical bytes shared by two circuits):

  ┌ compute writes a memory REQUEST on the ports ─────────────────────────────────────────────────────────┐
  │   ADDR (40b) [+ WE, WDATA for a store]                                                                  │
  └───────────────► pfc_mmu resolves it in-fabric ──────────────────────────────────────────────────────────┤
        FAST tier  → reads/writes its in-gates registers (the fed-back cell state, `mmu_cells`)             │
        STORAGE tier → computes the fold offset `PHYS`; the byte lives in the storage-RAM region (§N)        │
     ◄── the read word appears on RDATA, which SHARES bytes with `pfc_exec_input` ──────────────────────────┘
         → so the executor LOADs exactly what the MMU delivered; the executor's answer STOREs back through
           WDATA/WE; `pfc_store` then carries the final answer to the EXTERNAL safezone (unchanged, one-way).

So the executor's LOAD/STORE go THROUGH the pfc's own memory controller — the host is out of the address path, and the
address space is the whole storage-RAM (not titan's 40 GB file). All fabrication: allocate the port windows + write a
connection descriptor, byte-exact-reversible (genome), titan stays GGUF-valid, one-way, aim blind. If you want to check
the wiring, probe the junction bytes with the HIGH-IMPEDANCE meter (`host/pfc_meter.py`) — never a black-holing read.

  python host/pfc_membus.py           # fabricate the memory bus (reversible)
  python host/pfc_membus.py revert     # restore titan.gguf byte-exact + drop the registry entries
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_pfc_membus_genome.jsonl"
MAGIC = b"PFCMBUS1"
STORAGE_RAM = "C:/llm/sdc_out/pfc_storage_ram.bin"          # the storage-tier fold (§N), addressed by offset=PHYS

A_BYTES = 5      # 40-bit address / offset
W_BYTES = 2      # 16-bit word
CELLS_BYTES = 16 * 2                                        # FAST_N(16) x W(16b) fed-back cell state
# request/response ports to allocate (the compute's memory interface). RDATA is NOT allocated here — it is the
# shared-address junction onto the executor's existing input window.
PORTS = [("mmu_addr", A_BYTES), ("mmu_we", 1), ("mmu_wdata", W_BYTES), ("mmu_phys", A_BYTES), ("mmu_cells", CELLS_BYTES)]


def backup_and_write(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME):
        print("no membus genome — nothing to revert."); return 0
    for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    os.remove(GENOME)
    reg = json.load(open(REG))
    for k in ["pfc_membus"] + [p[0] for p in PORTS]: reg.pop(k, None)
    json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan.gguf byte-exact; pfc_membus + ports removed."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))
    for need in ("pfc_mmu", "pfc_exec_input", "pfc_executor", "pfc_store"):
        if need not in reg:
            print(f"{need} absent — fabricate it first (pfc_mmu.py / pfc_wire.py / pfc_executor.py)."); return 1
    if "pfc_membus" in reg:
        print("pfc_membus already fabricated. revert first to redo."); return 0

    mmu_off = int(reg["pfc_mmu"]["offset"])
    rdata_junction = int(reg["pfc_exec_input"]["offset"])       # the LOAD junction: MMU read word -> executor input window
    store_src = int(reg["pfc_executor"]["offset"])              # the STORE source: the executor's 72-bit answer

    # 1) allocate the request/response port windows (zeroed free-space; genome-backed so revert is byte-exact)
    port_off = {}
    for name, nbytes in PORTS:
        off, tn = TC._alloc(nbytes, reg)
        backup_and_write(off, b"\x00" * nbytes)
        reg[name] = {"tensor": tn, "offset": off, "len": nbytes}
        json.dump(reg, open(REG, "w"), indent=1); reg = json.load(open(REG))     # persist so _alloc avoids it next loop
        port_off[name] = off

    # 2) fabricate the connection descriptor: the wiring addresses of the whole memory bus (like pfc_connect/groups_block)
    order = ["mmu_addr", "mmu_we", "mmu_wdata", "mmu_phys", "mmu_cells"]
    blob = MAGIC + struct.pack("<QQ", mmu_off, rdata_junction) + b"".join(struct.pack("<Q", port_off[n]) for n in order) \
        + struct.pack("<Q", store_src)
    off, tn = TC._alloc(len(blob), reg)
    backup_and_write(off, blob)
    reg = json.load(open(REG))
    reg["pfc_membus"] = {
        "tensor": tn, "offset": off, "len": len(blob), "one_way": True,
        "controller": "pfc_mmu", "controller_off": mmu_off,
        "ports": {n: port_off[n] for n in order},
        "rdata_junction": {"shares": "pfc_exec_input", "offset": rdata_junction},   # §1E shared-address LOAD junction
        "store_source": {"from": "pfc_executor", "offset": store_src},
        "storage_region": STORAGE_RAM, "storage_is_offset": True,
        "memory_map": {"fast_cells_0..15": "in-gates registers (nonce/latch/scratch) via mmu_cells",
                       "addr>=16": "storage-RAM fold via PHYS offset"},
        "flow": ("compute -> ADDR(+WE/WDATA) -> pfc_mmu -> {FAST: mmu_cells | STORAGE: PHYS into storage_region} "
                 "-> RDATA shares pfc_exec_input -> executor LOADs; executor answer STOREs via WDATA/WE; "
                 "pfc_store -> external safezone. Host out of the address path; address space = whole storage-RAM."),
    }
    json.dump(reg, open(REG, "w"), indent=1)

    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print("FABRICATED the Muhlnickel MEMORY BUS pfc_membus (reversible):", flush=True)
    print(f"  controller pfc_mmu @ {mmu_off}", flush=True)
    print(f"  ports: " + ", ".join(f"{n}@{port_off[n]}" for n in order), flush=True)
    print(f"  LOAD junction (§1E shared bytes): RDATA -> pfc_exec_input @ {rdata_junction}", flush=True)
    print(f"  STORE source: pfc_executor answer @ {store_src}", flush=True)
    print(f"  STORAGE tier: PHYS offset -> {STORAGE_RAM} (whole storage-RAM; 40 GB file is not the ceiling)", flush=True)
    print(f"  descriptor @ {off}. titan GGUF-valid: {gg}.", flush=True)
    print(f"  the executor's LOAD/STORE now route through the Muhlnickel's own controller — host out of the address path.", flush=True)
    print(f"  check the junctions with the HIGH-IMPEDANCE meter (aim blind otherwise):  python host/pfc_meter.py pfc_exec_input", flush=True)
    print(f"  revert byte-exact:  python host/pfc_membus.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
