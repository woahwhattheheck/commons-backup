# SPDX-License-Identifier: Apache-2.0
"""Fail-closed source injector for Wave-4 F46.

The V5 superiority/RAW gate still owns archive remint authorization.  This
module only exposes a deterministic source transformation stacked on the exact
C02 delivery-choice postimage.  It never emits or publishes a candidate.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib

TARGET = "delivery_choice.py"
HELPER = "f46_saleable_quantity_forecast.py"
C02_POSTIMAGE_SHA256 = "f367b527c8570d3f9bdfe5c1062f58fb2b7636f31f035f9a4587bc35a1b292b3"

_ANCHOR = (
    b"        finally:\n"
    b"            for lot in harvested:\n"
    b"                lot['status'] = 'harvest_returned'\n"
    b"        now = int(obs['step'])\n"
)

_PATCH = (
    b"        finally:\n"
    b"            for lot in harvested:\n"
    b"                lot['status'] = 'harvest_returned'\n"
    b"        import f46_saleable_quantity_forecast as f46\n"
    b"        out, f46_report = f46.suppress_dead_sell_suffix(out, post)\n"
    b"        self.report['f46_saleable_quantity_forecast'] = f46_report\n"
    b"        now = int(obs['step'])\n"
)


def digest(raw):
    return hashlib.sha256(bytes(raw)).hexdigest()


def patch_delivery_choice(source):
    """Patch one exact source shape; duplicate/missing anchors fail closed."""
    raw = bytes(source)
    count = raw.count(_ANCHOR)
    if count != 1:
        raise ValueError(f"F46 expected exactly one C02 market anchor; found {count}")
    return raw.replace(_ANCHOR, _PATCH, 1)


def inject(base_files, helper_source):
    """Return candidate members with only delivery_choice + F46 helper changed.

    ``base_files`` is copied. The exact C02 postimage is mandatory so the
    transformation cannot silently apply to a stale or independently modified
    market controller.
    """
    if not isinstance(base_files, dict):
        raise TypeError("base_files must be a member mapping")
    if TARGET not in base_files:
        raise ValueError("F46 requires delivery_choice.py in the candidate base")
    if HELPER in base_files:
        raise ValueError("F46 helper already exists in candidate base")
    if digest(base_files[TARGET]) != C02_POSTIMAGE_SHA256:
        raise ValueError("F46 requires exact C02 delivery_choice.py postimage")

    files = deepcopy(base_files)
    files[TARGET] = patch_delivery_choice(files[TARGET])
    files[HELPER] = bytes(helper_source).replace(b"\r\n", b"\n")
    return files
