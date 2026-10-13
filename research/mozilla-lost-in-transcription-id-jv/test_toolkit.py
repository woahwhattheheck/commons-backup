#!/usr/bin/env python3
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from toolkit import (
    build_submission_zip,
    corpus_wer,
    inspect_submission_zip,
    normalize_for_scoring,
    stable_split,
    validate_submission_rows,
    write_split_manifest,
)


class NormalizeTests(unittest.TestCase):
    def test_annotations_and_wrappers(self):
        self.assertEqual(
            normalize_for_scoring('Halo [noise] (dunia) (?) "Ya"!'),
            "halo dunia Ya",
        )

    def test_sentence_initial_and_acronym(self):
        self.assertEqual(normalize_for_scoring("Halo. API Bagus"), "halo API Bagus")

    def test_ellipsis_preserved(self):
        self.assertEqual(normalize_for_scoring("Tunggu ... sebentar."), "tunggu sebentar")

    def test_apostrophe_entity(self):
        self.assertEqual(normalize_for_scoring("Itu #x27;oke#x27;"), "itu 'oke'")


class WerTests(unittest.TestCase):
    def test_exact_after_normalization(self):
        counts = corpus_wer(["Halo, dunia!"], ["halo dunia"])
        self.assertEqual(counts.wer, 0.0)

    def test_substitution(self):
        counts = corpus_wer(["satu dua tiga"], ["satu lima tiga"])
        self.assertEqual((counts.substitutions, counts.deletions, counts.insertions), (1, 0, 0))
        self.assertAlmostEqual(counts.wer, 1 / 3)

    def test_corpus_aggregation(self):
        counts = corpus_wer(["a b", "c d"], ["a", "c d e"])
        self.assertEqual(counts.reference_words, 4)
        self.assertEqual(counts.deletions + counts.insertions + counts.substitutions, 2)
        self.assertEqual(counts.wer, 0.5)


class ContractTests(unittest.TestCase):
    def test_submission_exact_coverage(self):
        expected = [{"audio_filename": "a.wav"}, {"audio_filename": "b.wav"}]
        predicted = [
            {"audio_filename": "b.wav", "transcript": "b"},
            {"audio_filename": "a.wav", "transcript": "a"},
        ]
        validate_submission_rows(expected, predicted)

    def test_submission_missing_fails(self):
        expected = [{"audio_filename": "a.wav"}, {"audio_filename": "b.wav"}]
        predicted = [{"audio_filename": "a.wav", "transcript": "a"}]
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            validate_submission_rows(expected, predicted)

    def test_submission_extra_column_fails(self):
        expected = [{"audio_filename": "a.wav"}]
        predicted = [{"audio_filename": "a.wav", "transcript": "a", "score": "1"}]
        with self.assertRaisesRegex(ValueError, "exactly"):
            validate_submission_rows(expected, predicted)


class SplitTests(unittest.TestCase):
    def test_stable(self):
        rows = [{"audio_filename": f"{i}.wav"} for i in range(100)]
        self.assertEqual(stable_split(rows), stable_split(rows))

    def test_group_stays_together(self):
        rows = [
            {"audio_filename": "a.wav", "session": "x"},
            {"audio_filename": "b.wav", "session": "x"},
            {"audio_filename": "c.wav", "session": "y"},
        ]
        labels = stable_split(rows, group_column="session")
        self.assertEqual(labels[0], labels[1])

    def test_manifest_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "metadata.csv"
            out = Path(td) / "split.csv"
            with src.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["audio_filename", "session"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"audio_filename": "a.wav", "session": "x"},
                        {"audio_filename": "b.wav", "session": "y"},
                    ]
                )
            write_split_manifest(src, out, group_column="session")
            with out.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(set(rows[0]), {"audio_filename", "session", "split"})


class ZipTests(unittest.TestCase):
    def test_deterministic_zip_and_root_main(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            src.mkdir()
            (src / "main.py").write_text("print('ok')\n", encoding="utf-8")
            (src / "model.txt").write_text("fixture\n", encoding="utf-8")
            z1 = Path(td) / "one.zip"
            z2 = Path(td) / "two.zip"
            h1 = build_submission_zip(src, z1)
            h2 = build_submission_zip(src, z2)
            self.assertEqual(h1, h2)
            self.assertEqual(z1.read_bytes(), z2.read_bytes())
            self.assertIn("main.py", inspect_submission_zip(z1))

    def test_missing_main_fails(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            src.mkdir()
            with self.assertRaisesRegex(ValueError, "main.py"):
                build_submission_zip(src, Path(td) / "bad.zip")


if __name__ == "__main__":
    unittest.main()
