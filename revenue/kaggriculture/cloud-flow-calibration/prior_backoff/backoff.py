# SPDX-License-Identifier: MIT
"""Prior-backed marginal event forecasts; not joint scenario probabilities."""
from __future__ import annotations

from collections.abc import Mapping
import math


def probability(value, name, *, strict=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite probability')
    if not (0 < value < 1 if strict else 0 <= value <= 1):
        raise ValueError(f'{name} is outside its probability range')
    return float(value)


def predict_event(forecast: Mapping, *, expert: str = 'model') -> dict:
    """Use ONLY a frozen pre-outcome forecast from CausalWindowEnsemble.

    p = (1-u)*p_expert + u*p_prior. The existing unknown mass u is retained;
    its marginal event rate is modeled with the existing causal prior instead
    of 0.5. A missing expert uses the prior exclusively. No label, stream fill,
    current opponent order or fitted parameter is accepted or inferred here.

    This probability is a regularized single threshold-event prediction. It
    does not replace the original unknown scenarios or assign their order,
    quantity, cross-product dependence or complete-plan feasibility.
    """
    if not isinstance(forecast, Mapping) or not isinstance(expert, str) or not expert:
        raise ValueError('supply a frozen forecast and an expert name')
    try:
        prior = probability(forecast['prior_rate_control'], 'prior', strict=True)
        mass = probability(forecast['unknown_mass'], 'unknown mass')
        if mass == 0:
            raise ValueError('this refinement requires positive prior-backoff mass')
        support = forecast['support']
        if type(support) is not int or support < 0:
            raise ValueError('support must be a nonnegative integer')
        points = forecast['expert_probabilities']
        if not isinstance(points, Mapping):
            raise ValueError('expert probabilities must be a mapping')
        present = expert == 'model' or expert in points
        raw = forecast['model_probability'] if expert == 'model' else points.get(expert)
        # Cold/missing components cannot become invented zero-flow evidence.
        if mass == 1 or not present:
            known, mass = None, 1.0
        else:
            known = probability(raw, 'expert probability')
        lower = 0.0 if known is None else (1.0 - mass) * known
        upper = lower + mass
        p = lower + mass * prior
        return dict(source_ticket=forecast['ticket'], expert=expert,
                    probability=p, source_probability=known, prior_probability=prior,
                    backoff_mass=mass, event_interval=[lower, upper], support=support,
                    interpretation='regularized marginal event forecast; not calibrated joint scenario weights',
                    recommended_alpha=0.0)
    except KeyError as exc:
        raise ValueError(f'missing frozen forecast field: {exc.args[0]}') from exc
