#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Native shadow census + paired fixed-action full-engine economics (OFF only).

The native entrypoint and its config are not edited. Each proposed intervention
is independently replayed from the authentic baseline state through terminal
step 718 against BOTH recorded action tapes. These are counterfactual receipts,
not adaptive candidate games or opponent-response/ladder-strength evidence.
"""
from __future__ import annotations
import argparse
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile
import time

from night_feed_frontier import propose_feed_tails
from night_feed_engine import Engine, digest, load_file

ARCHIVE_SHA256 = "b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9"


def authenticate(native_root: Path, archive: Path) -> dict[str, str]:
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("native archive is not the recovered checked b567 release")
    sources = {}
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                if not member.isdir():
                    raise ValueError("nonregular archive member")
                continue
            rel = PurePosixPath(member.name)
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError("nonrelative archive path")
            data = tf.extractfile(member).read()
            local = native_root.joinpath(*rel.parts)
            if local.is_symlink() or local.read_bytes() != data:
                raise ValueError(f"native input differs from checked archive: {rel}")
            sources[str(rel)] = hashlib.sha256(data).hexdigest()
    if len(sources) != 110:
        raise ValueError("unexpected native archive member count")
    return sources


def run(native_root: Path, archive: Path, seed: int, seat: int, output: Path):
    root = native_root.resolve(strict=True)
    sources = authenticate(root, archive.resolve(strict=True))
    engine = Engine(root)
    sys.path.insert(0, str(root))
    native = load_file(root / "main.py", f"_f3_native_{seed}_{seat}")
    state, env = engine.initialize(seed)
    tape = []
    proposals = []
    observations = []
    native_calls = 0
    fallbacks = 0
    began = time.perf_counter()
    for step in range(720):
        for s in state:
            s.observation.step = step
        selected = native.agent(copy.deepcopy(state[seat].observation), env.configuration)
        native_calls += 1
        status = native._INSTANCE.diagnostics.get("status") if native._INSTANCE else None
        fallbacks += status != "completed"
        joint = [None, None]
        joint[seat] = selected
        joint[1 - seat] = engine.engine.starter_agent(copy.deepcopy(state[1 - seat].observation))
        tape.append(copy.deepcopy(joint))
        if 16 <= step % 24 and step < 696 and status == "completed":
            controller = native._INSTANCE.controller
            route = controller.R[controller.cur]
            offers = propose_feed_tails(state[seat].observation, selected, route,
                                        env.configuration, enabled=True)
            for offer in offers:
                proposals.append((offer, copy.deepcopy((state, env))))
                observations.append({"proposal": asdict(offer),
                                     "public_own_observation_sha256": digest(state[seat].observation),
                                     "returned_action_sha256": digest(selected),
                                     "authored_suffix_sha256": digest(route[step:offer.end])})
        engine.transition(state, env, step, joint)
        if any(s.status == "DONE" for s in state):
            break
    final_digest = digest((state, env))
    baseline_money = [s.observation.farms[i]["money"] for i, s in enumerate(state)]
    records = []
    baseline_calls = engine.calls
    for i, (proposal, snapshot) in enumerate(proposals):
        record = {"proposal": asdict(proposal), "evidence": observations[i],
                  "snapshot": snapshot, "status": "NOT_RUN"}
        control, control_env, _ = engine.replay(snapshot, proposal.step, tape[proposal.step:])
        if digest((control, control_env)) != final_digest:
            raise AssertionError("unmodified counterfactual replay does not reproduce whole native state")
        record["control_full_state_sha256"] = digest((control, control_env))
        try:
            candidate, candidate_env, details = engine.replay(snapshot, proposal.step, tape[proposal.step:], proposal)
        except ValueError as exc:
            record.update(status="REJECTED_ACTUAL_SUFFIX", reason=str(exc))
            records.append(record)
            continue
        changed_money = [s.observation.farms[j]["money"] for j, s in enumerate(candidate)]
        own_delta = changed_money[seat] - baseline_money[seat]
        other_delta = changed_money[1 - seat] - baseline_money[1 - seat]
        reset = details["reset_state"]
        survived = [(x, y) for x, y in proposal.targets
                    if "animal" in reset[seat].observation.farms[seat]["tiles"][y][x]]
        record.update(status="REPLAYED_FIXED_ACTIONS", realized_feeds=len(details["feeds"]),
                      survived_reset=survived, terminal_money=changed_money,
                      own_delta=own_delta, rival_delta=other_delta, margin_delta=own_delta-other_delta,
                      full_state_sha256=digest((candidate, candidate_env)))
        records.append(record)
    result = {
        "schema": "titan.f3.feed-tail.native-shadow.v1",
        "python_version": sys.version, "optimization": sys.flags.optimize,
        "local_source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")},
        "method": "unchanged-native baseline; independent paired fixed-action terminal replays; NOT adaptive candidate games",
        "seed": seed, "seat": seat, "opponent": "official_starter",
        "input_archive_sha256": ARCHIVE_SHA256, "native_source_sha256": sources,
        "engine_sha256": engine.hashes, "native_calls": native_calls,
        "native_fallbacks": fallbacks, "terminal_money": baseline_money,
        "baseline_full_state_sha256": final_digest, "joint_tape_sha256": digest(tape),
        "baseline_interpreter_calls_including_initialization": baseline_calls,
        "total_interpreter_calls": engine.calls,
        "proposal_count": len(proposals), "records": records, "joint_tape": tape,
        "elapsed_seconds": time.perf_counter() - began,
        "integration": "UNACTIVATED_RESEARCH", "published": False,
    }
    # Reauthenticate after execution: no native source is changed by this runner.
    if authenticate(root, archive.resolve(strict=True)) != sources:
        raise AssertionError("source identity changed during gate")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("seed", "seat", "native_calls", "native_fallbacks", "terminal_money", "proposal_count", "total_interpreter_calls")}))
    for row in records:
        print(json.dumps({"step": row["proposal"]["step"], "actor": row["proposal"]["actor"],
                          "targets": row["proposal"]["targets"], "status": row["status"],
                          "margin_delta": row.get("margin_delta"), "reason": row.get("reason")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--seat", type=int, choices=(0, 1), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.native_root, args.archive, args.seed, args.seat, args.output)
