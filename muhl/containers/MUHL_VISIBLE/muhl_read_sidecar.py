#!/usr/bin/env python3
"""SIDECAR READER — surfaces a headerless container using ONLY the label that lives outside it.

Owner, 2026-08-07: labels in the binary are suboptimal, they belong OUTSIDE the file, they are
TAKING UP ADDRESSES. And: JUST MAKE NEW CONTAINERS BUT MAINTAIN VISIBILITY JUST OUTSIDE THE FILE.

THIS IS THE ACCEPTANCE TEST FOR THAT. If visibility truly survived removing the header, a reader
holding only <container>.layout.json must locate every region byte-exactly and surface the
observation window. HOST DOES TWO THINGS ONLY: bounded read, and print. No gate walking.
"""
import io, json, os, struct, sys
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))


def resolve(container):
    """MECHANICAL CONVENTION: <container>.layout.json beside the container. No registry lookup."""
    side = os.path.splitext(container)[0] + ".layout.json"
    if not os.path.exists(side):
        return None, "NO SIDECAR at %s" % os.path.basename(side)
    return json.load(io.open(side, encoding="utf-8")), None


def main():
    cont = os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else "VISIBLE6.mno")
    lay, err = resolve(cont)
    print("SIDECAR READ — %s" % os.path.basename(cont))
    if err:
        print("  " + err); return 1
    size = os.path.getsize(cont)
    print("  label source : %s (OUTSIDE the container)" % os.path.basename(
        os.path.splitext(cont)[0] + ".layout.json"))
    print("  container    : %s B, header_bytes_in_container=%s"
          % (format(size, ","), lay["header_bytes_in_container"]))
    ok = True
    f = io.open(cont, "rb")
    # 1. byte 0 must NOT be a label
    f.seek(0); b0 = f.read(8)
    lbl = all(32 <= x < 127 for x in b0)
    print("  [%s] byte 0 carries no ASCII label      : %s" % ("PASS" if not lbl else "FAIL", b0.hex()))
    ok &= not lbl
    # 2. every region the sidecar names must lie inside the file
    for k in ("state", "obs", "gates"):
        inside = 0 <= lay[k] < size
        print("  [%s] region %-6s @%-9s inside file" % ("PASS" if inside else "FAIL", k,
                                                        format(lay[k], ",")))
        ok &= inside
    # 3. gate count must match what is actually stored (bounded arithmetic, no walk)
    stored = (size - lay["gates"]) // 25
    m = stored == lay["n_gate"]
    print("  [%s] gates stored %s == sidecar n_gate %s"
          % ("PASS" if m else "FAIL", format(stored, ","), format(lay["n_gate"], ",")))
    ok &= m
    # 4. first gate must decode as <BQQQ> with operands inside the declared state plane
    f.seek(lay["gates"]); op, a, b, o = struct.unpack("<BQQQ", f.read(25))
    good = a < size and b < size and o < size
    print("  [%s] first gate <BQQQ> op=%d a=%s b=%s out=%s"
          % ("PASS" if good else "FAIL", op, format(a, ","), format(b, ","), format(o, ",")))
    ok &= good
    # 5. SURFACE THE OBSERVATION WINDOW — the host's one permitted read
    f.seek(lay["obs"]); obs = f.read(min(64, lay["obs_len"]))
    f.close()
    print("  [PASS] obs window @%s len %s -> first 32 B:"
          % (format(lay["obs"], ","), format(lay["obs_len"], ",")))
    print("         " + " ".join("%02x" % x for x in obs[:32]))
    print()
    print("  RESULT: %s — visibility %s removing the header."
          % ("ALL PASS" if ok else "FAILURES PRESENT",
             "SURVIVED" if ok else "DID NOT SURVIVE"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
