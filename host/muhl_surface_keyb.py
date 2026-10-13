#!/usr/bin/env python3
# host/muhl_surface_keyb.py — same button as infra/host.
from __future__ import annotations

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ALT = os.path.abspath(os.path.join(HERE, "..", "infra", "host", "muhl_surface_keyb.py"))
if os.path.isfile(ALT):
    sys.argv[0] = ALT
    runpy.run_path(ALT, run_name="__main__")
else:
    print("NEED infra/host/muhl_surface_keyb.py")
    raise SystemExit(2)
