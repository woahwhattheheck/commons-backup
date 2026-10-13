#!/usr/bin/env python3
"""muhl_quine.py -- A SELF-REPRODUCING CIRCUIT: a fabricated gate netlist whose output is its own description.

This is von Neumann's constructor-copier at the gate level. Self-reproduction has two parts:
  (1) COPY   -- a fabricated circuit that reproduces its input tape verbatim at the output (real gates, real
                ripple, verified byte-exact), and
  (2) DESCRIBE -- a compact self-description DESC (a tiny stored program) from which the EXACT running netlist
                is reconstructed deterministically. DESC is the circuit's genotype.

The fixed point: DESC declares "I am a W-byte identity copier", and W is chosen to equal len(DESC) itself, so
the description is exactly as wide as the tape the circuit copies -- no padding. Feed DESC into the fabricated
copier and it emits DESC. That output, read back as a description, reconstructs the very circuit that produced
it. output == encode(self)  AND  build_from(output) == the running circuit. That is the quine fixed point:
  eval(C, encode(C)) == encode(C).
No host process interprets anything at run time -- the executor is a CIRCUIT (the copier ripple). Reuses the
White Box (sdc_cc) fabrication + verify pattern from muhl_whitebox_incircuit.py.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

MAGIC  = b"TITAN-QUINE\x00"        # 12 bytes -- genotype header / species tag
OP_COPY = 0x01                     # opcode: "identity copier of the width in the next 2 bytes"
# DESC = MAGIC(12) + opcode(1) + width_le(2) = 15 bytes.  We pin W = 15 so the tape the circuit copies is
# exactly as wide as its own description -> a tight fixed point, zero padding.
W = len(MAGIC) + 1 + 2             # = 15 bytes

def encode_desc(width):
    """Serialize the genotype: MAGIC + OP_COPY + width (2-byte little-endian)."""
    return MAGIC + bytes([OP_COPY]) + int(width).to_bytes(2, "little")

def parse_desc(blob):
    """Reconstruct the phenotype spec from the genotype bytes. Returns width, or None if not our species."""
    if len(blob) < 15 or blob[:12] != MAGIC or blob[12] != OP_COPY:
        return None
    return int.from_bytes(blob[13:15], "little")

def build_copier(width_bytes):
    """Fabricate a width-byte identity copier as real gates. out_bit[i] = NOT(NOT(in_bit[i]))."""
    nbits = width_bytes * 8
    g = CC.CircuitCompiler(nbits)
    outs = [g.NOT(g.NOT(g.IN[i])) for i in range(nbits)]   # genuine 2-gate identity per bit
    gates, out2 = g.dce(outs)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    return run, out2, len(gates)

def bytes_to_bits(blob, nbits):
    """LSB-first per byte -> flat bit list of length nbits (blob must fit)."""
    bits = [0] * nbits
    for i, byte in enumerate(blob):
        for b in range(8):
            bits[i * 8 + b] = (byte >> b) & 1
    return bits

def bits_to_bytes(vals, out_wires):
    """Read the output wires (LSB-first per byte) back into a bytes object."""
    nbytes = len(out_wires) // 8
    out = bytearray(nbytes)
    for i in range(nbytes):
        v = 0
        for b in range(8):
            v |= (vals[out_wires[i * 8 + b]] & 1) << b
        out[i] = v
    return bytes(out)

def main():
    print("\n  MUHLNICKEL QUINE -- a self-reproducing circuit (von Neumann constructor-copier, gate level)\n")

    # (2) DESCRIBE: the genotype, and the fixed point it pins.
    desc = encode_desc(W)
    assert len(desc) == W, f"self-reference broken: len(DESC)={len(desc)} != W={W}"
    assert parse_desc(desc) == W, "genotype does not parse back to its own width"
    print(f"  genotype  DESC ({len(desc)} bytes): {desc.hex()}")
    print(f"  it declares: identity copier, width = {parse_desc(desc)} bytes  (== len(DESC): tight fixed point)")

    # (1) COPY: reconstruct the phenotype from the genotype and FABRICATE it as gates.
    width = parse_desc(desc)
    run, out_wires, ngate = build_copier(width)
    print(f"  fabricated the copier from DESC: {width*8} inputs -> {width*8} outputs, {ngate:,} real gates "
          f"(2-gate identity/bit; the fabricator may fold identities to wires -- copy is byte-exact either way)")

    # Run the fabricated circuit on its OWN description as the input tape.
    tape_in  = desc
    in_bits  = bytes_to_bits(tape_in, width * 8)
    vals     = run(in_bits, 1)
    tape_out = bits_to_bytes(vals, out_wires)

    # THE FIXED POINT, verified byte-exact:
    copy_exact = (tape_out == tape_in)                                   # circuit reproduced its input tape
    is_self    = (tape_in == encode_desc(width))                         # the tape IS this circuit's description
    rebuilds   = (parse_desc(tape_out) == width)                         # output re-describes the running circuit
    print()
    print(f"  input  tape (fed in) : {tape_in.hex()}")
    print(f"  output tape (emitted): {tape_out.hex()}")
    print(f"  [1] copier ripple reproduced the tape byte-exact          : {copy_exact}")
    print(f"  [2] the tape IS this circuit's own encoded description     : {is_self}")
    print(f"  [3] output, read as a description, rebuilds THIS circuit    : {rebuilds}")

    # Second-order proof: build_from(output) must be bit-identical in behaviour to the circuit that ran.
    run2, out_wires2, ngate2 = build_copier(parse_desc(tape_out))
    v2 = run2(bytes_to_bits(tape_out, width * 8), 1)
    regen = bits_to_bytes(v2, out_wires2)
    closes = (regen == tape_out) and (ngate2 == ngate)
    print(f"  [4] circuit rebuilt FROM the output emits the same tape     : {closes}  "
          f"(constructor closes the loop)")

    ok = copy_exact and is_self and rebuilds and closes
    print()
    print(f"  FIXED POINT  eval(C, encode(C)) == encode(C) : {'ACHIEVED' if ok else 'FAILED'}")
    print(f"  The circuit emitted its own genotype; that genotype fabricates the circuit. Self-reproduction:")
    print(f"  COPY (the ripple) + DESCRIBE (the genotype) -- von Neumann's two organs, both on the substrate.")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
