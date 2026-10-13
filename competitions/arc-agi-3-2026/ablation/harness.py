from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from enum import Enum
from statistics import median
from typing import Iterable, Mapping, Sequence

SCHEMA = "ARC3_SAGE_ABLATION_V1"
AUTHORITY = {
    "official_game_action": False,
    "kaggle_submission": False,
    "rules_acceptance": False,
    "leaderboard_score": False,
    "prize_claim": False,
    "payment_claim": False,
    "revenue_claim": False,
}


class AblationKind(str, Enum):
    ANIMATION = "FULL_ANIMATION_VS_SETTLED"
    INFO_GAIN = "INFO_GAIN_VS_RANDOM"
    COORDINATE = "COORDINATE_REDUCTION_VS_SUPERSET"
    TRANSFER = "CROSS_LEVEL_TRANSFER_VS_COLD_START"


@dataclass(frozen=True)
class ArmConfig:
    name: str
    treatment: bool
    retain_intermediate_frames: bool = True
    probe_policy: str = "INFO_GAIN"
    coordinate_policy: str = "REDUCED"
    transfer_policy: str = "TRANSFER"

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "treatment": self.treatment,
            "retain_intermediate_frames": self.retain_intermediate_frames,
            "probe_policy": self.probe_policy,
            "coordinate_policy": self.coordinate_policy,
            "transfer_policy": self.transfer_policy,
        }


@dataclass(frozen=True)
class TrialRow:
    experiment_id: str
    seed: int
    arm: str
    success: bool
    terminal: str
    real_actions: int
    simulated_expansions: int
    invalid_actions: int
    repeated_actions: int
    evidence_bits: int
    transfer_reuse: int
    abstentions: int
    budget_exhausted: bool
    trace_digest: str

    def as_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "seed": self.seed,
            "arm": self.arm,
            "success": self.success,
            "terminal": self.terminal,
            "real_actions": self.real_actions,
            "simulated_expansions": self.simulated_expansions,
            "invalid_actions": self.invalid_actions,
            "repeated_actions": self.repeated_actions,
            "evidence_bits": self.evidence_bits,
            "transfer_reuse": self.transfer_reuse,
            "abstentions": self.abstentions,
            "budget_exhausted": self.budget_exhausted,
            "trace_digest": self.trace_digest,
        }


@dataclass(frozen=True)
class ExperimentReceipt:
    document: dict

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.document)

    @property
    def digest(self) -> str:
        return sha256(self.canonical_bytes())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _validate_arm(arm: ArmConfig) -> None:
    if not arm.name or len(arm.name) > 64:
        raise ValueError("invalid arm name")
    if arm.probe_policy not in {"INFO_GAIN", "RANDOM"}:
        raise ValueError("invalid probe policy")
    if arm.coordinate_policy not in {"REDUCED", "SUPERSET"}:
        raise ValueError("invalid coordinate policy")
    if arm.transfer_policy not in {"TRANSFER", "COLD_START"}:
        raise ValueError("invalid transfer policy")


def validate_trial(row: TrialRow) -> None:
    if not row.experiment_id or len(row.experiment_id) > 96:
        raise ValueError("invalid experiment id")
    if type(row.seed) is not int or row.seed < 0 or row.seed > 2**31 - 1:
        raise ValueError("invalid seed")
    if not row.arm or len(row.arm) > 64:
        raise ValueError("invalid arm")
    if type(row.success) is not bool or type(row.budget_exhausted) is not bool:
        raise ValueError("invalid boolean")
    if row.terminal not in {"WIN", "LOSS", "BUDGET", "ABSTAIN"}:
        raise ValueError("invalid terminal")
    for name in (
        "real_actions", "simulated_expansions", "invalid_actions", "repeated_actions",
        "evidence_bits", "transfer_reuse", "abstentions",
    ):
        value = getattr(row, name)
        if type(value) is not int or value < 0 or value > 10**9:
            raise ValueError(f"invalid {name}")
    if row.invalid_actions > row.real_actions or row.repeated_actions > row.real_actions:
        raise ValueError("action subtype exceeds real actions")
    if row.success != (row.terminal == "WIN"):
        raise ValueError("success/terminal mismatch")
    if row.budget_exhausted != (row.terminal == "BUDGET"):
        raise ValueError("budget mismatch")
    if not _valid_digest(row.trace_digest):
        raise ValueError("invalid trace digest")


def _paired(rows: Sequence[TrialRow], control: str, treatment: str) -> list[tuple[TrialRow, TrialRow]]:
    by_key: dict[tuple[str, int, str], TrialRow] = {}
    for row in rows:
        validate_trial(row)
        key = (row.experiment_id, row.seed, row.arm)
        if key in by_key:
            if by_key[key] != row:
                raise ValueError("changed trial identity")
            raise ValueError("duplicate trial identity")
        by_key[key] = row
    pairs: list[tuple[TrialRow, TrialRow]] = []
    experiments = sorted({(r.experiment_id, r.seed) for r in rows})
    for exp, seed in experiments:
        c = by_key.get((exp, seed, control))
        t = by_key.get((exp, seed, treatment))
        if c is None or t is None:
            raise ValueError("missing paired arm")
        pairs.append((c, t))
    if len(pairs) * 2 != len(rows):
        raise ValueError("unexpected arm")
    if not pairs:
        raise ValueError("no pairs")
    return pairs


def _bp(successes: int, total: int) -> int:
    return (successes * 10000 + total // 2) // total


def _quantile_int(values: Sequence[int], numerator: int, denominator: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = ((len(ordered) - 1) * numerator) // denominator
    return ordered[idx]


def _bootstrap_mean_interval(deltas: Sequence[int], seed: int, samples: int = 2000) -> tuple[int, int]:
    if not deltas:
        return (0, 0)
    rng = random.Random(seed)
    n = len(deltas)
    means_milli: list[int] = []
    for _ in range(samples):
        total = sum(deltas[rng.randrange(n)] for _ in range(n))
        means_milli.append((total * 1000) // n)
    return (_quantile_int(means_milli, 25, 1000), _quantile_int(means_milli, 975, 1000))


def _sign_flip_extreme_count(deltas: Sequence[int]) -> tuple[int, int]:
    """Exact for <=18 pairs, deterministic Monte Carlo beyond that; statistic=sum(delta)."""
    observed = abs(sum(deltas))
    n = len(deltas)
    if n <= 18:
        extreme = 0
        total = 1 << n
        for mask in range(total):
            s = 0
            for i, d in enumerate(deltas):
                s += d if (mask >> i) & 1 else -d
            extreme += int(abs(s) >= observed)
        return extreme, total
    rng = random.Random(sha256(canonical_bytes(list(deltas))))
    total = 10000
    extreme = 0
    for _ in range(total):
        s = sum(d if rng.randrange(2) else -d for d in deltas)
        extreme += int(abs(s) >= observed)
    return extreme, total


def aggregate_pairs(pairs: Sequence[tuple[TrialRow, TrialRow]]) -> dict:
    controls = [p[0] for p in pairs]
    treatments = [p[1] for p in pairs]
    action_delta = [t.real_actions - c.real_actions for c, t in pairs]
    invalid_delta = [t.invalid_actions - c.invalid_actions for c, t in pairs]
    evidence_delta = [t.evidence_bits - c.evidence_bits for c, t in pairs]
    transfer_delta = [t.transfer_reuse - c.transfer_reuse for c, t in pairs]
    c_wins = sum(r.success for r in controls)
    t_wins = sum(r.success for r in treatments)
    ci = _bootstrap_mean_interval(action_delta, seed=0xA3A617)
    extreme, permutations = _sign_flip_extreme_count(action_delta)
    return {
        "pair_count": len(pairs),
        "control_success_bp": _bp(c_wins, len(pairs)),
        "treatment_success_bp": _bp(t_wins, len(pairs)),
        "success_delta_bp": _bp(t_wins, len(pairs)) - _bp(c_wins, len(pairs)),
        "control_action_median": int(median([r.real_actions for r in controls])),
        "treatment_action_median": int(median([r.real_actions for r in treatments])),
        "action_delta_sum": sum(action_delta),
        "action_delta_mean_milli": (sum(action_delta) * 1000) // len(action_delta),
        "action_delta_bootstrap95_milli": list(ci),
        "action_delta_signflip_extreme": extreme,
        "action_delta_signflip_total": permutations,
        "invalid_delta_sum": sum(invalid_delta),
        "evidence_delta_sum": sum(evidence_delta),
        "transfer_reuse_delta_sum": sum(transfer_delta),
        "control_simulated_expansions": sum(r.simulated_expansions for r in controls),
        "treatment_simulated_expansions": sum(r.simulated_expansions for r in treatments),
        "control_budget_exhausted": sum(r.budget_exhausted for r in controls),
        "treatment_budget_exhausted": sum(r.budget_exhausted for r in treatments),
    }


def compile_experiment(
    *,
    kind: AblationKind,
    control: ArmConfig,
    treatment: ArmConfig,
    rows: Iterable[TrialRow],
    scenario_manifest_digest: str,
    adapter_digest: str,
    max_real_actions: int,
) -> ExperimentReceipt:
    _validate_arm(control)
    _validate_arm(treatment)
    if control.treatment or not treatment.treatment or control.name == treatment.name:
        raise ValueError("arm role mismatch")
    if not _valid_digest(scenario_manifest_digest) or not _valid_digest(adapter_digest):
        raise ValueError("invalid source digest")
    if type(max_real_actions) is not int or not 1 <= max_real_actions <= 1_000_000:
        raise ValueError("invalid action budget")
    rows = tuple(rows)
    for row in rows:
        if row.real_actions > max_real_actions:
            raise ValueError("real-action budget exceeded")
    pairs = _paired(rows, control.name, treatment.name)
    raw = [r.as_dict() for r in sorted(rows, key=lambda r: (r.experiment_id, r.seed, r.arm))]
    raw_digest = sha256(canonical_bytes(raw))
    aggregate = aggregate_pairs(pairs)
    doc = {
        "schema": SCHEMA,
        "kind": kind.value,
        "control": control.as_dict(),
        "treatment": treatment.as_dict(),
        "scenario_manifest_digest": scenario_manifest_digest,
        "adapter_digest": adapter_digest,
        "max_real_actions": max_real_actions,
        "rows": raw,
        "rows_digest": raw_digest,
        "aggregate": aggregate,
        "authority": AUTHORITY,
    }
    unsigned = dict(doc)
    doc["receipt_digest"] = sha256(canonical_bytes(unsigned))
    return ExperimentReceipt(doc)


def verify_experiment(receipt: Mapping[str, object]) -> ExperimentReceipt:
    if set(receipt) != {
        "schema", "kind", "control", "treatment", "scenario_manifest_digest", "adapter_digest",
        "max_real_actions", "rows", "rows_digest", "aggregate", "authority", "receipt_digest",
    }:
        raise ValueError("receipt shape mismatch")
    if receipt["schema"] != SCHEMA or receipt["authority"] != AUTHORITY:
        raise ValueError("schema/authority mismatch")
    digest = receipt["receipt_digest"]
    if not _valid_digest(digest):
        raise ValueError("invalid receipt digest")
    unsigned = dict(receipt)
    unsigned.pop("receipt_digest")
    if sha256(canonical_bytes(unsigned)) != digest:
        raise ValueError("receipt tamper")
    try:
        kind = AblationKind(receipt["kind"])
    except Exception as exc:
        raise ValueError("invalid kind") from exc
    def arm_from(raw: object) -> ArmConfig:
        if not isinstance(raw, dict) or set(raw) != {
            "name", "treatment", "retain_intermediate_frames", "probe_policy", "coordinate_policy", "transfer_policy"
        }:
            raise ValueError("arm shape")
        return ArmConfig(**raw)
    c = arm_from(receipt["control"])
    t = arm_from(receipt["treatment"])
    raw_rows = receipt["rows"]
    if not isinstance(raw_rows, list):
        raise ValueError("rows shape")
    expected_fields = set(TrialRow.__dataclass_fields__)
    rows: list[TrialRow] = []
    for raw in raw_rows:
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            raise ValueError("row shape")
        rows.append(TrialRow(**raw))
    rebuilt = compile_experiment(
        kind=kind,
        control=c,
        treatment=t,
        rows=rows,
        scenario_manifest_digest=receipt["scenario_manifest_digest"],
        adapter_digest=receipt["adapter_digest"],
        max_real_actions=receipt["max_real_actions"],
    )
    if rebuilt.document != dict(receipt):
        raise ValueError("semantic mismatch")
    return rebuilt
