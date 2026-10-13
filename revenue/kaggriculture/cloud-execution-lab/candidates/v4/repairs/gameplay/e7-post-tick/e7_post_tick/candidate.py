#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact evaluator entrypoint for the E7 post-town-tick evening-flush experiment."""
from __future__ import annotations

from pathlib import Path
import sys

HERE = Path(__file__).resolve()
EXPERIMENTS = HERE.parents[1]
V3 = HERE.parents[2]
OVERLAY = V3 / "overlay"
for path in (EXPERIMENTS, OVERLAY):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import r04_full_router as r04  # noqa: E402
from e7_post_tick_evening_flush import install as install_e7  # noqa: E402

# The shipped ready-submission tuple has evening_flush ON.  E7 turns only that native
# outer layer off and recreates it in the experiment wrapper so hours 21-22 remain
# incumbent-identical while the safe hour-23 subset can cross the town tick.
BASE = r04.install(
    None,
    horizon=8,
    opening=0,
    row_order=True,
    evening_flush=False,
    sale_fertilizer=True,
    cattle_early=True,
)
agent = install_e7(BASE, enabled=True)

E7_EVALUATOR_CONFIG = {
    "r04_sale_horizon": 8,
    "r04_open_roundtrip": 0,
    "r04_row_order": True,
    "r04_native_evening_flush": False,
    "r04_sale_fertilizer": True,
    "r04_cattle_early": True,
    "e7_post_tick_evening_flush": True,
    "control_evening_flush": True,
    "turns_per_day": 24,
    "town_center_sell_interval": 24,
    "official_interpreter_commit": "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c",
    "official_engine_sha256": "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e",
}
