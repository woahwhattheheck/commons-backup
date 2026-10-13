"""ChartTrace Workbench package marker.

This module is integrator-owned. It does not import evidence, peer, app,
review, commercial, or fixture code. Those modules land from non-overlapping
lanes and are discovered only after they exist on the tree.

There is no ChartTrace door. The product is a local standalone application.
"""

from __future__ import annotations

from importlib import util
from typing import Mapping


__version__ = "0.1.0-synthetic"
PRODUCT_ID = "charttrace-medical-evidence-review-01"
PACKAGE_VERSION = "charttrace.package.v1"
DOOR_PATH = None
REAL_RECORDS = "HOLD"
NETWORK_DEFAULT = "DENY"
MODEL_DEFAULT = "none"

LANE_MODULES: Mapping[str, tuple[str, ...]] = {
    "A": ("charttrace.core", "charttrace.schema", "charttrace.storage"),
    "B": ("charttrace.peers", "charttrace.prompts", "charttrace.grounding"),
    "C": ("charttrace.app", "charttrace.ui", "charttrace.legal", "charttrace.packaging"),
    "D": ("charttrace.review", "charttrace.export", "charttrace.counsel"),
    "E": ("charttrace.commercial", "charttrace.pricing", "charttrace.affiliates"),
    "F": ("charttrace.fixtures", "charttrace.assurance"),
}


def available_lane_modules() -> dict[str, dict[str, bool]]:
    """Report which owned lane modules are importable on this tree."""

    report: dict[str, dict[str, bool]] = {}
    for lane, modules in LANE_MODULES.items():
        report[lane] = {name: util.find_spec(name) is not None for name in modules}
    return report


def door_path() -> None:
    """ChartTrace has no GitHub Pages / static HTML door."""

    return DOOR_PATH
