#!/usr/bin/env python3
"""host/muhl_cli.py — one line, one button, then die.

  python host/muhl_cli.py copy [slot]
  python host/muhl_cli.py inject [slot] [a] [b]
  python host/muhl_cli.py surface [slot] [addr] [n]
  python host/muhl_cli.py slots
  python host/muhl_cli.py die

Not a daemon. Not Claude-Code-as-resident-worker. Host = inject ∨ surface ∨ copy ∨ die.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

import muhl_backend as B


def _print_result(r):
    if not r.get("ok"):
        print("NEED_BRYCE — %s" % r.get("need_bryce", "?"))
        print("  training_started  NO")
        print("  (button dies)")
        return 1
    verb = r.get("verb", "?")
    print("MUHL CLI  %s" % verb)
    if verb == "copy":
        print("  germ   %s" % r["germ"])
        print("  slot   %s" % r["slot"])
        print("  bytes  %s" % r["bytes"])
    elif verb == "inject":
        print("  slot   %s" % r["slot"])
        print("  a,b    %s,%s" % (r["a"], r["b"]))
        print("  fwd    @%s  %s -> %s" % (r["fwd"]["off"], r["fwd"]["old"], r["fwd"]["new"]))
        print("  rev    @%s  %s -> %s" % (r["rev"]["off"], r["rev"]["old"], r["rev"]["new"]))
        print("  sel    @%s  %s -> %s" % (r["sel"]["off"], r["sel"]["old"], r["sel"]["new"]))
        if r.get("recv"):
            print("  recv   @%s  %s -> %s" % (r["recv"]["off"], r["recv"]["old"], r["recv"]["new"]))
    elif verb == "surface":
        print("  slot   %s" % r["slot"])
        print("  addr   %s  n=%s" % (r["addr"], r["n"]))
        print("  hex    %s" % r["hex"])
        if r.get("byte") is not None:
            print("  byte   %s" % r["byte"])
    elif verb == "slots":
        print("  dir    %s" % r["dir"])
        print("  n      %s" % r["n"])
        for s in r["slots"]:
            print("  %s  %s B" % (s["path"], s["bytes"]))
    elif verb == "die":
        pass
    print("  training_started  NO")
    print("  (button dies)")
    return 0


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    verb = a[0].lower()
    rest = a[1:]
    if verb == "copy":
        slot = rest[0] if rest else "slot_0.mno"
        return _print_result(B.copy(slot=slot))
    if verb == "inject":
        slot = rest[0] if rest else "slot_0.mno"
        aa = int(rest[1], 0) if len(rest) > 1 else 3
        bb = int(rest[2], 0) if len(rest) > 2 else 5
        return _print_result(B.inject(slot=slot, a=aa, b=bb))
    if verb == "surface":
        slot = rest[0] if rest else "slot_0.mno"
        addr = int(rest[1], 0) if len(rest) > 1 else None
        n = int(rest[2], 0) if len(rest) > 2 else 1
        return _print_result(B.surface(slot=slot, addr=addr, n=n))
    if verb == "slots":
        return _print_result(B.slots())
    if verb == "die":
        return _print_result(B.die())
    print("NEED_BRYCE — verb %r (copy|inject|surface|slots|die)" % verb)
    print("  (button dies)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
