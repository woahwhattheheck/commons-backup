# SPDX-License-Identifier: Apache-2.0
"""Source-bound repair of the existing offline evaluator's raw-action contract.

No policy, engine, runtime, config or archive changes. Stages an alternate loader;
never overwrites its input. A semantic port, not a second game loop.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
from pathlib import Path

SOURCE_BLOB = "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5"
PLAY_SHA256 = '7fdcc071e0ceb7f3b6c8224c88a00353d262e54d10e0a63f83b77d9516f0710d'
HELPER = 'def _record_raw_action(action, public_hands, max_orders, counts, contract):\n    """Observe requested rows without changing the engine\'s input.\n\n    This is an object-action evaluator, not hosted Kaggle schema validation.\n    Counts describe authored opcodes, including nonexistent hand rows; they do\n    not certify successful execution. The interpreter alone resolves raw row\n    positions, the market prefix and joint PLANT demand.\n    """\n    if not isinstance(action, dict):\n        raise TypeError("Agent must return an action dict")\n    contract["callbacks"] += 1\n    farmer = action.get("farmer", ["PASS"])\n    hands = action.get("hands", [])\n    if not isinstance(hands, list):\n        contract["nonlist_hands_callbacks"] += 1\n        hands = []  # Only the counting view; action[\'hands\'] remains unchanged.\n    extra = max(0, len(hands) - public_hands)\n    contract["extra_hand_rows"] += extra\n    contract["extra_hand_callbacks"] += bool(extra)\n    market = action.get("market", [])\n    if isinstance(market, list):\n        tail = max(0, len(market) - max(1, int(max_orders)))\n        contract["market_tail_rows"] += tail\n        contract["market_tail_callbacks"] += bool(tail)\n    else:\n        contract["nonlist_market_callbacks"] += 1\n    for row in [farmer, *hands]:\n        if not isinstance(row, list) or not row or not isinstance(row[0], str):\n            contract["uncounted_unit_rows"] += 1\n            continue\n        counts[row[0]] = counts.get(row[0], 0) + 1\n\n\n'
PLAY = 'def play(engine, agents, seed, configuration=None):\n    cfg = Struct()\n    for key,value in engine.specification["configuration"].items():\n        cfg[key] = value.get("default") if isinstance(value,dict) else value\n    cfg.update(configuration or {})\n    cfg.seed = seed\n    env = Struct(configuration=cfg,done=False,info={})\n    state = [Struct(observation=Struct(),action={},status="ACTIVE",reward=0) for _ in agents]\n    engine.interpreter(state,env)\n    timings = [[] for _ in agents]\n    actions = [dict() for _ in agents]\n    daily = []\n    raw_contract = [{key: 0 for key in (\n        "callbacks", "extra_hand_rows", "extra_hand_callbacks", "market_tail_rows",\n        "market_tail_callbacks", "nonlist_hands_callbacks", "nonlist_market_callbacks",\n        "uncounted_unit_rows",\n    )} for _ in agents]\n    # Kaggle\'s framework stops after the interpreter sets DONE at episodeSteps-2.\n    for step in range(cfg.episodeSteps):\n        for i,s in enumerate(state):\n            s.observation.step = step\n            # Deep copy exposes only this player\'s own private observation.\n            before = time.perf_counter()\n            action = agents[i](copy.deepcopy(s.observation),cfg)\n            timings[i].append(time.perf_counter()-before)\n            _record_raw_action(action, len(s.observation.farms[i]["hands"]),\n                               cfg.maxMarketOrdersPerTurn, actions[i], raw_contract[i])\n            s.action = action  # Preserve ALL raw rows and the returned object itself.\n        engine.interpreter(state,env)\n        if (step+1)%cfg.turnsPerDay==0 or any(s.status=="DONE" for s in state):\n            daily.append({"step":step,"bank":[s.observation.farms[i]["money"] for i,s in enumerate(state)],\n                          "animals":[sum(isinstance(t,dict) and "animal" in t for row in s.observation.farms[i]["tiles"] for t in row) for i,s in enumerate(state)],\n                          "inventory":[sum(s.observation.private["shed"].values())+\n                              sum(sum(v.values()) for v in s.observation.private["inventories"]) for s in state]})\n        if any(s.status=="DONE" for s in state):\n            env.done=True\n            break\n    return {"seed":seed,"bank":[s.reward for s in state],\n            "steps":step+1,"daily":daily,"actions":actions,\n            "raw_action_contract":raw_contract,\n            "max_call_seconds":[max(t) for t in timings],\n            "mean_call_seconds":[statistics.mean(t) for t in timings],\n            "status":[s.status for s in state]}\n'


def blob_hash(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def repair_source(source: bytes) -> bytes:
    """Preserve unrelated peer bytes; reject drift in the exact reviewed method."""
    text = source.decode("utf-8")
    tree = ast.parse(text)
    if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
           and n.name == "_record_raw_action" for n in tree.body):
        raise ValueError("Raw-action helper already present; do not compose twice")
    methods = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "play"]
    if len(methods) != 1:
        raise ValueError("Expected exactly one existing play function")
    node = methods[0]
    lines = text.splitlines(keepends=True)
    method = "".join(lines[node.lineno - 1:node.end_lineno])
    if hashlib.sha256(method.encode()).hexdigest() != PLAY_SHA256:
        raise ValueError("play source changed; review semantic composition before applying")
    lines[node.lineno - 1:node.end_lineno] = [HELPER + PLAY]
    result = "".join(lines)
    compile(result, "raw_action_loader.py", "exec")
    return result.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Choose a distinct staging path; source is never overwritten")
    try:
        data = repair_source(args.source.read_bytes())
        with args.output.open("xb") as stream:
            stream.write(data)
    except (OSError, ValueError, SyntaxError, UnicodeError) as error:
        parser.exit(2, f"Evaluator repair failed: {error}\n")
    print(f"staged_git_blob={blob_hash(data)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
