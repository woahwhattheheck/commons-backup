"""UIOWA-136 bid-assembly tests. Run normal and with python -O."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
import zipfile

try:
    from . import canonical, htmlwrite, pdfwrite
    from .assembler import (
        ERROR,
        AssemblyError,
        BidAssembly,
        load_manifest,
        sha256_bytes,
        sha256_file,
    )
    from .cli import main as cli_main
    from .docxwrite import read_docx_nav, read_docx_text
except ImportError:
    import canonical
    import htmlwrite
    import pdfwrite
    from assembler import (
        ERROR,
        AssemblyError,
        BidAssembly,
        load_manifest,
        sha256_bytes,
        sha256_file,
    )
    from cli import main as cli_main
    from docxwrite import read_docx_nav, read_docx_text

HERE = os.path.dirname(os.path.abspath(__file__))
PREPARED = os.path.join(HERE, "fixtures", "prepared")
DECLARED_ABSENT = os.path.join(HERE, "fixtures", "declared_absent")
INVENTED = os.path.join(HERE, "fixtures", "invented_approval")
EXTRA = os.path.join(HERE, "fixtures", "extra_file")


def _assemble(fixture, out):
    manifest = load_manifest(os.path.join(fixture, "manifest.json"))
    return BidAssembly(manifest, fixture).assemble(out)


class PreparedPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="uiowa136-")
        cls.out = os.path.join(cls.tmpdir, "draft")
        cls.result = _assemble(PREPARED, cls.out)
        with open(os.path.join(cls.out, "proposal.pdf"), "rb") as fh:
            cls.pdf = fh.read()
        with open(os.path.join(cls.out, "proposal.html"), encoding="utf-8") as fh:
            cls.html = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_review_draft_not_submission(self):
        self.assertEqual(self.result["readiness"]["status"], "SUBMISSION_INCOMPLETE")
        self.assertFalse(self.result["authority"]["submission"])
        self.assertFalse(self.result["authority"]["buyer_contact"])
        self.assertIn("REVIEW DRAFT", self.result["fiction_notice"])

    def test_pdf_has_multiple_pages_and_outline(self):
        pages = pdfwrite.read_pdf_pages(self.pdf)
        self.assertGreaterEqual(len(pages), 6)
        self.assertEqual(self.result["render"]["pdf_pages"], len(pages))
        outline = pdfwrite.read_pdf_outline(self.pdf)
        titles = [t for t, _ in outline]
        self.assertIn("Document Map", titles)
        self.assertIn("Attachment Index", titles)
        self.assertIn("Source and version register", titles)
        self.assertTrue(any(t.startswith("1. ") for t in titles))

    def test_pdf_internal_links_land_on_real_pages(self):
        pages = pdfwrite.read_pdf_pages(self.pdf)
        links = pdfwrite.read_pdf_links(self.pdf)
        self.assertGreaterEqual(len(links), 4)
        n = len(pages)
        for src, dest in links:
            self.assertGreaterEqual(src, 0)
            self.assertLess(src, n)
            self.assertGreaterEqual(dest, 0)
            self.assertLess(dest, n)

    def test_docx_bookmarks_and_hyperlinks(self):
        path = os.path.join(self.out, "proposal.docx")
        marks, links = read_docx_nav(path)
        self.assertIn("TOC", marks)
        self.assertIn("ATTIDX", marks)
        self.assertIn("S_COVER", marks)
        self.assertTrue(links)
        for anchor in links:
            self.assertIn(anchor, marks)
        paras = read_docx_text(path)
        blob = "\n".join(paras)
        self.assertIn("REVIEW DRAFT", blob)
        self.assertIn("PLACEHOLDER, NOT SUPPLIED", blob)

    def test_html_fragment_links_resolve(self):
        ids = set(htmlwrite.read_html_ids(self.html))
        hrefs = htmlwrite.read_html_hrefs(self.html)
        self.assertIn("TOC", ids)
        self.assertIn("ATTIDX", ids)
        self.assertTrue(hrefs)
        for h in hrefs:
            self.assertIn(h, ids)

    def test_missing_financials_are_unknown_not_zero(self):
        by_id = {a["id"]: a for a in self.result["attachments"]}
        for aid in ("ATT-FIN-01", "ATT-FIN-02", "ATT-QUAL-01", "ATT-QUAL-02", "ATT-FEE-01"):
            row = by_id[aid]
            self.assertFalse(row["present"])
            self.assertIsNone(row["bytes"])
            self.assertIsNone(row["sha256"])
            self.assertEqual(row["status"], "PLACEHOLDER-NOT SUPPLIED")
        csv_path = os.path.join(self.out, "attachment_index.csv")
        text = open(csv_path, encoding="utf-8").read()
        self.assertIn("UNKNOWN", text)
        self.assertNotRegex(text, r"ATT-FIN-01,.*,0,")

    def test_placeholder_files_exist_on_disk(self):
        names = os.listdir(os.path.join(self.out, "attachments"))
        placeholders = [n for n in names if n.endswith(".PLACEHOLDER.txt")]
        self.assertGreaterEqual(len(placeholders), 5)
        supplied = [n for n in names if not n.endswith(".PLACEHOLDER.txt")]
        self.assertEqual(len(supplied), 1)
        body = open(
            os.path.join(self.out, "attachments", placeholders[0]), encoding="utf-8"
        ).read()
        self.assertIn("PLACEHOLDER - NOT SUPPLIED", body)
        self.assertIn("never invented", body.lower())

    def test_supplied_attachment_hash_matches_source(self):
        src = os.path.join(PREPARED, "attachments", "proposal-draft.md")
        expected = sha256_file(src)
        row = next(a for a in self.result["attachments"] if a["id"] == "ATT-PROP-01")
        self.assertEqual(row["sha256"], expected)
        copied = os.path.join(self.out, "attachments", row["filename"])
        self.assertEqual(sha256_file(copied), expected)
        paths = {r["path"]: r for r in self.result["source_register"]}
        self.assertEqual(paths["attachments/proposal-draft.md"]["sha256"], expected)

    def test_workshare_is_not_prime_fee(self):
        hold = self.result["reconciliation"]
        self.assertTrue(hold["workshare_is_not_prime_fee"])
        self.assertEqual(hold["workshare_base_usd"], 24000)
        self.assertEqual(self.result["commercial_facts"]["base_amount_usd"], 24000)
        self.assertEqual(self.result["commercial_facts"]["roles"]["principal"], "prime")
        self.assertEqual(self.result["commercial_facts"]["roles"]["specialist"], "subcontract")
        joined = "\n".join(pdfwrite.read_pdf_pages(self.pdf))
        self.assertIn("not prime fee", joined.lower())
        codes = [i["code"] for i in self.result["issues"]]
        self.assertIn("PRIME_FEE_NOT_SUPPLIED", codes)
        self.assertIn("COMMERCIAL_FACTS_CONSUMED", codes)

    def test_deadline_currentness_hold(self):
        hold = self.result["reconciliation"]
        self.assertEqual(hold["status"], "CURRENTNESS_HOLD")
        self.assertFalse(hold["official_refresh_confirmed"])
        self.assertIn("2026-09-22", hold["rfq_printed_deadline"])
        self.assertIn("2026-09-29", hold["workshare_overlay_deadline"])
        codes = [i["code"] for i in self.result["issues"]]
        self.assertIn("DEADLINE_CURRENTNESS_HOLD", codes)

    def test_attribute_15_not_certified(self):
        hold = self.result["reconciliation"]
        self.assertIn("NOT_FILLED", hold["attribute_15"])
        joined = "\n".join(pdfwrite.read_pdf_pages(self.pdf))
        self.assertIn("Attribute 15", joined)

    def test_unresolved_appendix_stays_unresolved(self):
        xrefs = self.result["cross_references"]
        unresolved = [x for x in xrefs if x["status"] == "UNRESOLVED"]
        self.assertTrue(any(x["to"] == "S-APPENDIX-C" for x in unresolved))
        joined = "\n".join(pdfwrite.read_pdf_pages(self.pdf)).replace("\n", " ")
        self.assertIn("[UNRESOLVED REFERENCE: S-APPENDIX-C]", joined)

    def test_completeness_is_not_a_percentage(self):
        note = self.result["readiness"]["note"]
        self.assertNotIn("%", json.dumps(self.result["readiness"]))
        self.assertIn("not a readiness score", note.lower())

    def test_index_lists_required_missing(self):
        md = open(os.path.join(self.out, "00-INDEX.md"), encoding="utf-8").read()
        self.assertIn("ATT-FIN-01", md)
        self.assertIn("CURRENTNESS_HOLD", md)
        self.assertIn("subcontract", md)

    def test_rebuild_pdf_and_html_are_byte_identical(self):
        out2 = os.path.join(self.tmpdir, "draft-b")
        _assemble(PREPARED, out2)
        a = open(os.path.join(self.out, "proposal.pdf"), "rb").read()
        b = open(os.path.join(out2, "proposal.pdf"), "rb").read()
        self.assertEqual(a, b)
        ha = open(os.path.join(self.out, "proposal.html"), "rb").read()
        hb = open(os.path.join(out2, "proposal.html"), "rb").read()
        self.assertEqual(ha, hb)
        da = open(os.path.join(self.out, "proposal.docx"), "rb").read()
        db = open(os.path.join(out2, "proposal.docx"), "rb").read()
        self.assertEqual(da, db)


class NegativeControlTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="uiowa136-neg-")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_output_directory_overwrite_refused(self):
        out = os.path.join(self.tmpdir, "once")
        _assemble(PREPARED, out)
        with self.assertRaises(AssemblyError) as ctx:
            _assemble(PREPARED, out)
        self.assertIn("refusing to overwrite", str(ctx.exception))

    def test_invented_approval_status_refused(self):
        with self.assertRaises(AssemblyError) as ctx:
            load_manifest(os.path.join(INVENTED, "manifest.json"))
        self.assertIn("invents an approval", str(ctx.exception))

    def test_declared_provided_but_absent_is_error(self):
        out = os.path.join(self.tmpdir, "absent")
        result = _assemble(DECLARED_ABSENT, out)
        codes = [i["code"] for i in result["issues"] if i["severity"] == ERROR]
        self.assertIn("ATTACHMENT_DECLARED_PROVIDED_BUT_ABSENT", codes)
        row = next(a for a in result["attachments"] if a["id"] == "ATT-FIN-01")
        self.assertEqual(row["status"], "PLACEHOLDER-NOT SUPPLIED")
        self.assertIsNone(row["bytes"])

    def test_undeclared_file_is_error(self):
        out = os.path.join(self.tmpdir, "extra")
        result = _assemble(EXTRA, out)
        codes = [i["code"] for i in result["issues"] if i["severity"] == ERROR]
        self.assertIn("UNDECLARED_FILE_IN_PACK", codes)
        self.assertTrue(
            any("not-in-manifest.txt" in f for f in result["undeclared_files"])
        )

    def test_altered_source_changes_digest(self):
        copy = os.path.join(self.tmpdir, "altered")
        shutil.copytree(PREPARED, copy)
        target = os.path.join(copy, "attachments", "proposal-draft.md")
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\naltered-byte\n")
        out = os.path.join(self.tmpdir, "altered-out")
        result = _assemble(copy, out)
        original = sha256_file(os.path.join(PREPARED, "attachments", "proposal-draft.md"))
        row = next(a for a in result["attachments"] if a["id"] == "ATT-PROP-01")
        self.assertNotEqual(row["sha256"], original)

    def test_oversized_input_fails_visibly(self):
        copy = os.path.join(self.tmpdir, "huge")
        shutil.copytree(PREPARED, copy)
        huge = os.path.join(copy, "attachments", "proposal-draft.md")
        with open(huge, "wb") as fh:
            fh.write(b"x" * (2_000_000 + 10))
        with self.assertRaises(AssemblyError) as ctx:
            _assemble(copy, os.path.join(self.tmpdir, "huge-out"))
        self.assertIn("refusing to silently overflow", str(ctx.exception))

    def test_wrong_pdf_destination_is_detectable(self):
        out = os.path.join(self.tmpdir, "pdfchk")
        _assemble(PREPARED, out)
        data = open(os.path.join(out, "proposal.pdf"), "rb").read()
        links = pdfwrite.read_pdf_links(data)
        self.assertTrue(links)
        tampered = data.replace(b"/Annots [", b"/Xannots [")
        if tampered == data:
            self.fail("could not tamper annots bytes")
        bad = pdfwrite.read_pdf_links(tampered)
        self.assertEqual(bad, [])
        self.assertNotEqual(bad, links)

    def test_broken_docx_bookmark_is_detectable(self):
        out = os.path.join(self.tmpdir, "docxchk")
        _assemble(PREPARED, out)
        path = os.path.join(out, "proposal.docx")
        marks, links = read_docx_nav(path)
        self.assertTrue(marks)
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
        xml = xml.replace(b'w:name="TOC"', b'w:name="GONE"', 1)
        broken = os.path.join(self.tmpdir, "broken.docx")
        with zipfile.ZipFile(path) as src, zipfile.ZipFile(broken, "w") as dst:
            for info in src.infolist():
                payload = src.read(info.filename)
                if info.filename == "word/document.xml":
                    payload = xml
                dst.writestr(info, payload)
        marks2, _ = read_docx_nav(broken)
        self.assertNotIn("TOC", marks2)
        self.assertIn("GONE", marks2)

    def test_broken_html_link_is_detectable(self):
        out = os.path.join(self.tmpdir, "htmlchk")
        _assemble(PREPARED, out)
        html = open(os.path.join(out, "proposal.html"), encoding="utf-8").read()
        ids = set(htmlwrite.read_html_ids(html))
        hrefs = htmlwrite.read_html_hrefs(html)
        self.assertTrue(hrefs)
        target = hrefs[0]
        broken = html.replace('href="#%s"' % target, 'href="#NOPE"', 1)
        hrefs2 = htmlwrite.read_html_hrefs(broken)
        self.assertIn("NOPE", hrefs2)
        self.assertNotIn("NOPE", ids)

    def test_cli_prepared_exit_zero(self):
        out = os.path.join(self.tmpdir, "cli-ok")
        code = cli_main(
            ["--manifest", os.path.join(PREPARED, "manifest.json"), "--out", out]
        )
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(os.path.join(out, "proposal.pdf")))

    def test_cli_invented_approval_exit_two(self):
        code = cli_main(
            [
                "--manifest",
                os.path.join(INVENTED, "manifest.json"),
                "--out",
                os.path.join(self.tmpdir, "nope"),
            ]
        )
        self.assertEqual(code, 2)

    def test_cli_strict_declared_absent_exit_one(self):
        code = cli_main(
            [
                "--manifest",
                os.path.join(DECLARED_ABSENT, "manifest.json"),
                "--out",
                os.path.join(self.tmpdir, "strict"),
                "--strict",
            ]
        )
        self.assertEqual(code, 1)

    def test_required_checks_are_not_assert_statements(self):
        # python -O must still refuse invented approval and overwrite.
        src = open(os.path.join(HERE, "assembler.py"), encoding="utf-8").read()
        # Required validation uses raise, never a bare assert.
        self.assertNotRegex(src, r"(?m)^\s*assert ")


class FactsConsumptionTests(unittest.TestCase):
    def test_pinned_facts_match_landed_or_local(self):
        facts, source, mismatch = canonical.commercial_facts()
        self.assertEqual(mismatch, ())
        self.assertEqual(facts["rfq_id"], "18649")
        self.assertEqual(facts["base_amount_usd"], 24000)
        self.assertEqual(facts["option_amount_usd"], 4000)
        self.assertEqual(tuple(facts["milestone_split"]), (40, 40, 20))
        self.assertEqual(tuple(facts["milestone_amounts_usd"]), (9600, 9600, 4800))
        self.assertTrue(
            source == "pinned-local"
            or source.endswith("uiowa_rfq_18649_commercial_facts/canonical.py"),
            source,
        )

    def test_sha256_helper_is_stable(self):
        self.assertEqual(len(sha256_bytes(b"x")), 64)
        self.assertEqual(sha256_bytes(b"x"), sha256_bytes(b"x"))
        self.assertNotEqual(sha256_bytes(b"x"), sha256_bytes(b"y"))


if __name__ == "__main__":
    unittest.main()
