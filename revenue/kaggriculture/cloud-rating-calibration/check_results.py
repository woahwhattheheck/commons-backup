"""Recompute the compact published result from retained per-game inputs."""

import json
from pathlib import Path

from calibrate import calibrate


ROOT = Path(__file__).resolve().parent
SUMMARY = json.loads((ROOT / "result-summary.json").read_text())


def run(name):
    payload = json.loads((ROOT / name).read_text())
    return calibrate(payload, iterations=100_000, bootstrap_seed=SUMMARY["bootstrap_seed"])


def close(actual, expected, tolerance=1e-12):
    if abs(actual - expected) > tolerance:
        raise AssertionError((actual, expected))


def check():
    arlene_dev = run("input-development.json")
    arlene_held = run("input-held.json")
    frozen_dev = run("input-frozen-sell-development.json")
    frozen_held = run("input-frozen-sell-held.json")
    apex_dev = run("input-apex-development.json")

    for report, key in ((arlene_dev, "development"), (arlene_held, "held")):
        expected = SUMMARY[key]
        assert [report["sample"][k] for k in ("W", "T", "L")] == expected["W_T_L"]
        close(report["fit"]["elo_scale_proxy"], expected["elo_scale_proxy"])
        assert report["fit"]["elo_scale_proxy_95pct_cluster_bootstrap"] == expected["elo_scale_proxy_95pct_cluster_bootstrap"]
        assert report["anchored_score_proxy_sensitivity_band"] == expected["anchored_proxy_sensitivity_band"]

    families = SUMMARY["source_family_outcomes"]
    cases = (
        (arlene_dev, "arlene_development"), (arlene_held, "arlene_held"),
        (frozen_dev, "frozen_sell_development"), (frozen_held, "frozen_sell_held"),
        (apex_dev, "apex_development"),
    )
    for report, key in cases:
        observed = [report["expected_match_outcome"][label]["empirical_probability"] for label in ("W", "T", "L")]
        assert observed == families[key]["empirical_W_T_L_probability"]
    close(frozen_dev["fit"]["opponent_score_odds"], families["frozen_sell_development"]["frozen_sell_score_odds"])
    close(frozen_held["fit"]["opponent_score_odds"], families["frozen_sell_held"]["frozen_sell_score_odds"])
    assert not arlene_dev["rank"]["identified"]
    print("PASS: five exact inputs reproduce result-summary.json")


if __name__ == "__main__":
    check()
