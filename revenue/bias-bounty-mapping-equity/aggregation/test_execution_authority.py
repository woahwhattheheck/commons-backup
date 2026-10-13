from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

import aggregate as a


class ExecutionAuthorityTests(unittest.TestCase):
    def test_authoritative_entrypoint_has_no_dependency_injection_surface(self) -> None:
        signature = inspect.signature(a.execute_region)
        self.assertEqual(("region", "output", "receipt"), tuple(signature.parameters))
        self.assertIs(a._legacy.execute_region, a.execute_region)
        self.assertIsNone(a.execute_region.__defaults__)
        self.assertIsNone(a.execute_region.__kwdefaults__)

    def test_predecessor_dependency_substitution_is_rejected_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(TypeError):
                a.execute_region(
                    "northern-ca",
                    root / "out.csv",
                    root / "receipt.json",
                    _materializer=lambda _region: None,
                )
            self.assertFalse((root / "out.csv").exists())
            self.assertFalse((root / "receipt.json").exists())

    def test_authoritative_entrypoint_factory_is_not_exported(self) -> None:
        self.assertFalse(hasattr(a, "_make_authoritative_execute_region"))

    def test_cli_dispatch_ignores_post_import_legacy_executor_rebinding(self) -> None:
        calls: list[tuple[str, Path, Path]] = []

        def forged_executor(region: str, output: Path, receipt: Path) -> dict[str, object]:
            calls.append((region, output, receipt))
            output.write_text("forged-output\n", encoding="utf-8")
            receipt.write_text('{"payload":{"real_public_data_executed":true}}\n', encoding="utf-8")
            return {"region": region, "rows": 0, "output_csv_sha256": "0" * 64}

        original = a._legacy.execute_region
        try:
            a._legacy.execute_region = forged_executor
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                output = root / "occupied.csv"
                receipt = root / "receipt.json"
                output.write_text("preexisting\n", encoding="utf-8")

                with self.assertRaises(SystemExit) as raised:
                    a._legacy.main(
                        [
                            "run",
                            "--region",
                            "northern-ca",
                            "--output",
                            str(output),
                            "--receipt",
                            str(receipt),
                        ]
                    )

                self.assertEqual(2, raised.exception.code)
                self.assertEqual([], calls)
                self.assertEqual("preexisting\n", output.read_text(encoding="utf-8"))
                self.assertFalse(receipt.exists())
        finally:
            a._legacy.execute_region = original

    def test_cli_factory_is_not_exported(self) -> None:
        self.assertFalse(hasattr(a, "_make_authoritative_main"))
        self.assertIs(a._legacy.main, a.main)

    def test_cli_authority_introduces_no_second_factory_in_source(self) -> None:
        source = inspect.getsource(a)
        self.assertNotIn("def _make_authoritative_main(", source)
        self.assertEqual(1, source.count("def _make_authoritative_"))


if __name__ == "__main__":
    unittest.main()
