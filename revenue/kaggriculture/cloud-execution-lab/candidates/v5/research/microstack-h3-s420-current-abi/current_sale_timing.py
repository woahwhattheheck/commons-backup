# SPDX-License-Identifier: Apache-2.0
"""Evidence-only current-ABI H3/S420 source composer for TITAN V5.

This module deliberately reuses the already-landed canonical H3/S420 source
transform instead of defining a second sale-timing theorem.

Arms:
* control: current ``frozen_selected.py`` bytes unchanged;
* h3: current source with only the inherited baseline HORIZON shadowed to 3;
* h3_s420: exact canonical ``compose_current_h3s420.py`` rewrite semantics
  applied to the current pinned ``frozen_selected.py`` postimage.

Canonical S420 semantics are strict: at step >= 420 the entire *new plan
selection* block is skipped. Inherited/base SELL rows and already-planned due
quantities still flow through the untouched materialization tail. There is no
equal-total-only exception and no forced-feasibility bypass.

Production defaults/configuration are never changed by this research helper.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import types
from typing import Any, Callable

BASELINE_HORIZON = 3
SUPPRESS_NEW_PLANS_AFTER = 420

CURRENT_FROZEN_SELECTED_GIT_BLOB = "6a95505388ea1b5eba38bd1f927a2a2bf084490c"
CANONICAL_COMPOSER_GIT_BLOB = "7c5778b4d6d7c47f8feca7e800fc8093267b66f8"
CANONICAL_COMPOSER_RELATIVE = Path(
    "candidates/v4/research/sale-window-engagement/compose_current_h3s420.py"
)

_IMPORT_MARKER = (
    "from selected_sell_core import optimize_lot, joint_plan_metrics, shared_slot_ledger\n"
)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def _plain_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _load_canonical_rewrite(composer_path: Path) -> Callable[[str], str]:
    """Authenticate and load the canonical H3/S420 source rewrite once."""
    data = composer_path.read_bytes()
    actual = git_blob(data)
    if actual != CANONICAL_COMPOSER_GIT_BLOB:
        raise ValueError(
            "canonical H3/S420 composer drift; explicit source review required"
        )
    module = types.ModuleType("_titan_canonical_h3s420")
    module.__file__ = str(composer_path)
    exec(compile(data, str(composer_path), "exec"), module.__dict__)
    rewrite = module.__dict__.get("_rewrite_source")
    if not callable(rewrite):
        raise ValueError("canonical H3/S420 composer lost _rewrite_source")
    return rewrite


def _compose_h3(source: bytes) -> bytes:
    text = source.decode("utf-8")
    if text.count(_IMPORT_MARKER) != 1:
        raise ValueError("selected-sell import marker drift")
    constants = (
        _IMPORT_MARKER
        + "\n# H3 current-ABI experiment; evidence-only and default-off.\n"
        + f"HORIZON = {BASELINE_HORIZON}\n"
    )
    result = text.replace(_IMPORT_MARKER, constants, 1)
    compile(result, "<h3-current-frozen-selected>", "exec")
    return result.encode("utf-8")


def compose_current_frozen(
    source: bytes,
    *,
    arm: str,
    canonical_composer_path: Path,
) -> bytes:
    """Return one source-pinned control/H3/H3+S420 current experiment arm.

    The current source must be the exact reviewed postimage. ``h3_s420`` then
    applies the exact canonical source rewriter by authenticated composer blob,
    so this carrier cannot silently evolve a second S420 interpretation.
    """
    if git_blob(source) != CURRENT_FROZEN_SELECTED_GIT_BLOB:
        raise ValueError("current frozen_selected.py source drift; explicit rebase required")
    if arm == "control":
        return source
    if arm == "h3":
        return _compose_h3(source)
    if arm == "h3_s420":
        rewrite = _load_canonical_rewrite(canonical_composer_path)
        result = rewrite(source.decode("utf-8")).encode("utf-8")
        compile(result, "<h3s420-current-frozen-selected>", "exec")
        return result
    raise ValueError("arm must be one of: control, h3, h3_s420")


def default_canonical_composer_path(lab_root: Path) -> Path:
    """Resolve the one canonical composer from a cloud-execution-lab root."""
    return lab_root / CANONICAL_COMPOSER_RELATIVE


def canonical_semantics_receipt() -> dict[str, Any]:
    """Small immutable receipt for runners and evidence manifests."""
    return {
        "baseline_horizon": BASELINE_HORIZON,
        "suppress_new_plans_after": SUPPRESS_NEW_PLANS_AFTER,
        "canonical_composer_git_blob": CANONICAL_COMPOSER_GIT_BLOB,
        "current_frozen_selected_git_blob": CURRENT_FROZEN_SELECTED_GIT_BLOB,
        "semantics": (
            "all new plan selection suppressed at/after threshold; "
            "inherited/base SELL rows and already-planned due quantities remain materialized"
        ),
    }
