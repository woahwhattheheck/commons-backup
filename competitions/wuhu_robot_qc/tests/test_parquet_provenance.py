from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from wuhu_qc.lerobot_v21 import fit_dataset_reference, scan_dataset
from wuhu_qc.provenance import (
    CLEAN_REFERENCE_ROLE,
    TEST_ROLE,
    BoundReferenceProfile,
)


# Integration-test pattern carried forward from ZIB-N5Q3's concurrent #13695
# recovery. The assertions below target the stronger boundary already merged in
# #14576: explicit clean/test roles plus full declared-corpus overlap checks.
PARQUET_AVAILABLE = bool(
    importlib.util.find_spec("pyarrow") or importlib.util.find_spec("fastparquet")
)


def good_df(n: int = 40, episode_index: int = 0) -> pd.DataFrame:
    t = np.arange(n, dtype=np.float64) / 30.0
    state = np.stack([np.sin(t), np.cos(t), t, np.ones_like(t)], axis=1)
    action = np.stack([np.sin(t + 0.02), np.cos(t + 0.02), t + 0.01, np.full_like(t, 0.5)], axis=1)
    return pd.DataFrame(
        {
            "timestamp": t,
            "frame_index": np.arange(n),
            "episode_index": np.full(n, episode_index, dtype=int),
            "task_index": np.zeros(n, dtype=int),
            "observation.state": list(state),
            "action": list(action),
        }
    )


def write_dataset(
    root: Path,
    *,
    corrupt_episode: int | None = None,
    copied_episode: tuple[int, Path] | None = None,
) -> None:
    (root / "meta").mkdir(parents=True)
    (root / "data" / "chunk-000").mkdir(parents=True)
    info = {
        "codebase_version": "v2.1",
        "fps": 30,
        "chunks_size": 1000,
        "total_episodes": 2,
        "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
        "features": {
            "observation.state": {"dtype": "float32", "shape": [4]},
            "action": {"dtype": "float32", "shape": [4]},
        },
    }
    (root / "meta" / "info.json").write_text(
        json.dumps(info, sort_keys=True) + "\n", encoding="utf-8"
    )
    (root / "meta" / "episodes.jsonl").write_text(
        "".join(json.dumps({"episode_index": ep}) + "\n" for ep in range(2)),
        encoding="utf-8",
    )
    for ep in range(2):
        target = root / "data" / "chunk-000" / f"episode_{ep:06d}.parquet"
        if copied_episode is not None and copied_episode[0] == ep:
            shutil.copy2(copied_episode[1], target)
            continue
        df = good_df(40 + ep, ep)
        if corrupt_episode == ep:
            df = df.drop(columns=["action"])
        df.to_parquet(target, index=False)


@unittest.skipUnless(PARQUET_AVAILABLE, "real-Parquet integration requires pyarrow or fastparquet")
class RealParquetProvenanceTests(unittest.TestCase):
    def test_bound_reference_roundtrip_on_real_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "clean"
            write_dataset(root)
            reference = fit_dataset_reference(
                root, episodes=[0], role=CLEAN_REFERENCE_ROLE
            )
            self.assertEqual(reference, BoundReferenceProfile.from_dict(reference.as_dict()))

    def test_real_parquet_profile_rejects_incomplete_clean_episode(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "clean"
            write_dataset(root, corrupt_episode=1)
            with self.assertRaisesRegex(ValueError, "missing required modeled feature action"):
                fit_dataset_reference(root, role=CLEAN_REFERENCE_ROLE)

    def test_real_parquet_same_corpus_disjoint_selection_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "dataset"
            write_dataset(root)
            reference = fit_dataset_reference(
                root, episodes=[0], role=CLEAN_REFERENCE_ROLE
            )
            with self.assertRaisesRegex(ValueError, "same corpus"):
                scan_dataset(
                    root,
                    Path(td) / "out",
                    episodes=[1],
                    reference=reference,
                    dataset_role=TEST_ROLE,
                )

    def test_hidden_unselected_copied_reference_bytes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            clean = Path(td) / "clean"
            test = Path(td) / "test"
            write_dataset(clean)
            copied = clean / "data" / "chunk-000" / "episode_000000.parquet"
            # Put clean-reference bytes in test episode 1, then request scoring
            # only for test episode 0. Full-corpus hashing must still reject.
            write_dataset(test, copied_episode=(1, copied))
            reference = fit_dataset_reference(
                clean, episodes=[0], role=CLEAN_REFERENCE_ROLE
            )
            with self.assertRaisesRegex(ValueError, "exact episode bytes"):
                scan_dataset(
                    test,
                    Path(td) / "out",
                    episodes=[0],
                    reference=reference,
                    dataset_role=TEST_ROLE,
                )

    def test_serialized_full_corpus_manifest_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            clean = Path(td) / "clean"
            write_dataset(clean)
            reference = fit_dataset_reference(
                clean, episodes=[0], role=CLEAN_REFERENCE_ROLE
            )
            payload = reference.as_dict()
            payload["provenance"]["all_episode_files"][1]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "corpus manifest digest mismatch"):
                BoundReferenceProfile.from_dict(payload)


if __name__ == "__main__":
    unittest.main()
