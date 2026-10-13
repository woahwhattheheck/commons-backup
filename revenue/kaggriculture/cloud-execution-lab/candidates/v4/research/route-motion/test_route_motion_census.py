import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("route_motion_census", HERE / "route_motion_census.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def action(farmer=None, market=None):
    return {
        "farmer": farmer or ["PASS"],
        "hands": [],
        "market": market or [],
    }


def standard_spec(board_size=10, turns_per_day=24):
    return json.dumps(
        {
            "configuration": {
                "boardSize": {"type": "integer", "default": board_size, "minimum": 4},
                "turnsPerDay": {"type": "integer", "default": turns_per_day, "minimum": 1},
            }
        },
        sort_keys=True,
    ).encode("utf-8")


def fake_engine():
    return ("\n".join(mod.ENGINE_MARKERS) + "\n").encode("utf-8")


def fake_router():
    return ("\n".join(mod.ROUTER_MARKERS) + "\n").encode("utf-8")


def fake_tapes():
    return (
        "def load_tapes():\n"
        "    row = {'farmer': ['PASS'], 'hands': [], 'market': []}\n"
        "    return [[dict(row) for _ in range(719)] for _ in range(13)]\n"
    ).encode("utf-8")


class MotionCensusTests(unittest.TestCase):
    def test_two_step_loop_is_replay_candidate_not_rewrite_authority(self):
        report = mod.census_route(
            [action(["EAST"]), action(["WEST"])],
            plan=0,
        )
        self.assertEqual(report["open_loop_candidate_count"], 1)
        self.assertEqual(report["individually_pass_equivalent_movement_rows"], [])
        self.assertEqual(report["open_loop_candidate_movement_rows"], [0, 1])
        self.assertEqual(
            report["open_loop_closed_motion_candidates"][0]["movement_rows"], [0, 1]
        )
        self.assertEqual(
            report["open_loop_closed_motion_candidates"][0]["classification"],
            "OPEN_LOOP_REPLAY_REQUIRED",
        )
        self.assertNotIn("jointly_pass_equivalent_loop_movement_rows", report)

    def test_closed_loop_intermediate_positions_are_observable_candidates(self):
        report = mod.census_route(
            [action(["EAST"]), action(["WEST"])],
            plan=0,
        )
        self.assertEqual(report["individually_pass_equivalent_movement_rows"], [])
        self.assertEqual(
            report["open_loop_closed_motion_candidates"][0]["movement_rows"], [0, 1]
        )
        start = mod._default_spawn()
        after_east, _ = mod._move(start, "EAST", mod.BOARD_SIZE)
        after_west_only, _ = mod._move(start, "WEST", mod.BOARD_SIZE)
        self.assertNotEqual(after_east, start)
        self.assertNotEqual(after_west_only, start)

    def test_hire_is_a_position_semantics_barrier(self):
        report = mod.census_route(
            [
                action(["EAST"], [["HIRE"]]),
                action(["WEST"]),
            ],
            plan=0,
        )
        self.assertEqual(report["open_loop_candidate_count"], 0)
        self.assertEqual(report["individually_pass_equivalent_movement_rows"], [])
        self.assertEqual(report["open_loop_candidate_movement_rows"], [])

    def test_substantive_unit_action_is_a_barrier(self):
        report = mod.census_route(
            [
                action(["EAST"]),
                action(["WATER"]),
                action(["WEST"]),
            ],
            plan=0,
        )
        self.assertEqual(report["open_loop_candidate_count"], 0)

    def test_pass_inside_loop_preserves_open_loop_candidate(self):
        report = mod.census_route(
            [
                action(["EAST"]),
                action(["PASS"]),
                action(["WEST"]),
            ],
            plan=0,
        )
        self.assertEqual(report["open_loop_candidate_count"], 1)
        self.assertEqual(report["individually_pass_equivalent_movement_rows"], [])
        self.assertEqual(report["open_loop_candidate_movement_rows"], [0, 2])

    def test_boundary_move_is_already_pass_equivalent(self):
        report = mod.census_route(
            [action(["EAST"])],
            plan=0,
            board_size=1,
        )
        self.assertEqual(report["boundary_noop_rows"], [0])
        self.assertEqual(report["individually_pass_equivalent_movement_rows"], [0])
        self.assertEqual(report["open_loop_candidate_movement_rows"], [])

    def test_day_boundary_resets_loop_state(self):
        route = [action(["PASS"]) for _ in range(25)]
        route[23] = action(["EAST"])
        route[24] = action(["WEST"])
        report = mod.census_route(route, plan=0)
        self.assertEqual(report["open_loop_candidate_count"], 0)

    def test_disjoint_candidates_are_not_nested_spam(self):
        report = mod.census_route(
            [
                action(["EAST"]),
                action(["WEST"]),
                action(["NORTH"]),
                action(["SOUTH"]),
            ],
            plan=0,
        )
        self.assertEqual(report["open_loop_candidate_count"], 2)
        self.assertEqual(report["individually_pass_equivalent_movement_rows"], [])
        self.assertEqual(report["open_loop_candidate_movement_rows"], [0, 1, 2, 3])
        self.assertEqual(
            [g["movement_rows"] for g in report["open_loop_closed_motion_candidates"]],
            [[0, 1], [2, 3]],
        )

    def test_effective_route_uses_canonical_splice(self):
        tapes = []
        for plan in range(mod.TAPE_COUNT):
            tapes.append([
                {"farmer": ["PASS", plan, step], "hands": [], "market": []}
                for step in range(mod.TAPE_STEPS)
            ])
        route = mod.effective_route(tapes, 7)
        self.assertEqual(len(route), mod.TAPE_STEPS)
        self.assertEqual(route[143]["farmer"][1], 0)
        self.assertEqual(route[144]["farmer"][1], 7)
        self.assertEqual(route[647]["farmer"][1], 7)
        self.assertEqual(route[648]["farmer"][1], 2)

    def test_standard_config_is_bound_to_10_by_10_and_24_turn_day(self):
        self.assertEqual(
            mod._standard_configuration(standard_spec()),
            {"boardSize": 10, "turnsPerDay": 24},
        )

    def test_board_size_default_drift_fails_closed(self):
        with self.assertRaises(mod.MotionCensusError):
            mod._standard_configuration(standard_spec(board_size=12))

    def test_turns_per_day_default_drift_fails_closed(self):
        with self.assertRaises(mod.MotionCensusError):
            mod._standard_configuration(standard_spec(turns_per_day=48))

    def test_plain_integer_motion_configuration_required(self):
        with self.assertRaises(mod.MotionCensusError):
            mod.census_route([], board_size=True)
        with self.assertRaises(mod.MotionCensusError):
            mod.census_route([], turns_per_day=24.0)

    def test_source_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            engine = root / "engine.py"
            spec = root / "engine.json"
            tapes = root / "tapes.py"
            router = root / "router.py"
            engine.write_text("x = 1\n", encoding="utf-8")
            spec.write_bytes(standard_spec())
            tapes.write_text("x = 1\n", encoding="utf-8")
            router.write_text("x = 1\n", encoding="utf-8")
            with self.assertRaises(mod.MotionCensusError):
                mod.verify_sources(
                    engine_path=engine,
                    engine_spec_path=spec,
                    tapes_path=tapes,
                    router_path=router,
                )

    def test_authenticated_snapshots_survive_path_swap(self):
        engine_bytes = fake_engine()
        spec_bytes = standard_spec()
        tape_bytes = fake_tapes()
        router_bytes = fake_router()
        poison = b"raise RuntimeError('path reopened after authentication')\n"

        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            engine = root / "engine.py"
            spec = root / "engine.json"
            tapes = root / "tapes.py"
            router = root / "router.py"
            originals = {
                engine: engine_bytes,
                spec: spec_bytes,
                tapes: tape_bytes,
                router: router_bytes,
            }
            for path, data in originals.items():
                path.write_bytes(data)

            real_read = mod._read_snapshot

            def capture_then_swap(path):
                data = real_read(path)
                path.write_bytes(poison)
                return data

            patches = (
                mock.patch.object(mod, "EXPECTED_ENGINE_BLOB", mod._git_blob_bytes(engine_bytes)),
                mock.patch.object(mod, "EXPECTED_ENGINE_SPEC_BLOB", mod._git_blob_bytes(spec_bytes)),
                mock.patch.object(mod, "EXPECTED_TAPES_BLOB", mod._git_blob_bytes(tape_bytes)),
                mock.patch.object(mod, "EXPECTED_ROUTER_BLOB", mod._git_blob_bytes(router_bytes)),
                mock.patch.object(mod, "_read_snapshot", side_effect=capture_then_swap),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                verified = mod.verify_sources(
                    engine_path=engine,
                    engine_spec_path=spec,
                    tapes_path=tapes,
                    router_path=router,
                )

            self.assertEqual(
                verified.source_blobs["engine_blob"], mod._git_blob_bytes(engine_bytes)
            )
            self.assertEqual(
                verified.source_blobs["r04_full_router_blob"], mod._git_blob_bytes(router_bytes)
            )
            self.assertEqual(
                verified.standard_configuration,
                {"boardSize": 10, "turnsPerDay": 24},
            )
            loaded = mod.load_tapes(path=tapes, snapshot=verified.tapes_snapshot)
            self.assertEqual(len(loaded), 13)
            self.assertTrue(all(len(tape) == 719 for tape in loaded))

    def test_checkout_sources_and_full_bank(self):
        if not (
            mod.ENGINE_PATH.exists()
            and mod.ENGINE_SPEC_PATH.exists()
            and mod.TAPES_PATH.exists()
            and mod.ROUTER_PATH.exists()
        ):
            self.skipTest("repository checkout not mounted")
        sources = mod.verify_sources()
        tapes = mod.load_tapes(snapshot=sources.tapes_snapshot)
        report = mod.build_report(tapes, sources)
        self.assertEqual(report["schema"], "titan.v4.route-motion-census.v3")
        self.assertEqual(
            report["standard_configuration"],
            {"boardSize": 10, "turnsPerDay": 24},
        )
        self.assertEqual(
            report["sources"]["engine_spec_blob"],
            mod.EXPECTED_ENGINE_SPEC_BLOB,
        )
        self.assertIn("shared public observations", report["theorem"]["closed_loop_status"])
        self.assertEqual(len(report["routes"]), 13)
        self.assertEqual(
            report["totals"]["individually_pass_equivalent_count"],
            sum(
                route["individually_pass_equivalent_count"]
                for route in report["routes"]
            ),
        )
        self.assertEqual(
            report["totals"]["open_loop_candidate_movement_count"],
            sum(
                route["open_loop_candidate_movement_count"]
                for route in report["routes"]
            ),
        )


if __name__ == "__main__":
    unittest.main()
