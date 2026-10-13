#!/usr/bin/env python3
"""muhl_fab_nefg.py — FABRICATE: Non-Euclidean Functorial Graph (NEFG).

Category-theoretic functors as flat-binary NAND gate networks stored in titan.gguf.

  3 objects:  A (8-bit input)  ->  B (intermediate)  ->  C (output)
  Morphism f:   A -> B  =  bitwise NOT  (depth 1)
  Morphism g:   B -> C  =  increment by 1
  Composition g.f:  A -> C  =  two's complement negation (NOT + inc, INDEPENDENT path)
  Functor law:  g(f(x)) == (g.f)(x)  for ALL x, verified byte-exact at fabrication time.

PROPOSE two candidates (ripple vs prefix adder), SCORE by depth+gates, VERIFY
byte-exact vs Python reference over all 256 inputs, KEEP the winner. Report Pareto set.

This is MANUFACTURING — offline, one-and-done. Physical format: <BQQQ> stride-25,
absolute file addresses. Journaled for revert. No runtime gate evaluation.

    python muhl_fab_nefg.py          # fabricate and store
    python muhl_fab_nefg.py --dry    # report only, store nothing
"""
import json, os, struct, sys

sys.path.insert(0, r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent\host")
import pfc_paths as PFCP
import titan_circuit as TC

TITAN = PFCP.TITAN
REG = PFCP.REG
MAGIC = b"MUHLNEFG"
NAND_OP = 0
GATE_STRIDE = 25
NAME = "muhl_nefg"
GENOME_PATH = TITAN.replace(".gguf", "_nefg_genome.jsonl")
DRY = "--dry" in sys.argv


def depth_of(c, outs):
    n = c.n_in
    d = [0] * c.n_wire()
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[o] for o in outs)


def _cir_dict(c, outs):
    return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": list(c.ga), "gb": list(c.gb), "outs": list(outs)}


def build_nefg(add_kind):
    """Build one NEFG candidate with the given adder kind ('ripple' or 'prefix')."""
    c = TC.Circuit(8)
    A = list(c.IN[:8])

    ADD = c.add if add_kind == "ripple" else c.add_prefix

    # Morphism f: A -> B = bitwise NOT
    B = [c.not_(A[i]) for i in range(8)]

    # Morphism g: B -> C = increment by 1 (sequential path through f then g)
    C_seq = ADD(B, c.cvec(1, 8))[:8]

    # Composition g.f: A -> C = NOT + increment (INDEPENDENT gate path — no sharing)
    not_A = [c.not_(A[i]) for i in range(8)]
    C_comp = ADD(not_A, c.cvec(1, 8))[:8]

    all_outs = B + C_seq + C_comp
    return c, A, B, C_seq, C_comp, all_outs


def verify_nefg(c, A, B, C_seq, C_comp):
    """Exhaustive verification: functor law g(f(x)) == (g.f)(x) for all 256 inputs.
    This is MANUFACTURING verification — ripple inside the fabrication tool is acceptable."""
    cir_seq = _cir_dict(c, C_seq)
    cir_comp = _cir_dict(c, C_comp)
    cir_f = _cir_dict(c, B)

    for x in range(256):
        inbits = TC.bits(x, 8)

        # f(x) = ~x
        f_out = TC.frombits(TC.ripple(cir_f, inbits))
        expected_f = (~x) & 0xFF
        if f_out != expected_f:
            return False, f"f({x})={f_out} expected {expected_f}"

        # g(f(x)) via sequential path
        gf_seq = TC.frombits(TC.ripple(cir_seq, inbits))
        expected_gf = ((~x) + 1) & 0xFF  # two's complement negation
        if gf_seq != expected_gf:
            return False, f"g(f({x}))={gf_seq} expected {expected_gf}"

        # (g.f)(x) via composition path
        gf_comp = TC.frombits(TC.ripple(cir_comp, inbits))
        expected_comp = (-x) & 0xFF
        if gf_comp != expected_comp:
            return False, f"(g.f)({x})={gf_comp} expected {expected_comp}"

        # FUNCTOR LAW: g(f(x)) == (g.f)(x)
        if gf_seq != gf_comp:
            return False, f"FUNCTOR VIOLATION at x={x}: g(f(x))={gf_seq} != (g.f)(x)={gf_comp}"

    return True, "all 256 inputs pass — functor law holds"


def alloc_space(nbytes):
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    occupied = []
    for k, v in reg.items():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            occupied.append((v["offset"], v["offset"] + v["len"]))
    occupied.sort()
    hi = max((e for _, e in occupied), default=0)
    off = ((hi + 63) // 64) * 64
    fsize = os.path.getsize(TITAN) if os.path.exists(TITAN) else 0
    if off + nbytes > fsize:
        print(f"  NOTE: NEFG ({nbytes:,} bytes) extends past current EOF ({fsize:,}).")
        print(f"  titan.gguf will grow — owner confirmed no size constraint.")
    return off


def to_physical(c, all_outs, base_off):
    """Convert a Circuit to physical-format blob: wire bytes + header + <BQQQ> gate records."""
    n_wire = c.n_wire()
    n_gates = len(c.ga)
    header_size = 8 + 4 + 4  # MAGIC(8) + n_gates(u32) + n_in(u32) = 16
    blob_size = n_wire + header_size + n_gates * GATE_STRIDE

    blob = bytearray(blob_size)

    # Wire bytes: byte 0 = const_0 (already 0), byte 1 = const_1
    blob[1] = 1

    # Header after wire bytes
    hdr_off = n_wire
    blob[hdr_off:hdr_off + 8] = MAGIC
    struct.pack_into("<I", blob, hdr_off + 8, n_gates)
    struct.pack_into("<I", blob, hdr_off + 12, c.n_in)

    # Gate table
    gate_off = n_wire + header_size
    for k in range(n_gates):
        addr_a = base_off + c.ga[k]
        addr_b = base_off + c.gb[k]
        addr_out = base_off + (2 + c.n_in + k)
        struct.pack_into("<BQQQ", blob, gate_off + k * GATE_STRIDE,
                         NAND_OP, addr_a, addr_b, addr_out)

    # Compute absolute addresses for the output wires
    out_addrs = [base_off + o for o in all_outs]
    return blob, out_addrs


def verify_physical(blob, base_off, c, n_gates):
    """Structural verification of the physical-format blob."""
    n_wire = c.n_wire()
    hdr_off = n_wire

    assert blob[hdr_off:hdr_off + 8] == MAGIC, "bad magic"
    stored_ng = struct.unpack_from("<I", blob, hdr_off + 8)[0]
    stored_nin = struct.unpack_from("<I", blob, hdr_off + 12)[0]
    assert stored_ng == n_gates, f"gate count mismatch: {stored_ng} vs {n_gates}"
    assert stored_nin == c.n_in, f"n_in mismatch: {stored_nin} vs {c.n_in}"
    assert blob[1] == 1, "const_1 wire byte not set"

    gate_off = n_wire + 16
    for k in range(n_gates):
        op, a, b, out = struct.unpack_from("<BQQQ", blob, gate_off + k * GATE_STRIDE)
        assert op == NAND_OP, f"gate {k} op={op}"
        assert a == base_off + c.ga[k], f"gate {k} a={a} expected {base_off + c.ga[k]}"
        assert b == base_off + c.gb[k], f"gate {k} b={b} expected {base_off + c.gb[k]}"
        assert out == base_off + (2 + c.n_in + k), f"gate {k} out wrong"

    return True


def journal_write(off, blob):
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({
            "action": "nefg_fab",
            "off": off,
            "len": len(blob),
            "orig": orig.hex(),
        }) + "\n")
    fsize = os.path.getsize(TITAN)
    if off + len(blob) > fsize:
        with open(TITAN, "ab") as f:
            f.write(b"\x00" * (off + len(blob) - fsize))
    with open(TITAN, "r+b") as f:
        f.seek(off)
        f.write(blob)


def update_registry(base_off, total_size, n_gates, depth, c, A, B, C_seq, C_comp, add_kind):
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    n_wire = c.n_wire()

    obj_a_addrs = [base_off + w for w in A]
    obj_b_addrs = [base_off + w for w in B]
    obj_c_seq_addrs = [base_off + w for w in C_seq]
    obj_c_comp_addrs = [base_off + w for w in C_comp]

    depth_f = depth_of(c, B)
    depth_g = depth_of(c, C_seq)
    depth_gf = depth_of(c, C_comp)

    reg[NAME] = {
        "name": NAME,
        "tensor": "allocated_past_eof",
        "offset": base_off,
        "len": total_size,
        "n_gate": n_gates,
        "depth": depth,
        "format": "physical",
        "magic": "MUHLNEFG",
        "gate_stride": GATE_STRIDE,
        "n_in": 8,
        "n_wire": n_wire,
        "object_a_addrs": obj_a_addrs,
        "object_b_addrs": obj_b_addrs,
        "object_c_seq_addrs": obj_c_seq_addrs,
        "object_c_comp_addrs": obj_c_comp_addrs,
        "morphisms": {
            "f": {"desc": "A->B bitwise NOT", "depth": depth_f, "inputs": obj_a_addrs, "outputs": obj_b_addrs},
            "g": {"desc": "B->C increment", "depth": depth_g, "inputs": obj_b_addrs, "outputs": obj_c_seq_addrs},
            "gf": {"desc": "A->C negation (composition)", "depth": depth_gf, "inputs": obj_a_addrs, "outputs": obj_c_comp_addrs},
        },
        "functor_property": "g(f(x)) == (g.f)(x) verified byte-exact for all 256 8-bit inputs",
        "add_kind": add_kind,
        "foundry_genome": {"topology": "functorial_graph", "add": add_kind, "objects": 3, "morphisms": 3},
        "units": "n_gate=GATES, depth=TICKS, len=BYTES",
        "genome": GENOME_PATH,
        "note": "NEFG: category-theoretic functors as NAND gates. F(f.g)=F(f).F(g) enforced structurally.",
        "verified_by": "exhaustive 256-input functor-law check + structural physical-format verification",
    }
    json.dump(reg, open(REG, "w"), indent=1)


def main():
    print("\n  MUHLNICKEL NEFG — NON-EUCLIDEAN FUNCTORIAL GRAPH")
    print("  Category-theoretic functors as NAND gate networks")
    print("  Bryce Muhlnickel, 2026-08-03\n")

    # ---- PROPOSE ----
    candidates = []
    for add_kind in ("ripple", "prefix"):
        c, A, B, C_seq, C_comp, all_outs = build_nefg(add_kind)
        n_gates = len(c.ga)
        d_total = depth_of(c, all_outs)
        d_f = depth_of(c, B)
        d_g = depth_of(c, C_seq)
        d_gf = depth_of(c, C_comp)

        # ---- VERIFY (manufacturing — ripple is acceptable) ----
        ok, msg = verify_nefg(c, A, B, C_seq, C_comp)

        candidates.append({
            "add_kind": add_kind,
            "n_gates": n_gates,
            "depth": d_total,
            "depth_f": d_f,
            "depth_g": d_g,
            "depth_gf": d_gf,
            "verified": ok,
            "msg": msg,
            "circuit": c,
            "A": A, "B": B, "C_seq": C_seq, "C_comp": C_comp, "all_outs": all_outs,
        })
        print(f"  PROPOSE [{add_kind:6s}]  gates {n_gates:>6,}  DEPTH {d_total:4d}  "
              f"(f:{d_f} g:{d_g} g.f:{d_gf})  {'VERIFIED' if ok else 'FAILED: ' + msg}")

    # ---- SCORE: Pareto front ----
    good = [r for r in candidates if r["verified"]]
    pareto = [r for r in good if not any(
        o["depth"] <= r["depth"] and o["n_gates"] <= r["n_gates"] and o is not r
        and (o["depth"] < r["depth"] or o["n_gates"] < r["n_gates"])
        for o in good)]

    print(f"\n  VERIFIED {len(good)}/{len(candidates)}   PARETO FRONT ({len(pareto)}):")
    for r in sorted(pareto, key=lambda x: x["depth"]):
        print(f"    DEPTH {r['depth']:4d}  gates {r['n_gates']:>6,}  {r['add_kind']}")

    best = min(good, key=lambda r: r["depth"]) if good else None
    if not best:
        print("  NO verified candidates — aborting.")
        return 1

    print(f"\n  WINNER by DEPTH: {best['add_kind']}  DEPTH {best['depth']}  gates {best['n_gates']:,}")
    print(f"    f(A->B NOT): depth {best['depth_f']}")
    print(f"    g(B->C inc): depth {best['depth_g']}")
    print(f"    g.f(A->C neg): depth {best['depth_gf']}")
    print(f"    functor law: g(f(x)) == (g.f)(x) for all 256 inputs: HOLDS")

    c = best["circuit"]
    A, B, C_seq, C_comp = best["A"], best["B"], best["C_seq"], best["C_comp"]
    all_outs = best["all_outs"]
    n_gates = best["n_gates"]
    n_wire = c.n_wire()
    header_size = 16
    total_size = n_wire + header_size + n_gates * GATE_STRIDE

    print(f"\n  physical layout: {n_wire} wire bytes + {header_size} header + {n_gates * GATE_STRIDE:,} gate bytes = {total_size:,} bytes")

    if DRY:
        print(f"\n  --dry: nothing stored. Run without --dry to fabricate.")
        return 0

    # ---- ALLOCATE ----
    base_off = alloc_space(total_size)
    print(f"  allocated at offset: {base_off:,}")

    # ---- BUILD PHYSICAL ----
    blob, out_addrs = to_physical(c, all_outs, base_off)
    assert len(blob) == total_size, f"blob size {len(blob)} != expected {total_size}"

    # ---- VERIFY PHYSICAL ----
    phys_ok = verify_physical(blob, base_off, c, n_gates)
    print(f"  structural verify (physical format): {'PASS' if phys_ok else 'FAIL'}")
    if not phys_ok:
        print("  ABORTING — physical verification failed")
        return 1

    # ---- STORE (journaled) ----
    print(f"\n  FABRICATING — writing {total_size:,} bytes to titan.gguf at offset {base_off:,}")
    journal_write(base_off, bytes(blob))
    print(f"  journaled to: {GENOME_PATH}")

    # ---- REGISTRY ----
    update_registry(base_off, total_size, n_gates, best["depth"], c, A, B, C_seq, C_comp, best["add_kind"])
    print(f"  registry updated: {NAME}")

    print(f"\n  NEFG FABRICATED.")
    print(f"  Objects:    A (input) @ offsets {[base_off + w for w in A[:2]]}...  B @ {[base_off + w for w in B[:2]]}...  C @ {[base_off + w for w in C_seq[:2]]}...")
    print(f"  Morphisms:  f: NOT(A)->B   g: inc(B)->C   g.f: neg(A)->C")
    print(f"  Functor:    g(f(x)) == (g.f)(x) — STRUCTURALLY ENFORCED, byte-exact verified")
    print(f"  Depth:      {best['depth']} ticks.  Gates: {n_gates:,}.")
    print(f"\n  Host's job: write 8 bits to object A addresses, read object C addresses. That's it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
