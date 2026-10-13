import copy
import json
import stat
import tempfile
import unittest
import warnings
import zipfile
from hashlib import sha256
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import *
from priors import build as build_priors
from experiment import run as run_experiment
from pack import (
    VerificationError,
    build as build_pack,
    verify,
    verify_bundle,
    write_verification_proof,
)
from readiness import aggregate
from profile_runtime import profile


class CoreTests(unittest.TestCase):
    def test_unicode_normalize(self):
        self.assertEqual(normalize_transcript("  Á—B  O’Neil! "), "á b o'neil")

    def test_combining_marks_normalize(self):
        self.assertEqual(normalize_transcript("A\u0304"), "ā")

    def test_wer(self):
        self.assertEqual(corpus_wer(["a b"], ["a c"]), 0.5)

    def test_empty_ref(self):
        self.assertEqual(corpus_wer([""], [""]), 0.0)

    def test_mismatched_len(self):
        with self.assertRaises(ValueError):
            corpus_wer(["a"], [])

    def test_evidence_rejects_unknown_class(self):
        with self.assertRaises(ValueError):
            TranscriptEvidence("sp-en", "a", "private_competition", "x").validate()

    def test_evidence_rejects_track(self):
        with self.assertRaises(ValueError):
            TranscriptEvidence("xx", "a", "synthetic", "x").validate()

    def test_prior_track_bound(self):
        rows = [TranscriptEvidence("sp-en", "a b", "synthetic", "x")]
        p = TrackPrior.fit("sp-en", rows)
        self.assertEqual(p.track, "sp-en")
        self.assertEqual(p.transcript_count, 1)

    def test_prior_no_rows(self):
        with self.assertRaises(ValueError):
            TrackPrior.fit("sp-en", [])

    def test_consensus_deterministic(self):
        hs = [Hypothesis("a b", "x", 0), Hypothesis("a c", "y", 1), Hypothesis("a b", "z", 2)]
        a = choose_consensus("sp-en", hs)
        b = choose_consensus("sp-en", hs)
        self.assertEqual(a.evidence_sha256, b.evidence_sha256)
        self.assertEqual(a.text, "a b")

    def test_consensus_prior_mismatch(self):
        p = TrackPrior.fit("id-jv", [TranscriptEvidence("id-jv", "a b", "synthetic", "x")])
        with self.assertRaises(ValueError):
            choose_consensus("sp-en", [Hypothesis("a b", "x"), Hypothesis("a c", "y")], prior=p)

    def test_consensus_requires_two(self):
        with self.assertRaises(ValueError):
            choose_consensus("sp-en", [Hypothesis("a", "x")])

    def test_tie_abstains(self):
        r = choose_consensus(
            "sp-en",
            [Hypothesis("a b", "x", 0), Hypothesis("a c", "y", 0)],
            config=ConsensusConfig(margin_abstain=1.0),
        )
        self.assertTrue(r.abstain)


class PipelineTests(unittest.TestCase):
    def test_prior_and_experiment(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            pri = d / "p.json"
            rep = d / "r.json"
            payload = build_priors(ROOT / "fixtures/prior_evidence.jsonl", pri)
            self.assertEqual(set(payload["priors"]), set(TRACKS))
            report = run_experiment(ROOT / "fixtures/experiment.jsonl", rep, pri)
            self.assertEqual(set(report["tracks"]), set(TRACKS))
            self.assertEqual(report["tracks"]["sp-en"]["consensus_wer"], 0.0)

    def _source(self, d: Path, track: str = "sp-en") -> Path:
        s = d / f"src-{track}"
        s.mkdir()
        for f in ("core.py", "profiles.json", "runtime_contract.json"):
            (s / f).write_bytes((ROOT / f).read_bytes())
        (s / "main.py").write_text("print('offline')\n", encoding="utf-8")
        (s / "model_config.json").write_text(
            json.dumps({"track": track, "models": [{"name": "a"}, {"name": "b"}]}), encoding="utf-8"
        )
        return s

    def _valid(self, d: Path, track: str = "sp-en"):
        s = self._source(d, track)
        z = d / f"{track}.zip"
        r = d / f"{track}.build.json"
        p = d / f"{track}.proof.json"
        build_pack(s, track, z, r)
        proof = write_verification_proof(z, r, p)
        return s, z, r, p, proof

    def _copy_zip_add(self, source_zip: Path, dest_zip: Path, name: str, data: bytes, *, external_attr: int | None = None):
        with zipfile.ZipFile(source_zip) as src, zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():
                copied = zipfile.ZipInfo(info.filename, info.date_time)
                copied.compress_type = info.compress_type
                copied.external_attr = info.external_attr
                dst.writestr(copied, src.read(info))
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            if external_attr is not None:
                info.external_attr = external_attr
            dst.writestr(info, data)

    def _retarget_receipt_bundle(self, receipt_path: Path, zip_path: Path):
        r = json.loads(receipt_path.read_text(encoding="utf-8"))
        raw = zip_path.read_bytes()
        r["bundle_sha256"] = sha256(raw).hexdigest()
        r["bundle_bytes"] = len(raw)
        receipt_path.write_text(canonical_json(r), encoding="utf-8")

    def _all_three(self, d: Path):
        entries = []
        for t in sorted(TRACKS):
            _, z, r, p, _ = self._valid(d, t)
            entries.append((z, r, p))
        return entries

    def test_pack_reproducible_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            s = self._source(d)
            z1, r1 = d / "a.zip", d / "a.json"
            z2, r2 = d / "b.zip", d / "b.json"
            build_pack(s, "sp-en", z1, r1)
            build_pack(s, "sp-en", z2, r2)
            self.assertEqual(z1.read_bytes(), z2.read_bytes())
            self.assertTrue(verify(z1, r1))
            self.assertEqual(verify_bundle(z1, r1), verify_bundle(z2, r2))

    def test_pack_rejects_model_track_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            s = self._source(d, "sp-en")
            with self.assertRaises(ValueError):
                build_pack(s, "id-jv", d / "a.zip", d / "a.json")

    def test_pack_reject_network_import(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            s = self._source(d)
            (s / "bad.py").write_text("import requests\n")
            with self.assertRaises(ValueError):
                build_pack(s, "sp-en", d / "a.zip", d / "a.json")

    def test_pack_reject_network_literal(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            s = self._source(d)
            (s / "bad.py").write_text("X='https://example.com'\n")
            with self.assertRaises(ValueError):
                build_pack(s, "sp-en", d / "a.zip", d / "a.json")

    def test_pack_reject_oversize(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            s = self._source(d)
            with self.assertRaises(ValueError):
                build_pack(s, "sp-en", d / "a.zip", d / "a.json", max_bytes=1)

    def test_verify_detects_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _, z, r, _, _ = self._valid(d)
            z.write_bytes(z.read_bytes() + b"x")
            self.assertFalse(verify(z, r))

    def test_forged_empty_manifest_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _, z, r, _, _ = self._valid(d)
            forged = json.loads(r.read_text())
            forged["files"] = []
            forged.pop("manifest_sha256", None)
            r.write_text(canonical_json(forged))
            self.assertFalse(verify(z, r))

    def test_unmanifested_extra_payload_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _, z, r, _, _ = self._valid(d)
            evil = d / "evil.zip"
            self._copy_zip_add(z, evil, "evil_payload.py", b"print('surprise')\n")
            self._retarget_receipt_bundle(r, evil)
            with self.assertRaisesRegex(VerificationError, "unmanifested"):
                verify_bundle(evil, r)

    def test_duplicate_archive_member_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _, z, r, _, _ = self._valid(d)
            dup = d / "dup.zip"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                self._copy_zip_add(z, dup, "core.py", b"print('shadow')\n")
            self._retarget_receipt_bundle(r, dup)
            with self.assertRaisesRegex(VerificationError, "duplicate archive member"):
                verify_bundle(dup, r)

    def test_traversal_archive_member_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _, z, r, _, _ = self._valid(d)
            bad = d / "traversal.zip"
            self._copy_zip_add(z, bad, "../escape.py", b"pass\n")
            self._retarget_receipt_bundle(r, bad)
            with self.assertRaisesRegex(VerificationError, "unsafe archive member"):
                verify_bundle(bad, r)

    def test_absolute_archive_member_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _, z, r, _, _ = self._valid(d)
            bad = d / "absolute.zip"
            self._copy_zip_add(z, bad, "/tmp/escape.py", b"pass\n")
            self._retarget_receipt_bundle(r, bad)
            with self.assertRaisesRegex(VerificationError, "relative file"):
                verify_bundle(bad, r)

    def test_symlink_archive_member_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _, z, r, _, _ = self._valid(d)
            bad = d / "symlink.zip"
            self._copy_zip_add(z, bad, "link", b"core.py", external_attr=(stat.S_IFLNK | 0o777) << 16)
            self._retarget_receipt_bundle(r, bad)
            with self.assertRaisesRegex(VerificationError, "special archive member"):
                verify_bundle(bad, r)

    def test_expansion_ceiling_rejected_before_readiness(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _, z, r, _, _ = self._valid(d)
            with self.assertRaisesRegex(VerificationError, "expanded-byte ceiling"):
                verify_bundle(z, r, max_expanded_bytes=10)

    def test_member_ceiling_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _, z, r, _, _ = self._valid(d)
            with self.assertRaisesRegex(VerificationError, "member ceiling"):
                verify_bundle(z, r, max_members=1)

    def test_receipt_size_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _, z, r, _, _ = self._valid(d)
            receipt = json.loads(r.read_text())
            receipt["bundle_bytes"] += 1
            r.write_text(canonical_json(receipt))
            with self.assertRaisesRegex(VerificationError, "bundle_bytes mismatch"):
                verify_bundle(z, r)

    def test_receipt_runtime_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _, z, r, _, _ = self._valid(d)
            receipt = json.loads(r.read_text())
            receipt["runtime_commit"] = "wrong"
            r.write_text(canonical_json(receipt))
            with self.assertRaisesRegex(VerificationError, "runtime_commit mismatch"):
                verify_bundle(z, r)

    def test_duplicate_manifest_row_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _, z, r, _, _ = self._valid(d)
            receipt = json.loads(r.read_text())
            receipt["files"].append(copy.deepcopy(receipt["files"][0]))
            receipt.pop("manifest_sha256", None)
            r.write_text(canonical_json(receipt))
            with self.assertRaisesRegex(VerificationError, "duplicate manifest"):
                verify_bundle(z, r)

    def test_verifier_proof_is_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _, z, r, p, proof = self._valid(d)
            self.assertEqual(json.loads(p.read_text()), proof)
            self.assertEqual(proof, verify_bundle(z, r))
            self.assertEqual(len(proof["proof_sha256"]), 64)

    def test_readiness_all_three_verified(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            out = d / "ready.json"
            result = aggregate(self._all_three(d), out)
            self.assertEqual(result["state"], "ALL_THREE_LOCAL_BUNDLES_STRUCTURALLY_READY")
            self.assertFalse(result["provider_submission"])
            self.assertFalse(result["model_execution_proven"])
            self.assertEqual(len(result["verified_bundles"]), 3)

    def test_readiness_rejects_old_build_receipts_only(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            paths = []
            for t in sorted(TRACKS):
                p = d / f"{t}.json"
                p.write_text(json.dumps({"track": t, "accepted": True, "runtime_commit": "fake", "internet_at_execution": False, "bundle_sha256": "00"}))
                paths.append((p, p, p))
            result = aggregate(paths, d / "ready.json")
            self.assertEqual(result["state"], "HOLD")

    def test_readiness_hand_authored_proof_rejected_by_rederivation(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            entries = self._all_three(d)
            z, r, p = entries[0]
            proof = json.loads(p.read_text())
            proof["bundle_sha256"] = "0" * 64
            payload = {k: v for k, v in proof.items() if k != "proof_sha256"}
            proof["proof_sha256"] = sha256(canonical_json(payload).encode()).hexdigest()
            p.write_text(canonical_json(proof))
            result = aggregate(entries, d / "ready.json")
            self.assertEqual(result["state"], "HOLD")
            self.assertTrue(any("does not equal fresh bundle derivation" in x for x in result["reasons"]))

    def test_readiness_cross_track_proof_transplant_holds(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            entries = self._all_three(d)
            z, r, p = entries[0]
            proof = json.loads(p.read_text())
            proof["track"] = "sp-nh" if proof["track"] != "sp-nh" else "sp-en"
            payload = {k: v for k, v in proof.items() if k != "proof_sha256"}
            proof["proof_sha256"] = sha256(canonical_json(payload).encode()).hexdigest()
            p.write_text(canonical_json(proof))
            self.assertEqual(aggregate(entries, d / "r.json")["state"], "HOLD")

    def test_readiness_duplicate_track_holds(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            entries = self._all_three(d)
            entries[1] = entries[0]
            result = aggregate(entries, d / "r.json")
            self.assertEqual(result["state"], "HOLD")
            self.assertTrue(any("each track exactly once" in x for x in result["reasons"]))

    def test_readiness_runtime_contract_mismatch_holds(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            entries = self._all_three(d)
            z, r, p = entries[1]
            # Build a still-valid bundle with a different runtime commit, then verify it.
            track = json.loads(r.read_text())["track"]
            src = d / "runtime-drift"
            src.mkdir()
            for f in ("core.py", "profiles.json"):
                (src / f).write_bytes((ROOT / f).read_bytes())
            runtime = json.loads((ROOT / "runtime_contract.json").read_text())
            runtime["upstream_commit"] = "different-runtime"
            (src / "runtime_contract.json").write_text(canonical_json(runtime))
            (src / "main.py").write_text("print('offline')\n")
            (src / "model_config.json").write_text(json.dumps({"track": track, "models": [{"name": "a"}, {"name": "b"}]}))
            z2, r2, p2 = d / "drift.zip", d / "drift.build.json", d / "drift.proof.json"
            build_pack(src, track, z2, r2)
            write_verification_proof(z2, r2, p2)
            entries[1] = (z2, r2, p2)
            result = aggregate(entries, d / "r.json")
            self.assertEqual(result["state"], "HOLD")
            self.assertTrue(any("runtime commit mismatch" in x or "runtime contract mismatch" in x for x in result["reasons"]))

    def test_runtime_profiler_accepts_bounded_smoke(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "p.json"
            r = profile([sys.executable, "-c", "print(42)"], out, timeout_s=3, max_wall_s=3, max_rss_mib=4096)
            self.assertTrue(r["accepted"])
            self.assertEqual(r["returncode"], 0)

    def test_runtime_profiler_rejects_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "p.json"
            r = profile([sys.executable, "-c", "raise SystemExit(7)"], out, timeout_s=3, max_wall_s=3, max_rss_mib=4096)
            self.assertFalse(r["accepted"])
            self.assertEqual(r["returncode"], 7)


if __name__ == "__main__":
    unittest.main()
