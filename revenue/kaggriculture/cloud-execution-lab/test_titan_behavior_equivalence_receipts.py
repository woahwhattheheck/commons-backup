#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import multiprocessing

from titan_behavior_equivalence_test_support import *


def _append_worker(ledger_path: str, worker_id: int, count: int) -> None:
    report = gate.preflight_family(family_raw())
    for index in range(count):
        gate.append_ledger(
            ledger_path,
            report,
            f"worker-{worker_id:02d}-entry-{index:02d}",
        )


class LedgerAndCliTests(unittest.TestCase):
    def test_append_only_ledger_verifies_and_detects_tamper(self) -> None:
        report = gate.preflight_family(family_raw())
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            first = gate.append_ledger(ledger, report, "preflight")
            second = gate.append_ledger(ledger, report, "preflight-repeat")
            entries = gate.verify_ledger(ledger)
            self.assertEqual(2, len(entries))
            self.assertEqual(first["entry_sha256"], second["previous_entry_sha256"])
            lines = ledger.read_text(encoding="utf-8").splitlines()
            tampered = json.loads(lines[0])
            tampered["kind"] = "tampered"
            lines[0] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
            ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(gate.BehaviorGateError, "entry_sha256 mismatch"):
                gate.verify_ledger(ledger)

    def test_unterminated_or_noncanonical_ledger_is_refused_without_mutation(self) -> None:
        report = gate.preflight_family(family_raw())
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            gate.append_ledger(ledger, report, "preflight")
            canonical = ledger.read_bytes()

            unterminated = canonical[:-1]
            ledger.write_bytes(unterminated)
            with self.assertRaisesRegex(gate.BehaviorGateError, "final newline"):
                gate.verify_ledger(ledger)
            with self.assertRaisesRegex(gate.BehaviorGateError, "final newline"):
                gate.append_ledger(ledger, report, "must-not-write")
            self.assertEqual(unterminated, ledger.read_bytes())

            entry = json.loads(canonical.decode("utf-8"))
            noncanonical = (
                json.dumps(entry, sort_keys=False, separators=(", ", ": ")).encode("utf-8")
                + b"\n"
            )
            ledger.write_bytes(noncanonical)
            with self.assertRaisesRegex(gate.BehaviorGateError, "not canonical JSON"):
                gate.verify_ledger(ledger)

    def test_concurrent_appenders_form_one_contiguous_chain(self) -> None:
        workers = 4
        entries_per_worker = 6
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            context = multiprocessing.get_context("spawn")
            processes = [
                context.Process(
                    target=_append_worker,
                    args=(str(ledger), worker_id, entries_per_worker),
                )
                for worker_id in range(workers)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(30)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
                self.assertEqual(0, process.exitcode)

            entries = gate.verify_ledger(ledger)
            expected_count = workers * entries_per_worker
            self.assertEqual(expected_count, len(entries))
            self.assertEqual(list(range(expected_count)), [entry["sequence"] for entry in entries])
            self.assertEqual(
                {f"worker-{worker_id:02d}-entry-{index:02d}" for worker_id in range(workers) for index in range(entries_per_worker)},
                {entry["kind"] for entry in entries},
            )

    def test_invalid_report_receipt_cannot_be_appended(self) -> None:
        report = gate.preflight_family(family_raw())
        report["verdict"] = "FORGED"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(gate.BehaviorGateError, "report receipt is invalid"):
                gate.append_ledger(Path(directory) / "ledger.jsonl", report, "preflight")

    def test_cli_writes_json_markdown_and_ledger(self) -> None:
        family = family_raw()
        observations = observations_raw(family)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            family_path = root / "family.json"
            observations_path = root / "observations.json"
            report_path = root / "report.json"
            markdown_path = root / "report.md"
            ledger_path = root / "ledger.jsonl"
            family_path.write_text(json.dumps(family), encoding="utf-8")
            observations_path.write_text(json.dumps(observations), encoding="utf-8")
            result = gate.main(
                [
                    "analyze",
                    "--family",
                    str(family_path),
                    "--observations",
                    str(observations_path),
                    "--json-out",
                    str(report_path),
                    "--markdown-out",
                    str(markdown_path),
                    "--ledger",
                    str(ledger_path),
                ]
            )
            self.assertEqual(0, result)
            self.assertEqual("PASS", json.loads(report_path.read_text())["verdict"])
            self.assertIn("Statistical boundary", markdown_path.read_text())
            self.assertEqual(1, len(gate.verify_ledger(ledger_path)))

    def test_cli_returns_two_for_duplicate_executable_family(self) -> None:
        family = family_raw(closures=(digest("a"), digest("a")))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "family.json"
            output = Path(directory) / "preflight.json"
            path.write_text(json.dumps(family), encoding="utf-8")
            result = gate.main(["preflight", "--family", str(path), "--json-out", str(output)])
            self.assertEqual(2, result)
            self.assertEqual("REFUSED_DUPLICATE_EXECUTABLES", json.loads(output.read_text())["verdict"])
