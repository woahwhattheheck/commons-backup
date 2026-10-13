"""Both-seat replay orchestration and evidence rendering for Titan W06."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from w06_common import SCHEMA, canonical, import_file, plain, sha256_file, write_gzip_json, write_json
from w06_trace import InterpreterTrace, analyze_transitions, intervention_candidates, money


def run_one(
    evaluator,
    *,
    engine_dir: Path,
    loader: Path,
    candidate: str,
    apex: str,
    seed: int,
    candidate_seat: int,
    rng_seed: int,
    action_timeout: float,
    startup_timeout: float,
    game_timeout: float,
    intervention: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    engine, engine_hashes = evaluator.get_engine(engine_dir, loader)
    tracer = InterpreterTrace(candidate_seat, intervention)
    original = engine.interpreter
    engine.interpreter = tracer.wrap(original)
    specs = [candidate, apex] if candidate_seat == 0 else [apex, candidate]
    try:
        game = evaluator.play(
            engine, specs, engine_dir, loader, seed, candidate_seat, rng_seed,
            action_timeout, startup_timeout, game_timeout,
        )
    finally:
        engine.interpreter = original
    applied_trace = [
        {
            "game_step": row["game_step"],
            "applied_actions": row["applied_actions"],
            "after_money": [money(row["after"][candidate_seat], 0), money(row["after"][candidate_seat], 1)]
            if row["game_step"] is not None else None,
        }
        for row in tracer.transitions
        if row["game_step"] is not None
    ]
    game["engine_sha256"] = engine_hashes
    game["intervention_requested"] = plain(intervention) if intervention else None
    game["intervention_applied"] = tracer.applied
    game["applied_transition_sha256"] = hashlib.sha256(canonical(applied_trace)).hexdigest()
    game["evaluator_trace_scope"] = (
        "worker-returned actions plus resulting banks; for an intervention, "
        "applied_transition_sha256 is the authoritative changed-action trace"
    )
    return game, tracer.transitions


def score_margin(game: dict[str, Any]) -> float | None:
    scores = game.get("scores")
    seat = game["candidate_seat"]
    if game.get("status") != "complete" or not isinstance(scores, list) or len(scores) != 2:
        return None
    return float(scores[seat]) - float(scores[1 - seat])


def _artifact_manifest(directory: Path, exclude: set[str] | None = None) -> dict[str, Any]:
    exclude = exclude or set()
    files = {}
    for path in sorted(directory.rglob("*")):
        rel = str(path.relative_to(directory))
        if path.is_file() and rel not in exclude:
            files[rel] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    return {"files": files, "total_files": len(files), "total_bytes": sum(row["bytes"] for row in files.values())}


def render_summary(report: dict[str, Any]) -> str:
    lines = [
        "# Titan W06 Apex counterexample", "",
        f"Seed: `{report['seed']}`  ",
        f"Release: `{report['release']['sha256']}`  ",
        f"Evaluator: `{report['source']['evaluator']['sha256']}`  ", "",
        "## Baseline", "",
        "| candidate seat | status | candidate score | Apex score | margin | permanent money-deficit onset |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for seat_report in report["seats"]:
        game = seat_report["baseline"]["game"]
        scores = game.get("scores") or [None, None]
        seat = game["candidate_seat"]
        onset = seat_report["baseline"]["analysis"].get("permanent_deficit_onset")
        lines.append(
            f"| {seat} | {game['status']} | {scores[seat]} | {scores[1-seat]} | "
            f"{score_margin(game)} | {onset.get('game_step') if onset else None} |"
        )
    lines.extend([
        "", "## Counterfactual screen", "",
        "A positive terminal-margin delta is a repair lead, not proof: the returned action is changed after the actor has updated any private internal state.", "",
        "| seat | step | intervention | baseline margin | counterfactual margin | delta | status |",
        "|---:|---:|---|---:|---:|---:|---|",
    ])
    for seat_report in report["seats"]:
        for item in seat_report["counterfactuals"]:
            spec = item["spec"]
            lines.append(
                f"| {seat_report['candidate_seat']} | {spec['game_step']} | {spec['mode']} | "
                f"{item['baseline_score_margin']} | {item['counterfactual_score_margin']} | "
                f"{item['score_margin_delta']} | {item['game']['status']} |"
            )
    lines.extend([
        "", "## Interpretation boundary", "",
        "This artifact locates deterministic transition and intervention candidates. Promote a controller change only after a source-level mechanism, exact regression tests, both-seat replay, and fresh-seed nonregression evidence.", "",
    ])
    return "\n".join(lines)


def replay(args) -> int:
    output = args.output_dir.resolve()
    if output.exists():
        raise FileExistsError(f"preserve existing output and choose a new path: {output}")
    output.mkdir(parents=True)
    evaluator = import_file(args.evaluator.resolve(), "titan_w06_official_evaluator")
    candidate = str(args.candidate.resolve()) + ("::" + args.candidate_callable if args.candidate_callable else "")
    apex = str(args.apex.resolve()) + ("::" + args.apex_callable if args.apex_callable else "")
    source = {
        "evaluator": {"path": str(args.evaluator), "sha256": sha256_file(args.evaluator)},
        "loader": {"path": str(args.loader), "sha256": sha256_file(args.loader)},
        "candidate": {"path": str(args.candidate), "sha256": sha256_file(args.candidate), "callable": args.candidate_callable or "agent"},
        "apex": {"path": str(args.apex), "sha256": sha256_file(args.apex), "callable": args.apex_callable or "agent"},
    }
    pin = json.loads(args.pin.read_text(encoding="utf-8"))
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "method": "official evaluator play(); parent interpreter transition capture; bounded one-returned-action interventions",
        "limitations": [
            "Offline official interpreter result, not hosted Kaggle scoring.",
            "A counterfactual action is substituted after the actor returns; actor-private state may reflect its original action.",
            "One seed can source-locate a mechanism but cannot establish broad playing strength.",
        ],
        "seed": args.seed,
        "rng_seed": args.rng_seed,
        "release": pin["release"],
        "source": source,
        "seats": [],
    }
    failed = False
    for seat in (0, 1):
        game, transitions = run_one(
            evaluator, engine_dir=args.engine_dir.resolve(), loader=args.loader.resolve(),
            candidate=candidate, apex=apex, seed=args.seed, candidate_seat=seat,
            rng_seed=args.rng_seed, action_timeout=args.action_timeout,
            startup_timeout=args.startup_timeout, game_timeout=args.game_timeout,
        )
        analysis = analyze_transitions(transitions, seat)
        baseline_path = output / f"baseline-seat{seat}.json.gz"
        write_gzip_json(baseline_path, {
            "schema": SCHEMA, "kind": "baseline_full_transition_trace", "source": source,
            "game": game, "analysis": analysis, "transitions": transitions,
        })
        failed |= game["status"] != "complete"
        baseline_margin = score_margin(game)
        counterfactuals = []
        if game["status"] == "complete":
            for intervention in intervention_candidates(analysis, args.max_interventions_per_seat):
                alt_game, alt_transitions = run_one(
                    evaluator, engine_dir=args.engine_dir.resolve(), loader=args.loader.resolve(),
                    candidate=candidate, apex=apex, seed=args.seed, candidate_seat=seat,
                    rng_seed=args.rng_seed, action_timeout=args.action_timeout,
                    startup_timeout=args.startup_timeout, game_timeout=args.game_timeout,
                    intervention=intervention,
                )
                alt_margin = score_margin(alt_game)
                counterfactuals.append({
                    "spec": intervention,
                    "game": alt_game,
                    "analysis": analyze_transitions(alt_transitions, seat),
                    "baseline_score_margin": baseline_margin,
                    "counterfactual_score_margin": alt_margin,
                    "score_margin_delta": None if baseline_margin is None or alt_margin is None else alt_margin - baseline_margin,
                    "trace_retained": False,
                })
                failed |= alt_game["status"] != "complete" or not alt_game["intervention_applied"]
        report["seats"].append({
            "candidate_seat": seat,
            "baseline": {"game": game, "analysis": analysis, "trace_file": baseline_path.name},
            "counterfactuals": counterfactuals,
        })
    write_json(output / "REPORT.json", report)
    (output / "SUMMARY.md").write_text(render_summary(report), encoding="utf-8")
    write_json(output / "MANIFEST.json", {
        "schema": SCHEMA, "kind": "artifact_manifest",
        **_artifact_manifest(output, {"MANIFEST.json"}),
    })
    print(json.dumps({
        "output": str(output), "seed": args.seed,
        "baseline_margins": [score_margin(item["baseline"]["game"]) for item in report["seats"]],
        "counterfactuals": sum(len(item["counterfactuals"]) for item in report["seats"]),
        "failed": bool(failed),
    }, sort_keys=True))
    return int(failed)
