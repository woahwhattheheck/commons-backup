"""Deterministic no-network benchmark for SAGE."""
from __future__ import annotations

import argparse
import json
from statistics import mean

from mock_env import SwitchDoorEnv
from receipts import compile_receipt, verify_receipt
from sage import SAGEAgent


def run(seed: int, *, max_actions: int = 80) -> dict[str, object]:
    env = SwitchDoorEnv(seed)
    agent = SAGEAgent()
    obs = env.reset()
    for step in range(max_actions):
        if obs.state != "NOT_FINISHED":
            break
        decision = agent.decide(obs, actions_left=max_actions - step)
        after = env.step(decision.action)
        agent.learn(obs, decision, after)
        obs = after
    receipt_ok = False
    receipt_sha = None
    if agent.trace:
        receipt = compile_receipt(agent.trace, agent_revision="local-sage", source_refs={"env": f"mock:{seed}"})
        receipt_ok = verify_receipt(receipt)
        receipt_sha = receipt["receipt_sha256"]
    return {
        "seed": seed,
        "won": obs.state == "WIN",
        "actions": len(agent.trace),
        "skills": len(agent.skills.skills),
        "receipt_ok": receipt_ok,
        "receipt_sha256": receipt_sha,
    }


def suite(seeds: range, *, max_actions: int = 80) -> dict[str, object]:
    rows = [run(seed, max_actions=max_actions) for seed in seeds]
    wins = sum(bool(row["won"]) for row in rows)
    return {
        "runs": rows,
        "wins": wins,
        "total": len(rows),
        "win_rate": wins / len(rows) if rows else 0.0,
        "mean_actions": mean(int(row["actions"]) for row in rows) if rows else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=12)
    parser.add_argument("--max-actions", type=int, default=80)
    args = parser.parse_args()
    if not 1 <= args.seeds <= 1000:
        parser.error("--seeds must be 1..1000")
    report = suite(range(args.seeds), max_actions=args.max_actions)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["wins"] == report["total"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
