from __future__ import annotations

import json
import os
import tempfile
import unittest
import warnings
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from revenue.scorm_delivery_assurance.assurance import (
    AssuranceError,
    HOLD,
    READY,
    _exclusive,
    _read_regular,
    compile_assurance,
    default_policy,
    main as cli_main,
    verify_assurance,
)

MANIFEST = b'''<?xml version="1.0" encoding="UTF-8"?>
<manifest xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
 xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2">
 <metadata><schema>ADL SCORM</schema><schemaversion>1.2</schemaversion></metadata>
 <organizations default="ORG"><organization identifier="ORG">
  <item identifier="ITEM1" identifierref="RES1"><title>Module One</title></item>
  <item identifier="ITEM2" identifierref="RES2"><title>Module Two</title></item>
 </organization></organizations>
 <resources>
  <resource identifier="RES1" type="webcontent" adlcp:scormtype="sco" href="m1/index.html">
   <file href="m1/index.html"/><file href="m1/app.js"/>
  </resource>
  <resource identifier="RES2" type="webcontent" adlcp:scormtype="sco" href="m2/index.html">
   <file href="m2/index.html"/>
  </resource>
 </resources>
</manifest>'''


def sidecar(caption2: str = "m2/captions.vtt") -> bytes:
    return json.dumps(
        {
            "schema": "tjlabs.scorm-course-evidence/v1",
            "course_id": "course-demo-01",
            "source_revision_sha256": "a" * 64,
            "modules": [
                {
                    "id": "m1",
                    "resource_id": "RES1",
                    "title": "Module One",
                    "assessment": {"required": True, "passing_score": 80},
                    "completion": {"required": True},
                    "accessibility": {
                        "transcript": "m1/transcript.txt",
                        "captions": ["m1/captions.vtt"],
                    },
                },
                {
                    "id": "m2",
                    "resource_id": "RES2",
                    "title": "Module Two",
                    "assessment": {"required": True, "passing_score": 75},
                    "completion": {"required": True},
                    "accessibility": {
                        "transcript": "m2/transcript.txt",
                        "captions": [caption2],
                    },
                },
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def make_zip(extra=None, manifest=MANIFEST, evidence=None, duplicate=None) -> bytes:
    files = {
        "imsmanifest.xml": manifest,
        "course.assurance.json": evidence if evidence is not None else sidecar(),
        "m1/index.html": b"<html><body>one</body></html>",
        "m1/app.js": b"console.log('one')",
        "m1/transcript.txt": b"Transcript one",
        "m1/captions.vtt": b"WEBVTT\n",
        "m2/index.html": b"<html><body>two</body></html>",
        "m2/transcript.txt": b"Transcript two",
        "m2/captions.vtt": b"WEBVTT\n",
    }
    if extra:
        files.update(extra)
    out = BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name])
        if duplicate:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(duplicate[0], duplicate[1])
    return out.getvalue()


class AssuranceTests(unittest.TestCase):
    def test_ready_two_module_package(self):
        package = make_zip()
        report = compile_assurance(package)
        self.assertEqual(READY, report["status"])
        self.assertEqual(2, report["facts"]["module_count"])
        self.assertEqual("SCORM_1_2", report["facts"]["standard"])
        self.assertTrue(verify_assurance(package, report))

    def test_scorm_2004_metadata_is_accepted(self):
        manifest = MANIFEST.replace(
            b"<schemaversion>1.2</schemaversion>",
            b"<schemaversion>2004 4th Edition</schemaversion>",
        )
        report = compile_assurance(make_zip(manifest=manifest))
        self.assertEqual(READY, report["status"])
        self.assertEqual("SCORM_2004", report["facts"]["standard"])

    def test_missing_caption_holds(self):
        report = compile_assurance(make_zip(evidence=sidecar("m2/missing.vtt")))
        self.assertEqual(HOLD, report["status"])
        self.assertTrue(any("missing accessibility evidence" in x for x in report["reasons"]))

    def test_traversal_holds(self):
        report = compile_assurance(make_zip(extra={"../escape.txt": b"x"}))
        self.assertEqual(HOLD, report["status"])
        self.assertTrue(any("non-canonical" in x for x in report["reasons"]))

    def test_external_launch_holds(self):
        manifest = MANIFEST.replace(
            b'href="m1/index.html"', b'href="https://evil.invalid/a"', 1
        )
        report = compile_assurance(make_zip(manifest=manifest))
        self.assertEqual(HOLD, report["status"])
        self.assertTrue(any("external manifest href" in x for x in report["reasons"]))

    def test_duplicate_member_holds(self):
        report = compile_assurance(make_zip(duplicate=("m1/index.html", b"changed")))
        self.assertEqual(HOLD, report["status"])
        self.assertTrue(any("duplicate ZIP member" in x for x in report["reasons"]))

    def test_case_collision_holds(self):
        report = compile_assurance(make_zip(extra={"M1/INDEX.HTML": b"shadow"}))
        self.assertEqual(HOLD, report["status"])
        self.assertTrue(any("case-colliding" in x for x in report["reasons"]))

    def test_sidecar_resource_set_must_match_org(self):
        obj = json.loads(sidecar())
        obj["modules"] = obj["modules"][:1]
        report = compile_assurance(make_zip(evidence=json.dumps(obj).encode()))
        self.assertEqual(HOLD, report["status"])
        self.assertTrue(any("resource set" in x for x in report["reasons"]))

    def test_duplicate_json_key_holds(self):
        raw = (
            b'{"schema":"tjlabs.scorm-course-evidence/v1","schema":"x",'
            b'"course_id":"a","source_revision_sha256":"' + b"a" * 64 + b'","modules":[]}'
        )
        report = compile_assurance(make_zip(evidence=raw))
        self.assertEqual(HOLD, report["status"])
        self.assertTrue(any("duplicate JSON key" in x for x in report["reasons"]))

    def test_bool_as_integer_policy_rejected(self):
        policy = default_policy()
        policy["max_files"] = True
        with self.assertRaises(ValueError):
            compile_assurance(make_zip(), policy)

    def test_policy_file_threshold_holds(self):
        policy = default_policy()
        policy["max_files"] = 2
        report = compile_assurance(make_zip(), policy)
        self.assertEqual(HOLD, report["status"])
        self.assertTrue(any("file count" in x for x in report["reasons"]))

    def test_tamper_breaks_verify(self):
        package = make_zip()
        report = compile_assurance(package)
        changed = make_zip(extra={"note.txt": b"changed"})
        self.assertFalse(verify_assurance(changed, report))

    def test_exact_bytes_are_deterministic(self):
        package = make_zip()
        self.assertEqual(compile_assurance(package), compile_assurance(package))

    def test_authority_never_claims_certification_or_revenue(self):
        authority = compile_assurance(make_zip())["authority"]
        self.assertTrue(authority)
        self.assertTrue(all(value is False for value in authority.values()))

    def test_utf16_dtd_entity_manifest_holds_before_xml_semantics(self):
        text = MANIFEST.decode("utf-8").replace(
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<?xml version="1.0" encoding="UTF-16"?>\n<!DOCTYPE manifest [<!ENTITY x "hello">]>',
        ).replace("<schema>ADL SCORM</schema>", "<schema>ADL &x; SCORM</schema>")
        report = compile_assurance(make_zip(manifest=text.encode("utf-16")))
        self.assertEqual(HOLD, report["status"])
        self.assertTrue(any("UTF-8" in x for x in report["reasons"]))

    def test_utf32_dtd_entity_manifest_holds_before_xml_semantics(self):
        text = MANIFEST.decode("utf-8").replace(
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<?xml version="1.0" encoding="UTF-32"?>\n<!DOCTYPE manifest [<!ENTITY x "hello">]>',
        )
        report = compile_assurance(make_zip(manifest=text.encode("utf-32")))
        self.assertEqual(HOLD, report["status"])
        self.assertTrue(any("UTF-8" in x for x in report["reasons"]))

    def test_utf8_dtd_entity_manifest_holds(self):
        manifest = MANIFEST.replace(
            b"?>\n<manifest",
            b'?>\n<!DOCTYPE manifest [<!ENTITY x "hello">]>\n<manifest',
        )
        report = compile_assurance(make_zip(manifest=manifest))
        self.assertEqual(HOLD, report["status"])
        self.assertTrue(any("DTD/entity" in x for x in report["reasons"]))

    def test_root_identifier_cannot_mint_scorm_version(self):
        manifest = MANIFEST.replace(
            b'<manifest xmlns=', b'<manifest identifier="course-2004" xmlns=', 1
        ).replace(b"<schemaversion>1.2</schemaversion>", b"")
        report = compile_assurance(make_zip(manifest=manifest))
        self.assertEqual(HOLD, report["status"])
        self.assertTrue(any("schemaversion" in x for x in report["reasons"]))

    def test_schema_is_required_and_must_be_adl_scorm(self):
        manifest = MANIFEST.replace(b"<schema>ADL SCORM</schema>", b"<schema>not-scorm</schema>")
        report = compile_assurance(make_zip(manifest=manifest))
        self.assertEqual(HOLD, report["status"])
        self.assertTrue(any("schema must be ADL SCORM" in x for x in report["reasons"]))

    def test_conflicting_schemaversion_declarations_hold(self):
        manifest = MANIFEST.replace(
            b"<schemaversion>1.2</schemaversion>",
            b"<schemaversion>1.2</schemaversion><schemaversion>2004</schemaversion>",
        )
        report = compile_assurance(make_zip(manifest=manifest))
        self.assertEqual(HOLD, report["status"])
        self.assertTrue(any("exactly one schemaversion" in x for x in report["reasons"]))

    def test_read_regular_rejects_symlink_swapped_at_open(self):
        if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "symlink"):
            self.skipTest("platform lacks O_NOFOLLOW/symlink")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.bin"
            target = Path(directory) / "target.bin"
            path.write_bytes(b"safe")
            target.write_bytes(b"other")
            real_open = os.open
            swapped = False

            def racing_open(name, flags, mode=0o777):
                nonlocal swapped
                if Path(name) == path and not swapped:
                    swapped = True
                    path.unlink()
                    path.symlink_to(target)
                return real_open(name, flags, mode)

            with patch("revenue.scorm_delivery_assurance.assurance.os.open", side_effect=racing_open):
                with self.assertRaises(OSError):
                    _read_regular(path, 32)

    def test_read_regular_rejects_fifo_swapped_at_open_without_blocking(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("platform lacks FIFO support")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.bin"
            path.write_bytes(b"safe")
            real_open = os.open
            swapped = False

            def racing_open(name, flags, mode=0o777):
                nonlocal swapped
                if Path(name) == path and not swapped:
                    swapped = True
                    path.unlink()
                    os.mkfifo(path)
                return real_open(name, flags, mode)

            with patch("revenue.scorm_delivery_assurance.assurance.os.open", side_effect=racing_open):
                with self.assertRaisesRegex(AssuranceError, "not a regular file"):
                    _read_regular(path, 32)

    def test_read_regular_rejects_oversize_swapped_at_open(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.bin"
            replacement = Path(directory) / "replacement.bin"
            path.write_bytes(b"safe")
            replacement.write_bytes(b"x" * 33)
            real_open = os.open
            swapped = False

            def racing_open(name, flags, mode=0o777):
                nonlocal swapped
                if Path(name) == path and not swapped:
                    swapped = True
                    os.replace(replacement, path)
                return real_open(name, flags, mode)

            with patch("revenue.scorm_delivery_assurance.assurance.os.open", side_effect=racing_open):
                with self.assertRaisesRegex(AssuranceError, "exceeds size limit"):
                    _read_regular(path, 32)

    def test_read_regular_detects_same_inode_mutation_with_restored_mtime(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.bin"
            path.write_bytes(b"A" * 16)
            before = path.stat()
            real_read = os.read
            mutated = False

            def racing_read(fd, size):
                nonlocal mutated
                if not mutated:
                    mutated = True
                    with path.open("r+b", buffering=0) as stream:
                        stream.write(b"B" * 16)
                        stream.flush()
                    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
                return real_read(fd, size)

            with patch("revenue.scorm_delivery_assurance.assurance.os.read", side_effect=racing_read):
                with self.assertRaisesRegex(AssuranceError, "changed during read"):
                    _read_regular(path, 32)

    def test_output_late_failure_never_unlinks_foreign_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            real_fsync = os.fsync
            fired = False

            def failing_fsync(fd):
                nonlocal fired
                if not fired:
                    fired = True
                    path.unlink()
                    path.write_bytes(b"foreign")
                    raise OSError("synthetic late failure")
                return real_fsync(fd)

            with patch("revenue.scorm_delivery_assurance.assurance.os.fsync", side_effect=failing_fsync):
                with self.assertRaisesRegex(OSError, "synthetic late failure"):
                    _exclusive(path, b"ours")
            self.assertEqual(b"foreign", path.read_bytes())

    def test_cli_compile_verify_and_no_overwrite(self):
        package = make_zip()
        with tempfile.TemporaryDirectory() as directory:
            pkg = Path(directory) / "course.zip"
            receipt = Path(directory) / "receipt.json"
            pkg.write_bytes(package)
            self.assertEqual(0, cli_main(["compile", str(pkg), str(receipt)]))
            self.assertEqual(0, cli_main(["verify", str(pkg), str(receipt)]))
            self.assertEqual(2, cli_main(["compile", str(pkg), str(receipt)]))


if __name__ == "__main__":
    unittest.main()
