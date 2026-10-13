# SPDX-License-Identifier: Apache-2.0
"""Fail-closed proof that deferred SELL plans cannot cross an Arlene tail switch."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

EXPECTED = {
    "frozen_selected.py": "fc7baf5c179818a55037f6a61d92984d81d1a21c",
    "scheduler.py": "a483b24dd72b580d7d8811636b54d2d44f391575",
    "reference/next-panel/vendor/arlene.py": "bdb9cf58148a3c7961c085f4902759537decabf6",
}
HORIZON_NEEDLE = (
    "checkpoints=[checkpoint for checkpoint,*_ in parent.DECISIONS\n"
    "                 if now<checkpoint<=represented_end]\n"
    "    if checkpoints:\n"
    "        represented_end=min(represented_end,min(checkpoints)-1)"
)
SWITCH_NEEDLE = (
    "for (turn, feat, thr, target) in DECISIONS:\n"
    "            if turn == step and target != self.cur and self._switch_ok(target, turn):\n"
    "                if _feature(obs, feat) >= thr:\n"
    "                    self.cur = target"
)
IMPORT_NEEDLE = "parent = _load('intact_arlene', HERE/'reference/next-panel/vendor/arlene.py')"


def git_blob(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def pinned_text(lab: Path, relative: str) -> str:
    path = lab / relative
    data = path.read_bytes()
    actual = git_blob(data)
    if actual != EXPECTED[relative]:
        raise ValueError(f"{relative} blob mismatch: {actual}")
    return data.decode("utf-8")


def audit(lab: Path) -> dict[str, Any]:
    lab = lab.resolve()
    frozen_text = pinned_text(lab, "frozen_selected.py")
    scheduler_text = pinned_text(lab, "scheduler.py")
    arlene_text = pinned_text(lab, "reference/next-panel/vendor/arlene.py")
    if frozen_text.count(HORIZON_NEEDLE) != 1:
        raise ValueError("checkpoint horizon clip is absent or ambiguous")
    if scheduler_text.count(IMPORT_NEEDLE) != 1:
        raise ValueError("scheduler controller source is absent or ambiguous")
    if arlene_text.count(SWITCH_NEEDLE) != 1:
        raise ValueError("controller exact-turn switch is absent or ambiguous")

    if str(lab) not in sys.path:
        sys.path.insert(0, str(lab))
    import frozen_selected

    actor = frozen_selected.FrozenSelected()
    route = actor.controller.R[actor.controller.cur]
    decisions = list(frozen_selected.parent.DECISIONS)
    checkpoints = [decision[0] for decision in decisions]
    if checkpoints != [226, 360, 433]:
        raise ValueError(f"unexpected controller checkpoints: {checkpoints}")

    rows = []
    for decision in decisions:
        checkpoint = decision[0]
        now = checkpoint - 1
        end, horizon = frozen_selected.event_aware_horizon(
            now,
            len(route) - 2,
            route,
            {frozen_selected.PRODUCTS[0]: 1},
            [],
            {},
        )
        if end >= checkpoint or horizon["hard_end"] != now:
            raise ValueError(
                f"horizon crosses checkpoint {checkpoint}: "
                f"end={end}, hard_end={horizon['hard_end']}"
            )
        rows.append({"checkpoint": checkpoint, "end": end, "hard_end": horizon["hard_end"]})

    return {
        "verdict": "NO_DEFERRED_PLAN_CAN_CROSS_A_CONTROLLER_SWITCH",
        "initial_route": actor.controller.cur,
        "checkpoints": rows,
        "source_blobs": EXPECTED,
    }


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    print(json.dumps(audit(here.parent.parent), indent=2, sort_keys=True))
