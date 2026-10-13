import csv
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


score = load("score_compat", ROOT / "tools" / "score_compat.py")
builder = load("build_submission", ROOT / "tools" / "build_submission.py")
validator = load("validate_submission", ROOT / "tools" / "validate_submission.py")
split_manifest = load("split_manifest", ROOT / "tools" / "split_manifest.py")


class PipelineTests(unittest.TestCase):
    def test_normalization_preserves_orthography_but_matches_public_punctuation_rules(self):
        raw = 'Áxkan, [ruido] entonces (tikneki) ¿Cien pesos? ...'
        self.assertEqual(score.normalize_text(raw), "áxkan entonces tikneki Cien pesos ...")

    def test_corpus_wer(self):
        refs = ["ni mits ilwia cien pesos", "hola"]
        hyps = ["ni mits ilwia cien peso", "hola"]
        self.assertAlmostEqual(score.corpus_wer(refs, hyps), 1 / 6)

    def test_deterministic_pack_has_root_main_and_no_audio(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "src"
            src.mkdir()
            (src / "main.py").write_text("print('ok')\n", encoding="utf-8")
            (src / "notes.txt").write_text("stable\n", encoding="utf-8")
            first, second = td / "a.zip", td / "b.zip"
            a = builder.build(src, first)
            b = builder.build(src, second)
            self.assertEqual(a, b)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(sorted(archive.namelist()), ["main.py", "notes.txt"])
            validator.validate_zip(first)

    def test_builder_rejects_audio(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "src"
            src.mkdir()
            (src / "main.py").write_text("pass\n", encoding="utf-8")
            (src / "speaker.wav").write_bytes(b"not-real-audio")
            with self.assertRaisesRegex(ValueError, "audio"):
                builder.build(src, td / "submission.zip")

    def test_split_manifest_is_stable_and_does_not_copy_transcripts(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            source = td / "metadata.csv"
            source.write_text(
                "audio_filename,transcript,speaker\n"
                "a.wav,secret one,s1\n"
                "b.wav,secret two,s2\n",
                encoding="utf-8",
            )
            first = split_manifest.build_manifest(source, td / "one.json", seed="fixed", validation_fraction=0.5)
            second = split_manifest.build_manifest(source, td / "two.json", seed="fixed", validation_fraction=0.5)
            self.assertEqual(first, second)
            serialized = (td / "one.json").read_text(encoding="utf-8")
            self.assertNotIn("secret one", serialized)
            self.assertNotIn("speaker", serialized)
            self.assertEqual([r["audio_filename"] for r in first["rows"]], ["a.wav", "b.wav"])
            self.assertEqual(first["source_csv_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())

    def test_csv_contract_and_key_alignment(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            fmt = td / "submission_format.csv"
            pred = td / "submission.csv"
            for path, rows in (
                (fmt, [("a.wav", ""), ("b.wav", "")]),
                (pred, [("b.wav", "hola"), ("a.wav", "niltze")]),
            ):
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(["audio_filename", "transcript"])
                    writer.writerows(rows)
            validator.validate_csv(pred, fmt)


if __name__ == "__main__":
    unittest.main()
