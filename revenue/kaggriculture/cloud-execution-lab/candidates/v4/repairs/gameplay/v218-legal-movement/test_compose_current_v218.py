import hashlib
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import compose_current_v218 as c


OLD_FIXTURE = f'''# fixture\ndef f(tiles, view, half):\n    {c.PATH_OLD}\n        return None\n    {c.SHEDS_OLD}\n    return sheds\n'''
NEW_FIXTURE = OLD_FIXTURE.replace(c.PATH_OLD, c.PATH_NEW).replace(c.SHEDS_OLD, c.SHEDS_NEW)


def repair_module(transform):
    return types.SimpleNamespace(transform=transform)


class CurrentV218IntakeTests(unittest.TestCase):
    def test_git_blob_matches_git_object_rule(self):
        data = b"abc\n"
        expected = hashlib.sha1(b"blob 4\0abc\n").hexdigest()
        self.assertEqual(c.git_blob(data), expected)

    def test_audit_accepts_only_exact_two_lines(self):
        changed = c.audit_two_line_delta(OLD_FIXTURE, NEW_FIXTURE)
        self.assertEqual(len(changed), 2)
        self.assertEqual({x["before"].strip() for x in changed}, {c.PATH_OLD, c.SHEDS_OLD})

    def test_audit_rejects_extra_mutation(self):
        with self.assertRaisesRegex(c.IntakeError, "exactly two"):
            c.audit_two_line_delta(OLD_FIXTURE, NEW_FIXTURE.replace("return sheds", "return list(sheds)"))

    def test_audit_rejects_wrong_semantic_pair(self):
        bad = OLD_FIXTURE.replace(c.PATH_OLD, "if False:").replace(c.SHEDS_OLD, c.SHEDS_NEW)
        with self.assertRaisesRegex(c.IntakeError, "changed-line set"):
            c.audit_two_line_delta(OLD_FIXTURE, bad)

    def test_off_is_whole_file_identity(self):
        raw = OLD_FIXTURE.encode()
        blob = c.git_blob(raw)
        fake = repair_module(lambda source, enabled: (_ for _ in ()).throw(AssertionError("OFF delegated unexpectedly")))
        out, receipt = c._compose_verified(raw, enabled=False, expected_source_blob=blob, repair=fake)
        self.assertIs(out, raw)
        self.assertEqual(receipt["source_blob"], receipt["output_blob"])
        self.assertEqual(receipt["changed_line_count"], 0)

    def test_on_delegates_then_audits(self):
        raw = OLD_FIXTURE.encode()
        blob = c.git_blob(raw)
        calls = []
        def transform(source, *, enabled=False):
            calls.append(enabled)
            return source.replace(c.PATH_OLD, c.PATH_NEW).replace(c.SHEDS_OLD, c.SHEDS_NEW)
        out, receipt = c._compose_verified(raw, enabled=True, expected_source_blob=blob, repair=repair_module(transform))
        self.assertEqual(calls, [True])
        self.assertEqual(out.decode(), NEW_FIXTURE)
        self.assertEqual(receipt["changed_line_count"], 2)
        self.assertFalse(receipt["production_activation"])
        self.assertFalse(receipt["legacy_materializer_used"])

    def test_source_blob_drift_fails_before_transform(self):
        raw = OLD_FIXTURE.encode()
        fake = repair_module(lambda source, enabled=True: NEW_FIXTURE)
        with self.assertRaisesRegex(c.IntakeError, "current router blob drift"):
            c._compose_verified(raw, enabled=True, expected_source_blob="0" * 40, repair=fake)

    def test_enabled_identical_output_is_rejected(self):
        raw = OLD_FIXTURE.encode()
        blob = c.git_blob(raw)
        fake = repair_module(lambda source, enabled=True: source)
        with self.assertRaises(c.IntakeError):
            c._compose_verified(raw, enabled=True, expected_source_blob=blob, repair=fake)

    def test_actual_sibling_repair_blob_is_pinned(self):
        module = c._load_repair(Path(__file__).with_name(c.REPAIR_TOOL_NAME))
        self.assertEqual(module.CURRENT_ROUTER_BLOB, c.CURRENT_ROUTER_BLOB)

    def test_repair_tool_blob_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / c.REPAIR_TOOL_NAME
            path.write_text("def transform(x, enabled=False): return x\n")
            with self.assertRaisesRegex(c.IntakeError, "repair tool blob drift"):
                c._load_repair(path)

    def test_cli_never_overwrites_existing_output(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "source.py"
            out = td / "out.py"
            tool = td / c.REPAIR_TOOL_NAME
            src.write_bytes(OLD_FIXTURE.encode())
            out.write_text("sentinel")
            tool.write_text("placeholder")
            with mock.patch.object(c, "compose_current", return_value=(b"candidate", {"ok": True})):
                rc = None
                with self.assertRaises(SystemExit) as caught:
                    c.main([str(src), str(out), "--repair-tool", str(tool)])
                rc = caught.exception.code
            self.assertEqual(rc, 2)
            self.assertEqual(out.read_text(), "sentinel")


if __name__ == "__main__":
    unittest.main()
