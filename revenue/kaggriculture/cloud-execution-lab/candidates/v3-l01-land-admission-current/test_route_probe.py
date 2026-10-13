# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from route_probe import compare_snapshots, snapshot


UNWRAPPED_MAIN = """
class Controller:
    def __init__(self):
        self.R = {'MAIN': [{'market': []}, {'market': []}]}

class Agent:
    def _initialize(self):
        self.controller = Controller()

def _new_instance(root, config):
    return Agent()
"""

WRAPPED_MAIN = """
class Controller:
    def __init__(self):
        self.R = {'MAIN': [{'market': []}, {'market': [['BUY_LAND']]}]}

class Agent:
    def __init__(self):
        self._land_admission_wrapped = True
        self._land_admission_state = {'initializations': 0, 'receipt': None}

    def _initialize(self):
        self.controller = Controller()
        self._land_admission_state['initializations'] += 1
        self._land_admission_state['receipt'] = {
            'schema': 'test-install-v1',
            'installed': True,
            'activations': 1,
        }

def _new_instance(root, config):
    return Agent()
"""

SELF_REPAIR_MECHANISM = """
def wrap(agent):
    agent._land_admission_wrapped = True
    original = agent._initialize
    def initialize():
        original()
        agent.controller.R['MAIN'][1]['market'].append(['BUY_LAND'])
        agent._land_admission_state = {
            'initializations': 1,
            'receipt': {'installed': True, 'activations': 1},
        }
    agent._initialize = initialize
    return agent
"""


class RouteProbeTests(unittest.TestCase):
    def _package(self, root: Path, main_source: str, mechanism_source: str = "") -> Path:
        package = root / "package"
        package.mkdir()
        (package / "main.py").write_text(main_source, encoding="utf-8")
        (package / "TITAN-CONFIG.json").write_text("{}\n", encoding="utf-8")
        (package / "land_admission.py").write_text(
            mechanism_source, encoding="utf-8"
        )
        return package

    def test_candidate_snapshot_rejects_unwrapped_builder(self):
        """The predecessor probe silently repaired this invalid package itself."""
        with tempfile.TemporaryDirectory() as raw:
            package = self._package(
                Path(raw), UNWRAPPED_MAIN, SELF_REPAIR_MECHANISM
            )
            with self.assertRaisesRegex(
                ValueError, "construction did not install LAND admission"
            ):
                snapshot(package, apply_land=True)

    def test_candidate_snapshot_uses_preinstalled_wrapper_without_repair(self):
        with tempfile.TemporaryDirectory() as raw:
            package = self._package(
                Path(raw),
                WRAPPED_MAIN,
                "raise AssertionError('route probe must not import mechanism to repair candidate')\n",
            )
            report = snapshot(package, apply_land=True)
            self.assertTrue(report["land_admission_wrapped"])
            self.assertTrue(report["land_admission_receipt"]["installed"])
            self.assertEqual(report["land_admission_receipt"]["activations"], 1)
            self.assertEqual(report["routes"]["MAIN"][1]["market"], [["BUY_LAND"]])

    def test_baseline_snapshot_rejects_preinstalled_admission(self):
        with tempfile.TemporaryDirectory() as raw:
            package = self._package(Path(raw), WRAPPED_MAIN)
            with self.assertRaisesRegex(
                ValueError, "baseline package unexpectedly installed LAND admission"
            ):
                snapshot(package, apply_land=False)

    def test_candidate_snapshot_requires_install_receipt(self):
        source = WRAPPED_MAIN.replace(
            "'installed': True,", "'installed': False,"
        )
        with tempfile.TemporaryDirectory() as raw:
            package = self._package(Path(raw), source)
            with self.assertRaisesRegex(
                ValueError, "did not emit an installed initialization receipt"
            ):
                snapshot(package, apply_land=True)

    def test_exact_transform(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            mechanism = root / "land_admission.py"
            mechanism.write_text(
                "BUY_LAND='BUY_LAND'\n"
                "def patch_routes(routes):\n"
                "    sites=[]\n"
                "    for name, route in routes.items():\n"
                "        route[1].setdefault('market', []).append([BUY_LAND])\n"
                "        sites.append({'route':name,'step':1,'market_index':0})\n"
                "    return {'activations':len(sites),'sites':sites}\n",
                encoding="utf-8",
            )
            before_routes = {
                "MAIN": [
                    {"market": []},
                    {"market": []},
                ]
            }
            after_routes = {
                "MAIN": [
                    {"market": []},
                    {"market": [["BUY_LAND"]]},
                ]
            }

            def make_snapshot(routes):
                payload = json.dumps(
                    routes, sort_keys=True, separators=(",", ":")
                ).encode()
                return {
                    "routes": routes,
                    "routes_sha256": hashlib.sha256(payload).hexdigest(),
                    "route_count": 1,
                }

            report = compare_snapshots(
                make_snapshot(before_routes),
                make_snapshot(after_routes),
                mechanism,
            )
            self.assertTrue(report["exact_transform_match"])
            self.assertEqual(report["changed_rows"], 1)
            self.assertEqual(report["first_divergence"]["step"], 1)


if __name__ == "__main__":
    unittest.main()
