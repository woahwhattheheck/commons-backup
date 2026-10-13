# SPDX-License-Identifier: MIT
from __future__ import annotations
import csv
import json
import math
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from dat_readiness.assets import validate_asset_manifest
from dat_readiness.contract import read_submission_format, run_independent, validate_probability
from dat_readiness.package import deterministic_zip

class ContractTests(unittest.TestCase):
    def _format(self, root: Path, rows=("a","b")) -> Path:
        path=root/"submission_format.csv"
        with path.open("w",encoding="utf-8",newline="") as h:
            w=csv.writer(h); w.writerow(("uid","is_pathologic")); [w.writerow((uid,"")) for uid in rows]
        return path
    def test_independent_runner_and_output(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); fmt=self._format(root); scans=root/"niftis"; scans.mkdir()
            (scans/"a.nii.gz").write_bytes(b"synthetic-a"); (scans/"b.nii.gz").write_bytes(b"synthetic-b")
            seen=[]
            def predictor(path):
                seen.append(path.name); return {"a.nii.gz":0.2,"b.nii.gz":0.8}[path.name]
            out=run_independent(fmt,scans,root/"submission.csv",predictor)
            self.assertEqual(seen,["a.nii.gz","b.nii.gz"])
            with out.open(encoding="utf-8",newline="") as h:
                rows=list(csv.DictReader(h))
            self.assertEqual(rows,[{"uid":"a","is_pathologic":"0.2"},{"uid":"b","is_pathologic":"0.8"}])
    def test_bad_probabilities_rejected(self):
        for value in (-0.1,1.1,float("nan"),float("inf"),"x"):
            with self.subTest(value=value), self.assertRaises(ValueError): validate_probability(value)
    def test_format_exact_and_unique(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); fmt=self._format(root,("a","a"))
            with self.assertRaises(ValueError): read_submission_format(fmt)
            fmt.write_text("uid,wrong\na,\n",encoding="utf-8")
            with self.assertRaises(ValueError): read_submission_format(fmt)

class PackageTests(unittest.TestCase):
    def test_deterministic_root_main(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/"src"; src.mkdir(); (src/"main.py").write_text("print('ok')\n",encoding="utf-8"); (src/"model.bin").write_bytes(b"x")
            one=deterministic_zip(src,root/"one.zip"); two=deterministic_zip(src,root/"two.zip")
            self.assertEqual(one.read_bytes(),two.read_bytes())
            with zipfile.ZipFile(one) as z: self.assertEqual(z.namelist(),["main.py","model.bin"])
            cache=src/"__pycache__"; cache.mkdir(); (cache/"main.cpython-312.pyc").write_bytes(b"compiled")
            three=deterministic_zip(src,root/"three.zip")
            with zipfile.ZipFile(three) as z: self.assertEqual(z.namelist(),["main.py","model.bin"])
    def test_refuses_nifti_and_generated_csv(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/"src"; src.mkdir(); (src/"main.py").write_text("pass\n",encoding="utf-8")
            for name in ("patient.nii.gz","submission_format.csv","submission.csv"):
                p=src/name; p.write_text("x",encoding="utf-8")
                with self.subTest(name=name), self.assertRaises(ValueError): deterministic_zip(src,root/"x.zip")
                p.unlink()

class AssetTests(unittest.TestCase):
    def test_asset_manifest_requires_three_confirmations(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"assets.json"
            good={"name":"weights","source":"https://example.invalid/model","license":"Apache-2.0","commercial_use_confirmed":True,"redistributable_in_submission":True,"organizer_disclosure_recorded":True}
            p.write_text(json.dumps([good]),encoding="utf-8"); self.assertEqual(len(validate_asset_manifest(p)),1)
            for field in ("commercial_use_confirmed","redistributable_in_submission","organizer_disclosure_recorded"):
                bad=dict(good); bad[field]=False; p.write_text(json.dumps([bad]),encoding="utf-8")
                with self.subTest(field=field), self.assertRaises(ValueError): validate_asset_manifest(p)

if __name__=="__main__": unittest.main()
