#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure intermediate unit-stage shed occupancy on retained DELVE trajectories.

The input is the existing TITAN DELVE funding-evidence ZIP. This tool verifies the
whole source manifest, replays only recorded actions through the pinned interpreter,
and instruments the interpreter's existing unit-action boundary. It never invokes
a policy and does not choose or modify an action.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from unit_capacity_support import *  # re-export the tested public analysis surface
from unit_capacity_phase import *
from unit_capacity_result import *

HERE = Path(__file__).resolve().parent
SOURCE_FILES = (
    'check_unit_capacity_occurrence.py',
    'unit_capacity_support.py',
    'unit_capacity_phase.py',
    'unit_capacity_result.py',
)


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def analyze(archive_path: Path, expected_archive_sha256: str) -> dict[str, Any]:
    members, source = read_verified_archive(archive_path, expected_archive_sha256)
    replayed = [replay_stream(stream, members) for stream in discover_complete_streams(members)]
    source['analyzer_sources_sha256'] = {
        name: sha256((HERE / name).read_bytes()) for name in SOURCE_FILES
    }
    source['analyzer_sha256'] = source['analyzer_sources_sha256'][SOURCE_FILES[0]]
    source['python'] = sys.version
    return summarize(replayed, source)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--expected-archive-sha256', default=EXPECTED_ARCHIVE_SHA256)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    report = analyze(args.archive, args.expected_archive_sha256)
    atomic_write(args.report, json.dumps(report, indent=2, sort_keys=True).encode() + b'\n')
    print(json.dumps({'schema': report['schema'], 'source': report['source']['archive_sha256'],
                      **report['summary']}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
