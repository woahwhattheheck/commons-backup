from __future__ import annotations

import argparse
import json
from pathlib import Path

from .harness import AblationKind, ArmConfig, canonical_bytes, compile_experiment, sha256, verify_experiment
from .synthetic import paired_rows

ADAPTER_DIGEST = sha256(b"arc3-sage-ablation-synthetic-adapter-v1")


def arms(kind: AblationKind) -> tuple[ArmConfig, ArmConfig]:
    if kind == AblationKind.ANIMATION:
        return (
            ArmConfig("settled", False, retain_intermediate_frames=False),
            ArmConfig("full-animation", True, retain_intermediate_frames=True),
        )
    if kind == AblationKind.INFO_GAIN:
        return (
            ArmConfig("random", False, probe_policy="RANDOM"),
            ArmConfig("info-gain", True, probe_policy="INFO_GAIN"),
        )
    if kind == AblationKind.COORDINATE:
        return (
            ArmConfig("superset", False, coordinate_policy="SUPERSET"),
            ArmConfig("reduced", True, coordinate_policy="REDUCED"),
        )
    if kind == AblationKind.TRANSFER:
        return (
            ArmConfig("cold-start", False, transfer_policy="COLD_START"),
            ArmConfig("transfer", True, transfer_policy="TRANSFER"),
        )
    raise AssertionError(kind)


def render_markdown(doc: dict) -> str:
    a = doc["aggregate"]
    return "\n".join([
        f"# {doc['kind']}",
        "",
        f"Pairs: **{a['pair_count']}**",
        f"Success: control **{a['control_success_bp']/100:.2f}%** vs treatment **{a['treatment_success_bp']/100:.2f}%** (delta {a['success_delta_bp']/100:+.2f} pp)",
        f"Median real actions: control **{a['control_action_median']}** vs treatment **{a['treatment_action_median']}**",
        f"Mean paired real-action delta (treatment-control): **{a['action_delta_mean_milli']/1000:.3f}**",
        f"Bootstrap 95% interval, milli-actions: **{a['action_delta_bootstrap95_milli']}**",
        f"Paired sign-flip extreme/total: **{a['action_delta_signflip_extreme']}/{a['action_delta_signflip_total']}**",
        f"Evidence delta sum: **{a['evidence_delta_sum']:+d}**; transfer reuse delta: **{a['transfer_reuse_delta_sum']:+d}**",
        "",
        "Synthetic/data-free evidence only. No official ARC/Kaggle score, rank, submission, prize, payment or revenue is claimed.",
        "",
        f"Receipt digest: `{doc['receipt_digest']}`",
    ]) + "\n"


def build(kind: AblationKind, seeds: int, budget: int) -> dict:
    control, treatment = arms(kind)
    rows, scenario_digest = paired_rows(kind, range(seeds), control, treatment, budget)
    receipt = compile_experiment(
        kind=kind, control=control, treatment=treatment, rows=rows,
        scenario_manifest_digest=scenario_digest, adapter_digest=ADAPTER_DIGEST,
        max_real_actions=budget,
    )
    verify_experiment(receipt.document)
    return receipt.document


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=64)
    p.add_argument("--budget", type=int, default=24)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if not 1 <= args.seeds <= 10000 or not 1 <= args.budget <= 100000:
        p.error("out of range")
    docs = [build(k, args.seeds, args.budget) for k in AblationKind]
    bundle = {"schema": "ARC3_SAGE_ABLATION_BUNDLE_V1", "experiments": docs}
    bundle["bundle_digest"] = sha256(canonical_bytes(bundle))
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        for doc in docs:
            stem = doc["kind"].lower()
            (args.output / f"{stem}.json").write_bytes(canonical_bytes(doc) + b"\n")
            (args.output / f"{stem}.md").write_text(render_markdown(doc), encoding="utf-8")
        (args.output / "bundle.json").write_bytes(canonical_bytes(bundle) + b"\n")
    print(json.dumps({"bundle_digest": bundle["bundle_digest"], "experiments": [
        {"kind": d["kind"], "receipt_digest": d["receipt_digest"], "aggregate": d["aggregate"]} for d in docs
    ]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
