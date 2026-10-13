import contextlib
import gzip
import io
import json
import tarfile
import unittest
from unittest import mock

import export_staging_component as exp


def packed(files):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for name, body in files:
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = 0o644
            info.mtime = 0
            tf.addfile(info, io.BytesIO(body))
    out = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=out, mode="wb", mtime=0) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def replacement_component(cid, member, before, after, *, conflicts_with=None):
    return {
        "component_id": cid,
        "manifest_sha256": "1" * 64,
        "depends_on": [],
        "conflicts_with": list(conflicts_with or []),
        "replacements": {member: {
            "preimage_sha256": exp.digest(before),
            "postimage_sha256": exp.digest(after),
            "overlap_after": None,
        }},
        "additions": {},
    }


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


class StagedHistoryGraphTests(unittest.TestCase):
    def baseline_contract(self, baseline):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(exp, "BASELINE_SHA256", exp.digest(baseline)))
        stack.enter_context(
            mock.patch.object(exp.staging_composer, "BASELINE_SHA256", exp.digest(baseline))
        )
        return stack

    def nonbaseline_inputs(self, *, historical_conflicts=None):
        baseline = packed([("a", b"A"), ("b", b"B")])
        current = packed([("a", b"X"), ("b", b"B")])
        candidate = packed([("a", b"X"), ("b", b"Y")])
        receipt = receipt_for(
            baseline,
            current,
            [replacement_component(
                "first", "a", b"A", b"X", conflicts_with=historical_conflicts
            )],
        )
        common = {
            "baseline_raw": baseline,
            "current_raw": current,
            "candidate_raw": candidate,
            "candidate_sha256": exp.digest(candidate),
            "current_sha256": exp.digest(current),
            "current_receipt_raw": receipt,
            "current_receipt_sha256": exp.digest(receipt),
        }
        return baseline, common

    def test_baseline_export_rejects_missing_dependency(self):
        baseline = packed([("a", b"A")])
        candidate = packed([("a", b"B")])
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(exp.ExportError, "unsatisfied dependency: ghost"):
                exp.derive_component(
                    baseline_raw=baseline,
                    current_raw=baseline,
                    candidate_raw=candidate,
                    candidate_sha256=exp.digest(candidate),
                    current_sha256=None,
                    component_id="new",
                    depends_on=["ghost"],
                )

    def test_nonbaseline_export_rejects_missing_dependency(self):
        baseline, common = self.nonbaseline_inputs()
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(exp.ExportError, "unsatisfied dependency: ghost"):
                exp.derive_component(
                    **common,
                    component_id="new",
                    depends_on=["ghost"],
                )

    def test_nonbaseline_export_rejects_conflict_with_included_component(self):
        baseline, common = self.nonbaseline_inputs()
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(
                exp.ExportError, "conflicts with included component: first"
            ):
                exp.derive_component(
                    **common,
                    component_id="new",
                    conflicts_with=["first"],
                )

    def test_nonbaseline_export_rejects_reverse_historical_conflict(self):
        baseline, common = self.nonbaseline_inputs(historical_conflicts=["new"])
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(
                exp.ExportError, "historical component first conflicts with new"
            ):
                exp.derive_component(
                    **common,
                    component_id="new",
                )

    def test_nonbaseline_export_rejects_reused_component_id(self):
        baseline, common = self.nonbaseline_inputs()
        with self.baseline_contract(baseline):
            with self.assertRaisesRegex(
                exp.ExportError, "component_id already included in current history: first"
            ):
                exp.derive_component(
                    **common,
                    component_id="first",
                )


if __name__ == "__main__":
    unittest.main()
