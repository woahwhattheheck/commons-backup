from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from producer_surface_scan import (  # noqa: E402
    SCAN_SCHEMA,
    ScanError,
    canonical_sha256,
    scan_repository,
)


def write(root: Path, relative: str, content: str | bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


FULL_CYCLE = '''
class FarmPolicy:
    def use_fertilizer(self, tick):
        self.worker_action("fertilize", tick)

    def harvest_crop(self):
        return self.harvest_ready_crop()

    def deposit_in_shed(self, units):
        self.inventory.store(units)

    def sell_at_market(self):
        self.cash += self.market_price

    def protect_commitment(self):
        return self.reserve_stock_shortfall
'''


class ProducerSurfaceScanTests(unittest.TestCase):
    def test_detects_and_ranks_a_full_cycle_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "src/policy.py", FULL_CYCLE)
            write(root, "src/other.py", "def tick_worker():\n    return 1\n")
            result = scan_repository(root=root, scope=Path("src"))
            self.assertEqual(result["schema"], SCAN_SCHEMA)
            self.assertEqual(result["decision"], "SURFACE_FOUND")
            top = result["candidates"][0]
            self.assertEqual(top["path"], "src/policy.py")
            self.assertTrue(top["full_cycle_candidate"])
            self.assertTrue(
                {"fertilizer", "harvest", "storage", "sale_cash"}.issubset(
                    top["phases"]
                )
            )
            self.assertRegex(top["sha256"], r"^[0-9a-f]{64}$")

    def test_comments_alone_do_not_create_hits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(
                root,
                "src/comments.py",
                "# fertilizer harvest deposit sale cash tick\ndef noop():\n    return 1\n",
            )
            result = scan_repository(root=root, scope="src")
            self.assertEqual(result["decision"], "NO_SURFACE")
            self.assertEqual(result["candidates"], [])

    def test_string_and_identifier_hits_are_line_bound_to_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(
                root,
                "src/policy.py",
                "def fertilizer_quote():\n    return 'harvest then sell at market'\n",
            )
            result = scan_repository(root=root, scope="src")
            symbol = result["candidates"][0]["symbols"][0]
            self.assertEqual(symbol["name"], "fertilizer_quote")
            self.assertIn("fertilizer", symbol["phases"])
            self.assertIn("harvest", symbol["phases"])
            self.assertIn("sale_cash", symbol["phases"])

    def test_result_is_deterministic_and_self_hashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "src/b.py", FULL_CYCLE)
            write(
                root,
                "src/a.py",
                "def fertilizer_and_harvest():\n    return 1\n",
            )
            first = scan_repository(root=root, scope="src")
            second = scan_repository(root=root, scope="src")
            self.assertEqual(first, second)
            claimed = first.pop("result_sha256")
            self.assertEqual(claimed, canonical_sha256(first))
            self.assertEqual(
                [row["path"] for row in second["candidates"]],
                [row["path"] for row in first["candidates"]],
            )

    def test_scope_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            root.mkdir()
            with self.assertRaisesRegex(ScanError, "scope escapes root"):
                scan_repository(root=root, scope=Path("../outside"))

    def test_symlinked_scope_is_rejected(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unavailable")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            target = base / "target"
            root.mkdir()
            target.mkdir()
            try:
                (root / "linked").symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            with self.assertRaisesRegex(ScanError, "scope escapes root"):
                scan_repository(root=root, scope="linked")

    def test_oversized_file_is_recorded_without_reading_as_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "src/large.py", b"fertilizer harvest sale\n" * 20)
            result = scan_repository(root=root, scope="src", max_file_bytes=10)
            self.assertEqual(result["candidates"], [])
            self.assertEqual(
                result["skipped"],
                [{"path": "src/large.py", "reason": "oversized"}],
            )

    def test_syntax_error_is_visible_not_silently_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(
                root,
                "src/broken.py",
                "def fertilizer_harvest(:\n    return 'sell cash'\n",
            )
            result = scan_repository(root=root, scope="src")
            candidate = result["candidates"][0]
            self.assertTrue(candidate["parse_error"].startswith("SyntaxError:"))
            self.assertEqual(candidate["symbols"], [])

    def test_max_file_limit_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "src/a.py", "fertilizer = 1\n")
            write(root, "src/b.py", "harvest = 1\n")
            with self.assertRaisesRegex(ScanError, "exceeds max_files=1"):
                scan_repository(root=root, scope="src", max_files=1)

    def test_self_analysis_directory_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "analysis/w10-fertilizer-cycle/self.py", FULL_CYCLE)
            write(
                root,
                "producer.py",
                "def fertilizer_then_harvest():\n    return 1\n",
            )
            result = scan_repository(root=root, scope=".")
            self.assertNotIn(
                "analysis/w10-fertilizer-cycle/self.py",
                [row["path"] for row in result["candidates"]],
            )

    def test_cli_writes_report_and_returns_zero_for_surface(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "src/policy.py", FULL_CYCLE)
            output = root / "report.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "producer_surface_scan.py"),
                    "--root",
                    str(root),
                    "--scope",
                    "src",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                json.loads(output.read_text())["decision"], "SURFACE_FOUND"
            )

    def test_cli_returns_one_without_surface_unless_allow_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "src/noop.py", "def noop():\n    return 1\n")
            base = [
                sys.executable,
                str(HERE / "producer_surface_scan.py"),
                "--root",
                str(root),
                "--scope",
                "src",
            ]
            rejected = subprocess.run(
                base, check=False, capture_output=True, text=True
            )
            allowed = subprocess.run(
                [*base, "--allow-empty"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertEqual(allowed.returncode, 0)


if __name__ == "__main__":
    unittest.main()
