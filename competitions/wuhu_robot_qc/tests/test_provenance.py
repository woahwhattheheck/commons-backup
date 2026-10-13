from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from wuhu_qc.lerobot_v21 import fit_dataset_reference, scan_dataset
from wuhu_qc.provenance import (
    CLEAN_REFERENCE_ROLE, TEST_ROLE, BOUND_REFERENCE_VERSION,
    BoundReferenceProfile, assert_no_reference_overlap, build_corpus_manifest,
)

def dataset(root: Path, payloads: list[bytes]):
    (root/"meta").mkdir(parents=True)
    info={
      "codebase_version":"v2.1","total_episodes":len(payloads),"chunks_size":1000,
      "fps":30,
      "data_path":"data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
      "video_path":"videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4",
      "features":{
        "observation.state":{"dtype":"float32","shape":[2]},
        "action":{"dtype":"float32","shape":[2]},
      }
    }
    (root/"meta"/"info.json").write_text(json.dumps(info,sort_keys=True))
    (root/"meta"/"episodes.jsonl").write_text("".join(json.dumps({"episode_index":i})+"\n" for i in range(len(payloads))))
    paths={}
    for i,b in enumerate(payloads):
        p=root/"data"/"chunk-000"/f"episode_{i:06d}.parquet"
        p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b); paths[i]=p
    return info,paths

def frame(ep=0, *, missing=False, nonfinite=False):
    n=4
    state=[np.array([float(i),float(i+1)]) for i in range(n)]
    action=[np.array([float(i)/2,float(i)/3]) for i in range(n)]
    if nonfinite: state[2]=np.array([np.nan,1.0])
    data={"timestamp":np.arange(n)/30,"frame_index":np.arange(n),"episode_index":[ep]*n,"task_index":[0]*n,"action":action}
    if not missing: data["observation.state"]=state
    return pd.DataFrame(data)

class ProvenanceTests(unittest.TestCase):
    def test_same_corpus_rejected_even_disjoint_selection(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); info,paths=dataset(root,[b"a",b"b",b"c"])
            clean=build_corpus_manifest(root,role=CLEAN_REFERENCE_ROLE,declared_episode_indices=[0,1,2],selected_episode_indices=[0],data_paths=paths)
            test=build_corpus_manifest(root,role=TEST_ROLE,declared_episode_indices=[0,1,2],selected_episode_indices=[2],data_paths=paths)
            from wuhu_qc.core import ReferenceProfile, ReferenceFeature
            profile=ReferenceProfile("wuhu-reference/v1",{"action":ReferenceFeature((0.0,),(1.0,),0.0,1.0)})
            ref=BoundReferenceProfile(BOUND_REFERENCE_VERSION,clean,("action",),profile)
            with self.assertRaisesRegex(ValueError,"same corpus"):
                assert_no_reference_overlap(ref,test)

    def test_exact_episode_bytes_overlap_rejected_across_distinct_corpus(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/"a"; b=Path(td)/"b"
            _,pa=dataset(a,[b"shared",b"clean-only"])
            _,pb=dataset(b,[b"test-other",b"shared"])
            clean=build_corpus_manifest(a,role=CLEAN_REFERENCE_ROLE,declared_episode_indices=[0,1],selected_episode_indices=[0],data_paths=pa)
            test=build_corpus_manifest(b,role=TEST_ROLE,declared_episode_indices=[0,1],selected_episode_indices=[0],data_paths=pb)
            from wuhu_qc.core import ReferenceProfile, ReferenceFeature
            profile=ReferenceProfile("wuhu-reference/v1",{"action":ReferenceFeature((0.0,),(1.0,),0.0,1.0)})
            ref=BoundReferenceProfile(BOUND_REFERENCE_VERSION,clean,("action",),profile)
            with self.assertRaisesRegex(ValueError,"exact episode bytes"):
                assert_no_reference_overlap(ref,test)

    def test_fit_requires_every_selected_episode_feature(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); dataset(root,[b"a",b"b"])
            frames={0:frame(0),1:frame(1,missing=True)}
            def fake_read(path): return frames[int(path.stem.split("_")[-1])]
            with patch("wuhu_qc.lerobot_v21._require_parquet_engine",lambda:None), patch("wuhu_qc.lerobot_v21.pd.read_parquet",side_effect=fake_read):
                with self.assertRaisesRegex(ValueError,"missing required modeled feature"):
                    fit_dataset_reference(root,role=CLEAN_REFERENCE_ROLE)

    def test_fit_rejects_nonfinite_selected_episode(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); dataset(root,[b"a",b"b"])
            frames={0:frame(0),1:frame(1,nonfinite=True)}
            def fake_read(path): return frames[int(path.stem.split("_")[-1])]
            with patch("wuhu_qc.lerobot_v21._require_parquet_engine",lambda:None), patch("wuhu_qc.lerobot_v21.pd.read_parquet",side_effect=fake_read):
                with self.assertRaisesRegex(ValueError,"non-finite"):
                    fit_dataset_reference(root,role=CLEAN_REFERENCE_ROLE)

    def test_serialized_reference_rejects_manifest_reseal_gap(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); dataset(root,[b"a",b"b"])
            frames={0:frame(0),1:frame(1)}
            def fake_read(path): return frames[int(path.stem.split("_")[-1])]
            with patch("wuhu_qc.lerobot_v21._require_parquet_engine",lambda:None), patch("wuhu_qc.lerobot_v21.pd.read_parquet",side_effect=fake_read):
                ref=fit_dataset_reference(root,episodes=[0],role=CLEAN_REFERENCE_ROLE)
            raw=ref.as_dict()
            raw["provenance"]["all_episode_files"][1]["sha256"]="0"*64
            with self.assertRaisesRegex(ValueError,"corpus manifest digest mismatch"):
                BoundReferenceProfile.from_dict(raw)

    def test_bound_reference_roundtrip_and_scan_same_corpus_block(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); dataset(root,[b"a",b"b"])
            frames={0:frame(0),1:frame(1)}
            def fake_read(path): return frames[int(path.stem.split("_")[-1])]
            with patch("wuhu_qc.lerobot_v21._require_parquet_engine",lambda:None), patch("wuhu_qc.lerobot_v21.pd.read_parquet",side_effect=fake_read):
                ref=fit_dataset_reference(root,episodes=[0],role=CLEAN_REFERENCE_ROLE)
                again=BoundReferenceProfile.from_dict(ref.as_dict())
                self.assertEqual(again,ref)
                with self.assertRaisesRegex(ValueError,"same corpus"):
                    scan_dataset(root,root/"out",episodes=[1],reference=again,dataset_role=TEST_ROLE)

if __name__=="__main__": unittest.main()
