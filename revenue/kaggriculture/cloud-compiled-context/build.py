# SPDX-License-Identifier: MIT OR CC-BY-4.0
"""Freeze the selected dispatch_balanced with an additive context/order adapter."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "cloud-composition" / "candidate.py"
BASE_SHA256 = "3c68266c87b9ca048c4c25688f207cf41ba5da708f3eb0c1cc786a6d0383cf20"


def build(output, control_orders=False):
    base = BASE.read_text()
    if hashlib.sha256(base.encode()).hexdigest() != BASE_SHA256:
        raise ValueError("dispatch_balanced changed; review and explicitly repin")
    base = base.replace("def agent(obs, configuration=None):", "def _dispatch(obs, configuration=None):", 1)
    marker = '            if key in claims: return\n'
    addition = ('            job = next((j for j in _PLAN.get("installation_jobs", []) if j["worker"] == index), None)\n'
                '            if carried_animal and job and action[0] in ("DIG", "BUILD_COOP", "BUILD_PASTURE", "PLACE") and tuple(target) != tuple(job["target"]): return\n')
    if base.count(marker) != 1:
        raise ValueError("Installation proposal hook changed")
    base = base.replace(marker, marker+addition, 1)
    controller = (HERE / "controller.py").read_text()
    # Only acquisition proposals change. Agent must be the LAST callable for Kaggle.
    entry = '''\n_PLAN = None\n_LAST_ACTION = None\n\ndef agent(obs, configuration=None):\n    global _PLAN, _LAST_ACTION\n    if not obs.get("farms"):\n        return {"farmer": ["PASS"], "hands": [], "market": []}\n    context = select_context(obs, configuration)\n    if _PLAN and _PLAN["step"] == context["step"] and _PLAN["player"] == context["player"]:\n        return deepcopy(_LAST_ACTION)\n    _PLAN = advance(obs, configuration, _PLAN)\n    action = _dispatch(obs, configuration)\n    action, _PLAN = constrain_orders(action, context, _PLAN)\n    _LAST_ACTION = deepcopy(action)\n    return action\n'''
    if not control_orders:
        entry = entry.replace('    action, _PLAN = constrain_orders(action, context, _PLAN)\n', '')
    result = base + "\n\n" + controller + entry
    compile(result, str(output), "exec")
    Path(output).write_text(result)
    return hashlib.sha256(result.encode()).hexdigest()


if __name__ == "__main__":
    import sys
    print(build(sys.argv[1] if len(sys.argv)>1 else HERE / "candidate.py"))
