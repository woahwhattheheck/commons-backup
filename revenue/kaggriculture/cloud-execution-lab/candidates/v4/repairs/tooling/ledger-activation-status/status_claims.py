#!/usr/bin/env python3
"""Token-aware lifecycle status classification for TITAN V4 integration ledgers."""
from __future__ import annotations

import re
from typing import Any


def claims_activation(status: Any) -> bool:
    """Return True only for an unnegated activation/promote/enable status token.

    This is a coordination-claim parser, not gameplay authority.  In particular,
    ``default_off``, ``inactive`` and ``not_runtime_promoted`` are not positive
    activation claims merely because their text contains misleading substrings.
    """
    if not isinstance(status, str):
        return False
    words = re.sub(r"[^a-z0-9]+", "_", status.casefold()).strip("_")
    words = re.sub(
        r"(?:^|_)not_(?:(?:runtime|production)_)?"
        r"(?:promoted|active|enabled|activated)(?=_|$)",
        "_",
        words,
    )
    return bool(
        re.search(r"(?:^|_)(?:promoted|active|enabled|activated)(?:_|$)", words)
    )
