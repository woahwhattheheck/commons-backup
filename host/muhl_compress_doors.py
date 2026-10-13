#!/usr/bin/env python3
"""host/muhl_compress_doors.py — print the public compression doors.

Additive. Does not edit foldpack / stackpack / evolve.
Does not inject. Does not pulse 78. Does not fire 337.
--go refused. --inject refused. --submit refused.

  python host/muhl_compress_doors.py

Anyone on the board uses the HTML doors. This script only prints
the map and the CLI that still belongs to the three artifacts.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAGES = "https://woahwhattheheck.github.io/commons"


def _refuse(msg):
    print("REFUSE: %s" % msg)
    return 2


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    low = [x.lower() for x in a]
    if "--go" in low:
        return _refuse("--go")
    if "--inject" in low:
        return _refuse("--inject")
    if "--submit" in low:
        return _refuse("--submit")
    if any(x.lstrip("-").isdigit() and int(x) == 337 for x in a):
        return _refuse("337")

    print("COMPRESS DOORS — public. any claim. no host required.")
    print("plaza   %s/compress.html" % PAGES)
    print("1 rooms     %s/rooms.html" % PAGES)
    print("2 glyphs    %s/glyphs.html" % PAGES)
    print("3 program   %s/program.html" % PAGES)
    print("4 accordion %s/accordion.html" % PAGES)
    print("5 breath    %s/breath.html" % PAGES)
    print("6 mail      %s/stringmail.html" % PAGES)
    print("7 foldbook  %s/foldbook.html" % PAGES)
    print("8 C         %s/cweather.html" % PAGES)
    print("obs look/shots/face/flipbook/loop/net159 also this session")
    print()
    print("published computers in this repo:")
    print("  muhl/containers/MUHLNICKEL_DISTRO/SEED0.mno")
    print("  muhl/containers/MUHLNICKEL_DISTRO/SEED0_GERM.mno")
    print("  muhl/containers/MUHLNICKEL_DISTRO/muhlnickel.mno")
    print()
    print("CLI artifacts (untouched):")
    print("  python foldpack.py IMAGE.png --mode adjacent --folds 11")
    print("  python stackpack.py FILE.mno --width 200")
    print("  python evolve.py FILE.mno --width 200")
    for name in ("foldpack.py", "stackpack.py", "evolve.py"):
        path = os.path.join(ROOT, name)
        print("  %s %s" % (name, "present" if os.path.isfile(path) else "MISSING"))
    print("337 NO")
    print("HTTP is not the computer")
    print("button dies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
