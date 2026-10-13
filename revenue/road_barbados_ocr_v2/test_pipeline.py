from .test_support import *  # noqa: F401,F403


class PipelineTests(unittest.TestCase):
    def test_profile_structure_recomputed_receipt_still_rejected(self):
        m = manifest(); p = build_profile(m, labels(), oof()); p["models"][0]["metric"]["reference_words"] = -1
        p.pop("receipt_sha256"); p["receipt_sha256"] = sha256_hex(p)
        with self.assertRaisesRegex(RoadV2Error, "profile metric invalid"):
            ensemble(m, p, labels(), preds())

    def test_ensemble_consensus_and_determinism(self):
        m = manifest(); l = labels(); p = build_profile(m, l, oof()); first, a1 = ensemble(m, p, l, preds())
        reverse = {k: dict(reversed(list(v.items()))) for k, v in reversed(list(preds().items()))}
        second, a2 = ensemble(m, p, l, reverse)
        self.assertEqual(first, second)
        self.assertEqual(canonical_bytes(a1), canonical_bytes(a2))
        self.assertEqual(first["te1"], "John Thomas")

    def test_ensemble_prediction_model_mismatch(self):
        m = manifest(); p = build_profile(m, labels(), oof()); bad = preds(); bad.pop("gamma")
        with self.assertRaisesRegex(RoadV2Error, "prediction model set"):
            ensemble(m, p, labels(), bad)

    def test_ensemble_prediction_id_mismatch(self):
        m = manifest(); p = build_profile(m, labels(), oof()); bad = preds(); bad["gamma"].pop("te2")
        with self.assertRaisesRegex(RoadV2Error, "prediction ID sets"):
            ensemble(m, p, labels(), bad)

    def test_pseudo_admits_consensus(self):
        *_, chosen, audit, _, _, _, _ = artifacts()
        pseudo = admit_pseudo_labels(audit, chosen, min_support_models=2, min_support_ppm=500_000, min_agreement_ppm=700_000)
        self.assertEqual({x["id"] for x in pseudo["rows"]}, {"te1", "te2"})
        self.assertFalse(pseudo["authority"]["self_training_authorized_by_artifact"])

    def test_pseudo_threshold_can_hold(self):
        *_, chosen, audit, _, _, _, _ = artifacts()
        pseudo = admit_pseudo_labels(audit, chosen, min_support_models=3, min_support_ppm=1_000_000, min_agreement_ppm=1_000_000)
        self.assertLessEqual(len(pseudo["rows"]), 1)

    def test_pseudo_audit_id_transplant(self):
        *_, chosen, audit, _, _, _, _ = artifacts(); audit = deepcopy(audit)
        audit["rows"][0]["id_sha256"] = "0" * 64; audit.pop("receipt_sha256"); audit["receipt_sha256"] = sha256_hex(audit)
        with self.assertRaisesRegex(RoadV2Error, "AUDIT_ID_TRANSPLANT"):
            admit_pseudo_labels(audit, chosen)

    def test_pseudo_audit_text_transplant(self):
        *_, chosen, audit, _, _, _, _ = artifacts(); changed = dict(chosen); changed["te1"] = "changed"
        with self.assertRaisesRegex(RoadV2Error, "AUDIT_TEXT_TRANSPLANT"):
            admit_pseudo_labels(audit, changed)

    def test_pseudo_audit_authority_escalation_recomputed_receipt(self):
        *_, chosen, audit, _, _, _, _ = artifacts(); audit = deepcopy(audit); audit["authority"]["manual_test_labels"] = True
        audit.pop("receipt_sha256"); audit["receipt_sha256"] = sha256_hex(audit)
        with self.assertRaisesRegex(RoadV2Error, "AUDIT_AUTHORITY_ESCALATION"):
            admit_pseudo_labels(audit, chosen)

    def test_submission_preserves_sample_order(self):
        *_, chosen, _, _, _, _, _ = artifacts(); sample = b"ID,transcription\nte2,\nte1,\n"
        sub = compile_submission(sample, chosen).decode()
        self.assertEqual(sub.splitlines()[1].split(",")[0], "te2")
        self.assertEqual(sub.splitlines()[2].split(",")[0], "te1")

    def test_submission_id_mismatch(self):
        with self.assertRaisesRegex(RoadV2Error, "ID set"):
            compile_submission(b"ID,text\nx,\n", {"y": "value"})

    def test_submission_duplicate_sample_id(self):
        with self.assertRaisesRegex(RoadV2Error, "duplicate"):
            compile_submission(b"ID,text\nx,\nx,\n", {"x": "value"})

    def test_csv_duplicate_header(self):
        with self.assertRaisesRegex(RoadV2Error, "duplicate header"):
            csv_text_map(b"ID,ID\nx,y\n", where="bad")

    def test_receipt_verifies(self):
        *_, sample, sub, receipt = artifacts()
        self.assertTrue(verify_receipt(receipt, sample_raw=sample, submission_raw=sub))

    def test_receipt_tamper_fails(self):
        *_, sample, sub, receipt = artifacts(); receipt["submission_sha256"] = "0" * 64
        self.assertFalse(verify_receipt(receipt, sample_raw=sample, submission_raw=sub))

    def test_receipt_sample_tamper_fails(self):
        *_, sample, sub, receipt = artifacts()
        self.assertFalse(verify_receipt(receipt, sample_raw=sample + b"x", submission_raw=sub))

    def test_receipt_submission_tamper_fails(self):
        *_, sample, sub, receipt = artifacts()
        self.assertFalse(verify_receipt(receipt, sample_raw=sample, submission_raw=sub + b"x"))

    def test_build_receipt_rejects_pseudo_authority_even_rehashed(self):
        m, _, p, _, audit, pseudo, sample, sub, _ = artifacts(); pseudo = deepcopy(pseudo)
        pseudo["authority"]["submission_authorized"] = True; pseudo.pop("receipt_sha256"); pseudo["receipt_sha256"] = sha256_hex(pseudo)
        dig = {k: sha256_hex(canonical_bytes(v)) for k, v in preds().items()}
        with self.assertRaisesRegex(RoadV2Error, "PSEUDO_AUTHORITY_ESCALATION"):
            build_receipt(m, p, audit, pseudo, sample_raw=sample, submission_raw=sub, input_prediction_digests=dig)

    def test_cli_end_to_end_and_create_exclusive(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); (td / "manifest.json").write_bytes(canonical_bytes(manifest()))
            (td / "train.csv").write_text("ID,text\n" + "\n".join(f"{k},{v}" for k,v in labels().items()) + "\n", encoding="utf-8")
            for mid, rows in oof().items():
                (td / f"oof-{mid}.csv").write_text("ID,text\n" + "\n".join(f"{k},{v}" for k,v in rows.items()) + "\n", encoding="utf-8")
            for mid, rows in preds().items():
                (td / f"pred-{mid}.csv").write_text("ID,text\n" + "\n".join(f"{k},{v}" for k,v in rows.items()) + "\n", encoding="utf-8")
            (td / "sample.csv").write_bytes(b"ID,transcription\nte2,\nte1,\n")
            out = td / "out"
            cmd = [sys.executable, "-m", "revenue.road_barbados_ocr_v2.cli", "build", "--manifest", str(td/"manifest.json"), "--train", str(td/"train.csv"), "--sample", str(td/"sample.csv"), "--out", str(out)]
            for mid in ("alpha", "beta", "gamma"):
                cmd += ["--oof", f"{mid}={td/f'oof-{mid}.csv'}", "--pred", f"{mid}={td/f'pred-{mid}.csv'}"]
            run = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("LOCAL_BUILD_COMPLETE_NOT_SUBMITTED", run.stdout)
            self.assertEqual({p.name for p in out.iterdir()}, {"submission.csv", "profile.json", "ensemble-audit.json", "pseudo-labels.json", "receipt.json"})
            verify = subprocess.run([sys.executable, "-m", "revenue.road_barbados_ocr_v2.cli", "verify", "--receipt", str(out/"receipt.json"), "--sample", str(td/"sample.csv"), "--submission", str(out/"submission.csv")], cwd=root, capture_output=True, text=True)
            self.assertEqual((verify.returncode, verify.stdout.strip()), (0, "PASS"))
            again = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertIn("already exists", again.stderr)

    def test_source_package_deterministic_and_excludes_data(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            a = build_package(root, td/"a.zip", td/"a.json")
            b = build_package(root, td/"b.zip", td/"b.json")
            self.assertEqual((td/"a.zip").read_bytes(), (td/"b.zip").read_bytes())
            self.assertEqual(a["archive_sha256"], b["archive_sha256"])
            self.assertFalse(any(a["authority"].values()))
            self.assertFalse(any("Train.csv" in r["path"] or "images" in r["path"] for r in a["files"]))
