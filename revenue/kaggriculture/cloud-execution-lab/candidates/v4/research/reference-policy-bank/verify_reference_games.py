# SPDX-License-Identifier: Apache-2.0
"""Acceptance wrapper around existing cloud-eval.play, NOT a new gauntlet.

First compare the bridge to its direct raw-loader control in both seats versus
the official starter. Then execute the supplied candidate against the reference
in both seats on declared seeds. Candidate strength is scoped to supplied bytes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import reference_policies as rp


def run(kg_root: Path, engine_dir: Path, runtime: Path, candidate: Path,
        seeds: list[int], output: Path) -> dict:
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("Declare a nonempty, unique seed list")
    if output.exists():
        raise FileExistsError(output)
    kg_root, engine_dir = kg_root.resolve(strict=True), engine_dir.resolve(strict=True)
    runtime, candidate = runtime.resolve(strict=True), candidate.resolve(strict=True)
    ev = rp.load_module(kg_root / "cloud-eval/evaluate.py", "basalt_game_evaluator")
    loader = kg_root / "20260907-offline-agent/evaluate.py"
    engine, engine_hashes = ev.get_engine(engine_dir, loader)
    original_actor = ev.Actor
    reference = str(runtime / "adapter.py")
    bridge_mode = [False]

    class ReferenceActor:
        def __init__(self, spec, cache, loader, rng_seed, startup_timeout):
            self.policy = rp.ReferencePolicy(runtime, Path(cache), rng_seed=rng_seed,
                                             startup_timeout=startup_timeout)
            self.ready = self.policy.actor.ready
        def act(self, obs, cfg, timeout):
            self.policy.action_timeout = timeout
            try:
                return {"kind": "action", "action": self.policy(obs, cfg)}
            except rp.PolicyFailure as exc:
                return exc.response
        def close(self):
            self.policy.close()
        def report(self):
            return self.policy.report()

    def actor_factory(spec, cache, loader, rng_seed, startup_timeout):
        cls = ReferenceActor if bridge_mode[0] and spec == reference else original_actor
        return cls(spec, cache, loader, rng_seed, startup_timeout)

    report = {"schema": "titan.v4.reference-acceptance.v1", "python": sys.version,
              "bridge_sha256": rp.digest(Path(rp.__file__)), "runner_sha256": rp.digest(Path(__file__)),
              "runtime_manifest": json.loads((runtime / "manifest.json").read_text()),
              "engine_ref": ev.ENGINE_REF, "engine_sha256": engine_hashes,
              "evaluator_sha256": rp.digest(kg_root / "cloud-eval/evaluate.py"),
              "candidate_entry_sha256": rp.digest(candidate),
              "candidate_source_manifest_sha256": rp.digest(candidate.parent / "SOURCE.json")
                  if (candidate.parent / "SOURCE.json").exists() else None,
              "seeds": seeds, "workers": 1, "games": [], "bridge_equivalence": [],
              "method": "Existing pinned interpreter and cloud-eval.play; only Actor selection "
                        "is bridged. Both seats; no hosted Kaggle claim. Reference control matches "
                        "are not candidate wins. Candidate identity must be bound externally to its archive."}
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        temp = output.with_suffix(output.suffix + ".tmp")
        temp.write_text(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
        temp.replace(output)

    def game(mode, specs, seed, seat, phase):
        bridge_mode[0] = mode == "bridge"
        row = ev.play(engine, specs, engine_dir, loader, seed, seat, game_timeout=180.0)
        row.update(phase=phase, bridge_mode=mode, opponent=report["runtime_manifest"]["key"])
        report["games"].append(row)
        save()
        print(json.dumps({k: row[k] for k in ("phase", "bridge_mode", "seed", "candidate_seat", "status", "scores", "failure")}), flush=True)
        if row["status"] != "complete" or row["steps"] != 719:
            raise RuntimeError("Reference acceptance game failed; raw failure retained")
        return row

    ev.Actor = actor_factory
    try:
        for seat in (0, 1):
            pair = [reference, "official_starter"] if seat == 0 else ["official_starter", reference]
            direct = game("direct", pair, seeds[0], seat, "reference_loader_control")
            bridged = game("bridge", pair, seeds[0], seat, "reference_loader_control")
            same = direct["scores"] == bridged["scores"] and direct["trace_sha256"] == bridged["trace_sha256"]
            report["bridge_equivalence"].append({"seat": seat, "same_scores_and_trace": same})
            save()
            if not same:
                raise AssertionError("Bridge changed the reference policy's complete-game behavior")
        with tempfile.TemporaryDirectory(prefix="basalt-candidate-adapter-") as temp:
            pack = rp.load_module(kg_root / "cloud-pack/pack.py", "basalt_acceptance_pack")
            adapter = Path(temp) / "candidate.py"
            pack.write_adapter(adapter, candidate)
            for seed in seeds:
                for seat in (0, 1):
                    pair = [str(adapter), reference] if seat == 0 else [reference, str(adapter)]
                    game("bridge", pair, seed, seat, "candidate_vs_reference")
    finally:
        ev.Actor = original_actor
        save()
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kg-root", type=Path, required=True)
    p.add_argument("--engine-dir", type=Path, required=True)
    p.add_argument("--reference-runtime", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--seeds", default="11,22,33")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    run(a.kg_root, a.engine_dir, a.reference_runtime, a.candidate,
        [int(n) for n in a.seeds.split(",")], a.out)


if __name__ == "__main__":
    main()
