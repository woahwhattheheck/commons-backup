#!/usr/bin/env python3
# host/muhl_fab_keyb01.py — same button as infra/host.
from __future__ import annotations

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ALT = os.path.abspath(os.path.join(HERE, "..", "infra", "host", "muhl_fab_keyb01.py"))
if os.path.isfile(ALT):
    sys.argv[0] = ALT
    runpy.run_path(ALT, run_name="__main__")
else:
    print("NEED infra/host/muhl_fab_keyb01.py")
    raise SystemExit(2)
