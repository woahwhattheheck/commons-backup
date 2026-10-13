from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
import types
import unittest

import materialize


SCHEDULER_FIXTURE = (
    "def prefix():\n    return 1\n\n\nclass SellScheduler:\n"
    "    def act(self, base, route, config, now, item):\n"
    "        def receipt_feasible(plan):return True\n"
    "        current={}\n"
    "        self.planned={}\n"
    "        if True:\n"
    "            def feasible(plan):\n"
    "                for t,q in plan:\n"
    "                    if q<=0:continue\n"
    "                    orders=base['market'] if t==now else route[t].get('market',[]) if t<len(route) else []\n"
    + materialize.OLD_BLOCK
    + "\n                return receipt_feasible(plan)\n"
    "            return feasible\n"
)

FROZEN_FIXTURE = (
    "from scheduler import *\nimport scheduler as scheduling\n\n"
    "class FrozenSelected(SellScheduler):\n"
    "    def transform(self, base, route, config, now, item):\n"
    "        def receipt_feasible(plan):return True\n"
    "        current={}\n"
    "        self.planned={}\n"
    "        if True:\n"
    "            def feasible(plan):\n"
    "                for t,q in plan:\n"
    "                    if q<=0:continue\n"
    "                    orders=base['market'] if t==now else route[t].get('market',[]) if t<len(route) else []\n"
    + materialize.OLD_BLOCK
    + "\n                return receipt_feasible(plan)\n"
    "            return feasible\n"
)

HELPER = """\n\ndef _planned_slot_reservations(planned,current,item,now,step,orders):\n    return 0\n"""


class FakeDonor:
    EXPECTED_SOURCE_BLOB = materialize.EXPECTED_SCHEDULER_BLOB
    OPERATION = materialize.DONOR_OPERATION
    OLD_BLOCK = materialize.OLD_BLOCK
    NEW_BLOCK = "_planned_slot_reservations"

    @staticmethod
    def patch_source(source: str, *, expected_blob: str | None):
        if expected_blob is not None and materialize.git_blob_sha(source.encode()) != expected_blob:
            raise ValueError("fixture source mismatch")
        if source.count("\n\nclass SellScheduler:\n") != 1:
            raise ValueError("fixture class anchor mismatch")
        if source.count(materialize.OLD_BLOCK) != 1:
            raise ValueError("fixture predicate mismatch")
        return source.replace("\n\nclass SellScheduler:\n", HELPER + "\n\nclass SellScheduler:\n", 1).replace(
            materialize.OLD_BLOCK,
            materialize.OLD_BLOCK.replace(
                "if len(orders)>=int(config.get('maxMarketOrdersPerTurn',10)):",
                "reserved=_planned_slot_reservations(self.planned,current,item,now,t,orders)\n                    if len(orders)+reserved>=int(config.get('maxMarketOrdersPerTurn',10)):",
            ),
            1,
        )


class FrozenPortTests(unittest.TestCase):
    def test_patch_frozen_is_unique_parseable_and_active(self):
        patched = materialize.patch_frozen(FROZEN_FIXTURE, expected_blob=None)
        ast.parse(patched)
        self.assertNotEqual(patched, FROZEN_FIXTURE)
        self.assertEqual(patched.count("scheduling._planned_slot_reservations("), 1)
        self.assertEqual(patched.count(materialize.NEW_BLOCK), 1)
        self.assertNotIn(materialize.OLD_BLOCK, patched)

    def test_patch_frozen_rejects_duplicate_or_missing_preimage(self):
        patched = materialize.patch_frozen(FROZEN_FIXTURE, expected_blob=None)
        with self.assertRaises(ValueError):
            materialize.patch_frozen(patched, expected_blob=None)
        with self.assertRaises(ValueError):
            materialize.patch_frozen(FROZEN_FIXTURE.replace("import scheduler as scheduling\n", ""), expected_blob=None)
        with self.assertRaises(ValueError):
            materialize.patch_frozen(FROZEN_FIXTURE + "\n" + materialize.OLD_BLOCK, expected_blob=None)

    def test_wrong_frozen_blob_fails_closed(self):
        with self.assertRaises(ValueError):
            materialize.patch_frozen(FROZEN_FIXTURE, expected_blob="0" * 40)

    def test_pair_connects_donor_helper_to_active_consumer(self):
        scheduler_post, frozen_post = materialize.materialize_pair(
            SCHEDULER_FIXTURE,
            FROZEN_FIXTURE,
            FakeDonor,
            expected_scheduler_blob=None,
            expected_frozen_blob=None,
        )
        ast.parse(scheduler_post)
        ast.parse(frozen_post)
        self.assertEqual(scheduler_post.count("def _planned_slot_reservations("), 1)
        self.assertEqual(frozen_post.count("scheduling._planned_slot_reservations("), 1)

    def test_strict_json_rejects_duplicate_and_nonfinite(self):
        self.assertEqual(materialize.load_json_strict(b'{"consumer":"frozen"}'), {"consumer": "frozen"})
        for payload in (b'{"consumer":"frozen","consumer":"parent"}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    materialize.load_json_strict(payload)

    def test_validate_paths_rejects_alias_and_existing_destination(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.py"
            source.write_text("x=1\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                materialize.validate_paths(
                    [("source", source)],
                    [("output", source)],
                )
            existing = root / "existing.py"
            existing.write_text("old\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                materialize.validate_paths(
                    [("source", source)],
                    [("output", existing)],
                )

    def test_exclusive_publish_rolls_back_partial_creation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = root / "first"
            second = root / "second"
            second.write_bytes(b"incumbent")
            with self.assertRaises(FileExistsError):
                materialize.publish_exclusive([(first, b"new-first"), (second, b"new-second")])
            self.assertFalse(first.exists())
            self.assertEqual(second.read_bytes(), b"incumbent")

    def test_receipt_is_deterministic_and_binds_both_postimages(self):
        values = dict(
            scheduler_source=b"scheduler-before",
            frozen_source=b"frozen-before",
            runtime_source=b"runtime",
            config_source=b'{"consumer":"frozen"}',
            donor_source=b"donor",
            scheduler_post=b"scheduler-after",
            frozen_post=b"frozen-after",
        )
        first = materialize.build_receipt(**values)
        second = materialize.build_receipt(**values)
        self.assertEqual(first, second)
        self.assertEqual(first["donor"]["head"], materialize.EXPECTED_DONOR_HEAD)
        self.assertNotEqual(first["inputs"]["scheduler"]["sha256"], first["outputs"]["scheduler"]["sha256"])
        self.assertNotEqual(first["inputs"]["frozen_selected"]["sha256"], first["outputs"]["frozen_selected"]["sha256"])
        json.dumps(first, sort_keys=True)


if __name__ == "__main__":
    unittest.main()
