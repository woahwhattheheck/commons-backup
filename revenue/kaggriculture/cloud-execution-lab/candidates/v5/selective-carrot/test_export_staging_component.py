import gzip
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

import export_staging_component as exp


def packed(files, *, weird=None):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for name, body in files:
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = 0o644
            info.mtime = 0
            tf.addfile(info, io.BytesIO(body))
        if weird is not None:
            tf.addfile(weird)
    out = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=out, mode="wb", mtime=0) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def receipt_for(baseline, current, components):
    current_files = exp.staging_composer.archive_members(current)
    obj = {
        "schema": exp.staging_composer.RECEIPT_SCHEMA,
        "baseline_archive_sha256": exp.digest(baseline),
        "candidate_archive_sha256": exp.digest(current),
        "member_count": len(current_files),
        "components": components,
        "files": {name: exp.digest(body) for name, body in sorted(current_files.items())},
        "kaggle_submission_hold": True,
    }
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()


def replacement_component(cid, member, before, after, *, overlap_after=None):
    return {
        "component_id": cid,
        "manifest_sha256": "1" * 64,
        "depends_on": [],
        "conflicts_with": [],
        "replacements": {member: {
            "preimage_sha256": exp.digest(before),
            "postimage_sha256": exp.digest(after),
            "overlap_after": overlap_after,
        }},
        "additions": {},
    }


class ExportContractTests(unittest.TestCase):
    def baseline_contract(self, raw):
        stack = __import__("contextlib").ExitStack()
        stack.enter_context(mock.patch.object(exp, "BASELINE_SHA256", exp.digest(raw)))
        stack.enter_context(mock.patch.object(exp.staging_composer, "BASELINE_SHA256", exp.digest(raw)))
        return stack

    def derive(self, baseline_files, candidate_files, **kwargs):
        baseline = packed(baseline_files)
        candidate = packed(candidate_files)
        current = kwargs.pop("current_raw", baseline)
        current_sha = kwargs.pop("current_sha256", None)
        with self.baseline_contract(baseline):
            return exp.derive_component(
                baseline_raw=baseline,
                current_raw=current,
                candidate_raw=candidate,
                candidate_sha256=exp.digest(candidate),
                current_sha256=current_sha,
                component_id=kwargs.pop("component_id", "lane-a"),
                **kwargs,
            )

    def test_read_regular_preserves_ctrl_z_and_following_binary_bytes(self):
        raw = b"gzip-prefix\x1aarchive-bytes-after-dos-eof\x00\xff"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "candidate.tar.gz"
            path.write_bytes(raw)
            self.assertEqual(exp.read_regular(path), raw)

    def test_replacement_and_addition_match_composer_v1(self):
        manifest, payloads = self.derive(
            [("a.py", b"A"), ("dir/b.py", b"B")],
            [("a.py", b"A2"), ("dir/b.py", b"B"), ("c.py", b"C")],
        )
        self.assertEqual(manifest["schema"], "titan-v5-staging-component/v1")
        self.assertTrue(manifest["kaggle_submission_hold"])
        self.assertEqual(set(manifest), {
            "schema", "component_id", "baseline_archive_sha256", "depends_on",
            "conflicts_with", "overlap_after", "replacements", "additions",
            "kaggle_submission_hold",
        })
        replacement = manifest["replacements"]["a.py"]
        self.assertEqual(replacement["preimage_sha256"], exp.digest(b"A"))
        self.assertEqual(replacement["postimage_sha256"], exp.digest(b"A2"))
        addition = manifest["additions"]["c.py"]
        self.assertEqual(addition["postimage_sha256"], exp.digest(b"C"))
        self.assertEqual(payloads[replacement["source"]], b"A2")
        self.assertEqual(payloads[addition["source"]], b"C")
        self.assertRegex(replacement["source"], r"^files/[0-9a-f]{64}\.bin$")

    def test_candidate_digest_mismatch_rejects(self):
        baseline = packed([("a", b"A")])
        candidate = packed([("a", b"B")])
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(exp.ExportError, "candidate archive SHA256 mismatch"):
                exp.derive_component(
                    baseline_raw=baseline, current_raw=baseline, candidate_raw=candidate,
                    candidate_sha256="0" * 64, current_sha256=None, component_id="x")

    def test_delete_rejects(self):
        with self.assertRaisesRegex(exp.ExportError, "candidate deletes current member"):
            self.derive([("a", b"A"), ("b", b"B")], [("a", b"A2")])

    def test_no_delta_rejects(self):
        with self.assertRaisesRegex(exp.ExportError, "no delta"):
            self.derive([("a", b"A")], [("a", b"A")])

    def test_overlap_required_for_prior_modified_member(self):
        baseline = packed([("a", b"A"), ("b", b"B")])
        current = packed([("a", b"X"), ("b", b"B")])
        candidate = packed([("a", b"Y"), ("b", b"B")])
        receipt = receipt_for(
            baseline, current,
            [replacement_component("first", "a", b"A", b"X")],
        )
        common = dict(
            baseline_raw=baseline, current_raw=current, candidate_raw=candidate,
            candidate_sha256=exp.digest(candidate), current_sha256=exp.digest(current),
            current_receipt_raw=receipt, current_receipt_sha256=exp.digest(receipt),
            component_id="second",
        )
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(exp.ExportError, "requires exact overlap predecessor first"):
                exp.derive_component(**common)
            manifest, _ = exp.derive_component(
                **common, depends_on=["first"], overlap_after={"a": "first"})
        self.assertEqual(manifest["overlap_after"], {"a": "first"})
        self.assertEqual(manifest["replacements"]["a"]["preimage_sha256"], exp.digest(b"X"))

    def test_identical_prior_write_still_requires_overlap(self):
        baseline = packed([("a", b"A")])
        current = baseline
        candidate = packed([("a", b"Y")])
        receipt = receipt_for(
            baseline, current,
            [replacement_component("first", "a", b"A", b"A")],
        )
        common = dict(
            baseline_raw=baseline, current_raw=current, candidate_raw=candidate,
            candidate_sha256=exp.digest(candidate), current_sha256=exp.digest(current),
            current_receipt_raw=receipt, current_receipt_sha256=exp.digest(receipt),
            component_id="second",
        )
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(exp.ExportError, "requires exact overlap predecessor first"):
                exp.derive_component(**common)
            manifest, _ = exp.derive_component(**common, overlap_after={"a": "first"})
        self.assertEqual(manifest["overlap_after"], {"a": "first"})

    def test_forged_current_receipt_digest_rejects(self):
        baseline = packed([("a", b"A")])
        current = packed([("a", b"X")])
        candidate = packed([("a", b"Y")])
        receipt = receipt_for(
            baseline, current,
            [replacement_component("first", "a", b"A", b"X")],
        )
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(exp.ExportError, "receipt SHA256 mismatch"):
                exp.derive_component(
                    baseline_raw=baseline, current_raw=current, candidate_raw=candidate,
                    candidate_sha256=exp.digest(candidate), current_sha256=exp.digest(current),
                    current_receipt_raw=receipt, current_receipt_sha256="0" * 64,
                    component_id="second", overlap_after={"a": "first"})

    def test_receipt_history_must_reproduce_current(self):
        baseline = packed([("a", b"A")])
        current = packed([("a", b"X")])
        candidate = packed([("a", b"Y")])
        receipt = receipt_for(
            baseline, current,
            [replacement_component("first", "a", b"A", b"Z")],
        )
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(exp.ExportError, "history does not reproduce"):
                exp.derive_component(
                    baseline_raw=baseline, current_raw=current, candidate_raw=candidate,
                    candidate_sha256=exp.digest(candidate), current_sha256=exp.digest(current),
                    current_receipt_raw=receipt, current_receipt_sha256=exp.digest(receipt),
                    component_id="second", overlap_after={"a": "first"})

    def test_receipt_dependency_and_conflict_fields_must_be_lists(self):
        baseline = packed([("a", b"A")])
        current = packed([("a", b"X")])
        candidate = packed([("a", b"Y")])
        for field, bad in (("depends_on", ""), ("conflicts_with", {"first": True})):
            with self.subTest(field=field):
                component = replacement_component("first", "a", b"A", b"X")
                component[field] = bad
                receipt = receipt_for(baseline, current, [component])
                with self.baseline_contract(baseline):
                    with self.assertRaisesRegex(exp.ExportError, f"receipt {field} must be a list"):
                        exp.derive_component(
                            baseline_raw=baseline,
                            current_raw=current,
                            candidate_raw=candidate,
                            candidate_sha256=exp.digest(candidate),
                            current_sha256=exp.digest(current),
                            current_receipt_raw=receipt,
                            current_receipt_sha256=exp.digest(receipt),
                            component_id="second",
                            overlap_after={"a": "first"},
                        )

    def test_component_dependency_conflict_intersection_rejects(self):
        with self.assertRaisesRegex(exp.ExportError, "both depend on and conflict with"):
            self.derive(
                [("a", b"A")],
                [("a", b"B")],
                depends_on=["p01"],
                conflicts_with=["p01"],
            )

    def test_overlap_on_baseline_owned_member_rejects(self):
        with self.assertRaisesRegex(exp.ExportError, "baseline-owned"):
            self.derive(
                [("a", b"A")], [("a", b"B")],
                overlap_after={"a": "first"})

    def test_overlap_cannot_name_addition(self):
        with self.assertRaisesRegex(exp.ExportError, "non-replacement"):
            self.derive(
                [("a", b"A")], [("a", b"A"), ("new.py", b"N")],
                overlap_after={"new.py": "first"})

    def test_current_digest_is_required_when_current_is_not_baseline(self):
        baseline = packed([("a", b"A")])
        current = packed([("a", b"X")])
        candidate = packed([("a", b"Y")])
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(exp.ExportError, "requires current_sha256"):
                exp.derive_component(
                    baseline_raw=baseline, current_raw=current, candidate_raw=candidate,
                    candidate_sha256=exp.digest(candidate), current_sha256=None,
                    component_id="x")

    def test_nonbaseline_current_requires_authenticated_receipt(self):
        baseline = packed([("a", b"A")])
        current = packed([("a", b"X")])
        candidate = packed([("a", b"Y")])
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(exp.ExportError, "requires authenticated composer receipt"):
                exp.derive_component(
                    baseline_raw=baseline, current_raw=current, candidate_raw=candidate,
                    candidate_sha256=exp.digest(candidate), current_sha256=exp.digest(current),
                    component_id="second")

    def test_duplicate_tar_member_rejects(self):
        baseline = packed([("a", b"A")])
        candidate = packed([("a", b"B"), ("a", b"C")])
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(exp.ExportError, "invalid candidate archive"):
                exp.derive_component(
                    baseline_raw=baseline, current_raw=baseline, candidate_raw=candidate,
                    candidate_sha256=exp.digest(candidate), current_sha256=None,
                    component_id="x")

    def test_symlink_tar_member_rejects(self):
        baseline = packed([("a", b"A")])
        link = tarfile.TarInfo("link")
        link.type = tarfile.SYMTYPE
        link.linkname = "a"
        candidate = packed([("a", b"B")], weird=link)
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(exp.ExportError, "invalid candidate archive"):
                exp.derive_component(
                    baseline_raw=baseline, current_raw=baseline, candidate_raw=candidate,
                    candidate_sha256=exp.digest(candidate), current_sha256=None,
                    component_id="x")

    def test_traversal_tar_member_rejects(self):
        baseline = packed([("a", b"A")])
        candidate = packed([("../evil", b"E"), ("a", b"A")])
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(exp.ExportError, "noncanonical"):
                exp.derive_component(
                    baseline_raw=baseline, current_raw=baseline, candidate_raw=candidate,
                    candidate_sha256=exp.digest(candidate), current_sha256=None,
                    component_id="x")

    def test_end_to_end_publication_is_create_only(self):
        baseline = packed([("a.py", b"A")])
        candidate = packed([("a.py", b"B"), ("new.py", b"N")])
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            bp = td / "baseline.tar.gz"
            cp = td / "candidate.tar.gz"
            out = td / "component"
            bp.write_bytes(baseline)
            cp.write_bytes(candidate)
            with self.baseline_contract(baseline):
                manifest = exp.export_component(
                    baseline_path=bp, candidate_path=cp,
                    candidate_sha256=exp.digest(candidate), out_dir=out,
                    component_id="winner")
                on_disk = json.loads((out / "COMPONENT.json").read_text())
                self.assertEqual(on_disk, manifest)
                for spec in list(manifest["replacements"].values()) + list(manifest["additions"].values()):
                    self.assertTrue((out / spec["source"]).is_file())
                with self.assertRaisesRegex(exp.ExportError, "not empty"):
                    exp.export_component(
                        baseline_path=bp, candidate_path=cp,
                        candidate_sha256=exp.digest(candidate), out_dir=out,
                        component_id="winner")

    def test_failed_publication_empty_scaffold_can_retry_same_output(self):
        baseline = packed([("a", b"A")])
        candidate = packed([("a", b"B")])
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            bp = td / "b.tgz"
            cp = td / "c.tgz"
            out = td / "out"
            bp.write_bytes(baseline)
            cp.write_bytes(candidate)
            real_publish = exp.publish_exclusive
            first = True

            def fail_once(requested):
                nonlocal first
                if first:
                    first = False
                    requested[1][0].parent.mkdir(parents=True, exist_ok=True)
                    raise OSError("injected publication failure")
                return real_publish(requested)

            with self.baseline_contract(baseline), mock.patch.object(
                exp, "publish_exclusive", side_effect=fail_once
            ):
                with self.assertRaisesRegex(exp.ExportError, "injected publication failure"):
                    exp.export_component(
                        baseline_path=bp,
                        candidate_path=cp,
                        candidate_sha256=exp.digest(candidate),
                        out_dir=out,
                        component_id="x",
                    )
                self.assertTrue((out / "files").is_dir())
                self.assertEqual([], list((out / "files").iterdir()))
                exp.export_component(
                    baseline_path=bp,
                    candidate_path=cp,
                    candidate_sha256=exp.digest(candidate),
                    out_dir=out,
                    component_id="x",
                )
            self.assertTrue((out / "COMPONENT.json").is_file())

    def test_empty_existing_output_directory_can_recover(self):
        baseline = packed([("a", b"A")])
        candidate = packed([("a", b"B")])
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            bp = td / "b.tgz"
            cp = td / "c.tgz"
            out = td / "out"
            bp.write_bytes(baseline)
            cp.write_bytes(candidate)
            out.mkdir()
            with self.baseline_contract(baseline):
                exp.export_component(
                    baseline_path=bp, candidate_path=cp,
                    candidate_sha256=exp.digest(candidate), out_dir=out,
                    component_id="x")
            self.assertTrue((out / "COMPONENT.json").is_file())


if __name__ == "__main__":
    unittest.main()
