"""Independent, pinned fixture checks; verification never reseals checked-in files."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
NAME = '_uiowa032_fixture_generator_' + hashlib.sha256(str(HERE).encode()).hexdigest()[:12]
SPEC = importlib.util.spec_from_file_location(NAME, HERE / 'make_synthetic_corpus.py')
if SPEC is None or SPEC.loader is None:
    raise RuntimeError('Cannot load fixture generator')
corpus = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(corpus)
EXTRACT_SPEC = importlib.util.spec_from_file_location(NAME + '_extract', HERE / 'extract.py')
if EXTRACT_SPEC is None or EXTRACT_SPEC.loader is None:
    raise RuntimeError('Cannot load original extraction interface')
extract = importlib.util.module_from_spec(EXTRACT_SPEC)
sys.modules[EXTRACT_SPEC.name] = extract
EXTRACT_SPEC.loader.exec_module(extract)

# Independent expectations: generation does not write or recompute these constants.
PINS = {
    'blank.pdf': (581, '30fc26e616121afb5c3807bc9ed9c6545d8c3cfd02ad62150082b2cb059d4e9e'),
    'sample.docx': (1939, '8f36c9232b62001c183db65e900c6dc8f162e2f1d003277f8bbb18d4f204cb52'),
    'sample.pdf': (920, 'bc6d27b06cc92fca0e9a399f88722104db00b84ed46ce5e000ba43f8e26bacdf'),
    'sample.txt': (160, '762501465412bb8589fc358495c1444c6d886a0c305bc907af702dd9cc938875'),
}


def inventory(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}


def mismatched_pins(root):
    changed = []
    for name, (size, digest) in PINS.items():
        path = root / name
        if not path.is_file():
            changed.append(name)
            continue
        data = path.read_bytes()
        if (len(data), hashlib.sha256(data).hexdigest()) != (size, digest):
            changed.append(name)
    return changed


class FixtureIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_generated_bytes_match_independent_pins(self):
        corpus.build_corpus(self.root)
        self.assertEqual(mismatched_pins(self.root), [])

    def test_manifest_matches_pins_and_declares_fiction(self):
        emitted = corpus.build_corpus(self.root)
        saved = json.loads((self.root / 'manifest.json').read_text())
        self.assertEqual(emitted, saved)
        self.assertEqual(set(saved), set(PINS))
        for name, (size, digest) in PINS.items():
            self.assertEqual(saved[name], {'bytes': size, 'sha256': digest, 'synthetic': True})

    def test_two_locations_and_two_clocks_generate_identical_bytes(self):
        a, b = self.root / 'a', self.root / 'other' / 'b'
        with patch('time.localtime', return_value=(2000, 1, 2, 3, 4, 6, 6, 2, 0)):
            corpus.build_corpus(a)
        with patch('time.localtime', return_value=(2035, 8, 9, 10, 11, 12, 3, 221, 0)):
            corpus.build_corpus(b)
        self.assertEqual({k: v[0] for k, v in inventory(a).items()},
                         {k: v[0] for k, v in inventory(b).items()})

    def test_word_container_metadata_is_fixed(self):
        corpus.build_corpus(self.root)
        with zipfile.ZipFile(self.root / 'sample.docx') as zf:
            self.assertEqual(zf.namelist(), ['[Content_Types].xml', '_rels/.rels', 'word/document.xml'])
            for info in zf.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(info.create_system, 3)
                self.assertEqual(info.external_attr, 0o100644 << 16)

    def test_unrelated_file_is_unchanged_and_not_manifested(self):
        other = self.root / 'unrelated-evidence.txt'
        other.write_bytes(b'Unrelated example, not owned by the fixture generator.\n')
        before = (other.read_bytes(), other.stat().st_mtime_ns)
        manifest = corpus.build_corpus(self.root)
        self.assertNotIn(other.name, manifest)
        self.assertEqual((other.read_bytes(), other.stat().st_mtime_ns), before)

    def test_independent_verification_detects_tamper_without_healing(self):
        corpus.build_corpus(self.root)
        p = self.root / 'sample.txt'
        p.write_bytes(p.read_bytes() + b'Changed synthetic source.\n')
        # Even a self-consistent newly written manifest cannot change the independent pins.
        manifest = json.loads((self.root / 'manifest.json').read_text())
        manifest['sample.txt']['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
        manifest['sample.txt']['bytes'] = p.stat().st_size
        (self.root / 'manifest.json').write_text(json.dumps(manifest))
        before = inventory(self.root)
        for _ in range(3):
            self.assertEqual(mismatched_pins(self.root), ['sample.txt'])
        self.assertEqual(inventory(self.root), before)

    def test_cli_explicit_output_matches_pins(self):
        output = self.root / 'cli-output'
        proc = subprocess.run([sys.executable, *(['-O'] if sys.flags.optimize else []), str(HERE / 'make_synthetic_corpus.py'),
                               '--output-dir', str(output)], capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(mismatched_pins(output), [])

    def test_existing_suite_does_not_mutate_any_lane_fixture(self):
        lane = self.root / 'lane'
        lane.mkdir()
        for name in ('extract.py', 'make_synthetic_corpus.py', 'test_extract.py'):
            shutil.copyfile(HERE / name, lane / name)
        fixtures = lane / 'fixtures'
        fixtures.mkdir()
        # Deliberately do not use valid generated bytes: setup must never overwrite these.
        for name in (*PINS, 'manifest.json'):
            (fixtures / name).write_bytes(b'Preserve these previously retained fixture bytes.\n')
        before = inventory(lane)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        proc = subprocess.run([sys.executable, *(['-O'] if sys.flags.optimize else []), '-m', 'unittest', '-v', 'test_extract'],
                              cwd=lane, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(inventory(lane), before)

    def test_no_backend_runs_non_pdf_tests_and_preserves_skips(self):
        # -I -S strips PYTHONPATH and site packages. Add only this component explicitly.
        code = ('import sys,unittest; sys.path.insert(0,sys.argv[1]); '
                'suite=unittest.defaultTestLoader.loadTestsFromNames(["test_extract"]); '
                'r=unittest.TextTestRunner(verbosity=2).run(suite); '
                'raise SystemExit(0 if r.wasSuccessful() and len(r.skipped)==2 else 1)')
        proc = subprocess.run([sys.executable, *(['-O'] if sys.flags.optimize else []), '-I', '-S', '-c', code, str(HERE)],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn('skipped=2', proc.stderr)

    def test_missing_pdf_backend_has_named_error(self):
        source = self.root / "synthetic.pdf"
        corpus._write_minimal_pdf(source, ["Synthetic dependency contract."])
        with patch.dict(sys.modules, {"pypdf": None}):
            with self.assertRaisesRegex(extract.ExtractionError, "PDF_BACKEND_UNAVAILABLE"):
                extract.extract(source)


if __name__ == '__main__':
    unittest.main()
