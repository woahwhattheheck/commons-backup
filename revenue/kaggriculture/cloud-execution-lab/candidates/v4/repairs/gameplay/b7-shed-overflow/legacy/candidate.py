#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""B7 wrapped around the exact shipped-8e3 V3.1 R04 stack."""
from __future__ import annotations

from pathlib import Path
import sys

HERE = Path(__file__).resolve()
EXPERIMENTS = HERE.parents[1]
for path in (HERE.parent, EXPERIMENTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from baseline import CURRENT_STACK_CONFIG, agent as BASE  # noqa: E402
from b7_shed_room_guard import install as install_b7  # noqa: E402

agent = install_b7(BASE, enabled=True)

B7_CURRENTROOT_CONFIG = dict(CURRENT_STACK_CONFIG)
B7_CURRENTROOT_CONFIG["b7_shed_room_guard"] = True
