#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path
import shutil
import tempfile
import unittest

from PIL import Image, ImageDraw, ImageFont

import baseline


class BaselineTests(unittest.TestCase):
    def test_contract_accepts_different_id_case_and_preserves_prediction_name(self) -> None:
        result = baseline.validate_contract(
            ["ID"], [{"ID": "b"}, {"ID": "a"}],
            ["id", "Target"], [{"id": "a", "Target": ""}, {"id": "b", "Target": ""}],
        )
        self.assertEqual(result, ("ID", "id", "Target"))

    def test_contract_rejects_mismatched_ids(self) -> None:
        with self.assertRaisesRegex(baseline.BaselineError, "ID sets differ"):
            baseline.validate_contract(
                ["ID"], [{"ID": "a"}],
                ["ID", "text"], [{"ID": "b", "text": ""}],
            )

    def test_resolver_accepts_stem_and_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "abc123.jpg"
            Image.new("L", (20, 20), 255).save(image)
            index = baseline.build_image_index(root)
            self.assertEqual(baseline.resolve_image("abc123", index), image)
            self.assertEqual(baseline.resolve_image("abc123.jpg", index), image)
            with self.assertRaisesRegex(baseline.BaselineError, "unsafe"):
                baseline.resolve_image("../abc123.jpg", index)

    def test_parse_tsv_uses_length_weighted_confidence(self) -> None:
        tsv = "text\tconf\nold\t80\nrecords\t90\n\t-1\n"
        text, confidence, words = baseline.parse_tsv(tsv)
        self.assertEqual(text, "old records")
        self.assertEqual(words, 2)
        self.assertAlmostEqual(confidence, (80 * 3 + 90 * 7) / 10)

    @unittest.skipUnless(shutil.which("tesseract"), "tesseract is not installed")
    def test_real_tesseract_pipeline_writes_schema_preserving_submission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            images = root / "images"
            images.mkdir()
            canvas = Image.new("L", (900, 140), 255)
            draw = ImageDraw.Draw(canvas)
            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 64
                )
            except OSError:
                font = ImageFont.load_default()
            draw.text((30, 25), "historic records", fill=0, font=font)
            canvas.save(images / "line-001.jpg")

            test_csv = root / "Test.csv"
            sample_csv = root / "SampleSubmission.csv"
            for path, columns, rows in (
                (test_csv, ["ID"], [["line-001"]]),
                (sample_csv, ["ID", "transcription"], [["line-001", ""]]),
            ):
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(columns)
                    writer.writerows(rows)

            output = root / "submission.csv"
            report = baseline.run(
                baseline.parser().parse_args(
                    [
                        "--test-csv", str(test_csv),
                        "--sample-submission", str(sample_csv),
                        "--images-dir", str(images),
                        "--output", str(output),
                        "--psms", "7",
                    ]
                )
            )
            self.assertEqual(report["state"], "BASELINE_COMPLETE")
            self.assertEqual(report["empty_predictions"], 0)
            header, rows = baseline.read_csv(output)
            self.assertEqual(header, ["ID", "transcription"])
            self.assertEqual(rows[0]["ID"], "line-001")
            self.assertTrue(rows[0]["transcription"].strip())


if __name__ == "__main__":
    unittest.main()
