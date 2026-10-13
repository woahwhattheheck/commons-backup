# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from collections import deque
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import p05_weed_queue_completion as p05


def _tar_with_router(router: bytes, *, duplicate: bool = False, symlink: bool = False) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz", format=tarfile.PAX_FORMAT) as tf:
        if symlink:
            info = tarfile.TarInfo(p05.ROUTER_MEMBER)
            info.type = tarfile.SYMTYPE
            info.linkname = "elsewhere"
            tf.addfile(info)
        else:
            for _ in range(2 if duplicate else 1):
                info = tarfile.TarInfo(p05.ROUTER_MEMBER)
                info.size = len(router)
                tf.addfile(info, io.BytesIO(router))
    return out.getvalue()


def _fixture_source() -> bytes:
    return b"""from collections import deque\nWEED_BLOCKED_WORK = {\"PLANT\", \"BUILD_COOP\", \"BUILD_PASTURE\"}\nTURNS_PER_DAY = 24\ndef repair_weeds(action, view, state, step):\n    day = step // TURNS_PER_DAY\n    if day != state.day:\n        state.day = day\n        state.queues.clear()\n    workers = [action.get(\"farmer\") or [\"PASS\"], *(action.get(\"hands\") or [])]\n    for worker in range(min(len(workers), len(view.positions))):\n        queue = state.queues.setdefault(worker, deque())\n        queue.append(list(workers[worker]))\n        x, y = view.positions[worker]\n        tile = view.tiles[y][x]\n        blocked = (queue[0][0] in WEED_BLOCKED_WORK and isinstance(tile, dict) and tile.get(\"kind\") == \"WEED\")\n        workers[worker] = [\"DIG\"] if blocked else queue.popleft()\n    action[\"farmer\"], action[\"hands\"] = workers[0], workers[1:]\n"""


class _State:
    def __init__(self):
        self.day = -1
        self.queues = {}


class _View:
    def __init__(self, kind="SOIL"):
        self.positions = [(0, 0)]
        self.tiles = [[{"kind": kind}]]


def _load_repair(source: bytes):
    namespace = {}
    exec(compile(source, "fixture_router.py", "exec"), namespace)
    return namespace["repair_weeds"]


class P05TransformTests(unittest.TestCase):
    def test_anchor_must_be_exactly_once(self):
        src = _fixture_source()
        self.assertRaises(ValueError, p05.transform_router, src.replace(p05._ANCHOR, b""))
        self.assertRaises(ValueError, p05.transform_router, src + p05._ANCHOR)

    def test_no_debt_pass_stays_pass(self):
        repair = _load_repair(p05.transform_router(_fixture_source()))
        state = _State()
        action = {"farmer": ["PASS"], "hands": []}
        repair(action, _View(), state, 0)
        self.assertEqual(action["farmer"], ["PASS"])
        self.assertEqual(list(state.queues[0]), [])

    def test_blocked_work_uses_later_pass_to_catch_up(self):
        repair = _load_repair(p05.transform_router(_fixture_source()))
        state = _State()
        blocked = {"farmer": ["PLANT", "CARROT"], "hands": []}
        repair(blocked, _View("WEED"), state, 0)
        self.assertEqual(blocked["farmer"], ["DIG"])
        self.assertEqual(list(state.queues[0]), [["PLANT", "CARROT"]])

        catchup = {"farmer": ["PASS"], "hands": []}
        repair(catchup, _View("SOIL"), state, 1)
        self.assertEqual(catchup["farmer"], ["PLANT", "CARROT"])
        self.assertEqual(list(state.queues[0]), [])

        next_action = {"farmer": ["HARVEST"], "hands": []}
        repair(next_action, _View("SOIL"), state, 2)
        self.assertEqual(next_action["farmer"], ["HARVEST"])
        self.assertEqual(list(state.queues[0]), [])

    def test_pass_does_not_discard_debt_while_weed_remains(self):
        repair = _load_repair(p05.transform_router(_fixture_source()))
        state = _State()
        first = {"farmer": ["PLANT", "CARROT"], "hands": []}
        repair(first, _View("WEED"), state, 0)
        second = {"farmer": ["PASS"], "hands": []}
        repair(second, _View("WEED"), state, 1)
        self.assertEqual(second["farmer"], ["DIG"])
        self.assertEqual(list(state.queues[0]), [["PLANT", "CARROT"]])

    def test_non_pass_preserves_fifo_shift(self):
        repair = _load_repair(p05.transform_router(_fixture_source()))
        state = _State()
        first = {"farmer": ["PLANT", "CARROT"], "hands": []}
        repair(first, _View("WEED"), state, 0)
        second = {"farmer": ["HARVEST"], "hands": []}
        repair(second, _View("SOIL"), state, 1)
        self.assertEqual(second["farmer"], ["PLANT", "CARROT"])
        self.assertEqual(list(state.queues[0]), [["HARVEST"]])

    def test_dawn_still_discards_unfinished_debt(self):
        repair = _load_repair(p05.transform_router(_fixture_source()))
        state = _State()
        first = {"farmer": ["PLANT", "CARROT"], "hands": []}
        repair(first, _View("WEED"), state, 23)
        dawn = {"farmer": ["HARVEST"], "hands": []}
        repair(dawn, _View("SOIL"), state, 24)
        self.assertEqual(dawn["farmer"], ["HARVEST"])
        self.assertEqual(list(state.queues[0]), [])


class P05BuilderTests(unittest.TestCase):
    def test_builder_binds_archive_router_and_manifest(self):
        router = _fixture_source()
        archive = _tar_with_router(router)
        patched, manifest_bytes = p05.build_component(
            archive,
            expected_archive_sha256=hashlib.sha256(archive).hexdigest(),
            expected_router_sha256=hashlib.sha256(router).hexdigest(),
        )
        self.assertNotEqual(patched, router)
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest["schema"], p05.COMPONENT_SCHEMA)
        self.assertEqual(manifest["component_id"], p05.COMPONENT_ID)
        self.assertTrue(manifest["kaggle_submission_hold"])
        replacement = manifest["replacements"][p05.ROUTER_MEMBER]
        self.assertEqual(replacement["preimage_sha256"], hashlib.sha256(router).hexdigest())
        self.assertEqual(replacement["postimage_sha256"], hashlib.sha256(patched).hexdigest())

    def test_builder_rejects_wrong_archive_hash(self):
        router = _fixture_source()
        archive = _tar_with_router(router)
        with self.assertRaisesRegex(ValueError, "archive SHA256 mismatch"):
            p05.build_component(
                archive,
                expected_archive_sha256="0" * 64,
                expected_router_sha256=hashlib.sha256(router).hexdigest(),
            )

    def test_builder_rejects_wrong_router_hash(self):
        router = _fixture_source()
        archive = _tar_with_router(router)
        with self.assertRaisesRegex(ValueError, "r04_full_router.py SHA256 mismatch"):
            p05.build_component(
                archive,
                expected_archive_sha256=hashlib.sha256(archive).hexdigest(),
                expected_router_sha256="0" * 64,
            )

    def test_builder_rejects_duplicate_or_nonregular_router(self):
        router = _fixture_source()
        duplicate = _tar_with_router(router, duplicate=True)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            p05.build_component(
                duplicate,
                expected_archive_sha256=hashlib.sha256(duplicate).hexdigest(),
                expected_router_sha256=hashlib.sha256(router).hexdigest(),
            )
        symlink = _tar_with_router(router, symlink=True)
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            p05.build_component(
                symlink,
                expected_archive_sha256=hashlib.sha256(symlink).hexdigest(),
                expected_router_sha256=hashlib.sha256(router).hexdigest(),
            )

    def test_materialize_uses_create_exclusive_pair(self):
        router = _fixture_source()
        archive = _tar_with_router(router)
        patched, manifest = p05.build_component(
            archive,
            expected_archive_sha256=hashlib.sha256(archive).hexdigest(),
            expected_router_sha256=hashlib.sha256(router).hexdigest(),
        )
        # Exercise shared publisher separately because public materialize pins the real hashes.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p05.publish_exclusive(
                [(root / p05.ROUTER_MEMBER, patched), (root / "COMPONENT.json", manifest)]
            )
            self.assertEqual((root / p05.ROUTER_MEMBER).read_bytes(), patched)
            self.assertEqual((root / "COMPONENT.json").read_bytes(), manifest)
            with self.assertRaises(FileExistsError):
                p05.publish_exclusive(
                    [(root / p05.ROUTER_MEMBER, patched), (root / "COMPONENT.json", manifest)]
                )


if __name__ == "__main__":
    unittest.main()
