from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HOSTILE = r'''
from __future__ import annotations

import importlib
import json
import os
import sqlite3
import stat
import sys
from pathlib import Path
from unittest import mock

from tools.github_content_write_pacemaker import store as store_module
from tools.github_content_write_pacemaker import store_base as store_base_module

root = Path(sys.argv[1])
requested = root / "state.db"
victim = root / "victim.db"

victim_db = sqlite3.connect(victim)
try:
    victim_db.execute("CREATE TABLE sentinel(value TEXT NOT NULL)")
    victim_db.execute("INSERT INTO sentinel(value) VALUES('keep')")
    victim_db.commit()
finally:
    victim_db.close()
os.chmod(victim, 0o644)
before = (victim.read_bytes(), stat.S_IMODE(os.stat(victim).st_mode))
real_connect = sqlite3.connect

def foreign_connect(*args, **kwargs):
    return real_connect(victim)

with mock.patch.object(
    store_base_module.sqlite3,
    "connect",
    side_effect=foreign_connect,
):
    importlib.reload(store_base_module)
    importlib.reload(store_module)

repaired = store_module.PacemakerStore(requested)
try:
    report = repaired.verify()
finally:
    repaired.close()

victim_after = (victim.read_bytes(), stat.S_IMODE(os.stat(victim).st_mode))
victim_db = real_connect(victim)
try:
    sentinel = victim_db.execute(
        "SELECT value FROM sentinel"
    ).fetchone()[0]
    victim_tables = {
        row[0] for row in victim_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
finally:
    victim_db.close()

requested_db = real_connect(requested)
try:
    requested_tables = {
        row[0] for row in requested_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
finally:
    requested_db.close()

if report["integrity"] != "VALID":
    raise RuntimeError("fresh public store generation failed verification")
if victim_after != before:
    raise RuntimeError("reload generation schema-wrote the foreign victim")
if sentinel != "keep" or "meta" in victim_tables or "mutations" in victim_tables:
    raise RuntimeError("foreign victim schema or sentinel changed")
if not {"meta", "mutations"}.issubset(requested_tables):
    raise RuntimeError("requested database did not receive the pacemaker schema")

print(json.dumps({
    "integrity": report["integrity"],
    "requestedTables": sorted(requested_tables),
    "victimTables": sorted(victim_tables),
    "victimUnchanged": victim_after == before,
}, sort_keys=True))
'''


class ReloadGenerationTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX reload-generation hostile")
    def test_reload_cannot_recapture_substituted_sqlite_connector(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            command = [sys.executable]
            if sys.flags.optimize:
                command.append("-" + "O" * sys.flags.optimize)
            command.extend(["-c", HOSTILE, tmp])
            env = os.environ.copy()
            path = env.get("PYTHONPATH")
            env["PYTHONPATH"] = (
                str(repo_root) if not path else str(repo_root) + os.pathsep + path
            )
            completed = subprocess.run(
                command,
                cwd=repo_root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                "reload-generation hostile failed\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["integrity"], "VALID")
        self.assertTrue(payload["victimUnchanged"])
        self.assertEqual(payload["victimTables"], ["sentinel"])
        self.assertIn("meta", payload["requestedTables"])
        self.assertIn("mutations", payload["requestedTables"])


if __name__ == "__main__":
    unittest.main()
