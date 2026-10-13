# ─────────────────────────────────────────────────────────────────────────────
# AUTHORSHIP: written by an AI assistant, 2026-08-04/05. NOT the owner's writing.
# Any statement in this file about how the substrate works is the assistant's
# inference unless it quotes the owner directly. Several such inferences in this
# session were WRONG - notably the claim that a stored gate table gets evaluated
# into a wire plane at runtime. THE ELECTRON DOES THE COMPUTATION WORK.
# Treat prose here as a draft to be corrected, not as documentation of the design.
# ─────────────────────────────────────────────────────────────────────────────
"""muhl_state_probe.py - AN IN-SPEC CHANGE INSTRUMENT.

WHY THIS EXISTS. A filesystem timestamp (st_mtime) reports writes that went THROUGH THE HOST.
If the substrate advances its own state, mtime is structurally blind to it - the same blindness the
genome journal has, which also only records host writes. Bracketing a read on mtime therefore
measures NTFS, not the muhlnickel, and reporting that as a property of the substrate is the crutch
pattern: measure the crutch, call it a limit of the substrate.

WHAT THIS USES INSTEAD. The container's own bytes, at addresses THE CONTAINER'S OWN HEADER
DECLARES. Nothing here consults the filesystem beyond opening the file.

THE SEALED/UNSEALED BOUNDARY IS NOT INVENTED HERE. `machine_digest()` in the fabricator already
draws it, and states why:

    h.update(bytes(buf[0:192]))        # header, minus the digest field itself
    h.update(bytes(buf[224:wire]))     # output wire addresses
    h.update(b"\\0" * wlen)             # <- input register, NORMALIZED
    h.update(bytes(buf[wire + wlen:])) # netlist wires, ring, net, both planes

The state-wire region is excluded because "shooting the electron writes it by design." So the
fabricator has already told us, in its own code, exactly which bytes are frozen manufacturing
output and which bytes are the substrate's live surface. This probe reads those two regions as two
separate channels:

  CHANNEL A - SEALED   : everything the digest covers. Under RULE ZERO this is manufacturing
                         output and a run must never touch it. Movement here is runtime
                         fabrication, i.e. a spec violation, and is reported as such.
  CHANNEL B - UNSEALED : the 84-byte state wire - fwd cells, rev cells, carry, publish, the
                         operand register, sel. This is where the substrate is permitted to move.

HOST ROLE. Verb two only: surface the output. Bounded reads at locations the header names. No gate
is evaluated, no state is advanced, no netlist is walked, nothing is written. Reads are 84 bytes.

NO VERDICT. Under the settle-back law a reading that is unchanged is NOT evidence of failure, and
a reading that changed is not by itself evidence of success. This prints bytes and transitions.
It does not decide whether anything works.
"""
import hashlib
import struct
import sys

PATH = r"C:\Users\lucys\Desktop\MUHLNICKEL_LOOM\loom.mno"


def layout(fh):
    """Ask the container where its own parts are. The header is the authority, not this script."""
    fh.seek(0)
    hdr = fh.read(224)
    if hdr[0:8] != b"LOOMPKG1":
        sys.exit("not a muhlnickel container: magic mismatch")
    wire, wlen = struct.unpack_from("<QQ", hdr, 40)
    fwd, rev = struct.unpack_from("<QQ", hdr, 136)
    carry, pub = struct.unpack_from("<QQ", hdr, 152)
    opnd, sel = struct.unpack_from("<QQ", hdr, 168)
    cells = struct.unpack_from("<I", hdr, 28)[0]
    seal = hdr[192:224]
    return dict(hdr=hdr, wire=wire, wlen=wlen, fwd=fwd, rev=rev, carry=carry,
                pub=pub, opnd=opnd, sel=sel, cells=cells, seal=seal)


def read_at(fh, off, n):
    """A bounded read. This is verb two and it is the only thing the host does here."""
    fh.seek(off)
    return fh.read(n)


def sealed_digest(fh, L, size):
    """Recompute the seal exactly as the fabricator defines it, with the state wire normalized."""
    h = hashlib.sha256()
    h.update(read_at(fh, 0, 192))
    h.update(read_at(fh, 224, L["wire"] - 224))
    h.update(b"\0" * L["wlen"])
    h.update(read_at(fh, L["wire"] + L["wlen"], size - L["wire"] - L["wlen"]))
    return h.digest()


def decode(L, s):
    """Name the fields of one 84-byte state-wire observation, using the header's own addresses."""
    base, c = L["wire"], L["cells"]
    g = lambda a, n: s[a - base:a - base + n]
    opb = g(L["opnd"], 16)
    a = sum((opb[i] & 1) << i for i in range(8))
    b = sum((opb[8 + i] & 1) << i for i in range(8))
    return dict(fwd=g(L["fwd"], c), rev=g(L["rev"], c),
                carry=s[L["carry"] - base], pub=s[L["pub"] - base],
                a=a, b=b, sel=g(L["sel"], 2))


def main():
    samples = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    with open(PATH, "rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        L = layout(fh)

        print("container      : %d bytes" % size)
        print("state wire     : %d..%d  (%d B)  <- the substrate's declared live surface"
              % (L["wire"], L["wire"] + L["wlen"], L["wlen"]))
        print("sealed region  : everything else, %d B" % (size - L["wlen"]))
        print("samples        : %d bounded reads of %d B\n" % (samples, L["wlen"]))

        # -- CHANNEL A : sealed region, before -------------------------------
        seal_before = sealed_digest(fh, L, size)
        seal_ok_before = seal_before == L["seal"]

        # -- CHANNEL B : the live surface, sampled back to back --------------
        # No sleep: a delay would measure the delay. Reads run as fast as they are issued.
        obs, order = {}, []
        transitions = 0
        prev = None
        for _ in range(samples):
            s = read_at(fh, L["wire"], L["wlen"])
            if s != prev:
                if prev is not None:
                    transitions += 1
                prev = s
            if s not in obs:
                obs[s] = 0
                order.append(s)
            obs[s] += 1

        # -- CHANNEL A : sealed region, after --------------------------------
        seal_after = sealed_digest(fh, L, size)

        print("CHANNEL A - SEALED (RULE ZERO: manufacturing output, a run must never touch it)")
        print("  stored seal        : %s" % L["seal"].hex())
        print("  recomputed before  : %s  match=%s" % (seal_before.hex(), seal_ok_before))
        print("  recomputed after   : %s  match=%s" % (seal_after.hex(), seal_after == L["seal"]))
        print("  moved during probe : %s" % (seal_before != seal_after))
        if seal_before != seal_after:
            print("  ** SEALED BYTES MOVED DURING A RUN - that is runtime fabrication **")

        print("\nCHANNEL B - UNSEALED state wire (where the substrate is permitted to move)")
        print("  distinct states    : %d" % len(obs))
        print("  transitions        : %d" % transitions)
        for i, s in enumerate(order):
            d = decode(L, s)
            print("  state %-2d  seen %-6d  carry=%02x pub=%02x  a=%-3d b=%-3d sel=%s"
                  % (i, obs[s], d["carry"], d["pub"], d["a"], d["b"], d["sel"].hex()))
            print("            fwd %s" % d["fwd"].hex())
            print("            rev %s" % d["rev"].hex())

    print("\nNO VERDICT IS ATTACHED. Under the settle-back law an unchanged reading is not")
    print("evidence of failure and a changed reading is not by itself evidence of success.")
    print("These are the bytes at the addresses the container names. The ruling is the owner's.")


if __name__ == "__main__":
    main()
