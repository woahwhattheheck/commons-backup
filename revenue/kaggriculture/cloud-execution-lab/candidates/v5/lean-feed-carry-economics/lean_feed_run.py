from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from lean_feed_core import (
    ALLOWED_CASH_USE,
    ARM_CURRENT,
    ARM_MIN,
    ARMS,
    CURRENT_POLICY,
    SEATS,
    SPLITS,
    _int_map,
    _is_int,
    _number,
    _require,
    compute_reserve_oracle,
    sha256_json,
)


@dataclass(frozen=True)
class Identity:
    run_id: str
    split: str
    arm: str
    opponent: str
    seed: int
    seat: int
    pair_id: str


@dataclass(frozen=True)
class RunMetrics:
    identity: Identity
    windows: int
    reachable_excess_windows: int
    activations: int
    units_removed: float
    cash_liberated: float
    downstream_cash_used: float
    obligation_failures: int
    productivity_loss: float
    survival_loss: float
    own: float
    rival: float
    margin: float
    outcome: str
    evidence_sha256: str

    def row(self) -> dict[str, Any]:
        return {
            **self.identity.__dict__,
            **{key: value for key, value in self.__dict__.items() if key != "identity"},
        }


def _identity(run: Mapping[str, Any]) -> Identity:
    for key in ("run_id", "split", "arm", "opponent", "seed", "seat", "pair_id"):
        _require(key in run, f"run missing {key}")
    _require(isinstance(run["run_id"], str) and run["run_id"], "run_id invalid")
    _require(run["split"] in SPLITS, "split invalid")
    _require(run["arm"] in ARMS, "arm invalid")
    _require(isinstance(run["opponent"], str) and run["opponent"], "opponent invalid")
    _require(_is_int(run["seed"]), "seed invalid")
    _require(run["seat"] in SEATS, "seat invalid")
    _require(isinstance(run["pair_id"], str) and run["pair_id"], "pair_id invalid")
    return Identity(
        run["run_id"],
        run["split"],
        run["arm"],
        run["opponent"],
        run["seed"],
        run["seat"],
        run["pair_id"],
    )


def _validate_decision(
    window: Mapping[str, Any], identity: Identity, oracle: Mapping[str, Any]
) -> tuple[float, float, float, int, float, float, int]:
    decision = window.get("decision")
    _require(isinstance(decision, Mapping), f"decision missing in {identity.run_id}")
    _require(decision.get("authoritative") is True, "decision must be authoritative")
    _require(
        decision.get("source") == "instrumented_runtime",
        "decision source must be instrumented_runtime",
    )
    _require(
        decision.get("oracle_sha256") == oracle["oracle_sha256"],
        "decision oracle digest mismatch",
    )
    decision_step = decision.get("step")
    _require(_is_int(decision_step), "decision step must be an integer")
    expected = oracle["arms"][identity.arm]["executable"]
    actual = _int_map(
        decision.get("executable_purchase"), "executable_purchase", CURRENT_POLICY
    )
    _require(actual == expected, f"decision differs from {identity.arm} oracle")

    reachable = int(bool(oracle["reachable_excess"]))
    units_removed = 0.0
    liberated = 0.0
    used = 0.0
    if identity.arm == ARM_MIN and oracle["reachable_excess"]:
        _require(
            decision.get("candidate_active") is True,
            "reachable MIN_PROVABLE seam must activate",
        )
        _require(
            decision.get("parent_executable_purchase")
            == oracle["arms"][ARM_CURRENT]["executable"],
            "parent executable purchase mismatch",
        )
        declared_removed = _int_map(
            decision.get("units_removed"), "units_removed", CURRENT_POLICY
        )
        _require(declared_removed == oracle["units_removed"], "units_removed mismatch")
        units_removed = float(sum(declared_removed.values()))
        liberated = _number(decision.get("cash_liberated"), "cash_liberated")
        _require(
            abs(liberated - oracle["cash_tied_in_discretionary_feed"]) <= 1e-9,
            "cash_liberated mismatch",
        )
        liberation_id = decision.get("liberation_id")
        _require(
            isinstance(liberation_id, str) and liberation_id,
            "liberation_id required",
        )
        uses = window.get("cash_uses", [])
        _require(isinstance(uses, list), "cash_uses must be a list")
        for use in uses:
            _require(isinstance(use, Mapping), "cash use invalid")
            _require(
                use.get("authoritative") is True
                and use.get("source") == "runtime_cash_ledger",
                "cash use is not authoritative",
            )
            _require(
                use.get("liberation_id") == liberation_id,
                "cash use liberation link mismatch",
            )
            _require(
                use.get("category") in ALLOWED_CASH_USE,
                "cash use is not a downstream game action",
            )
            amount = _number(use.get("amount"), "cash use amount")
            _require(
                _is_int(use.get("step")) and use["step"] > decision_step,
                "cash use must be later",
            )
            used += amount
        _require(used <= liberated + 1e-9, "downstream use exceeds liberated cash")
    else:
        _require(
            decision.get("candidate_active") is False,
            "non-lean/non-seam decision cannot activate",
        )
        _require(
            not window.get("cash_uses"),
            "non-activation cannot claim liberated-cash use",
        )

    check = window.get("obligation_check")
    _require(isinstance(check, Mapping), "obligation_check required")
    _require(
        check.get("authoritative") is True
        and check.get("source") == "instrumented_runtime",
        "obligation check is not authoritative",
    )
    _require(
        check.get("horizon_step") == oracle["next_boundary_step"],
        "obligation horizon mismatch",
    )
    satisfied = check.get("satisfied") is True
    productivity = _number(check.get("productivity_loss"), "productivity_loss")
    survival = _number(check.get("survival_loss"), "survival_loss")
    failures = 0 if satisfied else 1
    return (
        units_removed,
        liberated,
        used,
        failures,
        productivity,
        survival,
        reachable,
    )


def analyze_run(run: Mapping[str, Any]) -> RunMetrics:
    identity = _identity(run)
    windows = run.get("decision_windows")
    _require(
        isinstance(windows, list) and windows,
        f"decision_windows required in {identity.run_id}",
    )
    seen: set[str] = set()
    removed = liberated = used = productivity = survival = 0.0
    failures = activations = reachable = 0
    for window in windows:
        _require(isinstance(window, Mapping), "decision window invalid")
        window_id = window.get("window_id")
        _require(
            isinstance(window_id, str) and window_id and window_id not in seen,
            "window_id invalid/duplicate",
        )
        seen.add(window_id)
        oracle = compute_reserve_oracle(window.get("snapshot"))
        (
            window_removed,
            window_liberated,
            window_used,
            window_failures,
            window_productivity,
            window_survival,
            window_reachable,
        ) = _validate_decision(window, identity, oracle)
        removed += window_removed
        liberated += window_liberated
        used += window_used
        failures += window_failures
        productivity += window_productivity
        survival += window_survival
        reachable += window_reachable
        if identity.arm == ARM_MIN and window_reachable:
            activations += 1

    result = run.get("result")
    _require(isinstance(result, Mapping), "result required")
    own = _number(result.get("own"), "result.own", nonnegative=False)
    rival = _number(result.get("rival"), "result.rival", nonnegative=False)
    margin = _number(result.get("margin"), "result.margin", nonnegative=False)
    _require(abs(margin - (own - rival)) <= 1e-9, "margin must equal own-rival")
    outcome = result.get("outcome")
    _require(outcome in ("win", "loss", "tie", "ended"), "outcome invalid")
    return RunMetrics(
        identity,
        len(windows),
        reachable,
        activations,
        removed,
        liberated,
        used,
        failures,
        productivity,
        survival,
        own,
        rival,
        margin,
        outcome,
        sha256_json(windows),
    )
