#!/usr/bin/env python3
"""Apply an optional critical-rank scheduling delta; never overwrite source/output.

The unchanged original solver remains the default; FLEET_CRITICAL_BANDS=1 enables
expansion. This tool makes no network requests and launches no solver/checker.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

PATCHES = (
 ('#include "rapidjson/istreamwrapper.h"', '#include "rapidjson/istreamwrapper.h"\n#include "critical_bands.hpp"'),
 ('''        int stalled = 0;
        // A resumed incumbent''', '''        int stalled = 0;
        const bool expandCritical = setting("FLEET_CRITICAL_BANDS", 0) != 0;
        const double requestedCap = setting("FLEET_CRITICAL_MAX_RANK", 0);
        if (std::floor(requestedCap) != requestedCap)
            throw std::runtime_error("FLEET_CRITICAL_MAX_RANK must be an integer");
        const int rankCap = expandCritical ? static_cast<int>(std::min<double>(loads.size(), requestedCap)) : 0;
        trace_rank::CriticalBands criticalBands(static_cast<int>(loads.size()), expandCritical, rankCap);
        long long criticalRounds = 0;
        const char* criticalExit = "round_limit";
        // A resumed incumbent'''),
 ('''            int count = std::min<int>(32, static_cast<int>(critical.size()));''',
  '''            int count = criticalBands.sort_count();'''),
 ('''            int position = critical[stalled % count], t = position / m, e = position % m;''',
  '''            int position = critical[criticalBands.rank(stalled)], t = position / m, e = position % m;
            ++criticalRounds;
            const long long criticalAttemptStart = attempted;'''),
 ('''            if (adaptive && stalled >= 64) break;''',
  '''            if (criticalBands.record(attempted - criticalAttemptStart, accepted - oldAccepted, adaptive, stalled)) {
                criticalExit = expandCritical ? "rank_bands_exhausted" : "original_stall";
                break;
            }'''),
 ('''        writeSolution();
        statistics();''',
  '''        writeSolution();
        statistics();
        if (interrupted) criticalExit = "signal";
        else if (elapsed() >= seconds) criticalExit = "deadline";
        criticalBands.write(std::getenv("FLEET_BAND_STATS"), criticalExit, criticalRounds);'''),
)

def transform(source: str) -> str:
    """Each anchor must match once. All other source bytes remain unchanged."""
    output = source
    for before, after in PATCHES:
        if output.count(before) != 1:
            raise ValueError(f"Expected exactly one original source anchor: {before[:80]!r}")
        output = output.replace(before, after, 1)
    return output

def build(base: Path, output: Path) -> dict:
    raw = base.read_bytes()
    generated = transform(raw.decode('utf-8')).encode('utf-8')
    header = Path(__file__).with_name('critical_bands.hpp').read_bytes()
    # Refuse pre-existing targets; validation precedes directory creation.
    output.mkdir(parents=True, exist_ok=False)
    try:
        (output/'main.cpp').write_bytes(generated)
        (output/'critical_bands.hpp').write_bytes(header)
        record = {'schema':'roadef.critical-bands-build.v1', 'baseline_sha256':hashlib.sha256(raw).hexdigest(),
                  'generated_sha256':hashlib.sha256(generated).hexdigest(),
                  'header_sha256':hashlib.sha256(header).hexdigest(), 'default_enabled':False,
                  'source_regions_changed':['include','run'], 'solver_or_checker_runs':0}
        (output/'SOURCE.json').write_text(json.dumps(record, indent=2)+'\n')
        return record
    except BaseException:
        shutil.rmtree(output)
        raise

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(build(args.base, args.output), sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
