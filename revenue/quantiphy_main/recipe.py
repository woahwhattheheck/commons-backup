"""Recipe selection and frozen-recipe application for QuantiPhy Main."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .common import (
    CATEGORIES, GROUND_TRUTH, MAX_SAFE_INT, SCHEMA, QuantiPhyMainError,
    _hex, _int, _list, _obj, _receipt_index, canonical_sha, category_of, row_key,
    validate_dataset, validate_receipts,
)
from .scoring import (
    _candidate_cost, _ensemble_rows, _grouped_folds, _model_cv,
    _model_prediction_rows, apply_scales, fit_scales, score_rows,
)

def build_recipe(
    dataset_raw: Any,
    receipts_raw: Any,
    *,
    budget_microusd: int,
    fold_count: int = 4,
) -> dict[str, Any]:
    budget_microusd = _int(budget_microusd, "budget_microusd", 0, MAX_SAFE_INT)
    dataset = validate_dataset(dataset_raw, require_truth=True)
    receipts = validate_receipts(receipts_raw, dataset)
    receipts_by_model = _receipt_index(receipts)
    models = sorted(receipts_by_model)
    folds = _grouped_folds(dataset, fold_count)

    candidates: list[dict[str, Any]] = []
    cv_by_model_category: dict[str, dict[str, float]] = {}

    for model in models:
        base = _model_prediction_rows(model, dataset, receipts_by_model)
        if base is None:
            continue
        cost = _candidate_cost([model], None, dataset, receipts_by_model)
        if cost > budget_microusd:
            continue
        cv, cat = _model_cv(model, base, dataset, folds, fold_count)
        cv_by_model_category[model] = cat
        candidates.append({"name": f"model:{model}", "kind": "model", "models": [model], "cv_mra": cv, "cost_microusd": cost, "base_rows": base})

    complete_models = [model for model in models if _model_prediction_rows(model, dataset, receipts_by_model) is not None]
    if len(complete_models) > 1:
        for method in ("median", "geometric_mean", "arithmetic_mean"):
            base = _ensemble_rows(complete_models, method, dataset, receipts_by_model)
            if base is None:
                continue
            cost = _candidate_cost(complete_models, None, dataset, receipts_by_model)
            if cost > budget_microusd:
                continue
            cv, _ = _model_cv(method, base, dataset, folds, fold_count)
            candidates.append({"name": f"ensemble:{method}", "kind": "ensemble", "models": complete_models, "method": method, "cv_mra": cv, "cost_microusd": cost, "base_rows": base})

    # Category router: train/CV-derived per-category best complete model, with no cross-video leakage.
    if len(cv_by_model_category) > 1:
        route: dict[str, str] = {}
        for cat in CATEGORIES:
            route[cat] = max(sorted(cv_by_model_category), key=lambda model: (cv_by_model_category[model][cat], model))
        router_rows: list[dict[str, Any]] = []
        if len(set(route.values())) < 2:
            route = {}
        for row in dataset if route else []:
            model = route[category_of(row)]
            receipt = receipts_by_model[model][row_key(row)]
            if receipt["status"] != "OK":
                router_rows = []
                break
            router_rows.append({**dict(row), "parsed_value": receipt["parsed_value"]})
        if router_rows:
            cost = _candidate_cost([], route, dataset, receipts_by_model)
            if cost <= budget_microusd:
                cv, _ = _model_cv("category_router", router_rows, dataset, folds, fold_count)
                candidates.append({"name": "router:category", "kind": "router", "models": sorted(set(route.values())), "route": route, "cv_mra": cv, "cost_microusd": cost, "base_rows": router_rows})

    if not candidates:
        raise QuantiPhyMainError("no complete candidate fits the budget")
    candidates.sort(key=lambda c: c["name"])
    selected = max(candidates, key=lambda c: (c["cv_mra"], -c["cost_microusd"], -len(c["models"]), c["name"]))
    full_scales = fit_scales(dataset, selected["base_rows"])
    scaled = apply_scales(selected["base_rows"], full_scales)
    full_score = score_rows(dataset, scaled)
    selected_clean = {k: v for k, v in selected.items() if k != "base_rows"}
    recipe = {
        "schema": SCHEMA,
        "dataset_sha256": canonical_sha(dataset),
        "receipts_sha256": canonical_sha(receipts),
        "budget_microusd": budget_microusd,
        "observed_total_cost_microusd": sum(_int(r["cost_microusd"], "cost_microusd") for r in receipts),
        "fold_count": fold_count,
        "fold_policy": "video_id grouped; deterministic category-balancing greedy assignment",
        "selected": selected_clean,
        "category_scales": full_scales,
        "public_validation_mra": full_score["mra_average"],
        "public_validation_mra_by_category": full_score["mra_by_category"],
        "candidates": [
            {k: v for k, v in c.items() if k != "base_rows"}
            for c in candidates
        ],
        "authority": {
            "provider_call_performed": False,
            "paid_spend_authorized": False,
            "competition_submission_authorized": False,
            "hidden_test_accessed": False,
            "prize_or_revenue_claimed": False,
        },
    }
    recipe["recipe_sha256"] = canonical_sha(recipe)
    return recipe


def _verify_recipe_integrity(recipe: Mapping[str, Any]) -> None:
    if recipe.get("schema") != SCHEMA:
        raise QuantiPhyMainError("recipe schema invalid")
    claimed = recipe.get("recipe_sha256")
    _hex(claimed, "recipe.recipe_sha256")
    stripped = dict(recipe)
    stripped.pop("recipe_sha256", None)
    if canonical_sha(stripped) != claimed:
        raise QuantiPhyMainError("recipe self-digest mismatch")


def apply_recipe(dataset_raw: Any, receipts_raw: Any, recipe: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Apply a frozen validation-fitted recipe to a separate inference dataset.

    The recipe stays bound to its fit-time validation evidence, while this function
    accepts a distinct organizer-shaped dataset and separately validated receipts.
    No labels are required or consulted here.
    """
    _verify_recipe_integrity(recipe)
    dataset = validate_dataset(dataset_raw, require_truth=False)
    receipts = validate_receipts(receipts_raw, dataset)
    receipts_by_model = _receipt_index(receipts)
    selected = _obj(recipe.get("selected"), "recipe.selected")
    kind = selected.get("kind")
    if kind == "model":
        models = _list(selected.get("models"), "selected.models", 100)
        base = _model_prediction_rows(models[0], dataset, receipts_by_model) if len(models) == 1 else None
    elif kind == "ensemble":
        models = _list(selected.get("models"), "selected.models", 100)
        base = _ensemble_rows(models, str(selected.get("method")), dataset, receipts_by_model)
    elif kind == "router":
        route = _obj(selected.get("route"), "selected.route")
        base = []
        for row in dataset:
            model = route.get(category_of(row))
            if type(model) is not str:
                raise QuantiPhyMainError("router missing category model")
            receipt = receipts_by_model.get(model, {}).get(row_key(row))
            if receipt is None or receipt["status"] != "OK":
                raise QuantiPhyMainError("router receipt incomplete")
            base.append({**dict(row), "parsed_value": receipt["parsed_value"]})
    else:
        raise QuantiPhyMainError("recipe selected kind invalid")
    if base is None:
        raise QuantiPhyMainError("selected candidate receipts incomplete")
    scales = _obj(recipe.get("category_scales"), "category_scales")
    return apply_scales(base, {str(k): str(v) for k, v in scales.items()})

def _unlabeled_dataset(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in row.items() if k != GROUND_TRUTH} for row in rows]


def _selected_inference_cost(dataset: Sequence[Mapping[str, Any]], receipts: Sequence[Mapping[str, Any]], recipe: Mapping[str, Any]) -> int:
    receipts_by_model = _receipt_index(receipts)
    selected = _obj(recipe.get("selected"), "recipe.selected")
    kind = selected.get("kind")
    if kind == "model":
        models = _list(selected.get("models"), "selected.models", 100)
        if len(models) != 1:
            raise QuantiPhyMainError("model recipe must name exactly one model")
        return _candidate_cost(models, None, dataset, receipts_by_model)
    if kind == "ensemble":
        models = _list(selected.get("models"), "selected.models", 100)
        return _candidate_cost(models, None, dataset, receipts_by_model)
    if kind == "router":
        route = _obj(selected.get("route"), "selected.route")
        return _candidate_cost([], {str(k): str(v) for k, v in route.items()}, dataset, receipts_by_model)
    raise QuantiPhyMainError("recipe selected kind invalid")
