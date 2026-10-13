#!/usr/bin/env python3
"""host/pfc_phys_fab.py — lay out ANY circuit as PHYSICALLY-WIRED gates in titan.gguf: every wire is a real file
byte-address, and a gate's OUTPUT address IS the next gate's INPUT address (shared physical connection) — not a
serialized gate list rippled in Python. (owner 07-23: "your circuitry needs to be physically connected via storage bit
address, not just a list of gates you ripple; if the bit-flip location is shared with a logic gate, flipping it to a 1
propagates the output and so forth.")

This is the general form of host/pfc_physical_gates.py: take a NAND circuit (built with titan_circuit), assign each wire a
real byte in a fabricated region, write the connections as SHARED addresses (wire w lives at addr[w]; every gate that uses
w points at the same addr[w]). Prefab the bytes into the file BEFORE any signal (genome-reversible). The receiver = the
circuit's input addresses. Then test the owner's way: flip the input addresses, probe propagation.

  python host/pfc_phys_fab.py test      # lay out a REAL circuit (an adder) physically, verify byte-exact, A/B propagation
  python host/pfc_phys_fab.py revert
"""
import json, os, sys, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_physfab_genome.jsonl"


def _write(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("phys_layout", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan byte-exact; phys_layout removed."); return 0


def rb(a):
    with open(TITAN, "rb") as f: f.seek(a); return f.read(1)[0] & 1
def wb(a, v):
    with open(TITAN, "r+b") as f: f.seek(a); f.write(bytes([v & 1]))


def layout(circ, outs):
    """assign a physical byte-address to every wire; write the prefab; store the shared-address gate wiring."""
    reg = json.load(open(REG))
    n_wire = circ.n_wire()
    off, tn = TC._alloc(n_wire, reg)                          # one real file byte per wire
    addr = [off + w for w in range(n_wire)]                   # addr[w] = the PHYSICAL byte for wire w
    prefab = bytearray(n_wire); prefab[1] = 1                  # const0 wire=0, const1 wire=1, rest 0
    _write(off, bytes(prefab))
    base = 2 + circ.n_in
    # each gate g: out wire (base+g) lives at addr[base+g]; its inputs are the SHARED addresses addr[ga], addr[gb]
    gates = [{"out": addr[base + g], "a": addr[circ.ga[g]], "b": addr[circ.gb[g]]} for g in range(len(circ.ga))]
    reg = json.load(open(REG))
    reg["phys_layout"] = {"tensor": tn, "offset": off, "len": n_wire, "n_in": circ.n_in, "n_wire": n_wire,
                          "in_addr": [addr[2 + i] for i in range(circ.n_in)], "const1_addr": addr[1],
                          "out_addr": [addr[o] for o in outs], "gates": gates,
                          "note": "wires are physical file bytes; gate.out addr shared as next gate.in addr (NAND)"}
    json.dump(reg, open(REG, "w"), indent=1)
    return reg["phys_layout"]


def set_inputs(e, bits):
    wb(e["const1_addr"], 1)
    for i, a in enumerate(e["in_addr"]): wb(a, bits[i] if i < len(bits) else 0)


def phys_pass(e):
    """ONE pass over the PHYSICAL addresses: each gate reads its shared input bytes, writes its output byte (NAND)."""
    for g in e["gates"]: wb(g["out"], 1 - (rb(g["a"]) & rb(g["b"])))


def read_out(e):
    return sum(rb(a) << i for i, a in enumerate(e["out_addr"]))


def test():
    # a REAL circuit: 4-bit adder (a+b)&15 — laid out as PHYSICAL shared-address gates in the file
    c = TC.Circuit(8); xs, ys = c.IN[:4], c.IN[4:]; s = c.add(xs, ys)
    reg = json.load(open(REG))
    e = reg["phys_layout"] if "phys_layout" in reg else layout(c, s)
    print(f"physically wired a 4-bit adder into titan.gguf: {e['n_wire']} wires = real file bytes "
          f"[{e['offset']}..{e['offset']+e['n_wire']-1}], {len(e['gates'])} NAND gates (shared addresses).\n")

    # A — OWNER'S THEORY: flip the input bytes (the receiver), probe the output WITHOUT a host pass
    ok_A = 0; ok_B = 0; N = 16
    random.seed(0)
    for _ in range(N):
        a = random.randint(0, 15); b = random.randint(0, 15); ref = (a + b) & 15
        bits = [(a >> i) & 1 for i in range(4)] + [(b >> i) & 1 for i in range(4)]
        # zero the wires, then set inputs (flip the physical input bytes)
        for w in range(e["n_wire"]): wb(e["offset"] + w, 0)
        set_inputs(e, bits)
        outA = read_out(e); ok_A += (outA == ref)
        # B — a pass over the physical shared addresses (evaluate the wiring)
        phys_pass(e); outB = read_out(e); ok_B += (outB == ref)
    print(f"  A (flip inputs, probe output, NO pass): {ok_A}/{N} correct  <- does the signal propagate on the bare flip?")
    print(f"  B (flip inputs, ONE pass over the shared physical addresses): {ok_B}/{N} correct")
    print(f"\n  the adder is physically wired in the file (real byte addresses, shared gate connections). the A/B is the")
    print(f"  measured propagation. revert: python host/pfc_phys_fab.py revert")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    raise SystemExit(revert() if cmd == "revert" else test())
