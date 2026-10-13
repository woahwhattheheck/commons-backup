"""Deterministic synthetic benchmark for policy-level evidence only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core import RadiusController, better, canonical_sha256, choose_elites, halton_points, jitter_around, make_budget_plan, make_run_receipt
from synthetic import BowlWithAnnulus, InfeasibleTrap


def run(seed: int = 17, evaluations: int = 320) -> dict[str, object]:
    problem = BowlWithAnnulus()
    plan = make_budget_plan(evaluations, exploration_fraction=0.20, restart_count=4)
    candidates = []
    incumbent = None
    index = 0
    for point in halton_points(problem.bounds, plan.exploration_evaluations):
        c = problem.evaluate(point, index, "halton")
        index += 1
        candidates.append(c)
        if better(c, incumbent):
            incumbent = c
    assert incumbent is not None
    controller = RadiusController(radius=0.30)
    elites = choose_elites(candidates, plan.restart_count)
    remaining = plan.local_evaluations
    round_index = 0
    while remaining > 0:
        anchor = elites[round_index % len(elites)] if round_index < len(elites) else incumbent
        block = min(8, remaining)
        proposals = jitter_around(anchor.params, problem.bounds, radius=controller.radius, count=block, seed=seed + round_index)
        improved = False
        for point in proposals:
            c = problem.evaluate(point, index, "trust-jitter")
            index += 1
            candidates.append(c)
            if better(c, incumbent):
                incumbent = c
                improved = True
        controller.observe(improved)
        remaining -= block
        round_index += 1
    receipt = make_run_receipt(seed=seed, plan=plan, best=incumbent, radius=controller, evidence_class="SYNTHETIC_LOCAL")
    trap = InfeasibleTrap()
    trap_points = halton_points(trap.bounds, 96)
    trap_candidates = [trap.evaluate(p, i, "trap-halton") for i, p in enumerate(trap_points)]
    trap_best = choose_elites(trap_candidates, 1)[0]
    if not trap_best.feasible:
        raise RuntimeError("feasibility-first ranking failed on trap benchmark")
    return {
        "schema": "tjlabs.learn2design2026/synthetic-benchmark-v1",
        "seed": seed,
        "evaluations": evaluations,
        "bestLoss": incumbent.loss,
        "bestFeasible": incumbent.feasible,
        "bestViolation": incumbent.violation,
        "trapBestFeasible": trap_best.feasible,
        "receipt": receipt,
        "resultSha256": canonical_sha256({"best": incumbent.loss, "trap": trap_best.loss, "seed": seed}),
        "authority": {"officialScore": False, "organizerRun": False, "submission": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--evaluations", type=int, default=320)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.seed, args.evaluations)
    text = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
