import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import staging_composer as sc


def h(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class ComposerAdditionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.base = {
            "main.py": b"base-main\n",
            "r04_full_router.py": b"router-0\n",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def component(
        self,
        cid,
        *,
        replacements=None,
        additions=None,
        depends=None,
        overlap=None,
    ):
        folder = self.root / cid
        folder.mkdir()
        replacement_specs = {}
        for member, (pre, body) in (replacements or {}).items():
            source = member.replace("/", "__") + ".replacement"
            (folder / source).write_bytes(body)
            replacement_specs[member] = {
                "source": source,
                "preimage_sha256": h(pre),
                "postimage_sha256": h(body),
            }
        addition_specs = {}
        for member, body in (additions or {}).items():
            source = member.replace("/", "__") + ".addition"
            (folder / source).write_bytes(body)
            addition_specs[member] = {
                "source": source,
                "postimage_sha256": h(body),
            }
        obj = {
            "schema": sc.COMPONENT_SCHEMA,
            "component_id": cid,
            "baseline_archive_sha256": sc.BASELINE_SHA256,
            "depends_on": depends or [],
            "conflicts_with": [],
            "overlap_after": overlap or {},
            "replacements": replacement_specs,
            "kaggle_submission_hold": True,
        }
        if additions is not None:
            obj["additions"] = addition_specs
        path = folder / "COMPONENT.json"
        path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    def load(self, *paths):
        return [sc.load_component(path) for path in paths]

    def test_adds_absent_member_and_receipt_distinguishes_addition(self):
        helper = b"def gate():\n    return True\n"
        path = self.component("p01", additions={"p01_productive_expansion_gate.py": helper})
        files, applied = sc.compose_files(self.base, self.load(path))
        self.assertEqual(files["p01_productive_expansion_gate.py"], helper)
        addition = applied[0]["additions"]["p01_productive_expansion_gate.py"]
        self.assertEqual(addition["postimage_sha256"], h(helper))
        self.assertIs(addition["absence_precondition"], True)
        self.assertEqual(applied[0]["replacements"], {})

    def test_addition_rejects_member_present_in_baseline(self):
        path = self.component("p01", additions={"main.py": b"shadow\n"})
        with self.assertRaisesRegex(sc.ComposerError, "addition targets existing member"):
            sc.compose_files(self.base, self.load(path))

    def test_second_addition_of_same_member_rejects(self):
        a = self.component("a", additions={"helper.py": b"a\n"})
        b = self.component("b", additions={"helper.py": b"b\n"})
        with self.assertRaisesRegex(sc.ComposerError, "addition targets existing member"):
            sc.compose_files(self.base, self.load(a, b))

    def test_forged_addition_postimage_rejects_at_load(self):
        path = self.component("p01", additions={"helper.py": b"body\n"})
        obj = json.loads(path.read_text())
        obj["additions"]["helper.py"]["postimage_sha256"] = "0" * 64
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(sc.ComposerError, "addition postimage mismatch"):
            sc.load_component(path)

    def test_same_manifest_cannot_replace_and_add_same_member(self):
        path = self.component(
            "p01",
            replacements={"main.py": (self.base["main.py"], b"new-main\n")},
            additions={"helper.py": b"helper\n"},
        )
        obj = json.loads(path.read_text())
        addition = obj["additions"].pop("helper.py")
        obj["additions"]["main.py"] = addition
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(sc.ComposerError, "replacement and addition"):
            sc.load_component(path)

    def test_replacing_added_member_requires_exact_overlap_owner(self):
        a = self.component("a", additions={"helper.py": b"v1\n"})
        b = self.component(
            "b",
            replacements={"helper.py": (b"v1\n", b"v2\n")},
            depends=["a"],
        )
        with self.assertRaisesRegex(sc.ComposerError, "without exact declaration"):
            sc.compose_files(self.base, self.load(a, b))

    def test_replacing_added_member_with_exact_overlap_is_deterministic(self):
        a = self.component("a", additions={"helper.py": b"v1\n"})
        b = self.component(
            "b",
            replacements={"helper.py": (b"v1\n", b"v2\n")},
            depends=["a"],
            overlap={"helper.py": "a"},
        )
        components = self.load(a, b)
        left_files, left_applied = sc.compose_files(self.base, components)
        right_files, right_applied = sc.compose_files(dict(reversed(list(self.base.items()))), components)
        self.assertEqual(left_files["helper.py"], b"v2\n")
        self.assertEqual(left_files, right_files)
        self.assertEqual(sc.archive_bytes(left_files), sc.archive_bytes(right_files))
        self.assertEqual(left_applied, right_applied)
        self.assertEqual(left_applied[0]["additions"]["helper.py"]["postimage_sha256"], h(b"v1\n"))
        self.assertEqual(left_applied[1]["replacements"]["helper.py"]["overlap_after"], "a")


if __name__ == "__main__":
    unittest.main()
