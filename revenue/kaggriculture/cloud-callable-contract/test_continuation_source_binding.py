"""Exercise continuation entry-file source binding through its real loader.

The complete continuation module is loaded by the existing callable contract
helper. These tests create temporary Python policies and actual bytecode caches;
they do not run games, simulations, opponents, or seed panels.
"""

import builtins
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import py_compile
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

from test_continuation_callable import read_continuation


class ContinuationSourceBinding(unittest.TestCase):
    def setUp(self):
        self.namespace = read_continuation()
        self.load = self.namespace["load_agent"]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "policy.py"
        self.spec = f"{self.path}::agent"

    def write(self, source):
        self.path.write_bytes(source)
        return source

    def assert_identity(self, metadata, source):
        digest = hashlib.sha256(source).hexdigest()
        self.assertEqual(metadata, {
            "spec": self.spec,
            "kind": "file",
            "path": str(self.path.resolve()),
            "function": "agent",
            "sha256": digest,
            "label": f"policy.py::agent@{digest[:12]}",
        })

    def test_same_size_timestamp_cache_cannot_replace_entry_source(self):
        old = self.write(b"def agent(obs): return 'old'\n")
        stamp = self.path.stat()
        cached = py_compile.compile(
            str(self.path), doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
        )
        current = b"def agent(obs): return 'new'\n"
        self.assertEqual(len(old), len(current))
        self.write(current)
        os.utime(self.path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertTrue(Path(cached).is_file())
        call, metadata = self.load(self.spec)
        with self.subTest("executed source"):
            self.assertEqual(call({}), "new")
        with self.subTest("reported source"):
            self.assert_identity(metadata, current)

    def test_unchecked_hash_cache_cannot_replace_entry_source(self):
        self.write(b"def agent(obs): return 'cached'\n")
        cached = py_compile.compile(
            str(self.path), doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
        )
        current = self.write(b"def agent(obs): return 'current source'\n")
        self.assertTrue(Path(cached).is_file())
        call, metadata = self.load(self.spec)
        with self.subTest("executed source"):
            self.assertEqual(call({}), "current source")
        with self.subTest("reported source"):
            self.assert_identity(metadata, current)

    def test_rewrite_after_read_keeps_execution_and_identity_together(self):
        captured = self.write(b"def agent(obs): return 'captured'\n")
        replacement = b"def agent(obs): return 'replacement'\n"
        original_open = builtins.open
        original_io_open = io.open
        target = self.path
        reads = []

        class RewriteAfterRead:
            def __init__(self, stream):
                self.stream = stream

            def read(self, *args, **kwargs):
                data = self.stream.read(*args, **kwargs)
                reads.append(data)
                if len(reads) == 1:
                    with original_open(target, "wb") as changed:
                        changed.write(replacement)
                return data

            def __enter__(self):
                self.stream.__enter__()
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def __getattr__(self, name):
                return getattr(self.stream, name)

        def intercept(opener):
            def open_entry(file, mode="r", *args, **kwargs):
                stream = opener(file, mode, *args, **kwargs)
                if not isinstance(file, int) and Path(file) == target and mode == "rb":
                    return RewriteAfterRead(stream)
                return stream
            return open_entry

        with patch("builtins.open", intercept(original_open)), \
                patch("io.open", intercept(original_io_open)):
            call, metadata = self.load(self.spec)
        self.assertTrue(reads, "The race must occur at an actual entry-file read")
        with self.subTest("executed captured bytes"):
            self.assertEqual(call({}), "captured")
        with self.subTest("reported captured bytes"):
            self.assert_identity(metadata, captured)
        self.assertEqual(self.path.read_bytes(), replacement)

    def test_import_rewrite_does_not_change_loaded_identity(self):
        replacement = b"def agent(obs): return 'replacement'\n"
        source = self.write((
            "from pathlib import Path\n"
            f"Path(__file__).write_bytes({replacement!r})\n"
            "def agent(obs): return 'original'\n"
        ).encode())
        call, metadata = self.load(self.spec)
        self.assertEqual(call({}), "original")
        self.assert_identity(metadata, source)
        self.assertEqual(self.path.read_bytes(), replacement)

    def test_import_removal_does_not_change_loaded_identity(self):
        source = self.write(
            b"from pathlib import Path\n"
            b"Path(__file__).unlink()\n"
            b"def agent(obs): return 'loaded'\n"
        )
        call, metadata = self.load(self.spec)
        self.assertFalse(self.path.exists())
        self.assertEqual(call({}), "loaded")
        self.assert_identity(metadata, source)

    def test_later_source_change_does_not_relabel_existing_callable(self):
        source = self.write(b"def agent(obs): return 'first'\n")
        call, metadata = self.load(self.spec)
        self.write(b"def agent(obs): return 'later'\n")
        self.assertEqual(call({}), "first")
        self.assert_identity(metadata, source)

    def test_fresh_load_observes_new_bytes_and_fresh_module_state(self):
        first_source = self.write(
            b"calls = 0\n"
            b"def agent(obs):\n"
            b"    global calls\n"
            b"    calls += 1\n"
            b"    return 'first', calls\n"
        )
        first, first_identity = self.load(self.spec)
        second_source = self.write(first_source.replace(b"'first'", b"'second'"))
        second, second_identity = self.load(self.spec)
        self.assertEqual([first({}), first({}), second({})],
                         [("first", 1), ("first", 2), ("second", 1)])
        self.assert_identity(first_identity, first_source)
        self.assert_identity(second_identity, second_source)

    def test_encoding_cookie_and_raw_byte_digest(self):
        source = self.write(
            b"# coding: latin-1\n"
            b"def agent(obs): return 'caf\xe9'\n"
        )
        call, metadata = self.load(self.spec)
        self.assertEqual(call({}), "caf\u00e9")
        self.assert_identity(metadata, source)

    def test_utf8_bom_and_raw_byte_digest(self):
        source = self.write(b"\xef\xbb\xbfdef agent(obs): return 'snow \xe2\x98\x83'\n")
        call, metadata = self.load(self.spec)
        self.assertEqual(call({}), "snow \u2603")
        self.assert_identity(metadata, source)

    def test_module_metadata_and_code_filename_are_preserved(self):
        self.write(
            b"def agent(obs):\n"
            b"    return (__name__, __file__, __package__, __cached__, "
            b"__spec__.name, __spec__.origin, __loader__ is __spec__.loader, "
            b"agent.__code__.co_filename)\n"
        )
        call, _ = self.load(self.spec)
        name, file, package, cached, spec_name, origin, same_loader, filename = call({})
        self.assertEqual(name, f"cont_{abs(hash(str(self.path) + 'agent'))}")
        self.assertEqual(file, str(self.path))
        self.assertEqual(package, "")
        self.assertEqual(cached, importlib.util.cache_from_source(str(self.path)))
        self.assertEqual(spec_name, name)
        self.assertEqual(origin, file)
        self.assertTrue(same_loader)
        self.assertEqual(filename, file)

    def test_standalone_agent_identity_retains_readonly_contract(self):
        source = self.write(b"raise AssertionError('identity must not execute')\n")
        self.assert_identity(self.namespace["agent_identity"](self.spec), source)
        self.path.unlink()
        metadata = self.namespace["agent_identity"](self.spec)
        self.assertIsNone(metadata["sha256"])
        self.assertEqual(metadata["path"], str(self.path))
        self.assertEqual(metadata["label"], "policy.py::agent@?")

    def test_missing_entry_file_raises_file_error(self):
        with self.assertRaises(FileNotFoundError) as caught:
            self.load(self.spec)
        self.assertEqual(caught.exception.filename, str(self.path))

    def test_missing_entrypoint_raises_attribute_error(self):
        self.write(b"def other(obs): return obs\n")
        with self.assertRaises(AttributeError):
            self.load(self.spec)

    def test_syntax_error_retains_entry_filename(self):
        self.write(b"def agent(obs)\n    return obs\n")
        with self.assertRaises(SyntaxError) as caught:
            self.load(self.spec)
        self.assertEqual(caught.exception.filename, str(self.path))

    def test_import_exception_propagates_same_object(self):
        helper = ModuleType("_continuation_source_error")
        helper.error = RuntimeError("entry module failed during import")
        self.write(b"from _continuation_source_error import error\nraise error\n")
        with patch.dict(sys.modules, {helper.__name__: helper}):
            with self.assertRaises(RuntimeError) as caught:
                self.load(self.spec)
        self.assertIs(caught.exception, helper.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
