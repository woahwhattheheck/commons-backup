from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from validate_framework_crosswalk import DEFAULT_CSV, ValidationError, validate


class FrameworkCrosswalkTests(unittest.TestCase):
    def test_repository_crosswalk_passes(self) -> None:
        summary = validate(DEFAULT_CSV)
        self.assertGreaterEqual(summary["rows"], 40)
        self.assertEqual(
            set(summary["framework_counts"]),
            {"SSDF", "CSF", "AI RMF"},
        )
        self.assertEqual(
            set(summary["area_counts"]),
            {
                "software_development",
                "security",
                "deployment_operations",
                "ai_readiness",
            },
        )

    def test_duplicate_locator_is_rejected(self) -> None:
        header = (
            "framework,version,publication_date,locator,source_concept,"
            "assessment_area,proposed_assessment_use,evidence_examples,"
            "adaptation_limit,source_url\n"
        )
        row = (
            'SSDF,1.1,2022-02-03,PO.1,Concept,software_development,Use,'
            'Evidence,Limit,https://nvlpubs.nist.gov/example.pdf\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate.csv"
            path.write_text(header + row * 40, encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "duplicate framework locator"):
                validate(path)


if __name__ == "__main__":
    unittest.main()
