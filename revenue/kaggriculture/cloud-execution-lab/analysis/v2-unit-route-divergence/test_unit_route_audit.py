#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Synthetic fail-closed contracts for the submitted V2 unit-route audit."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from audit_common import AuditError, canonical_json, sha256_bytes
from audit_report import build_report
from unit_route_audit import main, write_json_atomic

AGENT = "Bryce Muhlnickel"
OPPONENT = "Apa"


def _gzip_bytes(payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as handle:
        handle.write(payload)
    return buffer.getvalue()


def _write_gzip(path: Path, root: dict) -> str:
    payload = json.dumps(root, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    data = _gzip_bytes(payload)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _farm(*, money: float = 10, hires_today: int = 0, farmer=(0, 0), hands=None):
    return {
        "money": money,
        "hires_today": hires_today,
        "farmer": [farmer[0], farmer[1]],
        "hands": [[x, y] for x, y in (hands or [])],
        "tiles": [[0, 0], [0, 0]],
        "unlocked_quadrants": [],
    }


def _private(n_actors: int):
    return {
        "inventories": [{} for _ in range(n_actors)],
        "seeds": {},
        "shed": {},
    }


def _observation(*, step: int, turns_per_day: int, seat: int, farm: dict, n_actors: int):
    other = _farm(money=0.0, farmer=(1, 1), hands=[])
    farms = [other, farm] if seat == 1 else [farm, other]
    return {
        "player": seat,
        "day": step // turns_per_day,
        "hour": step % turns_per_day,
        "farms": farms,
        "private": _private(n_actors),
        "market": [],
        "town": {},
    }


def _action(*, n_hands: int = 0, market=None, farmer=None, hands=None):
    return {
        "farmer": farmer or ["WAIT"],
        "hands": hands if hands is not None else [["WAIT"] for _ in range(n_hands)],
        "market": list(market or []),
    }


def _frame(*, step: int, turns_per_day: int, seat: int, farm: dict, n_actors: int, action: dict):
    row = {
        "action": action,
        "observation": _observation(
            step=step, turns_per_day=turns_per_day, seat=seat, farm=farm, n_actors=n_actors
        ),
        "reward": 0,
        "info": {},
        "status": "ACTIVE",
    }
    other = {
        "action": _action(),
        "observation": _observation(
            step=step,
            turns_per_day=turns_per_day,
            seat=1 - seat,
            farm=_farm(money=0.0, farmer=(1, 1), hands=[]),
            n_actors=1,
        ),
        "reward": 0,
        "info": {},
        "status": "ACTIVE",
    }
    return [other, row] if seat == 1 else [row, other]


def valid_root(
    *,
    episode_id: int = 101,
    seed: int = 7,
    seat: int = 1,
    opponent: str = OPPONENT,
    agent: str = AGENT,
    episode_steps: int = 3,
    turns_per_day: int = 3,
    max_market_orders: int = 10,
    reward: float = 1.0,
    rival_reward: float = 0.0,
    hire_at: int = 1,
    hire_requested: int = 1,
    hire_completed: int = 1,
    later_hand_commands: int | None = None,
) -> dict:
    """Build a tiny valid hosted replay with one same-day HIRE orientation witness."""
    teams = [opponent, agent] if seat == 1 else [agent, opponent]
    steps = []
    hands = []
    money = 6.0
    for step in range(episode_steps):
        market = []
        n_input = len(hands)
        if step == hire_at:
            market = [["HIRE"] for _ in range(hire_requested)]
            hands = list(hands) + [(i + 1, 0) for i in range(hire_completed)]
            money = money - hire_completed
        planned = n_input if later_hand_commands is None or step <= hire_at else later_hand_commands
        farm = _farm(
            money=money,
            hires_today=len(hands) if step >= hire_at else 0,
            farmer=(0, 0),
            hands=hands,
        )
        steps.append(
            _frame(
                step=step,
                turns_per_day=turns_per_day,
                seat=seat,
                farm=farm,
                n_actors=1 + len(hands),
                action=_action(n_hands=planned, market=market),
            )
        )
    rewards = [rival_reward, reward] if seat == 1 else [reward, rival_reward]
    return {
        "info": {"EpisodeId": episode_id, "seed": seed, "TeamNames": teams},
        "configuration": {
            "episodeSteps": episode_steps,
            "turnsPerDay": turns_per_day,
            "maxMarketOrdersPerTurn": max_market_orders,
        },
        "rewards": rewards,
        "steps": steps,
    }


def write_replay(directory: Path, name: str, root: dict) -> dict:
    digest = _write_gzip(directory / name, root)
    info = root["info"]
    teams = info["TeamNames"]
    seat = teams.index(AGENT)
    return {
        "file": name,
        "episode_id": info["EpisodeId"],
        "seed": info["seed"],
        "seat": seat,
        "opponent": teams[1 - seat],
        "gzip_sha256": digest,
    }


def write_manifest(directory: Path, rows: list[dict], *, steps: int = 3) -> Path:
    manifest = {
        "schema_version": 1,
        "agent_name": AGENT,
        "expected_episode_steps": steps,
        "replays": rows,
    }
    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def two_replays(directory: Path, **kwargs) -> tuple[Path, list[dict]]:
    left = write_replay(directory, "left.json.gz", valid_root(episode_id=101, seed=7, **kwargs))
    right = write_replay(
        directory,
        "right.json.gz",
        valid_root(episode_id=202, seed=8, opponent="Gappy", reward=2.0, **kwargs),
    )
    steps = kwargs.get("episode_steps", 3)
    return write_manifest(directory, [left, right], steps=steps), [left, right]


class UnitRouteAuditTests(unittest.TestCase):
    def test_duplicate_json_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            path = directory / "dup.json.gz"
            root = valid_root()
            text = json.dumps(root, separators=(",", ":"))
            text = text[:-1] + ',"info":null}'
            path.write_bytes(_gzip_bytes(text.encode("utf-8")))
            row = {
                "file": path.name,
                "episode_id": 101,
                "seed": 7,
                "seat": 1,
                "opponent": OPPONENT,
                "gzip_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            other = write_replay(directory, "ok.json.gz", valid_root(episode_id=202, seed=8))
            manifest = write_manifest(directory, [row, other])
            with self.assertRaisesRegex(AuditError, "duplicate JSON key"):
                build_report(manifest, directory)

    def test_bool_quantity_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            root = valid_root()
            root["steps"][0][1]["observation"]["farms"][1]["hires_today"] = True
            row = write_replay(directory, "bool.json.gz", root)
            other = write_replay(directory, "ok.json.gz", valid_root(episode_id=202, seed=8))
            manifest = write_manifest(directory, [row, other])
            with self.assertRaisesRegex(AuditError, "must be an integer"):
                build_report(manifest, directory)

    def test_non_square_board_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            root = valid_root()
            root["steps"][0][1]["observation"]["farms"][1]["tiles"] = [[0, 0], [0]]
            row = write_replay(directory, "board.json.gz", root)
            other = write_replay(directory, "ok.json.gz", valid_root(episode_id=202, seed=8))
            manifest = write_manifest(directory, [row, other])
            with self.assertRaisesRegex(AuditError, "tile board must be square"):
                build_report(manifest, directory)

    def test_inventory_cardinality_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            root = valid_root()
            root["steps"][1][1]["observation"]["private"]["inventories"] = [{}]
            row = write_replay(directory, "inv.json.gz", root)
            other = write_replay(directory, "ok.json.gz", valid_root(episode_id=202, seed=8))
            manifest = write_manifest(directory, [row, other])
            with self.assertRaisesRegex(AuditError, "inventories="):
                build_report(manifest, directory)

    def test_empty_unit_action_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            root = valid_root()
            root["steps"][0][1]["action"]["farmer"] = []
            row = write_replay(directory, "empty.json.gz", root)
            other = write_replay(directory, "ok.json.gz", valid_root(episode_id=202, seed=8))
            manifest = write_manifest(directory, [row, other])
            with self.assertRaisesRegex(AuditError, "unit action cannot be empty"):
                build_report(manifest, directory)

    def test_market_sell_arity_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            root = valid_root()
            root["steps"][0][1]["action"]["market"] = [["SELL", "WHEAT"]]
            row = write_replay(directory, "sell.json.gz", root)
            other = write_replay(directory, "ok.json.gz", valid_root(episode_id=202, seed=8))
            manifest = write_manifest(directory, [row, other])
            with self.assertRaisesRegex(AuditError, "SELL must have exactly three fields"):
                build_report(manifest, directory)

    def test_copied_replay_bytes_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            first = write_replay(directory, "a.json.gz", valid_root())
            duplicate = dict(first)
            duplicate["file"] = "b.json.gz"
            (directory / "b.json.gz").write_bytes((directory / "a.json.gz").read_bytes())
            manifest = write_manifest(directory, [first, duplicate])
            with self.assertRaisesRegex(AuditError, "duplicate replay bytes"):
                build_report(manifest, directory)

    def test_duplicate_episode_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            left = write_replay(directory, "a.json.gz", valid_root(episode_id=101, seed=7))
            right = write_replay(
                directory, "b.json.gz", valid_root(episode_id=101, seed=8, opponent="Gappy")
            )
            manifest = write_manifest(directory, [left, right])
            with self.assertRaisesRegex(AuditError, "duplicate episode_id"):
                build_report(manifest, directory)

    def test_gzip_sha_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest, rows = two_replays(directory)
            rows[0]["gzip_sha256"] = "0" * 64
            manifest.write_text(
                json.dumps({
                    "schema_version": 1,
                    "agent_name": AGENT,
                    "expected_episode_steps": 3,
                    "replays": rows,
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuditError, "gzip SHA mismatch"):
                build_report(manifest, directory)

    def test_missing_replay_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest, rows = two_replays(directory)
            (directory / rows[0]["file"]).unlink()
            with self.assertRaisesRegex(AuditError, "missing replay"):
                build_report(manifest, directory)

    def test_seat_declaration_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest, rows = two_replays(directory)
            rows[0]["seat"] = 0
            manifest.write_text(
                json.dumps({
                    "schema_version": 1,
                    "agent_name": AGENT,
                    "expected_episode_steps": 3,
                    "replays": rows,
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuditError, "episode/seed/seat declaration mismatch"):
                build_report(manifest, directory)

    def test_opponent_declaration_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest, rows = two_replays(directory)
            rows[0]["opponent"] = "wrong"
            manifest.write_text(
                json.dumps({
                    "schema_version": 1,
                    "agent_name": AGENT,
                    "expected_episode_steps": 3,
                    "replays": rows,
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuditError, "opponent declaration mismatch"):
                build_report(manifest, directory)

    def test_seed_declaration_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest, rows = two_replays(directory)
            rows[0]["seed"] = 999
            manifest.write_text(
                json.dumps({
                    "schema_version": 1,
                    "agent_name": AGENT,
                    "expected_episode_steps": 3,
                    "replays": rows,
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuditError, "episode/seed/seat declaration mismatch"):
                build_report(manifest, directory)

    def test_action_observation_shift_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            root = valid_root(hire_requested=1, hire_completed=2)
            row = write_replay(directory, "shift.json.gz", root)
            other = write_replay(directory, "ok.json.gz", valid_root(episode_id=202, seed=8))
            manifest = write_manifest(directory, [row, other])
            with self.assertRaisesRegex(AuditError, "action/observation alignment is invalid"):
                build_report(manifest, directory)

    def test_hands_decrease_inside_day_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            root = valid_root(hire_completed=1)
            farm = root["steps"][2][1]["observation"]["farms"][1]
            farm["hands"] = []
            root["steps"][2][1]["observation"]["private"]["inventories"] = [{}]
            row = write_replay(directory, "drop.json.gz", root)
            other = write_replay(directory, "ok.json.gz", valid_root(episode_id=202, seed=8))
            manifest = write_manifest(directory, [row, other])
            with self.assertRaisesRegex(AuditError, "hands decreased inside a day"):
                build_report(manifest, directory)

    def test_no_orientation_witness_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            root = valid_root()
            for step in range(3):
                root["steps"][step][1]["action"]["market"] = []
                farm = root["steps"][step][1]["observation"]["farms"][1]
                farm["hands"] = []
                root["steps"][step][1]["observation"]["private"]["inventories"] = [{}]
            row = write_replay(directory, "none.json.gz", root)
            other = write_replay(directory, "ok.json.gz", valid_root(episode_id=202, seed=8))
            manifest = write_manifest(directory, [row, other])
            with self.assertRaisesRegex(AuditError, "no same-day HIRE transition"):
                build_report(manifest, directory)

    def test_incomplete_episode_grid_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            root = valid_root()
            root["steps"] = root["steps"][:2]
            row = write_replay(directory, "short.json.gz", root)
            other = write_replay(directory, "ok.json.gz", valid_root(episode_id=202, seed=8))
            manifest = write_manifest(directory, [row, other])
            with self.assertRaisesRegex(AuditError, "steps=2, expected 3"):
                build_report(manifest, directory)

    def test_hire_count_uses_market_prefix_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            root = valid_root(max_market_orders=1, hire_requested=1, hire_completed=1)
            root["steps"][1][1]["action"]["market"] = [["WAIT"], ["HIRE"]]
            row = write_replay(directory, "prefix.json.gz", root)
            other = write_replay(directory, "ok.json.gz", valid_root(episode_id=202, seed=8))
            manifest = write_manifest(directory, [row, other])
            with self.assertRaisesRegex(AuditError, "only 0 executable HIRE"):
                build_report(manifest, directory)

    def test_cli_writes_report_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest, _ = two_replays(directory)
            output = directory / "report.json"
            code = main(["--manifest", str(manifest), "--replay-dir", str(directory), "--output", str(output)])
            self.assertEqual(code, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["replay_count"], 2)
            payload = {key: value for key, value in report.items() if key != "report_payload_sha256"}
            self.assertEqual(report["report_payload_sha256"], sha256_bytes(canonical_json(payload)))

    def test_cli_returns_audit_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest = write_manifest(directory, [])
            output = directory / "report.json"
            code = main(["--manifest", str(manifest), "--replay-dir", str(directory), "--output", str(output)])
            self.assertEqual(code, 2)
            self.assertFalse(output.exists())

    def test_atomic_write_is_durable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "nested" / "out.json"
            write_json_atomic(path, {"ok": True})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"ok": True})
            leftovers = list(path.parent.glob(".out.json.*"))
            self.assertEqual(leftovers, [])

    def test_atomic_replace_failure_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "out.json"
            with mock.patch("os.replace", side_effect=OSError("busy")):
                with self.assertRaises(OSError):
                    write_json_atomic(path, {"ok": True})
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(raw).glob(".out.json.*")), [])


if __name__ == "__main__":
    unittest.main()
