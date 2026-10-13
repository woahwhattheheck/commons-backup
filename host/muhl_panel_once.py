#!/usr/bin/env python3
# host/muhl_panel_once.py — same button as infra/host. Repo root is parent.
from __future__ import annotations

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ALT = os.path.abspath(os.path.join(HERE, "..", "infra", "host", "muhl_panel_once.py"))
if os.path.isfile(ALT):
    sys.argv[0] = ALT
    runpy.run_path(ALT, run_name="__main__")
else:
    print("NEED infra/host/muhl_panel_once.py")
    raise SystemExit(2)
