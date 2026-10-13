#!/usr/bin/env python3
"""Synthetic no-network reference demo for the OSS funding route recensus compiler."""

from __future__ import annotations

import tempfile
from pathlib import Path

if __package__:
    from . import recensus
else:
    import recensus


def main() -> int:
    prior = Path("research/oss_sponsor_route_map/route_map.json")
    with tempfile.TemporaryDirectory(prefix="oss-route-recensus-") as td:
        root = Path(td)
        observations = root / "reference-observations.json"
        report = root / "report.json"
        recensus.make_reference_observations(prior, observations)
        prior_raw, prior_data = recensus._read(prior, "prior")
        obs_raw, obs_data = recensus._read(observations, "observations")
        compiled = recensus.compile_report(prior_raw, prior_data, obs_raw, obs_data)
        recensus._write_exclusive(report, recensus._canon(compiled))
        verified = recensus.verify_report(prior, observations, report)
        print("REFERENCE_DEMO " f"routes={verified['summary']['route_count']} " f"counts={verified['summary']['outcome_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
