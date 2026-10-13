from __future__ import annotations

from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from validate_white_paper import DraftError, validate_file, validate_text


class WhitePaperTests(unittest.TestCase):
    def test_checked_in_draft_has_three_bounded_sections_and_all_rubric_tags(self):
        out = validate_file(HERE / "white_paper.md")
        self.assertGreater(out["totalWords"], 540)
        self.assertLessEqual(out["totalWords"], 2250)

    def test_missing_rubric_tag_rejected(self):
        text = (HERE / "white_paper.md").read_text().replace("[TECHNICAL-40]", "[TECHNICAL]", 1)
        # A second technical tag exists, so remove both to prove the requirement.
        text = text.replace("[TECHNICAL-40]", "[TECHNICAL]")
        with self.assertRaisesRegex(DraftError, "missing rubric tags"):
            validate_text(text)

    def test_submission_authority_ceiling_required(self):
        text = (HERE / "white_paper.md").read_text().replace("submissionAuthorized=false", "submission flag withheld")
        with self.assertRaisesRegex(DraftError, "submission authority ceiling"):
            validate_text(text)

    def test_page_markers_must_be_exact_and_ordered(self):
        text = (HERE / "white_paper.md").read_text().replace("<!-- PAGE 2/3 -->", "<!-- PAGE 3/3 -->", 1)
        with self.assertRaisesRegex(DraftError, "exactly PAGE"):
            validate_text(text)


if __name__ == "__main__":
    unittest.main()
