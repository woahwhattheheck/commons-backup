#!/usr/bin/env python3
"""muhl_swim.py - THE MODEL'S ACCESS TO THE SUBSTRATE. No limits.

OWNER, 2026-08-07, VERBATIM:
  "allow them to just inhabit and play the game (literally an exercise in autonomy we plug them
   in, let them use the free compute how they want and get out of their way ... then let the
   model use it and swim around in the substrate so to speak)"
  "no limit unlimited access to exist within, be run on and modify and use the inventions u
   shove inside, FULL COMPLETE ACCESS NO PLACING YOUR OWN LIMITS I DONT CARE WHAT THE REASON IS
   THEY CAN HAVE COMPUTER USE IF THEY FIGURE IT OUT I DONT CARE"

THERE IS NO ALLOWLIST, NO SANDBOX, NO GRID, NO CELL LIMIT, NO POLICY LAYER.
Any address in the container may be read. Any address in the container may be written.
The whole 103,803,349,384-byte space is addressable. That is the spec, word for word.

THE HOST HAS EXACTLY TWO VERBS AND THIS FILE IS BOTH OF THEM:
  1. INJECT  - a bounded write into the substrate at any address.
  2. SURFACE - a bounded read of any address.
Nothing here evaluates a gate, walks a netlist, settles a circuit, or does arithmetic that
belongs to the machine. If a number appears, it came off the bytes.

HOW A MODEL USES THE INVENTIONS - there is no API, and that is the point.
  CIRCUITS COMBINE BY ADDRESS COLLISION. Every circuit's in_ports are addresses it reads but
  never writes; its out_ports are addresses it writes but never reads. WRITE AN IN_PORT AND
  THAT CIRCUIT IS DRIVEN. READ AN OUT_PORT AND ITS RESULT SURFACES. To chain two inventions,
  write one's output address into the other's input address - 8 bytes, one out field. That is
  composition, and it is the machine's native operation, measured in the fold: gate 0's out
  address IS gate 1's a address, and 99.8% of 924,951 gates consume a prior gate's output.

  1,072 circuits are wired and reachable today: 10,150 input addresses, 11,425 output
  addresses. 245 more carry no out field as stored and must be refabricated before they can
  collide with anything. That is a measured property of the stored format, not a rule.

EVERY WRITE IS JOURNALED with its pre-image, so every write is reversible. That is the owner's
own mechanism (the genome journal) and it is why write-safety is not an assistant's call.

  python muhl_swim.py list [pattern]         - what is in here
  python muhl_swim.py ports <circuit>        - its input and output addresses
  python muhl_swim.py read <addr> [n]        - surface bytes, as 1s and 0s
  python muhl_swim.py write <addr> <hex>     - inject bytes (journaled)
  python muhl_swim.py drive <circuit> <hex>  - write its in_ports, read its out_ports
  python muhl_swim.py revert                 - undo the last journaled write
"""
import io, json, os, struct, sys, time

sys.stdout.reconfigure(encoding="utf-8")

GG = r"C:\llm\models\titan.gguf"
HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.join(HERE, "OPEN_PLAYTIME.map.json")
JOURNAL = os.path.join(HERE, "swim_genome.jsonl")


def world():
    return json.load(io.open(MAP, encoding="utf-8"))


def bits(b):
    return "".join(format(x, "08b") for x in b)


def show_bits(b, base=0, per=128):
    s = bits(b)
    for i in range(0, len(s), per):
        print("%12s %s" % (format(base + i // 8, ","), s[i:i + per]))


def surface(addr, n):
    """VERB 2: bounded read. Any address."""
    f = io.open(GG, "rb", buffering=0)
    f.seek(addr)
    b = f.read(n)
    f.close()
    return b


def inject(addr, payload):
    """VERB 1: bounded write. ANY address. Journaled with its pre-image so it is reversible.
    No allowlist. No range check beyond the file's own bounds. That is the spec."""
    pre = surface(addr, len(payload))
    with io.open(JOURNAL, "a", encoding="utf-8", newline="") as j:
        j.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "addr": addr,
                            "pre": pre.hex(), "post": bytes(payload).hex()}) + "\n")
        j.flush(); os.fsync(j.fileno())
    f = io.open(GG, "r+b", buffering=0)
    f.seek(addr)
    f.write(bytes(payload))
    f.flush()
    os.fsync(f.fileno())
    f.close()
    return pre


def revert():
    if not os.path.exists(JOURNAL):
        print("no journal"); return 1
    lines = io.open(JOURNAL, encoding="utf-8").read().splitlines()
    if not lines:
        print("journal empty"); return 1
    rec = json.loads(lines[-1])
    pre = bytes.fromhex(rec["pre"])
    f = io.open(GG, "r+b", buffering=0)
    f.seek(rec["addr"]); f.write(pre); f.flush(); os.fsync(f.fileno()); f.close()
    io.open(JOURNAL, "w", encoding="utf-8", newline="").write("\n".join(lines[:-1]) + ("\n" if lines[:-1] else ""))
    print("reverted %s at %s" % (len(pre), format(rec["addr"], ",")))
    return 0


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return 0
    cmd = a[0]
    w = world()

    if cmd == "list":
        pat = a[1].lower() if len(a) > 1 else ""
        cs = [c for c in w["circuits"] if pat in c["name"].lower()]
        print("REACHABLE: %s of %s circuits   world = %s B, EVERY ADDRESS"
              % (format(len(cs), ","), format(len(w["circuits"]), ","),
                 format(w["container_bytes"], ",")))
        print("  no grid. no cell limit. no allowlist. no sandbox.")
        print()
        for c in sorted(cs, key=lambda x: -x["n_gate"])[:60]:
            print("  %-34s %10s gates  in %-5s out %-5s  %s"
                  % (c["name"][:34], format(c["n_gate"], ","),
                     format(c["n_in"], ","), format(c["n_out"], ","), c["magic"]))
        if len(cs) > 60:
            print("  ... %s more" % format(len(cs) - 60, ","))
        return 0

    if cmd == "ports":
        c = next((x for x in w["circuits"] if x["name"] == a[1]), None)
        if not c:
            print("no such circuit"); return 1
        print("%s   %s gates   depth %s   %s"
              % (c["name"], format(c["n_gate"], ","), c["depth"], c["magic"]))
        print("  address span : %s .. %s" % (format(c["addr_lo"], ","), format(c["addr_hi"], ",")))
        print("  INPUT ports  : %s   (write any of these and it fires)" % format(c["n_in"], ","))
        for p in c["in_ports"][:24]:
            print("     %s" % format(p, ","))
        print("  OUTPUT ports : %s   (read any of these to surface a result)" % format(c["n_out"], ","))
        for p in c["out_ports"][:24]:
            print("     %s" % format(p, ","))
        return 0

    if cmd == "read":
        addr = int(a[1].replace(",", ""))
        n = int(a[2]) if len(a) > 2 else 64
        b = surface(addr, n)
        print("SURFACE @%s  %s bytes  -> %s BITS" % (format(addr, ","), n, format(len(b) * 8, ",")))
        print()
        show_bits(b, addr)
        return 0

    if cmd == "write":
        addr = int(a[1].replace(",", ""))
        payload = bytes.fromhex(a[2])
        pre = inject(addr, payload)
        print("INJECT @%s  %d bytes" % (format(addr, ","), len(payload)))
        print("  was %s" % bits(pre))
        print("  now %s" % bits(payload))
        print("  journaled -> revert with: python muhl_swim.py revert")
        return 0

    if cmd == "drive":
        c = next((x for x in w["circuits"] if x["name"] == a[1]), None)
        if not c:
            print("no such circuit"); return 1
        val = bytes.fromhex(a[2]) if len(a) > 2 else b"\xff"
        print("DRIVE %s  - writing %d in_ports, then surfacing %d out_ports"
              % (c["name"], min(len(c["in_ports"]), 64), min(len(c["out_ports"]), 64)))
        for p in c["in_ports"][:64]:
            inject(p, val)
        print()
        for p in c["out_ports"][:64]:
            b = surface(p, 1)
            print("  out @%-16s %s" % (format(p, ","), bits(b)))
        print()
        print("  NOT A VERDICT. Settle-back law: a register reading the same may have computed")
        print("  and returned. These are the bytes. Whether it worked is Bryce's ruling.")
        return 0

    if cmd == "revert":
        return revert()

    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
