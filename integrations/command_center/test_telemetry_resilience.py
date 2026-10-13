"""Fail-soft host telemetry regressions; all synthetic inputs are explicit.

Run from repository root:
    python -m unittest integrations.command_center.test_telemetry_resilience -v
"""
import ctypes
import json
import unittest
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from integrations.command_center import telemetry


class TelemetryResilienceTests(unittest.TestCase):
    def observe(self, text="MemTotal: 8388608 kB\nMemAvailable: 3145728 kB\n",
                *, system="Linux", disk_error=None, read_error=None, cpu=4):
        disk = SimpleNamespace(total=100 * 2**30, free=25 * 2**30)
        with ExitStack() as stack:
            stack.enter_context(patch.object(telemetry.platform, "system", return_value=system))
            stack.enter_context(patch.object(telemetry.platform, "node", return_value="synthetic-host"))
            stack.enter_context(patch.object(telemetry.os, "cpu_count", return_value=cpu))
            stack.enter_context(patch.object(telemetry.shutil, "disk_usage",
                                             return_value=disk, side_effect=disk_error))
            read = stack.enter_context(patch.object(Path, "read_text",
                                                    return_value=text, side_effect=read_error))
            item = telemetry.host_observation("/synthetic/state")
        # Measurements returned by this interface must be strict JSON.
        json.dumps(item, allow_nan=False)
        self.assertEqual(item["disk_gib"], None if disk_error else 100)
        self.assertEqual(item["disk_free_gib"], None if disk_error else 25)
        self.assertEqual(item["workspace"], "/synthetic/state")
        self.assertEqual(item["id"], "host:synthetic-host")
        self.assertEqual(item["cpu"], cpu)
        self.assertEqual(item["cpu_measure"], "logical_processors")
        self.assertIsNone(item["gpu"])
        self.assertEqual(item["status"], "observed")
        self.assertEqual(datetime.fromisoformat(item["observed_at"].replace("Z", "+00:00")).utcoffset().total_seconds(), 0)
        if system == "Linux":
            read.assert_called_once()
        else:
            read.assert_not_called()
        return item

    def assert_ram(self, text, total, available):
        item = self.observe(text)
        self.assertEqual(item["ram_gib"], total)
        self.assertEqual(item["ram_available_gib"], available)

    def test_valid_memory_and_existing_metadata(self):
        self.assert_ram("MemTotal: 8388608 kB\nMemAvailable: 3145728 kB\n", 8, 3)

    def test_rounding_is_unchanged(self):
        self.assert_ram("MemTotal: 1572864 kB\nMemAvailable: 1294538 kB\n", 1.5, 1.23)

    def test_zero_is_a_measurement_not_missing(self):
        self.assert_ram("MemTotal: 0 kB\nMemAvailable: 0 kB\n", 0, 0)

    def test_kernel_style_whitespace(self):
        self.assert_ram("MemTotal:\t 8388608\t kB \nMemAvailable:  3145728   kB\n", 8, 3)

    def test_empty_file_leaves_memory_unknown(self):
        self.assert_ram("", None, None)

    def test_missing_total_preserves_available(self):
        self.assert_ram("MemAvailable: 3145728 kB\n", None, 3)

    def test_missing_available_preserves_total(self):
        self.assert_ram("MemTotal: 8388608 kB\n", 8, None)

    def test_truncated_total_does_not_abort_observation(self):
        self.assert_ram("MemTotal:\nMemAvailable: 3145728 kB\n", None, 3)

    def test_truncated_available_preserves_total(self):
        self.assert_ram("MemTotal: 8388608 kB\nMemAvailable:\n", 8, None)

    def test_nonnumeric_total_preserves_available(self):
        self.assert_ram("MemTotal: unavailable kB\nMemAvailable: 3145728 kB\n", None, 3)

    def test_nonnumeric_available_preserves_total(self):
        self.assert_ram("MemTotal: 8388608 kB\nMemAvailable: unavailable kB\n", 8, None)

    def test_negative_total_is_not_capacity(self):
        self.assert_ram("MemTotal: -1048576 kB\nMemAvailable: 3145728 kB\n", None, 3)

    def test_negative_available_is_not_capacity(self):
        self.assert_ram("MemTotal: 8388608 kB\nMemAvailable: -1048576 kB\n", 8, None)

    def test_missing_unit_is_not_assumed_to_be_kib(self):
        self.assert_ram("MemTotal: 8388608\nMemAvailable: 3145728 kB\n", None, 3)

    def test_wrong_unit_is_not_misreported_as_gib(self):
        self.assert_ram("MemTotal: 8388608 MB\nMemAvailable: 3145728 kB\n", None, 3)

    def test_extra_tokens_are_not_silently_ignored(self):
        self.assert_ram("MemTotal: 8388608 kB damaged\nMemAvailable: 3145728 kB\n", None, 3)

    def test_huge_integer_does_not_overflow_the_endpoint(self):
        self.assert_ram("MemTotal: " + "9" * 600 + " kB\nMemAvailable: 3145728 kB\n", None, 3)

    def test_fraction_is_invalid_but_other_measurement_survives(self):
        self.assert_ram("MemTotal: 8.5 kB\nMemAvailable: 3145728 kB\n", None, 3)

    def test_nonfinite_tokens_leave_only_that_value_unknown(self):
        for value in ("NaN", "Infinity", "-Infinity", "1e309"):
            with self.subTest(value=value):
                self.assert_ram(f"MemTotal: {value} kB\nMemAvailable: 3145728 kB\n", None, 3)

    def test_non_ascii_digits_are_not_kernel_measurements(self):
        self.assert_ram("MemTotal: ８３８８６０８ kB\nMemAvailable: 3145728 kB\n", None, 3)

    def test_unrelated_malformed_rows_are_ignored(self):
        self.assert_ram("Other:\nMemTotal: 8388608 kB\nBuffers: invalid\nMemAvailable: 3145728 kB\n", 8, 3)

    def test_similar_key_names_do_not_match(self):
        self.assert_ram("MemTotalExtra: 8388608 kB\nMemAvailableExtra: 3145728 kB\n", None, None)

    def test_valid_later_duplicate_wins_as_before(self):
        self.assert_ram("MemTotal: 1048576 kB\nMemTotal: 8388608 kB\nMemAvailable: 3145728 kB\n", 8, 3)

    def test_malformed_duplicate_does_not_erase_good_measurement(self):
        self.assert_ram("MemTotal: 8388608 kB\nMemTotal: broken kB\nMemAvailable: 3145728 kB\n", 8, 3)

    def test_read_error_preserves_cpu_and_disk(self):
        item = self.observe(read_error=OSError("synthetic missing procfs"))
        self.assertIsNone(item["ram_gib"])
        self.assertIsNone(item["ram_available_gib"])

    def test_decode_error_preserves_cpu_and_disk(self):
        item = self.observe(read_error=UnicodeDecodeError("ascii", b"\xff", 0, 1, "synthetic"))
        self.assertIsNone(item["ram_gib"])
        self.assertIsNone(item["ram_available_gib"])

    def test_disk_error_does_not_remove_good_memory(self):
        item = self.observe(disk_error=OSError("synthetic unavailable disk"))
        self.assertEqual(item["ram_gib"], 8)
        self.assertEqual(item["ram_available_gib"], 3)

    def test_unsupported_platform_keeps_memory_unknown(self):
        item = self.observe(system="Darwin")
        self.assertIsNone(item["ram_gib"])
        self.assertIsNone(item["ram_available_gib"])

    def test_unknown_cpu_count_remains_unknown(self):
        self.observe(cpu=None)

    def test_windows_success_keeps_existing_api_behavior(self):
        def memory_status(pointer):
            pointer._obj.total = 16 * 2**30
            pointer._obj.available = 5 * 2**30
            self.assertEqual(pointer._obj.length, ctypes.sizeof(pointer._obj))
            return 1
        dll = SimpleNamespace(kernel32=SimpleNamespace(GlobalMemoryStatusEx=memory_status))
        with patch.object(telemetry.ctypes, "windll", dll, create=True):
            item = self.observe(system="Windows")
        self.assertEqual(item["ram_gib"], 16)
        self.assertEqual(item["ram_available_gib"], 5)

    def test_windows_api_failure_keeps_memory_unknown(self):
        dll = SimpleNamespace(kernel32=SimpleNamespace(GlobalMemoryStatusEx=lambda _: 0))
        with patch.object(telemetry.ctypes, "windll", dll, create=True):
            item = self.observe(system="Windows")
        self.assertIsNone(item["ram_gib"])
        self.assertIsNone(item["ram_available_gib"])

    def test_with_host_retains_session_payload_and_other_state(self):
        state = {"sessions": [{"id": "existing-peer"}], "revision": 7}
        observed = {"id": "synthetic-observation"}
        with patch.object(telemetry, "host_observation", return_value=observed) as observe:
            result = telemetry.with_host(SimpleNamespace(state_dir="/synthetic/state"), state)
        observe.assert_called_once_with("/synthetic/state")
        self.assertEqual(result["sessions"], [observed, {"id": "existing-peer"}])
        self.assertEqual(result["machines"], [observed])
        self.assertEqual(result["revision"], 7)
        self.assertEqual(state, {"sessions": [{"id": "existing-peer"}], "revision": 7})


if __name__ == "__main__":
    unittest.main()
