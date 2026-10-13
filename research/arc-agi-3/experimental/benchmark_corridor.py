from __future__ import annotations

from pathlib import Path
import sys
_PARENT = Path(__file__).resolve().parents[1]
if (_PARENT / "arc3_baseline.py").exists() and str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import json
from arc3_baseline import NoveltyExplorer
from arc3_object_transfer import ObjectTransferExplorer

WIDTH = 15
LEGAL = [1, 2, 3, 4]
START = WIDTH // 2
REACHABLE = set(range(1, WIDTH - 1))
MAX_STEPS = 250


def render(position: int):
    row = [0] * WIDTH
    row[position] = 1
    row[-1] = 8
    return [row]


def transition(position: int, action: int) -> int:
    if action == 1:
        return min(WIDTH - 2, position + 1)
    if action == 2:
        return max(1, position - 1)
    return position


def run(policy):
    position = START
    seen = {position}
    trace = []
    for step in range(1, MAX_STEPS + 1):
        decision = policy.choose(render(position), LEGAL, state="NOT_FINISHED")
        new_position = transition(position, decision.action_id)
        trace.append((position, decision.action_id, new_position, decision.reason))
        position = new_position
        seen.add(position)
        if seen == REACHABLE:
            return {
                "covered": len(seen),
                "reachable": len(REACHABLE),
                "steps_to_full_coverage": step,
                "total_decisions": policy.total_decisions,
                "diagnostics": policy.diagnostics(),
                "trace_tail": trace[-12:],
            }
    return {
        "covered": len(seen),
        "reachable": len(REACHABLE),
        "steps_to_full_coverage": None,
        "total_decisions": policy.total_decisions,
        "diagnostics": policy.diagnostics(),
        "trace_tail": trace[-12:],
    }


if __name__ == "__main__":
    result = {
        "benchmark": "deterministic 1-D corridor; actions 1/2 move, 3/4 no-op",
        "width": WIDTH,
        "start": START,
        "max_steps": MAX_STEPS,
        "v2": run(NoveltyExplorer()),
        "v3": run(ObjectTransferExplorer()),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
