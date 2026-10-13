# SPDX-License-Identifier: Apache-2.0
"""State-conditioned safe-own objective overlay for TITAN's SELL optimizer.

The incumbent optimizes ``own_value - rival_receipts``.  The fixed own-value
experiment optimizes ``own_value``.  This overlay evaluates both objectives on
exactly the same canonical candidate family and returns the own-value result
only when exact incumbent receipt math proves, in every modeled scenario, that
it:

* strictly improves TITAN's own value over both the authored reference and the
  incumbent-selected plan; and
* remains non-regressive in true relative value versus the authored reference.

All other calls return the first incumbent result object unchanged.  The
canonical source file is never rewritten.  ``MarketPath.score`` is contextually
reweighted only during the isolated second optimizer pass.
"""
from __future__ import annotations

import copy
from contextvars import ContextVar
from functools import wraps
import hashlib
import importlib
import inspect
import math
from numbers import Real
from pathlib import Path
from typing import Any, Mapping, Sequence

VERSION = "titan-v3-state-conditioned-safe-own-v1"
EXPECTED_SELECTED_SELL_CORE_BLOB = "f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3"
EXPECTED_SCORE_SIGNATURE = "(self, plan, quantity, rival, alignment, terminal=False)"
EXPECTED_OPTIMIZE_SIGNATURE = (
    "(*, item, quantity, inventory, params, shops, config, now, dates, "
    "reference, rival_quantity, minimum_now=0, capacity_ok=None, last=718)"
)
EXPECTED_SCORE_NEEDLES = (
    "def score(self, plan, quantity, rival, alignment, terminal=False):",
    "return own_cash+carry-other_cash, own_cash,other_cash,remaining",
)
EXPECTED_OPTIMIZE_NEEDLES = (
    "baseline=[model.score(reference,quantity,r,a,end==last) for _,r,a in scenarios]",
    "first_score=model.score(plan,quantity,0,'paired',end==last)",
    "'forced_feasibility':forced",
)

_SCORE_TAG = "__titan_safe_own_score_version__"
_SCORE_ORIGINAL_TAG = "__titan_safe_own_score_original__"
_OPTIMIZE_TAG = "__titan_safe_own_optimize_version__"
_OPTIMIZE_ORIGINAL_TAG = "__titan_safe_own_optimize_original__"
_WEIGHT: ContextVar[float] = ContextVar("titan_safe_own_rival_weight", default=1.0)
_DEPTH: ContextVar[int] = ContextVar("titan_safe_own_optimizer_depth", default=0)


class ObjectiveBindingError(RuntimeError):
    """The overlay cannot prove attachment to the reviewed optimizer seam."""


class ObjectiveScoreError(RuntimeError):
    """A score or optimizer result violated the reviewed contract."""


def _git_blob_sha1(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ObjectiveBindingError(f"cannot read selected_sell_core.py: {exc}") from exc
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def _finite_real(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ObjectiveScoreError(f"{field} must be a finite real number")
    result = float(value)
    if not math.isfinite(result):
        raise ObjectiveScoreError(f"{field} must be a finite real number")
    return result


def _score_fields(score: Any, label: str) -> tuple[float, float, float, Any]:
    if not isinstance(score, tuple) or len(score) != 4:
        raise ObjectiveScoreError(f"{label} must be an exact four-tuple")
    relative = _finite_real(score[0], f"{label}.relative_value")
    own_cash = _finite_real(score[1], f"{label}.own_cash")
    rival_cash = _finite_real(score[2], f"{label}.rival_cash")
    return relative, own_cash, rival_cash, score[3]


def own_value_tuple(score: Any) -> tuple[Any, Any, Any, Any]:
    """Change only tuple element zero from relative value to TITAN own value."""
    relative, own_cash, rival_cash, remaining = _score_fields(score, "score")
    own_value = relative + rival_cash
    tolerance = 1e-9 * max(1.0, abs(own_value), abs(own_cash))
    if own_value + tolerance < own_cash:
        raise ObjectiveScoreError(
            "recovered own value is below realized own cash; continuation is invalid"
        )
    return own_value, score[1], score[2], remaining


def _canonical_plan(value: Any, label: str) -> tuple[tuple[int, int], ...]:
    if not isinstance(value, (tuple, list)):
        raise ObjectiveScoreError(f"{label} must be a list or tuple")
    result: list[tuple[int, int]] = []
    for index, row in enumerate(value):
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            raise ObjectiveScoreError(f"{label}[{index}] must be a two-field row")
        step, quantity = row
        if type(step) is not int or type(quantity) is not int or quantity < 0:
            raise ObjectiveScoreError(
                f"{label}[{index}] must contain an integer step and nonnegative quantity"
            )
        result.append((step, quantity))
    if len({step for step, _ in result}) != len(result):
        raise ObjectiveScoreError(f"{label} contains duplicate steps")
    return tuple(result)


def _strict_rule(config: Any) -> bool:
    if not isinstance(config, Mapping):
        return True
    return str(config.get("sellAcceptanceRule", "strict")).strip().lower() == "strict"


def _scenario_definitions(
    *, now: int, end: int, rival_quantity: Any
) -> tuple[tuple[str, Any, str], ...]:
    scenarios: list[tuple[str, Any, str]] = [
        ("no_rival", 0, "paired"),
        ("observed_paired", rival_quantity, "paired"),
        ("observed_later_order", rival_quantity, "after"),
    ]
    if end > now:
        scenarios.append(("observed_next_turn", ((now + 1, rival_quantity),), "paired"))
    if end > now + 2:
        scenarios.append(
            ("observed_before_delayed_batch", ((end - 1, rival_quantity),), "paired")
        )
    return tuple(scenarios)


def _evaluate_plan(
    *,
    module: Any,
    original_score: Any,
    arguments: Mapping[str, Any],
    plan: tuple[tuple[int, int], ...],
) -> dict[str, dict[str, float]]:
    dates = arguments["dates"]
    if not isinstance(dates, Sequence) or isinstance(dates, (str, bytes)) or not dates:
        raise ObjectiveScoreError("dates must be a nonempty sequence")
    now = arguments["now"]
    end = dates[-1]
    if type(now) is not int or type(end) is not int:
        raise ObjectiveScoreError("now and dates[-1] must be integers")
    model = module.MarketPath(
        arguments["item"],
        arguments["inventory"],
        arguments["params"],
        arguments["shops"],
        arguments["config"],
        now,
        end,
    )
    result: dict[str, dict[str, float]] = {}
    for name, rival, alignment in _scenario_definitions(
        now=now, end=end, rival_quantity=arguments["rival_quantity"]
    ):
        raw = original_score(
            model,
            plan,
            arguments["quantity"],
            rival,
            alignment,
            end == arguments["last"],
        )
        relative, own_cash, rival_cash, _remaining = _score_fields(raw, name)
        result[name] = {
            "relative_value": relative,
            "own_value": relative + rival_cash,
            "own_receipts": own_cash,
            "rival_receipts": rival_cash,
        }
    return result


def _result_parts(result: Any, label: str) -> tuple[tuple[tuple[int, int], ...], dict[str, Any]]:
    if not isinstance(result, tuple) or len(result) != 2:
        raise ObjectiveScoreError(f"{label} optimizer result must be a two-tuple")
    plan = _canonical_plan(result[0], f"{label}.plan")
    info = result[1]
    if not isinstance(info, dict):
        raise ObjectiveScoreError(f"{label}.info must be a dict")
    return plan, info


def _eligible_info(info: Mapping[str, Any]) -> bool:
    return (
        info.get("acceptance_rule") == "strict"
        and info.get("forced_feasibility") is False
        and info.get("feasible") is True
    )


def _tolerance(*values: float) -> float:
    scale = max((abs(value) for value in values), default=1.0)
    return 1e-9 * max(1.0, scale)


def _admit_candidate(
    *,
    reference: Mapping[str, Mapping[str, float]],
    control: Mapping[str, Mapping[str, float]],
    candidate: Mapping[str, Mapping[str, float]],
) -> tuple[bool, str, dict[str, dict[str, float]]]:
    names = tuple(reference)
    if not names or tuple(control) != names or tuple(candidate) != names:
        raise ObjectiveScoreError("scenario grids differ")
    metrics: dict[str, dict[str, float]] = {}
    for name in names:
        ref = reference[name]
        ctl = control[name]
        cand = candidate[name]
        values = (
            float(ref["own_value"]),
            float(ref["relative_value"]),
            float(ctl["own_value"]),
            float(ctl["relative_value"]),
            float(cand["own_value"]),
            float(cand["relative_value"]),
        )
        if not all(math.isfinite(value) for value in values):
            raise ObjectiveScoreError(f"scenario {name!r} contains non-finite values")
        tolerance = _tolerance(*values)
        row = {
            "own_gain_vs_reference": values[4] - values[0],
            "own_gain_vs_control": values[4] - values[2],
            "relative_gain_vs_reference": values[5] - values[1],
            "relative_gain_vs_control": values[5] - values[3],
        }
        metrics[name] = row
        if row["own_gain_vs_reference"] <= tolerance:
            return False, f"{name}:own_not_strictly_above_reference", metrics
        if row["own_gain_vs_control"] <= tolerance:
            return False, f"{name}:own_not_strictly_above_control", metrics
        if row["relative_gain_vs_reference"] < -tolerance:
            return False, f"{name}:relative_below_reference", metrics
    return True, "safe_own_frontier_dominates", metrics


def _validate_binding(
    module: Any, expected_root: Path | None
) -> tuple[Any, Any, Path, str, str, str]:
    source_path = Path(getattr(module, "__file__", "")).resolve()
    if source_path.name != "selected_sell_core.py":
        raise ObjectiveBindingError(
            f"expected selected_sell_core.py, got {source_path.name or '<missing>'}"
        )
    if expected_root is not None:
        expected_path = Path(expected_root).resolve() / "selected_sell_core.py"
        if source_path != expected_path:
            raise ObjectiveBindingError(
                f"selected_sell_core path mismatch: expected {expected_path}, got {source_path}"
            )
    blob = _git_blob_sha1(source_path)
    if blob != EXPECTED_SELECTED_SELL_CORE_BLOB:
        raise ObjectiveBindingError(
            "selected_sell_core Git blob drift: "
            f"expected {EXPECTED_SELECTED_SELL_CORE_BLOB}, got {blob}"
        )
    market_path = getattr(module, "MarketPath", None)
    score = getattr(market_path, "score", None)
    optimize = getattr(module, "optimize_lot", None)
    if not callable(score) or not callable(optimize):
        raise ObjectiveBindingError("MarketPath.score and optimize_lot must be callable")
    score_signature = str(inspect.signature(score))
    optimize_signature = str(inspect.signature(optimize))
    if score_signature != EXPECTED_SCORE_SIGNATURE:
        raise ObjectiveBindingError(
            f"MarketPath.score signature drift: {score_signature}"
        )
    if optimize_signature != EXPECTED_OPTIMIZE_SIGNATURE:
        raise ObjectiveBindingError(f"optimize_lot signature drift: {optimize_signature}")
    try:
        score_source = inspect.getsource(score)
        optimize_source = inspect.getsource(optimize)
    except (OSError, TypeError) as exc:
        raise ObjectiveBindingError("cannot inspect optimizer source") from exc
    missing_score = [needle for needle in EXPECTED_SCORE_NEEDLES if needle not in score_source]
    missing_optimize = [
        needle for needle in EXPECTED_OPTIMIZE_NEEDLES if needle not in optimize_source
    ]
    if missing_score or missing_optimize:
        raise ObjectiveBindingError(
            f"optimizer source drift: score={missing_score!r}, optimize={missing_optimize!r}"
        )
    return score, optimize, source_path, blob, score_signature, optimize_signature


def install(*, module: Any | None = None, expected_root: Path | None = None) -> dict[str, Any]:
    """Install the safe-own overlay once and return a machine-readable receipt."""
    if module is None:
        module = importlib.import_module("selected_sell_core")
    market_path = getattr(module, "MarketPath", None)
    current_score = getattr(market_path, "score", None)
    current_optimize = getattr(module, "optimize_lot", None)
    score_version = getattr(current_score, _SCORE_TAG, None)
    optimize_version = getattr(current_optimize, _OPTIMIZE_TAG, None)
    if score_version is not None or optimize_version is not None:
        if score_version != VERSION or optimize_version != VERSION:
            raise ObjectiveBindingError(
                f"conflicting objective overlay: score={score_version!r}, optimize={optimize_version!r}"
            )
        receipt = getattr(module, "__titan_safe_own_objective_receipt__", None)
        if not isinstance(receipt, dict):
            raise ObjectiveBindingError("idempotent overlay is missing its receipt")
        return dict(receipt)

    (
        original_score,
        original_optimize,
        source_path,
        blob,
        score_signature,
        optimize_signature,
    ) = _validate_binding(module, expected_root)
    optimize_signature_object = inspect.signature(original_optimize)

    @wraps(original_score)
    def patched_score(self: Any, *args: Any, **kwargs: Any) -> tuple[Any, Any, Any, Any]:
        raw = original_score(self, *args, **kwargs)
        weight = _WEIGHT.get()
        if weight == 1.0:
            return raw
        if weight != 0.0:
            raise ObjectiveScoreError(f"unsupported rival weight {weight!r}")
        return own_value_tuple(raw)

    @wraps(original_optimize)
    def patched_optimize(*args: Any, **kwargs: Any) -> Any:
        if _DEPTH.get() > 0:
            return original_optimize(*args, **kwargs)
        bound = optimize_signature_object.bind(*args, **kwargs)
        bound.apply_defaults()
        arguments = bound.arguments
        depth_token = _DEPTH.set(_DEPTH.get() + 1)
        control: Any = None
        try:
            control = original_optimize(*args, **kwargs)
            if not _strict_rule(arguments.get("config")):
                return control
            try:
                control_plan, control_info = _result_parts(control, "control")
            except ObjectiveScoreError:
                return control
            if not _eligible_info(control_info):
                return control

            weight_token = _WEIGHT.set(0.0)
            try:
                candidate = original_optimize(*args, **kwargs)
            except Exception as exc:  # optional candidate failure must not replace control
                setattr(
                    module,
                    "__titan_safe_own_last_decision__",
                    {"selected": False, "reason": f"candidate_error:{type(exc).__name__}"},
                )
                return control
            finally:
                _WEIGHT.reset(weight_token)

            try:
                candidate_plan, candidate_info = _result_parts(candidate, "candidate")
                if not _eligible_info(candidate_info) or candidate_info.get("accepted") is not True:
                    raise ObjectiveScoreError("candidate was not an accepted strict feasible plan")
                reference_plan = _canonical_plan(arguments["reference"], "reference")
                if candidate_plan == control_plan:
                    raise ObjectiveScoreError("candidate plan equals incumbent plan")
                if candidate_plan == reference_plan:
                    raise ObjectiveScoreError("candidate plan equals authored reference")
                reference_scores = _evaluate_plan(
                    module=module,
                    original_score=original_score,
                    arguments=arguments,
                    plan=reference_plan,
                )
                control_scores = _evaluate_plan(
                    module=module,
                    original_score=original_score,
                    arguments=arguments,
                    plan=control_plan,
                )
                candidate_scores = _evaluate_plan(
                    module=module,
                    original_score=original_score,
                    arguments=arguments,
                    plan=candidate_plan,
                )
                admitted, reason, metrics = _admit_candidate(
                    reference=reference_scores,
                    control=control_scores,
                    candidate=candidate_scores,
                )
            except (ObjectiveScoreError, KeyError, TypeError, ValueError) as exc:
                decision = {
                    "version": VERSION,
                    "selected": False,
                    "reason": f"candidate_invalid:{type(exc).__name__}:{exc}",
                }
                setattr(module, "__titan_safe_own_last_decision__", decision)
                return control

            decision = {
                "version": VERSION,
                "selected": admitted,
                "reason": reason,
                "reference_plan": [list(row) for row in reference_plan],
                "control_plan": [list(row) for row in control_plan],
                "candidate_plan": [list(row) for row in candidate_plan],
                "scenarios": metrics,
                "candidate_objective": "own_value",
                "safety_constraint": "true_relative_value >= authored_reference",
                "own_constraint": "candidate_own_value > control_and_reference",
            }
            setattr(module, "__titan_safe_own_last_decision__", copy.deepcopy(decision))
            if not admitted:
                return control
            selected_info = copy.deepcopy(candidate_info)
            selected_info["safe_own_selector"] = decision
            return candidate_plan, selected_info
        finally:
            _DEPTH.reset(depth_token)

    setattr(patched_score, _SCORE_TAG, VERSION)
    setattr(patched_score, _SCORE_ORIGINAL_TAG, original_score)
    setattr(patched_optimize, _OPTIMIZE_TAG, VERSION)
    setattr(patched_optimize, _OPTIMIZE_ORIGINAL_TAG, original_optimize)
    market_path.score = patched_score
    module.optimize_lot = patched_optimize
    receipt = {
        "version": VERSION,
        "source_path": str(source_path),
        "expected_git_blob": EXPECTED_SELECTED_SELL_CORE_BLOB,
        "actual_git_blob": blob,
        "score_signature": score_signature,
        "optimize_signature": optimize_signature,
        "changed_field": "MarketPath.score[0]",
        "orchestration_field": "selected_sell_core.optimize_lot",
        "incumbent_objective": "own_value - rival_receipts",
        "candidate_objective": "own_value",
        "selection": "candidate iff own dominates control/reference and true relative is nonnegative vs reference in every canonical scenario",
        "candidate_family_changed": False,
        "scenario_model_changed": False,
        "canonical_files_modified": False,
    }
    setattr(module, "__titan_safe_own_objective_receipt__", dict(receipt))
    return receipt
