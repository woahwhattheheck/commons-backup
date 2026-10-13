# SPDX-License-Identifier: Apache-2.0
"""Fail-closed current-native composer for the FERTDEADLINE eligibility repair.

The production idle-fertilizer owner already proves literal idle slack, same-day
round trip, future COLLECT/FEED exclusion, physical stock capacity, and a bound
sale outlet.  This transform changes only the historical extra restriction that
limited eligible fertilizer to an unfed/at-risk animal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_SOURCE_BLOB = "edbc423023479dbe2e78131495334384a87b607f"

OLD = """                if (not isinstance(tile,dict) or 'animal' not in tile
                        or not tile.get('fertilizer_available')
                        or tile.get('fed_today') or tile.get('consecutive_unfed',0)<1
                        or pos in bound[1] or pos in bound[2] or pos in self.reserved):continue
"""

NEW = """                if (not isinstance(tile,dict) or 'animal' not in tile
                        or not tile.get('fertilizer_available')
                        or pos in bound[1] or pos in bound[2] or pos in self.reserved):continue
"""


def git_blob_sha(text: str) -> str:
    data = text.encode("utf-8")
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def compose(source: str) -> str:
    source_blob = git_blob_sha(source)
    if source_blob != EXPECTED_SOURCE_BLOB:
        raise ValueError(
            f"spatial_tempo source drift: expected {EXPECTED_SOURCE_BLOB}, got {source_blob}"
        )
    if source.count(OLD) != 1:
        raise ValueError("expected exactly one idle-fertilizer eligibility block")
    output = source.replace(OLD, NEW)
    if output.count(NEW) != 1 or OLD in output:
        raise AssertionError("eligibility transform did not produce one exact postimage")
    if len(output.splitlines()) != len(source.splitlines()) - 1:
        raise AssertionError("unexpected line-count delta")
    compile(output, "spatial_tempo.py", "exec")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = args.input.read_text(encoding="utf-8")
    output = compose(source)
    args.output.write_text(output, encoding="utf-8")
    print(json.dumps({
        "repair": "FERTDEADLINE",
        "input_git_blob": git_blob_sha(source),
        "output_git_blob": git_blob_sha(output),
        "changed_line_count": 1,
        "production_activation": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
