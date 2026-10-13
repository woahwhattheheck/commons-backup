# SPDX-License-Identifier: Apache-2.0
"""Source-tree entrypoint for the isolated final crop-binding candidate."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
for _source in (HERE, LAB):
    if str(_source) not in sys.path:
        sys.path.insert(0, str(_source))


def _load_control_main():
    path = LAB / "main.py"
    spec = importlib.util.spec_from_file_location(
        "_sol_seal_exact_control_main",
        path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import exact control entrypoint: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_CONTROL_MAIN = _load_control_main()


def _new_instance(root, feature_data):
    """Construct the exact configured runtime with one isolated subclass."""
    from candidate_runtime import FinalCropBindingAgent
    from titan_runtime import Features, load

    features = Features(**feature_data)
    admission = None
    if features.fourth_quadrant:
        source = root / "funded_payback.py"
        if not source.is_file():
            source = root / "../cloud-economic-stress/funded_payback/funded_payback.py"
        module = load("_sol_seal_funded_payback", source, cache=True)
        adapter = load(
            "_sol_seal_funded_payback_runtime",
            root / "funded_payback_runtime.py",
            cache=True,
        )
        admission = adapter.make_admission(module.FundedPaybackAdmission)(
            seconds=features.budget_seconds,
            max_proposals=24,
        )
    return FinalCropBindingAgent(
        features,
        fourth_quadrant_admission=admission,
    )


# Reuse the canonical whole-call deadline, fallback, reset and configuration
# handling. Only construction is replaced inside this candidate process.
_CONTROL_MAIN._new_instance = _new_instance


def agent(observation, configuration=None):
    return _CONTROL_MAIN.agent(observation, configuration)
