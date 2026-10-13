"""Checkpoint metadata and bytes must describe the same committed workspace."""
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from host.toolbench import Bench


class CheckpointSnapshotConsistencyTests(unittest.TestCase):
    def test_peer_commit_before_backup_keeps_manifest_revision_consistent(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace.sqlite3"
            bench = Bench(workspace)
            bench.apply({"op": "add_job", "args": {"job_id": "original", "title": "Original"},
                         "request_id": "original-job"})
            peer = Bench(workspace)
            before = bench.snapshot()["revision"]
            real_connect = sqlite3.connect
            interleavings = []

            class InterleavedBackup(sqlite3.Connection):
                def backup(connection, target, *args, **kwargs):
                    # Schedule a real second-connection commit at the old race
                    # boundary. The SQLite backup and its bytes are not mocked.
                    interleavings.append("peer-commit")
                    peer.apply({"op": "add_job",
                                "args": {"job_id": "peer", "title": "Peer committed"},
                                "request_id": "peer-job"})
                    return super().backup(target, *args, **kwargs)

            def connect_with_interleaving(path, *args, **kwargs):
                if str(path) == str(workspace):
                    kwargs["factory"] = InterleavedBackup
                return real_connect(path, *args, **kwargs)

            with patch("host.toolbench.sqlite3.connect", side_effect=connect_with_interleaving):
                checkpoint = bench.checkpoint()

            with zipfile.ZipFile(io.BytesIO(checkpoint)) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                restored_path = Path(temporary) / "restored.sqlite3"
                restored_path.write_bytes(archive.read("workspace.sqlite3"))
            restored = Bench(restored_path).snapshot()
            self.assertEqual(["peer-commit"], interleavings)
            self.assertEqual(before + 1, restored["revision"])
            self.assertEqual({"original", "peer"}, {job["id"] for job in restored["jobs"]})
            self.assertEqual(restored["revision"], manifest["revision"])
            self.assertEqual(restored, bench.snapshot())


if __name__ == "__main__":
    unittest.main()
