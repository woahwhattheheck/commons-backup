#!/usr/bin/env python3
"""Tests for the cross-lane self-sealing-check auditor.

Two of these exist because the auditor produced them as real false positives
on its first run against the live tree. A tool that manufactures findings is
the same defect class as one that hides them, so both are regression-tested:

  * test_a_lane_that_reads_a_sibling_lane_is_not_reported -- the first version
    copied each lane alone, which deleted the sibling file one suite reads and
    reported six invented failures.
  * test_a_deliberately_broken_fixture_is_not_reported -- a shipped fixture
    whose README says its own green claim is false must not be read as a
    defect in the lane that ships it.
"""
import hashlib
import os
import shutil
import tempfile
import unittest

import audit_self_sealing as A

CLEAN_TEST = """import unittest
class T(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(1, 1)
"""


def write(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)


def tree_digest(root):
    h = hashlib.sha256()
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in A.SKIP_DIRS]
        for fn in sorted(files):
            if fn.endswith((".pyc", ".pyo")):
                continue
            full = os.path.join(dirpath, fn)
            h.update(os.path.relpath(full, root).encode())
            with open(full, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


class AuditorCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="auditor-test-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def lane(self, name):
        p = os.path.join(self.root, "uiowa_rfq_18649_" + name)
        os.makedirs(p, exist_ok=True)
        return p

    def audit(self, only=None):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        argv = [self.root, "--timeout", "60", "--format", "json"]
        if only:
            argv += ["--only", "uiowa_rfq_18649_" + only]
        with redirect_stdout(buf):
            A.main(argv)
        import json
        return {r["lane"]: r for r in json.loads(buf.getvalue())}


class TestDetection(AuditorCase):
    def test_a_self_sealing_manifest_is_caught(self):
        # The defect: the suite recomputes the artefact, then rewrites the
        # expected digest to match whatever it just produced.
        lane = self.lane("sealing")
        write(os.path.join(lane, "fixtures", "artifact.txt"), "original\n")
        write(os.path.join(lane, "fixtures", "manifest.json"),
              '{"sha256": "%s"}\n' % ("0" * 64))
        write(os.path.join(lane, "test_seal.py"), """import hashlib, json, os, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
class T(unittest.TestCase):
    def test_manifest_matches(self):
        art = os.path.join(HERE, "fixtures", "artifact.txt")
        with open(art, "w") as f:
            f.write("regenerated %s\\n" % os.getpid())
        with open(art, "rb") as f:
            d = hashlib.sha256(f.read()).hexdigest()
        mf = os.path.join(HERE, "fixtures", "manifest.json")
        with open(mf, "w") as f:
            json.dump({"sha256": d}, f)
        with open(mf) as f:
            self.assertEqual(json.load(f)["sha256"], d)
""")
        r = self.audit("sealing")["uiowa_rfq_18649_sealing"]
        self.assertEqual(r["verdict"], "SELF_SEALING")
        self.assertTrue(r["self_sealing"])
        self.assertTrue(any("manifest.json" in e["file"] for e in r["self_sealing"]))

    def test_a_clean_lane_is_clean(self):
        write(os.path.join(self.lane("clean"), "test_clean.py"), CLEAN_TEST)
        self.assertEqual(self.audit("clean")["uiowa_rfq_18649_clean"]["verdict"], "CLEAN")

    def test_a_lane_with_no_tests_is_not_a_defect(self):
        write(os.path.join(self.lane("doconly"), "README.md"), "# notes\n")
        self.assertEqual(self.audit("doconly")["uiowa_rfq_18649_doconly"]["verdict"],
                         "NO_TESTS")

    def test_a_suite_that_writes_into_a_neighbour_is_caught(self):
        write(os.path.join(self.lane("neighbour"), "data.txt"), "theirs\n")
        lane = self.lane("writer")
        write(os.path.join(lane, "test_writer.py"), """import os, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "..", "uiowa_rfq_18649_neighbour", "data.txt")
class T(unittest.TestCase):
    def test_scribble(self):
        with open(TARGET, "w") as f:
            f.write("mine now\\n")
        self.assertTrue(os.path.isfile(TARGET))
""")
        r = self.audit("writer")["uiowa_rfq_18649_writer"]
        self.assertEqual(r["verdict"], "WRITES_OUTSIDE_LANE")
        self.assertTrue(any("neighbour" in e["file"] for e in r["foreign_writes"]))

    def test_a_failing_suite_is_reported_but_not_as_self_sealing(self):
        write(os.path.join(self.lane("failing"), "test_fail.py"), """import unittest
class T(unittest.TestCase):
    def test_no(self):
        self.assertEqual(1, 2)
""")
        r = self.audit("failing")["uiowa_rfq_18649_failing"]
        self.assertEqual(r["verdict"], "TESTS_NOT_GREEN")
        self.assertEqual(r["self_sealing"], [])


class TestFalsePositivesItOnceProduced(AuditorCase):
    def test_a_lane_that_reads_a_sibling_lane_is_not_reported(self):
        write(os.path.join(self.lane("source"), "EXHIBIT.md"), "criterion AC-1\n")
        lane = self.lane("reader")
        write(os.path.join(lane, "test_reader.py"), """import os, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
SIB = os.path.join(HERE, "..", "uiowa_rfq_18649_source", "EXHIBIT.md")
class T(unittest.TestCase):
    def test_reads_the_sibling(self):
        with open(SIB) as f:
            self.assertIn("AC-1", f.read())
""")
        r = self.audit("reader")["uiowa_rfq_18649_reader"]
        self.assertEqual(r["verdict"], "CLEAN",
                         "isolating the lane broke a legitimate sibling read")

    def test_a_deliberately_broken_fixture_is_not_reported(self):
        lane = self.lane("kit")
        write(os.path.join(lane, "test_kit.py"), CLEAN_TEST)
        write(os.path.join(lane, "fixtures", "minikit", "README.md"),
              "Status: green. That claim is false and is here on purpose.\n")
        write(os.path.join(lane, "fixtures", "minikit", "test_broken.py"),
              """import unittest
class T(unittest.TestCase):
    def test_intentionally_fails(self):
        self.assertEqual("a", "b")
""")
        r = self.audit("kit")["uiowa_rfq_18649_kit"]
        self.assertEqual(r["verdict"], "CLEAN",
                         "a fixture's intended failure was read as a lane defect")


class TestItNeverTouchesTheSource(AuditorCase):
    def test_the_audited_tree_is_byte_identical_afterwards(self):
        # The auditor runs other seats' test suites. If it ran them in place it
        # would be mutating work it does not own -- which is the one thing it
        # must never do, especially while hunting for suites that mutate things.
        lane = self.lane("mutator")
        write(os.path.join(lane, "fixtures", "state.txt"), "pristine\n")
        write(os.path.join(lane, "test_mutate.py"), """import os, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
class T(unittest.TestCase):
    def test_writes_its_own_fixture(self):
        with open(os.path.join(HERE, "fixtures", "state.txt"), "w") as f:
            f.write("rewritten\\n")
        self.assertTrue(True)
""")
        before = tree_digest(self.root)
        r = self.audit("mutator")["uiowa_rfq_18649_mutator"]
        self.assertEqual(r["verdict"], "NON_HERMETIC")
        self.assertEqual(tree_digest(self.root), before,
                         "the auditor modified the tree it was auditing")


class TestRuleSurface(AuditorCase):
    def test_static_scan_flags_a_digest_written_into_a_manifest(self):
        lane = self.lane("static")
        write(os.path.join(lane, "build.py"),
              'import hashlib\nentry["sha256"] = hashlib.sha256(b"x").hexdigest()\n')
        hits = A.static_scan(lane)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["file"], "build.py")

    def test_digests_in_ignores_short_hex(self):
        self.assertEqual(A.digests_in(b"deadbeef cafe"), set())
        self.assertEqual(A.digests_in(b"a" * 64), {"a" * 64})


if __name__ == "__main__":
    unittest.main(verbosity=2)
