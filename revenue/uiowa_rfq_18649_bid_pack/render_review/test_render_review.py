"""Independent-reader replay and negative controls for a single reviewed PDF.

Run explicitly from this directory: python -m unittest -v test_render_review
PyMuPDF and Poppler are execution dependencies, not assembler dependencies.
"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import pymupdf as pdf
from replay_review import (DEFAULT_PDF, REVIEWED_GIT_BLOB, REVIEWED_SHA256,
                           inspect_pdf, main, replay)


class RenderReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = DEFAULT_PDF.read_bytes()

    def mutate(self, change):
        with pdf.open(stream=self.original, filetype="pdf") as document:
            change(document)
            return document.tobytes()

    def codes(self, data):
        return {f["code"] for f in inspect_pdf(data)["findings"]}

    def test_exact_original_provider_bytes(self):
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), REVIEWED_SHA256)
        self.assertEqual(hashlib.sha1(b"blob " + str(len(self.original)).encode()
                                    + b"\0" + self.original).hexdigest(), REVIEWED_GIT_BLOB)

    def test_reader_opens_all_nine_pages(self):
        report = inspect_pdf(self.original)
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["page_count"], 9)
        self.assertEqual(sum(p["text_runs"] for p in report["pages"]), 166)
        self.assertEqual(report["link_count"], 21)
        self.assertEqual(report["outline_count"], 9)

    def test_rerun_never_claims_visual_or_human_approval(self):
        report = inspect_pdf(self.original)
        self.assertEqual(report["visual_review"], "NOT_PERFORMED_BY_THIS_REPLAY")
        self.assertEqual(report["human_accessibility_review"], "OUTSTANDING")

    def test_wrong_existing_target_page_detected(self):
        def change(doc):
            page = doc[1]
            link = page.get_links()[0]
            link["page"] = 3
            page.update_link(link)
        self.assertIn("WRONG_VISIBLE_DESTINATION", self.codes(self.mutate(change)))

    def test_wrong_attachment_on_same_page_detected(self):
        def change(doc):
            page = doc[3]
            link = page.get_links()[2]
            # Point from Financial Capacity Letter to the existing ATT-FIN-02 row.
            link["to"] = pdf.Point(0, 335)
            page.update_link(link)
        self.assertIn("WRONG_VISIBLE_DESTINATION", self.codes(self.mutate(change)))

    def test_destination_below_page_detected(self):
        def change(doc):
            page = doc[1]
            link = page.get_links()[0]
            link["to"] = pdf.Point(0, 900)
            page.update_link(link)
        self.assertIn("DESTINATION_POSITION", self.codes(self.mutate(change)))

    def test_link_rectangle_in_blank_space_detected(self):
        def change(doc):
            page = doc[1]
            link = page.get_links()[0]
            link["from"] = pdf.Rect(72, 740, 140, 750)
            page.update_link(link)
        self.assertIn("LINK_WITHOUT_LABEL", self.codes(self.mutate(change)))

    def test_link_rectangle_on_another_real_label_detected(self):
        def change(doc):
            page = doc[1]
            links = page.get_links()
            links[0]["from"] = links[1]["from"]
            page.update_link(links[0])
        self.assertIn("WRONG_VISIBLE_LABEL", self.codes(self.mutate(change)))

    def test_dropped_navigation_annotation_detected(self):
        def change(doc):
            page = doc[1]
            page.delete_link(page.get_links()[0])
        self.assertIn("LINK_COUNT", self.codes(self.mutate(change)))

    def test_dropped_outline_detected(self):
        self.assertIn("OUTLINE", self.codes(self.mutate(lambda doc: doc.set_toc([]))))

    def test_text_crossing_printable_margin_detected(self):
        def change(doc):
            doc[0].insert_text((530, 400), "VISIBLE MARGIN OVERFLOW", fontsize=11)
        self.assertIn("TEXT_OUTSIDE_BODY", self.codes(self.mutate(change)))

    def test_placeholder_status_deletion_detected(self):
        def change(doc):
            page = doc[1]
            for box in page.search_for("SUBMISSION_INCOMPLETE"):
                page.add_redact_annot(box)
            page.apply_redactions()
        self.assertIn("MISSING_INDEX_MARKER", self.codes(self.mutate(change)))

    def test_unresolved_reference_deletion_detected(self):
        def change(doc):
            page = doc[5]
            for box in page.search_for("S-APPENDIX-C"):
                page.add_redact_annot(box)
            page.apply_redactions()
        self.assertIn("MISSING_UNRESOLVED_MARKER", self.codes(self.mutate(change)))

    def test_missing_physical_page_detected(self):
        self.assertIn("PAGE_COUNT", self.codes(self.mutate(lambda doc: doc.delete_page(8))))

    def test_changed_but_readable_bytes_do_not_inherit_review(self):
        changed = self.mutate(lambda doc: doc.set_metadata({"title": "Changed metadata"}))
        report = inspect_pdf(changed)
        self.assertEqual(report["findings"], [])
        self.assertFalse(report["matches_reviewed_bytes"])

    def test_replay_creates_all_pages_manifest_and_gallery(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "rendered"
            report = replay(DEFAULT_PDF, out, dpi=72)
            self.assertEqual(len(report["renders"]), 9)
            self.assertEqual(len(list(out.glob("*.png"))), 9)
            self.assertEqual(json.loads((out / "observations.json").read_text())["sha256"], REVIEWED_SHA256)
            html = (out / "index.html").read_text()
            self.assertEqual(html.count("<img "), 9)
            for image in report["renders"]:
                self.assertEqual(hashlib.sha256((out / image["file"]).read_bytes()).hexdigest(), image["sha256"])
            self.assertIn("not been visually reviewed", html)
            self.assertEqual(DEFAULT_PDF.read_bytes(), self.original)

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            marker = out / "owner.txt"
            marker.write_text("preserve")
            with self.assertRaises(FileExistsError):
                replay(DEFAULT_PDF, out)
            self.assertEqual(marker.read_text(), "preserve")
            self.assertEqual(list(out.iterdir()), [marker])

    def test_unreasonable_resolution_creates_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "absent"
            with self.assertRaises(ValueError):
                replay(DEFAULT_PDF, out, dpi=10000)
            self.assertFalse(out.exists())

    def test_changed_input_cli_returns_nonzero_even_when_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "changed.pdf"
            source.write_bytes(self.mutate(lambda doc: doc.set_metadata({"title": "Changed"})))
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["--pdf", str(source), "--out", str(Path(folder) / "rendered"), "--dpi", "72"])
            self.assertEqual(code, 1)

    def test_invalid_pdf_cli_returns_error_without_gallery(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "bad.pdf"
            source.write_bytes(b"not a PDF")
            out = Path(folder) / "rendered"
            with contextlib.redirect_stderr(io.StringIO()):
                code = main(["--pdf", str(source), "--out", str(out)])
            self.assertEqual(code, 2)
            self.assertFalse(out.exists())

    def test_original_cli_returns_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["--out", str(Path(folder) / "rendered"), "--dpi", "72"])
            self.assertEqual(code, 0)

    def test_independent_poppler_opens_and_renders_every_page(self):
        self.assertIsNotNone(shutil.which("pdftoppm"), "Poppler execution is missing, not passing.")
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(["pdftoppm", "-r", "72", "-png", str(DEFAULT_PDF),
                                     str(Path(folder) / "page")], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            self.assertEqual(len(list(Path(folder).glob("page-*.png"))), 9)
            self.assertTrue(all(p.stat().st_size > 1000 for p in Path(folder).glob("*.png")))


if __name__ == "__main__":
    unittest.main()
