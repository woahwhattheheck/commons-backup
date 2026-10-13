"""Bind the public lonespear proposal to the existing complete-queue comparator.

This is a consumer, not a market simulator, probability model, or policy selector.
The caller owns the selected unit action, post-unit state, and rival hypotheses.
"""
from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from typing import Any

from behavior import predict, propose_delayed_wheat_sale

SCHEMA = 'titan.lonespear-queue-response.v1'


def evaluate_wheat_response(compare_queues: Callable[..., dict], mechanics: Any, *,
        observation: Mapping[str, Any], configuration: Mapping[str, Any] | None,
        selected_action: Mapping[str, Any], own_farm: Mapping[str, Any],
        own_private: Mapping[str, Any], market: Mapping[str, Any],
        scenarios: list[dict], retained_wheat: int,
        deadline: float | None = None, max_scenarios: int = 32,
        max_unit_steps: int = 20000, max_orders_budget: int = 128) -> dict[str, Any]:
    """Return a complete conditional comparison, or the intact selected fallback.

    ``observation`` precedes the selected unit phase, as received by the actor.
    ``own_farm``, ``own_private`` and ``market`` are AFTER that already-selected
    unit phase. Every scenario contains a complete correlated post-unit rival
    farm/private/action hypothesis with provenance, in compare_queues' format.
    No input is inferred from the evaluation-only private traces. The function
    calls the existing comparator once at most; it never calls any controller.

    No action is automatically selected, even when all included rows gain cash.
    ``proposal_action`` is exposed only with a complete conditional report; a
    partial/unknown report leaves it None and retains ``fallback_action``.
    Completed partial rows remain diagnostics, with no aggregate bounds/ranking.
    """
    if not isinstance(selected_action, Mapping):
        raise TypeError('selected_action must be a mapping')
    fallback = copy.deepcopy(dict(selected_action))
    result: dict[str, Any] = dict(schema=SCHEMA, status='unknown', reason=None,
        action_selected=False, fallback_action=fallback, proposal_action=None,
        prediction=None, comparison=None,
        interpretation='Current-market comparison conditional on all supplied scenarios; not a future-value or game guarantee.')
    cfg = configuration if configuration is not None else {}
    prediction = predict(observation, cfg)
    result['prediction'] = prediction
    if prediction['status'] != 'known':
        result['reason'] = 'public_model_unknown:' + str(prediction.get('reason'))
        return result
    try:
        if not isinstance(own_private, Mapping) or not isinstance(own_private.get('shed'), Mapping):
            raise ValueError('post_unit_shed_missing')
        proposal = propose_delayed_wheat_sale(fallback, prediction,
            shed_wheat=own_private['shed'].get('WHEAT', 0), retained_wheat=retained_wheat,
            max_orders=cfg.get('maxMarketOrdersPerTurn', 10))
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        result['reason'] = 'proposal_input:' + str(exc)
        return result
    if not proposal['changed']:
        result.update(status='unchanged', reason=proposal['reason'])
        return result
    # The existing comparator owns all market, scenario, and budget execution.
    # Supply the full actions; do not compact PASS slots or replay unit commands.
    comparison = compare_queues(mechanics, step=prediction['step'],
        seat=1-prediction['actor'], own_farm=own_farm, own_private=own_private,
        market=market, baseline_action=fallback, proposed_action=proposal['action'],
        scenarios=scenarios, configuration=cfg, deadline=deadline,
        max_scenarios=max_scenarios, max_unit_steps=max_unit_steps,
        max_orders_budget=max_orders_budget)
    result['comparison'] = comparison
    if comparison.get('status') != 'complete_conditional':
        result['reason'] = 'queue_comparison_unknown:' + str(comparison.get('reason'))
        return result
    result.update(status='complete_conditional', reason='proposal_compared_not_selected',
                  proposal_action=proposal['action'])
    return result
