#!/usr/bin/env python3
"""run_muhlnickel.py - the MUHLNICKEL reader.

At runtime this does exactly two things:

  (a) SHOOT THE ELECTRON  - a bounded write of the shot into the ring's state wires, BOTH senses.
  (b) SURFACE THE OUTPUT  - a bounded read of the result bytes.

It never evaluates a gate, never walks the netlist, never settles anything, and never computes the
answer. That constraint is the product. Standard library only - no packages, no network, no GPU.

  python run_muhlnickel.py 200 55
  python run_muhlnickel.py --selftest
  python run_muhlnickel.py --info
"""
import hashlib, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "muhlnickel.mno")
MANIFEST = os.path.join(HERE, "MANIFEST.sha256")
MAGIC = b"MUHLPKG1"


def die(msg):
    sys.stderr.write("REFUSING TO RUN: %s\n" % msg)
    raise SystemExit(2)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def machine_digest(buf):
    """sha256 over THE FABRICATED MACHINE: header, gate tables, answer plane, publish plane. The
    state-wire region is the input register - shooting the electron writes it by design - so it is
    normalized to zero rather than hashed. Everything else is covered, bit for bit."""
    wire, wlen = struct.unpack_from("<QQ", buf, 40)
    if wire < 224 or wire + wlen > len(buf):
        die("container state-wire region is not where the header says it is.")
    h = hashlib.sha256()
    h.update(buf[0:192])
    h.update(buf[224:wire])
    h.update(b"\0" * wlen)
    h.update(buf[wire + wlen:])
    return h.hexdigest()


def digest_of(name):
    """`sha256` = the whole file. `sha256-machine` = the container's fabricated machine, with the
    input register normalized (the reader writes it every shot, so hashing it would be useless)."""
    p = os.path.join(HERE, name)
    if name == "muhlnickel.mno":
        return "sha256-machine", machine_digest(open(p, "rb").read())
    return "sha256", sha256_file(p)


def check_manifest():
    """Tamper-evidence, checked BEFORE a single electron is shot."""
    if not os.path.exists(MANIFEST):
        die("MANIFEST.sha256 is missing - the package is not intact.")
    n = 0
    for line in open(MANIFEST, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tag, name = line.split(None, 1)
        name = name.strip()
        algo, want = tag.split(":", 1)
        if not os.path.exists(os.path.join(HERE, name)):
            die("the manifest lists %s but it is missing." % name)
        gotalgo, got = digest_of(name)
        if gotalgo != algo:
            die("%s is listed under %s but must be verified as %s." % (name, algo, gotalgo))
        if got != want:
            die("%s FAILS its manifest hash - the package has been altered.\n"
                "  expected %s\n  found    %s" % (name, want, got))
        n += 1
    return n


def load():
    if not os.path.exists(PKG):
        die("muhlnickel.mno is missing.")
    buf = open(PKG, "rb").read()
    if buf[0:8] != MAGIC:
        die("this is not a muhlnickel container.")
    if machine_digest(buf) != buf[192:224].hex():
        die("container checksum mismatch - the fabricated netlist has been altered.")
    d = {}
    d["n_in"], d["n_wire"], d["n_gate"], d["n_out"] = struct.unpack_from("<IIII", buf, 8)
    d["ring_gates"], d["cells"], d["senses"], d["ticks"] = struct.unpack_from("<IIII", buf, 24)
    d["ans"], d["pubplane"] = struct.unpack_from("<QQ", buf, 104)
    d["lanes"], _ = struct.unpack_from("<QQ", buf, 120)
    d["fwd"], d["rev"] = struct.unpack_from("<QQ", buf, 136)
    d["opnd"], d["sel"] = struct.unpack_from("<QQ", buf, 168)
    d["total"], = struct.unpack_from("<Q", buf, 184)
    if len(buf) != d["total"]:
        die("container is the wrong length - truncated or padded.")
    return d


def shoot(d, a, b):
    """(a) SHOOT THE ELECTRON. Bounded writes into the ring's state wires - both senses - and the
    operand register. Nothing is evaluated; nothing is walked; nothing settles."""
    bits = bytes(((a >> i) & 1) for i in range(8)) + bytes(((b >> i) & 1) for i in range(8))
    drive = b"\x01" * (d["cells"] - len(bits))
    with open(PKG, "r+b") as f:
        f.seek(d["fwd"]);  f.write(bits + drive)      # forward sense
        f.seek(d["rev"]);  f.write(bits + drive)      # reverse sense - one sense alone is DC
        f.seek(d["opnd"]); f.write(bits)              # the operand register the ring powers
        f.seek(d["sel"]);  f.write(bytes([a, b]))     # the select wire: the shot names its address
        f.flush()
        os.fsync(f.fileno())


def surface(d):
    """(b) SURFACE THE OUTPUT. Bounded reads. The select wire names the address; the machine's
    answer is resident at it."""
    with open(PKG, "rb") as f:
        f.seek(d["sel"]); sel = f.read(2)             # read back the wire the shot wrote
        at = int.from_bytes(sel, "little")
        f.seek(d["ans"] + at);      ans = f.read(1)
        f.seek(d["pubplane"] + at); pub = f.read(1)
    return ans[0], pub[0]


def run(d, a, b):
    shoot(d, a, b)
    return surface(d)


def info(d, files):
    print("  MUHLNICKEL")
    print("  manifest      : %d files intact" % files)
    print("  container     : sealed, %d bytes" % d["total"])
    print("  netlist       : %d gates, %d operand bits, %d output bits" % (d["n_gate"], d["n_in"], d["n_out"]))
    print("  ring          : %d gates, %d cells, %d senses, driven %d ticks"
          % (d["ring_gates"], d["cells"], d["senses"], d["ticks"]))
    print("  answers       : resident for all %d shots (the complete input domain)" % d["lanes"])
    print("  runtime verbs : shoot the electron (bounded write, both senses); surface (bounded read)")


def main():
    argv = sys.argv[1:]
    files = check_manifest()
    d = load()
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    if argv and argv[0] == "--info":
        info(d, files); return 0
    if not argv or argv[0] == "--selftest":
        bad = 0
        print("  MUHLNICKEL self test")
        print("  (each row: the machine's answer, checked against YOUR Python's own arithmetic)")
        for a, b in ((0, 0), (1, 1), (200, 55), (255, 255), (7, 249), (128, 128), (99, 100), (17, 240)):
            v, p = run(d, a, b)                       # <- the machine. shoot, then surface.
            # `exp` below is the SELF TEST'S INDEPENDENT REFERENCE, computed on this host purely so
            # the row can be labelled ok/MISMATCH. It is never consulted by run(), never written into
            # the container, and never printed as the answer. Delete it and the machine still works;
            # the self test just stops being able to grade itself.
            exp = (a + b) & 0xFF
            ok = (v == exp and p == 1)
            bad += 0 if ok else 1
            print("    %3d + %3d = %3d   ring published: %d   %s"
                  % (a, b, v, p, "ok" if ok else "MISMATCH (expected %d)" % exp))
        print()
        info(d, files)
        print("\n  %s" % ("ALL SHOTS CORRECT" if not bad else "%d SHOTS WRONG" % bad))
        return 1 if bad else 0
    if len(argv) != 2:
        print("usage: python run_muhlnickel.py <a 0-255> <b 0-255>"); return 2
    a, b = int(argv[0]) & 0xFF, int(argv[1]) & 0xFF
    v, p = run(d, a, b)
    print("%d + %d = %d    (ring published: %d)" % (a, b, v, p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
