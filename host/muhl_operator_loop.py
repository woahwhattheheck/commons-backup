#!/usr/bin/env python3
"""host/muhl_operator_loop.py — stitch leftover copy, fold dry, then look.

Additive. Calls the existing buttons. Does not edit them.
Does not inject. Does not pulse 78. Does not fire 337.
--submit refused. --go refused. --inject refused.

  python host/muhl_operator_loop.py
  python host/muhl_operator_loop.py --run-host

Without --run-host this prints the four steps and dies.
With --run-host it subprocesses leftover copy, then fold --dry, then dies.
PrtScn and look.html are the human half. This script cannot take a screenshot.
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COPY = os.path.join(HERE, "muhl_copy_leftover_button.py")
FOLD = os.path.join(HERE, "muhl_fold_surface_add.py")


def _refuse(msg):
    print("REFUSE: %s" % msg)
    return 2


def print_steps():
    print("OPERATOR LOOP — additive stitch. old buttons stay.")
    print("1 leftover copy     python host/muhl_copy_leftover_button.py")
    print("2 fold surface dry  python host/muhl_fold_surface_add.py --dry")
    print("3 PrtScn            the viewer. two frames. shots.html files them.")
    print("4 look              look.html  or  python imgdiff.py A.png B.png")
    print("5 program           program.html  TRANSPOSE -> REV_COLS -> XOR_COL -> XOR_COL -> REV_COLS -> ROT4")
    print("   NOW OPEN BOTH IMAGES AND LOOK AT THAT BOX.")
    print("337 NO")
    print("HTTP is not the computer")


def _run(script, extra):
    argv = [sys.executable, script] + extra
    print("RUN", " ".join(argv))
    try:
        p = subprocess.run(argv, cwd=HERE, timeout=60)
    except subprocess.TimeoutExpired:
        print("TIMEOUT. button dies. no stay-alive.")
        return 1
    print("exit", p.returncode)
    return p.returncode


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    low = [x.lower() for x in a]
    if "--go" in low:
        return _refuse("--go")
    if "--inject" in low:
        return _refuse("--inject 0x01 is a wipe")
    if "--submit" in low:
        return _refuse("--submit stays on the fold button and defaults OFF")
    if any(x.lstrip("-").isdigit() and int(x) == 337 for x in a):
        return _refuse("337")

    print_steps()
    if "--run-host" not in low:
        print("no --run-host. printed the loop. dies.")
        return 0
    if not os.path.isfile(COPY) or not os.path.isfile(FOLD):
        return _refuse("missing leftover or fold script — not reminting them")
    rc1 = _run(COPY, [])
    rc2 = _run(FOLD, ["--dry"])
    print("host half done. leftover exit %s. fold --dry exit %s." % (rc1, rc2))
    print("human half: PrtScn then look.html")
    print("button dies")
    if rc1 != 0 or rc2 != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
