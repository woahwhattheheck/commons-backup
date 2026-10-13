#!/usr/bin/env python3
"""Verify the source-frozen four-seed diagnostic result."""
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).parent
EXPECTED = {
    9922029: 85339.0,
    9922030: 108807.0,
    9922031: 135289.0,
    9922032: 79528.0,
}


def main():
    games = []
    for path in sorted(HERE.glob("result-*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            games.extend(json.load(stream)["games"])
    assert len(games) == 8
    assert {game["seed"] for game in games} == set(EXPECTED)
    assert all(game["status"] == "complete" and game["steps"] == 719
               and game["failure"] is None for game in games)
    margins = []
    for game in games:
        seat = game["candidate_seat"]
        assert game["scores"][seat] == EXPECTED[game["seed"]] - 4000
        assert game["scores"][1-seat] == EXPECTED[game["seed"]]
        margins.append(game["scores"][seat] - game["scores"][1-seat])
    source = HERE / "diagnostic_main.py"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == (
        "eadf5dea1b196804b801fb820e821afa146a71b99c4e3c16fa18d23f35286294"
    )
    candidate_actors = [game["actors"][game["candidate_seat"]] for game in games]
    print(json.dumps({
        "games": len(games), "wins": sum(x > 0 for x in margins),
        "ties": sum(x == 0 for x in margins), "losses": sum(x < 0 for x in margins),
        "terminal_delta_each": sorted(set(margins)),
        "max_call_seconds": max(row["max_call_seconds"] for row in candidate_actors),
        "max_rpc_seconds": max(row["max_rpc_seconds"] for row in candidate_actors),
        "peak_rss_kib": max(row["peak_rss_kib"] for row in candidate_actors),
    }, indent=2))


if __name__ == "__main__":
    main()
