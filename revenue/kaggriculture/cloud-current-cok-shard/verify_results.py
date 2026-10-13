#!/usr/bin/env python3
"""Verify the exact current-package versus COK V10 development shard."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent
EXPECTED = {
    9969001: {0: ((91348, 72316), "80b0a86e1504e6e3376aa8db30dce998342185f5ff9d274fc022437cdcf3a0a8"),
              1: ((72316, 91348), "aeeb4feca021d9de18d251181b832540253dc8b8f06bd5efc82dffd34b6d980e")},
    9969019: {0: ((140100, 127068), "f8a2f0051f4e3b958a85f7687f4f0d78981a305445ba963764a864ba9d0d493b"),
              1: ((127068, 140100), "1c9993518d65e518181c1b393beac4144c03589e581dcd32c16fa6820c2df587")},
}
CANDIDATE = "a4ecdb513b48fa51877fe509597a84dd753dfe71d2d76a406ee3dc51475a9008"
OPPONENT = "f2160afe24ee9a50ef3843d5d94b2f32c3af53620a43b6cbb25c0020c4cd903c"
ENGINE = {
    "kaggriculture.py": "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e",
    "kaggriculture.json": "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867",
    "utils.py": "537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b",
}
LOADER = "cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e"
EVALUATOR = "e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    rows = []
    for seed in sorted(EXPECTED):
        path = ROOT / "raw" / f"current-vs-cok-{seed}.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["seeds"] == [seed]
        assert report["engine_ref"] == "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
        assert report["engine_sha256"] == ENGINE
        assert report["loader_sha256"] == LOADER
        assert report["evaluator_sha256"] == EVALUATOR
        assert report["candidate"]["sha256"] == CANDIDATE
        assert report["opponents"]["cok-v10"]["sha256"] == OPPONENT
        assert len(report["games"]) == 2
        for game in report["games"]:
            seat = int(game["candidate_seat"])
            expected_scores, expected_trace = EXPECTED[seed][seat]
            scores = tuple(int(x) for x in game["scores"])
            assert game["status"] == "complete" and game["failure"] is None
            assert game["steps"] == 719 and game["episode_steps"] == 720
            assert scores == expected_scores
            assert game["trace_sha256"] == expected_trace
            actor = game["actors"][seat]
            assert actor["calls"] == 719
            assert actor["max_call_seconds"] < 1.0
            assert actor["max_rpc_seconds"] < 1.0
            own, rival = scores[seat], scores[1-seat]
            rows.append((seed, seat, own, rival, own-rival, actor))
    assert len(rows) == 4
    assert all(margin > 0 for *_, margin, _ in rows)
    for seed in EXPECTED:
        pair = [row for row in rows if row[0] == seed]
        assert len(pair) == 2
        assert pair[0][2:5] == pair[1][2:5]
    result = json.loads((ROOT / "RESULTS.json").read_text(encoding="utf-8"))
    assert result["candidate"]["archive_sha256"] == "87d7b8bf7c4e9467f4b6b46887abe2eb03735c42453cdbf4f2cac12c5962acc7"
    assert result["development_seeds"] == [9969001, 9969019]
    assert result["game_rows"] == 4 and result["independent_seed_count"] == 2
    assert result["exact_mirrored_seed_pairs"] == 2
    assert result["summary"]["W"] == 4 and result["summary"]["T"] == 0 and result["summary"]["L"] == 0
    assert result["summary"]["candidate_call_count"] == 2876
    assert result["summary"]["mean_own_cash"] == statistics.fmean(row[2] for row in rows) == 115724.0
    assert result["summary"]["mean_rival_cash"] == statistics.fmean(row[3] for row in rows) == 99692.0
    assert result["summary"]["mean_margin"] == statistics.fmean(row[4] for row in rows) == 16032.0
    for name, expected in result["files"].items():
        path = ROOT / name
        assert path.is_file(), name
        assert path.stat().st_size == expected["bytes"], name
        assert digest(path) == expected["sha256"], name
    print(json.dumps({
        "status": "PASS",
        "game_rows": 4,
        "independent_seeds": 2,
        "W_T_L": [4, 0, 0],
        "mean_margin": 16032.0,
        "exact_mirrored_pairs": 2,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
