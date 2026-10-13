#!/usr/bin/env python3
"""host/muhl_wb_physical.py — MAKE wb_fwd PHYSICAL (local wire ids → absolute file addresses).

wb_fwd is a 2,448-gate forward block (y = W · x, K=3, OUT=2, VB=3, YB=8) stored in TITANCIR format.
Its gate operands are wire ids local to the circuit, so no gate is addressed by a file byte and the
ring (280) cannot drive it — "the electron was stored, not travelling" (fab_osc_physical.py, July).

WHAT THIS WRITES
  wires  n_wire bytes (one per local wire). wire w → WIRE_BASE + w
  table  MUHLOSCP | n_gate | 25, then stride-25 <BQQQ> records with ABSOLUTE operands:
             nand(WIRE_BASE+ga[i], WIRE_BASE+gb[i]) → WIRE_BASE + GBASE + i
  Contiguous allocation — 2,477 wire bytes + 61,216 gate table bytes = ~62 KB total.

THE ANSWER SURFACE
  The 16 output wires (2 outputs × 8 bits each) ARE the state, one byte each, at
  WIRE_BASE + outs[i]. No bit-unpacking needed — each output bit is its own byte.

THE INPUT SURFACE
  The 27 input wires (9 values × 3 bits each) are at WIRE_BASE + 2 .. WIRE_BASE + 28.
  The training loop writes x and W values here as individual bytes (0x00 or 0x01).

RULE 0
  No gate is evaluated. Nothing is rippled or computed on the host. The netlist is TRANSLATED and
  verified structurally. Owner, permanent: "ur not allowed to offload ANY computation into the host".

  python host/muhl_wb_physical.py --dry     # decide everything, write nothing
  python host/muhl_wb_physical.py           # fabricate
  python host/muhl_wb_physical.py revert    # byte-identical restore
"""
import json, os, struct, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TITAN = "C:/llm/models/titan.gguf"
REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_wbphys_genome.jsonl"

NAME = "muhl_wb_physical"
GATES_NAME = "muhl_wb_physical_gates"
SRC = "wb_fwd"
MAGIC = b"MUHLOSCP"
STRIDE = 25


def rd(off, n):
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off); return f.read(n)


def journal(off, blob):
    orig = rd(off, len(blob))
    with open(GENOME, "a") as g:
        g.write(json.dumps({"off": off, "n": len(blob), "orig": orig.hex()}) + "\n")
        g.flush(); os.fsync(g.fileno())
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)
        f.flush(); os.fsync(f.fileno())


def read_titancir(off):
    h = rd(off, 24)
    if h[:8] != b"TITANCIR":
        raise RuntimeError("not TITANCIR at %d: %r" % (off, h[:8]))
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", h, 8)
    p = off + 24
    ga = list(struct.unpack("<%di" % n_gate, rd(p, n_gate * 4))); p += n_gate * 4
    gb = list(struct.unpack("<%di" % n_gate, rd(p, n_gate * 4))); p += n_gate * 4
    outs = list(struct.unpack("<%di" % n_out, rd(p, n_out * 4)))
    return n_in, n_wire, n_gate, n_out, ga, gb, outs


def revert():
    if not os.path.exists(GENOME):
        print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for x in reversed(ent):
        with open(TITAN, "r+b") as f:
            f.seek(int(x["off"])); f.write(bytes.fromhex(x["orig"]))
            f.flush(); os.fsync(f.fileno())
    reg = json.load(open(REG))
    reg.pop(NAME, None); reg.pop(GATES_NAME, None)
    json.dump(reg, open(REG, "w"), indent=1)
    os.remove(GENOME)
    print("reverted %d edit(s); the file is byte-identical to before." % len(ent))
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    dry = "--dry" in sys.argv

    reg = json.load(open(REG))
    if SRC not in reg:
        print("%s is not fabricated." % SRC); return 1
    if NAME in reg:
        print("%s already stored @ %s. revert first." % (NAME, reg[NAME]["offset"])); return 0

    src = reg[SRC]
    t0 = time.time()
    n_in, n_wire, n_gate, n_out, ga, gb, outs = read_titancir(int(src["offset"]))
    GBASE = 2 + n_in

    print("MAKE wb_fwd PHYSICAL — local wire ids → absolute file addresses.\n")
    print("  source   %s @%d  TITANCIR" % (SRC, src["offset"]))
    print("  n_in %d  n_wire %d  n_gate %d  n_out %d" % (n_in, n_wire, n_gate, n_out))

    bad = [i for i, (a, b) in enumerate(zip(ga, gb)) if not (0 <= a < n_wire and 0 <= b < n_wire)]
    if bad:
        print("  %d gate(s) reference wire id outside 0..n_wire-1 — refusing." % len(bad)); return 1
    if max(outs) >= n_wire or min(outs) < 0:
        print("  an output names a wire outside the circuit — refusing."); return 1
    if GBASE + n_gate != n_wire:
        print("  2 + n_in + n_gate (%d) != n_wire (%d) — refusing." % (GBASE + n_gate, n_wire)); return 1
    print("  STRUCTURE: all operands in range · outs in range · 2+n_in+n_gate == n_wire  OK")

    gate_bytes = n_gate * STRIDE
    total = n_wire + 16 + gate_bytes
    print("  need  %s wire bytes + %s gate bytes = %s B total" %
          ("{:,}".format(n_wire), "{:,}".format(gate_bytes + 16), "{:,}".format(total)))

    import titan_circuit as TC
    WIRE_BASE, tn = TC._alloc(total, reg)
    TAB_OFF = WIRE_BASE + n_wire

    print("\n  WIRE_BASE @%d  tensor %s  (%s B contiguous)" %
          (WIRE_BASE, tn, "{:,}".format(n_wire)))
    print("  gate table @%d  (%s B)" % (TAB_OFF, "{:,}".format(16 + gate_bytes)))
    print("  wire w → %d + w   |   gate i → nand(base+ga[i], base+gb[i]) → base+%d+i"
          % (WIRE_BASE, GBASE))
    print("  RAILS: const0 @%d · const1 @%d" % (WIRE_BASE, WIRE_BASE + 1))

    print("\n  INPUT SURFACE (27 wires = 9 values × 3 bits, at WIRE_BASE+2..28):")
    labels = ["x[0]"] * 3 + ["x[1]"] * 3 + ["x[2]"] * 3 + \
             ["W[0]"] * 3 + ["W[1]"] * 3 + ["W[2]"] * 3 + ["W[3]"] * 3 + ["W[4]"] * 3 + ["W[5]"] * 3
    for i in range(n_in):
        print("    input[%2d] (%s bit %d) → @%d" % (i, labels[i], i % 3, WIRE_BASE + 2 + i))

    print("\n  OUTPUT SURFACE (16 wires = 2 outputs × 8 bits):")
    for k in range(n_out):
        print("    out[%2d] (y[%d] bit %d) local wire %-6d → @%d" %
              (k, k // 8, k % 8, outs[k], WIRE_BASE + outs[k]))

    if dry:
        print("\n  --dry: nothing written. 0 bytes changed. [%.1fs]" % (time.time() - t0))
        return 0

    print("\n  writing wires (%s B) ..." % "{:,}".format(n_wire))
    prefab = bytearray(n_wire)
    prefab[0] = 0
    prefab[1] = 1
    journal(WIRE_BASE, bytes(prefab))
    if rd(WIRE_BASE, 2) != b"\x00\x01":
        print("  const rails did not read back as 00 01 — run revert."); return 1

    print("  writing gate table (%s gates, %s B) ..." %
          ("{:,}".format(n_gate), "{:,}".format(16 + gate_bytes)))
    tb = bytearray(16); tb[0:8] = MAGIC
    struct.pack_into("<II", tb, 8, n_gate, STRIDE)
    rec = bytearray(gate_bytes)
    for i in range(n_gate):
        struct.pack_into("<BQQQ", rec, i * STRIDE, 0,
                         WIRE_BASE + ga[i], WIRE_BASE + gb[i], WIRE_BASE + GBASE + i)
    blob = bytes(tb) + bytes(rec)
    journal(TAB_OFF, blob)
    if rd(TAB_OFF, len(blob)) != blob:
        print("  gate table byte-compare FAILED — run revert."); return 1

    for i in (0, n_gate // 2, n_gate - 1):
        op, a, b, o = struct.unpack("<BQQQ", rd(TAB_OFF + 16 + i * STRIDE, STRIDE))
        want = (0, WIRE_BASE + ga[i], WIRE_BASE + gb[i], WIRE_BASE + GBASE + i)
        if (op, a, b, o) != want:
            print("  gate %d readback %s != %s — run revert." % (i, (op, a, b, o), want)); return 1
    print("  readback: const rails + gates 0 / %d / %d match source" % (n_gate // 2, n_gate - 1))

    reg = json.load(open(REG))
    input_wires = [WIRE_BASE + 2 + i for i in range(n_in)]
    output_wires = [WIRE_BASE + w for w in outs]
    reg[NAME] = {
        "tensor": tn, "offset": WIRE_BASE, "len": n_wire, "format": "physical",
        "wire_base": WIRE_BASE, "gate_stride": STRIDE, "magic": MAGIC.decode(),
        "gate_table_off": TAB_OFF + 16, "n_gate": n_gate, "n_in": n_in, "n_out": n_out,
        "n_wire": n_wire, "depth": src.get("depth"), "translated_from": SRC,
        "input_wires": input_wires,
        "output_wires": output_wires,
        "note": "PHYSICAL translation of %s. wire w IS byte %d+w. 27 input wires at "
                "WIRE_BASE+2..28 (9 values × 3 bits). 16 output wires (2 outputs × 8 bits). "
                "No host gate evaluation performed — translated and verified structurally."
                % (SRC, WIRE_BASE),
    }
    reg[GATES_NAME] = {"tensor": tn, "offset": TAB_OFF, "len": 16 + gate_bytes,
                       "n_gate": n_gate, "gate_stride": STRIDE, "magic": MAGIC.decode(),
                       "gate_table_off": TAB_OFF + 16,
                       "role": "%s gate table (stride-25 <BQQQ>, absolute-address operands)" % NAME}
    json.dump(reg, open(REG, "w"), indent=1)

    print("\n  STORED '%s'  wires @%d (%s B) + %s gates @%d  [%.1fs]  GGUF-valid: %s"
          % (NAME, WIRE_BASE, "{:,}".format(n_wire), "{:,}".format(n_gate), TAB_OFF,
             time.time() - t0, rd(0, 4) == b"GGUF"))
    print("  input wires:  @%d .. @%d  (write x and W values here, one bit per byte)"
          % (input_wires[0], input_wires[-1]))
    print("  output wires: @%d .. @%d  (read y values here, one bit per byte)"
          % (output_wires[0], output_wires[-1]))
    print("  revert: python host/muhl_wb_physical.py revert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
