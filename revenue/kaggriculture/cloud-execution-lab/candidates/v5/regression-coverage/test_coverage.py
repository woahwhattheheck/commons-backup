import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import coverage as target


GOOD_V31_RUNTIME = b"""
class TitanAgent:
    def act(self, observation, configuration=None, *, entry_started=None):
        invoked = time.perf_counter()
        if self.features.r03_full_router or self.features.r04_sale_window:
            return self._v3_r03_act(observation, configuration, invoked, entry_started)
        if not self.ready:
            self._initialize()
        return None

    def _v3_r03_act(self, observation, configuration, invoked, entry_started):
        route = "r04_sale_window" if self.features.r04_sale_window else "r03_full_router"
        try:
            if route == "r04_sale_window":
                from r04_full_router import install
                output = install(self)(observation, configuration)
            else:
                output = None
        except Exception:
            return None
        return output
"""

GOOD_V4_RUNTIME = b"""
class TitanAgent:
    def act(self, observation, configuration=None, *, entry_started=None):
        if not self.ready:
            self._initialize()
        return None
"""

GOOD_ROUTER = b"""
def v3_agent(observation, configuration):
    return None

def install(host=None):
    return v3_agent
"""


def fixture(v31_runtime=GOOD_V31_RUNTIME, router=GOOD_ROUTER):
    return (
        {
            "TITAN-CONFIG.json": json.dumps({"r04_sale_window": True}).encode(),
            "titan_runtime.py": v31_runtime,
            "r04_full_router.py": router,
        },
        {
            "TITAN-CONFIG.json": b"{}",
            "titan_runtime.py": GOOD_V4_RUNTIME,
        },
    )


class CoverageHelpersTest(unittest.TestCase):
    def _tar(self, members, *, symlink=None):
        tmp = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
        tmp.close()
        path = Path(tmp.name)
        with tarfile.open(path, "w:gz") as tf:
            for name, raw in members:
                info = tarfile.TarInfo(name)
                info.size = len(raw)
                tf.addfile(info, io.BytesIO(raw))
            if symlink is not None:
                info = tarfile.TarInfo(symlink)
                info.type = tarfile.SYMTYPE
                info.linkname = "target"
                tf.addfile(info)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_normalize_rejects_escape_absolute_and_backslash(self):
        for value in ("../x", "/x", "a/../../b", "a\\b", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                target.normalize_member_path(value)
        self.assertEqual(target.normalize_member_path("./a/b"), "a/b")

    def test_archive_inventory_rejects_duplicate(self):
        path = self._tar([("./a", b"one"), ("a", b"two")])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            target.archive_inventory(path)

    def test_archive_inventory_rejects_symlink_member(self):
        path = self._tar([("a", b"one")], symlink="link")
        with self.assertRaisesRegex(ValueError, "non-regular"):
            target.archive_inventory(path)

    def test_archive_inventory_rejects_symlink_authority(self):
        target_file = self._tar([("a", b"one")])
        link = target_file.with_name(target_file.name + ".link")
        link.symlink_to(target_file)
        self.addCleanup(link.unlink, missing_ok=True)
        with self.assertRaisesRegex(ValueError, "ordinary file"):
            target.archive_inventory(link)

    def test_archive_inventory_uses_single_capture_after_swap(self):
        path = self._tar([("a", b"trusted")])
        trusted = path.read_bytes()
        poison = self._tar([("a", b"poison")]).read_bytes()
        original = Path.read_bytes

        def read_then_swap(value):
            raw = original(value)
            value.write_bytes(poison)
            return raw

        with mock.patch.object(Path, "read_bytes", new=read_then_swap):
            inventory, contents = target.archive_inventory(path)
        self.assertEqual(inventory["archive_sha256"], target.sha256_bytes(trusted))
        self.assertEqual(contents["a"], b"trusted")
        self.assertEqual(path.read_bytes(), poison)

    def test_archive_inventory_uses_single_capture_after_delete(self):
        path = self._tar([("a", b"trusted")])
        trusted = path.read_bytes()
        original = Path.read_bytes

        def read_then_delete(value):
            raw = original(value)
            value.unlink()
            return raw

        with mock.patch.object(Path, "read_bytes", new=read_then_delete):
            inventory, contents = target.archive_inventory(path)
        self.assertEqual(inventory["archive_sha256"], target.sha256_bytes(trusted))
        self.assertEqual(contents["a"], b"trusted")
        self.assertFalse(path.exists())

    def test_pair_summary(self):
        left = {"members": {"a": {"sha256":"1","size":1}, "b":{"sha256":"2","size":1}}}
        right = {"members": {"a": {"sha256":"1","size":1}, "b":{"sha256":"3","size":1}, "c":{"sha256":"4","size":1}}}
        self.assertEqual(target.pair_summary(left, right), {
            "common_count":2,"identical_common_count":1,"changed_common_count":1,
            "v31_only_count":0,"v4_only_count":1,"changed_common_paths":["b"],"v4_only_paths":["c"]})

    def test_config_delta(self):
        got = target.config_delta(json.dumps({"same":1,"old":2}).encode(), json.dumps({"same":1,"new":3}).encode())
        self.assertEqual(got["common_equal_count"], 1)
        self.assertEqual(got["changed_common"], {})
        self.assertEqual(got["v31_only"], {"old":2})
        self.assertEqual(got["v4_only"], {"new":3})

    def test_changed_symbols(self):
        left = b"x=1\ndef f():\n return 1\nclass C:\n def m(self):\n  return 1\n"
        right = b"x=2\ndef f():\n return 2\nclass C:\n def m(self):\n  return 1\n"
        self.assertEqual(target.changed_symbols(left, right), ["f", "__module__"])

    def test_manifest_digest_is_canonical(self):
        a = {"b":1,"a":2}
        b = {"a":2,"b":1}
        self.assertEqual(target.sha256_bytes(target.canonical_json(a)), target.sha256_bytes(target.canonical_json(b)))

    def test_reachability_derives_complete_metadata(self):
        v31, v4 = fixture()
        self.assertEqual(target.derive_reachability(v31, v4), {
            "v31_active_route": {
                "canonical_controller_bypassed": True,
                "config_key": "r04_sale_window",
                "config_value": True,
                "delegate_factory": "install",
                "delegate_method": "TitanAgent._v3_r03_act",
                "delegate_module": "r04_full_router.py",
                "delegate_return": "v3_agent",
                "runtime_member": "titan_runtime.py",
            },
            "v4_active_route": {
                "canonical_runtime_path": True,
                "r04_full_router_member_present": False,
                "r04_sale_window_present": False,
            },
        })

    def test_reachability_rejects_unreachable_nested_guard(self):
        bad = GOOD_V31_RUNTIME.replace(
            b"        if self.features.r03_full_router or self.features.r04_sale_window:\n"
            b"            return self._v3_r03_act(observation, configuration, invoked, entry_started)\n",
            b"        if False:\n"
            b"            if self.features.r03_full_router or self.features.r04_sale_window:\n"
            b"                return self._v3_r03_act(observation, configuration, invoked, entry_started)\n",
        )
        v31, v4 = fixture(bad)
        with self.assertRaisesRegex(ValueError, "direct active R03/R04 guard"):
            target.derive_reachability(v31, v4)

    def test_reachability_rejects_wrong_guard(self):
        bad = GOOD_V31_RUNTIME.replace(b"self.features.r04_sale_window", b"self.features.crop_release", 1)
        v31, v4 = fixture(bad)
        with self.assertRaisesRegex(ValueError, "direct active R03/R04 guard"):
            target.derive_reachability(v31, v4)

    def test_v31_requires_initializer_in_method_scope(self):
        definitions = (
            b"def never_called():\n                self._initialize()",
            b"async def never_called():\n                self._initialize()",
            b"class Helper:\n                def never_called(self):\n                    self._initialize()",
            b"never_called = lambda: self._initialize()",
        )
        for definition in definitions:
            with self.subTest(definition=definition):
                v31, v4 = fixture(GOOD_V31_RUNTIME.replace(
                    b"            self._initialize()", b"            " + definition, 1))
                with self.assertRaisesRegex(ValueError, "V3.1 canonical initialization path missing"):
                    target.derive_reachability(v31, v4)

    def test_v4_requires_initializer_in_method_scope(self):
        definitions = (
            b"def never_called():\n                self._initialize()",
            b"async def never_called():\n                self._initialize()",
            b"class Helper:\n                def never_called(self):\n                    self._initialize()",
            b"never_called = lambda: self._initialize()",
        )
        for definition in definitions:
            with self.subTest(definition=definition):
                v31, v4 = fixture()
                v4["titan_runtime.py"] = GOOD_V4_RUNTIME.replace(
                    b"            self._initialize()", b"            " + definition, 1)
                with self.assertRaisesRegex(ValueError, "V4 canonical initialization path missing"):
                    target.derive_reachability(v31, v4)

    def test_dead_helper_before_guard_does_not_move_initialization(self):
        original = b"        invoked = time.perf_counter()"
        helper = (b"        def never_called():\n"
                  b"            self._initialize()\n" + original)
        v31, v4 = fixture(GOOD_V31_RUNTIME.replace(original, helper, 1))
        expected = target.derive_reachability(*fixture())
        self.assertEqual(target.derive_reachability(v31, v4), expected)

    def test_reachability_rejects_wrong_delegate_arguments(self):
        bad = GOOD_V31_RUNTIME.replace(
            b"return self._v3_r03_act(observation, configuration, invoked, entry_started)",
            b"return self._v3_r03_act(observation, configuration)",
            1,
        )
        v31, v4 = fixture(bad)
        with self.assertRaisesRegex(ValueError, "directly return"):
            target.derive_reachability(v31, v4)

    def test_reachability_rejects_wrong_factory_return(self):
        v31, v4 = fixture(router=GOOD_ROUTER.replace(b"return v3_agent", b"return None", 1))
        with self.assertRaisesRegex(ValueError, "directly return v3_agent"):
            target.derive_reachability(v31, v4)

    def test_reachability_rejects_metadata_drift(self):
        v31, v4 = fixture()
        declared = target.derive_reachability(v31, v4)
        declared["v31_active_route"]["delegate_return"] = "other"
        with self.assertRaisesRegex(ValueError, "metadata drift"):
            target.verify_v31_route_authority(v31, v4, {"reachability": declared})


if __name__ == "__main__":
    unittest.main()
