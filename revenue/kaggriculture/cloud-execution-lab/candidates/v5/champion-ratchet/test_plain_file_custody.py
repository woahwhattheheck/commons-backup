#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import threading
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("champion_gate_tests", HERE/"test_champion_gate.py")
T=importlib.util.module_from_spec(SPEC); assert SPEC and SPEC.loader; SPEC.loader.exec_module(T)
G=T.G

class PlainFileCustodyTests(unittest.TestCase):
    def setUp(self): self.f=T.Fixture()
    def tearDown(self): self.f.close()

    @staticmethod
    def _replace_with_symlink(path: Path, target: Path):
        path.replace(target)
        path.symlink_to(target)

    def test_manifest_symlink_cannot_authorize(self):
        target=self.f.root/"manifest-target.json"
        self._replace_with_symlink(self.f.manifest_path,target)
        with self.assertRaisesRegex(G.ChampionError,"ordinary non-symlink file"):
            self.f.eval()

    def test_run_receipt_symlink_cannot_authorize(self):
        path=self.f.roots["cand"][0]/"run.json"
        target=self.f.root/"candidate-run-target.json"
        self._replace_with_symlink(path,target)
        with self.assertRaisesRegex(G.ChampionError,"ordinary non-symlink file"):
            self.f.eval()

    def test_cell_symlink_cannot_authorize(self):
        root=self.f.roots["cand"][0]
        path=next(root.glob("*-p0.json"))
        target=self.f.root/f"candidate-cell-target-{path.name}"
        self._replace_with_symlink(path,target)
        with self.assertRaisesRegex(G.ChampionError,"ordinary non-symlink file"):
            self.f.eval()

    def test_archive_symlink_cannot_authorize(self):
        target=self.f.root/"candidate-archive-target.tar.gz"
        self._replace_with_symlink(self.f.cand,target)
        with self.assertRaisesRegex(G.ChampionError,"ordinary non-symlink file"):
            self.f.eval()

    def test_directory_is_not_evidence_file(self):
        with self.assertRaisesRegex(G.ChampionError,"ordinary non-symlink file"):
            G._read_json(self.f.root)

    def test_missing_nofollow_fails_closed(self):
        with mock.patch.object(G.os,"O_NOFOLLOW",None,create=True):
            with self.assertRaisesRegex(G.ChampionError,"platform lacks O_NOFOLLOW"):
                G._read_plain_file(self.f.manifest_path)

    def test_missing_nonblocking_open_fails_closed(self):
        with mock.patch.object(G.os,"O_NONBLOCK",None,create=True):
            with self.assertRaisesRegex(G.ChampionError,"platform lacks O_NONBLOCK"):
                G._read_plain_file(self.f.manifest_path)

    @unittest.skipUnless(hasattr(os,"O_NONBLOCK"), "requires O_NONBLOCK")
    def test_evidence_open_is_nonblocking_before_fstat(self):
        real_open=G.os.open
        seen_flags=[]
        def recording_open(path, flags, *args, **kwargs):
            seen_flags.append(flags)
            return real_open(path, flags, *args, **kwargs)
        with mock.patch.object(G.os,"open",side_effect=recording_open):
            G._read_plain_file(self.f.manifest_path)
        self.assertTrue(seen_flags)
        self.assertTrue(seen_flags[0] & os.O_NONBLOCK)

    @unittest.skipUnless(
        hasattr(os,"mkfifo") and hasattr(os,"O_NOFOLLOW") and hasattr(os,"O_NONBLOCK"),
        "requires POSIX FIFO + nofollow + nonblocking open",
    )
    def test_fifo_is_rejected_promptly_before_fstat_can_hang(self):
        fifo=self.f.root/"evidence.fifo"
        os.mkfifo(fifo)
        result=[]
        def read_fifo():
            try:
                G._read_plain_file(fifo)
            except Exception as exc:
                result.append(exc)
        thread=threading.Thread(target=read_fifo,daemon=True)
        thread.start()
        thread.join(1.0)
        self.assertFalse(thread.is_alive(),"evidence FIFO open blocked before type check")
        self.assertEqual(len(result),1)
        self.assertIsInstance(result[0],G.ChampionError)
        self.assertRegex(str(result[0]),"ordinary non-symlink file")

if __name__=="__main__": unittest.main()
