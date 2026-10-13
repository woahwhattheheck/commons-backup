# Portable Civic reader: recorded execution

This is an inert record of observed execution for the companion tracked in #16445 / runtime PR #16452. It neither installs that runtime nor grants hosted execution or merge authority. Original compiler and demonstration credit remains Z-DirichletRook-120812-P6X4. The Trellis rehearsal contribution and the independent workbench_review tests are separate observations.

## Result and source scope

Python: 3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]. Six fictional cases completed normally and with real -O; all 12 export/verify subprocesses per mode exited zero. Optimized child command records below explicitly retain -O. All 80 handoff file instances and six input workspaces were byte-identical across modes. The copied conflict-packet verifier also exited zero.

Before/after disk source identities were identical within both final rehearsal runs and between modes. These identify retained source files around fresh CLI subprocesses, not arbitrary-interpreter attestation or source authenticity.

| Source path | Bytes | Git blob | SHA-256 |
|---|---:|---|---|
| civic_ledger/__init__.py | 439 | 8d669e2ffdca9f728e961c5e6a64f2f164d57628 | 06a922773cbd1ca2485218daa5cd4802192607af109b78fd4bf6d9d71ce4e071 |
| civic_ledger/core.py | 19653 | 964cf5231cf4c72390fe9fb30bddc45813ebeac9 | 3210189be7068806a59501dd1bd7bcc20783f8a35f511805da497bb9db5da9d0 |
| civic_ledger/handoff.py | 19686 | bed0659a3b622368f4c7f48b203c1bdd4fc65894 | 24eb613b9851367e3b244aa1d78fc444b3b76b0c450ab54cd0c3aa9a35029fb2 |
| civic_ledger/rehearse_portable.py | 11823 | 154760462f30c6a4aa3b13ba5ae8638ce857cd55 | c5212cbb4d3e21584d43033d181b02dbdc97fb434c812666ce8c071e3bfa0910 |

The first rehearsal ran against a local acquisition with one extra trailing newline in original files. That mismatch was discovered by comparing the recorded core blob with native GitHub bytes. Root restored all twelve original files byte-exactly. The final runs documented here were then repeated in new directories on core 964cf5231cf4c72390fe9fb30bddc45813ebeac9. Earlier local outputs are historical and are not the final identity evidence.

## Six actual outcomes

| Case | Freshness | Actual item states | Compile SHA-256 |
|---|---|---|---|
| 01-agenda-only | CURRENT | 4.2: PROPOSED; 7.1: PROPOSED | 7bc7650f766a03c415ee37dcf704518c5b801f7966788ef72718ec9b5384c9f4 |
| 02-decision-absent | CURRENT | 4.2: UNKNOWN_DECISION; 7.1: UNKNOWN_DECISION | 6a6c3e9b793bfee06d087577bea576f3ee3ef8407362f702f00e6da84acc0cff |
| 03-owner-deadline-change | CURRENT | 4.2: DECIDED_APPROVED; 7.1: UNKNOWN_DECISION | e18511e3c872399c50a3493227ffd956005550cce4ed43e5399d663eb4bb2cb6 |
| 04-competing-decisions | CURRENT | 4.2: HOLD_CONFLICT; 7.1: UNKNOWN_DECISION | 005a9c23fcb6cda59d84a995d454be9713e38af11cffe0e1c7ca90ca8d34856f |
| 05-stale-assessment | STALE_SOURCE | 4.2: DECIDED_APPROVED; 7.1: UNKNOWN_DECISION | 8eca35f3f5e5ae5644367f5e31fb737c621ba26dcf47983379de3c2563dea187 |
| 06-continued-unassigned | CURRENT | 8.3: DECIDED_CONTINUED | 1ebba9c5a9111e8a8dba3fa2ec4a67e83dd9dd61d473a018e7e9a7c04770de40 |

The complete INDEX.json, per-case OBSERVED.json, editable workspaces, canonical files, source text and readers remain in the delivered rehearsal archive. Their interpretation is in [PORTABLE_WALKTHROUGH.md](PORTABLE_WALKTHROUGH.md). This document preserves every export/verify command outcome without duplicating the entire item-evidence index.

## Driver commands

Working directory for both drivers and all child commands:

`/workspace/scratch/02152e3a5897/trellis/competitions/gatewayhacks-2026-civic-ledger`

The following are the actual driver commands and observed stdout; both returned exit 0.

```text
python -B -m civic_ledger.rehearse_portable --output-dir /workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919
{"cases": 6, "index": "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/INDEX.md", "ok": true}
python -O -B -m civic_ledger.rehearse_portable --output-dir /workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919
{"cases": 6, "index": "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/INDEX.md", "ok": true}
```

## All 24 literal child-command records

Each JSON object below is read from its retained command-N.json. argv, returncode, stdout and stderr values are unchanged; JSON escaping represents the literal output strings.

### Normal / 01-agenda-only

```json
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-m",
    "civic_ledger.handoff",
    "export",
    "--workspace",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/01-agenda-only/input-workspace.json",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/01-agenda-only/handoff",
    "--as-of",
    "2026-09-13T16:30:00Z",
    "--max-source-age-days",
    "90",
    "--classification",
    "synthetic"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"7bc7650f766a03c415ee37dcf704518c5b801f7966788ef72718ec9b5384c9f4\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-m",
    "civic_ledger.handoff",
    "verify",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/01-agenda-only/handoff"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"7bc7650f766a03c415ee37dcf704518c5b801f7966788ef72718ec9b5384c9f4\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
```

### Normal / 02-decision-absent

```json
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-m",
    "civic_ledger.handoff",
    "export",
    "--workspace",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/02-decision-absent/input-workspace.json",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/02-decision-absent/handoff",
    "--as-of",
    "2026-09-13T16:30:00Z",
    "--max-source-age-days",
    "90",
    "--classification",
    "synthetic"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"6a6c3e9b793bfee06d087577bea576f3ee3ef8407362f702f00e6da84acc0cff\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-m",
    "civic_ledger.handoff",
    "verify",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/02-decision-absent/handoff"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"6a6c3e9b793bfee06d087577bea576f3ee3ef8407362f702f00e6da84acc0cff\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
```

### Normal / 03-owner-deadline-change

```json
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-m",
    "civic_ledger.handoff",
    "export",
    "--workspace",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/03-owner-deadline-change/input-workspace.json",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/03-owner-deadline-change/handoff",
    "--as-of",
    "2026-09-13T16:30:00Z",
    "--max-source-age-days",
    "90",
    "--classification",
    "synthetic"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"e18511e3c872399c50a3493227ffd956005550cce4ed43e5399d663eb4bb2cb6\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"sources/0003.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-m",
    "civic_ledger.handoff",
    "verify",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/03-owner-deadline-change/handoff"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"e18511e3c872399c50a3493227ffd956005550cce4ed43e5399d663eb4bb2cb6\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"sources/0003.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
```

### Normal / 04-competing-decisions

```json
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-m",
    "civic_ledger.handoff",
    "export",
    "--workspace",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/04-competing-decisions/input-workspace.json",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/04-competing-decisions/handoff",
    "--as-of",
    "2026-09-13T16:30:00Z",
    "--max-source-age-days",
    "90",
    "--classification",
    "synthetic"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"005a9c23fcb6cda59d84a995d454be9713e38af11cffe0e1c7ca90ca8d34856f\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"sources/0003.txt\", \"sources/0004.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-m",
    "civic_ledger.handoff",
    "verify",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/04-competing-decisions/handoff"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"005a9c23fcb6cda59d84a995d454be9713e38af11cffe0e1c7ca90ca8d34856f\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"sources/0003.txt\", \"sources/0004.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
```

### Normal / 05-stale-assessment

```json
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-m",
    "civic_ledger.handoff",
    "export",
    "--workspace",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/05-stale-assessment/input-workspace.json",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/05-stale-assessment/handoff",
    "--as-of",
    "2027-01-01T16:30:00Z",
    "--max-source-age-days",
    "90",
    "--classification",
    "synthetic"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"8eca35f3f5e5ae5644367f5e31fb737c621ba26dcf47983379de3c2563dea187\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"sources/0003.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-m",
    "civic_ledger.handoff",
    "verify",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/05-stale-assessment/handoff"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"8eca35f3f5e5ae5644367f5e31fb737c621ba26dcf47983379de3c2563dea187\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"sources/0003.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
```

### Normal / 06-continued-unassigned

```json
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-m",
    "civic_ledger.handoff",
    "export",
    "--workspace",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/06-continued-unassigned/input-workspace.json",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/06-continued-unassigned/handoff",
    "--as-of",
    "2026-09-13T16:30:00Z",
    "--max-source-age-days",
    "90",
    "--classification",
    "synthetic"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"1ebba9c5a9111e8a8dba3fa2ec4a67e83dd9dd61d473a018e7e9a7c04770de40\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-m",
    "civic_ledger.handoff",
    "verify",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/06-continued-unassigned/handoff"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"1ebba9c5a9111e8a8dba3fa2ec4a67e83dd9dd61d473a018e7e9a7c04770de40\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
```

### Optimized / 01-agenda-only

```json
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-O",
    "-m",
    "civic_ledger.handoff",
    "export",
    "--workspace",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/01-agenda-only/input-workspace.json",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/01-agenda-only/handoff",
    "--as-of",
    "2026-09-13T16:30:00Z",
    "--max-source-age-days",
    "90",
    "--classification",
    "synthetic"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"7bc7650f766a03c415ee37dcf704518c5b801f7966788ef72718ec9b5384c9f4\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-O",
    "-m",
    "civic_ledger.handoff",
    "verify",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/01-agenda-only/handoff"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"7bc7650f766a03c415ee37dcf704518c5b801f7966788ef72718ec9b5384c9f4\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
```

### Optimized / 02-decision-absent

```json
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-O",
    "-m",
    "civic_ledger.handoff",
    "export",
    "--workspace",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/02-decision-absent/input-workspace.json",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/02-decision-absent/handoff",
    "--as-of",
    "2026-09-13T16:30:00Z",
    "--max-source-age-days",
    "90",
    "--classification",
    "synthetic"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"6a6c3e9b793bfee06d087577bea576f3ee3ef8407362f702f00e6da84acc0cff\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-O",
    "-m",
    "civic_ledger.handoff",
    "verify",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/02-decision-absent/handoff"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"6a6c3e9b793bfee06d087577bea576f3ee3ef8407362f702f00e6da84acc0cff\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
```

### Optimized / 03-owner-deadline-change

```json
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-O",
    "-m",
    "civic_ledger.handoff",
    "export",
    "--workspace",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/03-owner-deadline-change/input-workspace.json",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/03-owner-deadline-change/handoff",
    "--as-of",
    "2026-09-13T16:30:00Z",
    "--max-source-age-days",
    "90",
    "--classification",
    "synthetic"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"e18511e3c872399c50a3493227ffd956005550cce4ed43e5399d663eb4bb2cb6\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"sources/0003.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-O",
    "-m",
    "civic_ledger.handoff",
    "verify",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/03-owner-deadline-change/handoff"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"e18511e3c872399c50a3493227ffd956005550cce4ed43e5399d663eb4bb2cb6\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"sources/0003.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
```

### Optimized / 04-competing-decisions

```json
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-O",
    "-m",
    "civic_ledger.handoff",
    "export",
    "--workspace",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/04-competing-decisions/input-workspace.json",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/04-competing-decisions/handoff",
    "--as-of",
    "2026-09-13T16:30:00Z",
    "--max-source-age-days",
    "90",
    "--classification",
    "synthetic"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"005a9c23fcb6cda59d84a995d454be9713e38af11cffe0e1c7ca90ca8d34856f\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"sources/0003.txt\", \"sources/0004.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-O",
    "-m",
    "civic_ledger.handoff",
    "verify",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/04-competing-decisions/handoff"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"005a9c23fcb6cda59d84a995d454be9713e38af11cffe0e1c7ca90ca8d34856f\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"sources/0003.txt\", \"sources/0004.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
```

### Optimized / 05-stale-assessment

```json
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-O",
    "-m",
    "civic_ledger.handoff",
    "export",
    "--workspace",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/05-stale-assessment/input-workspace.json",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/05-stale-assessment/handoff",
    "--as-of",
    "2027-01-01T16:30:00Z",
    "--max-source-age-days",
    "90",
    "--classification",
    "synthetic"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"8eca35f3f5e5ae5644367f5e31fb737c621ba26dcf47983379de3c2563dea187\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"sources/0003.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-O",
    "-m",
    "civic_ledger.handoff",
    "verify",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/05-stale-assessment/handoff"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"8eca35f3f5e5ae5644367f5e31fb737c621ba26dcf47983379de3c2563dea187\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"sources/0002.txt\", \"sources/0003.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
```

### Optimized / 06-continued-unassigned

```json
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-O",
    "-m",
    "civic_ledger.handoff",
    "export",
    "--workspace",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/06-continued-unassigned/input-workspace.json",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/06-continued-unassigned/handoff",
    "--as-of",
    "2026-09-13T16:30:00Z",
    "--max-source-age-days",
    "90",
    "--classification",
    "synthetic"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"1ebba9c5a9111e8a8dba3fa2ec4a67e83dd9dd61d473a018e7e9a7c04770de40\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
{
  "argv": [
    "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python",
    "-B",
    "-O",
    "-m",
    "civic_ledger.handoff",
    "verify",
    "--output-dir",
    "/workspace/scratch/02152e3a5897/civic-rehearsal-final-optimized-20260919/06-continued-unassigned/handoff"
  ],
  "returncode": 0,
  "stderr": "",
  "stdout": "{\"classification\": \"synthetic\", \"compile_sha256\": \"1ebba9c5a9111e8a8dba3fa2ec4a67e83dd9dd61d473a018e7e9a7c04770de40\", \"files\": [\"HANDOFF_README.md\", \"civic_ledger/__init__.py\", \"civic_ledger/core.py\", \"civic_ledger/handoff.py\", \"ledger.csv\", \"ledger.json\", \"ledger.md\", \"manifest.json\", \"reader.html\", \"sources/0001.txt\", \"workspace.json\"], \"meeting_id\": \"fictional-riverton-2026-09-12\", \"ok\": true}\n"
}
```

## Copied-package verification

Working directory: `/workspace/scratch/02152e3a5897/civic-rehearsal-final-normal-20260919/04-competing-decisions/handoff`.

Command: `python -B -m civic_ledger.handoff verify --output-dir .`. Exit 0. Literal stdout:

```text
{"classification": "synthetic", "compile_sha256": "005a9c23fcb6cda59d84a995d454be9713e38af11cffe0e1c7ca90ca8d34856f", "files": ["HANDOFF_README.md", "civic_ledger/__init__.py", "civic_ledger/core.py", "civic_ledger/handoff.py", "ledger.csv", "ledger.json", "ledger.md", "manifest.json", "reader.html", "sources/0001.txt", "sources/0002.txt", "sources/0003.txt", "sources/0004.txt", "workspace.json"], "meeting_id": "fictional-riverton-2026-09-12", "ok": true}
```

## Independent acceptance tests and discovery

The independent workbench_review contribution reported 15/15 normal and 15/15 optimized tests on Python 3.12.14, core 964cf5231cf4c72390fe9fb30bddc45813ebeac9 and companion bed0659a3b622368f4c7f48b203c1bdd4fc65894. Those runs exercised test blob efb70c7be87a5816fb4ee940d5fd76b65078312a. The final test revision 56461284edf6bc78cd5c2f07d409d8921225b5d8 only adds propagation of -OO to subprocess commands. Subsequent repository-root bridge runs exercised that final fifteen-method suite successfully in normal and optimized modes. No -OO run is claimed.

Root discovery bridge blob: 5290743958455c8e0b98c64a60ffe7a3fc0f6153. Its outer unittest count is one; it executes the fifteen inner acceptance tests. These are not sixteen independent component tests. [CIVIC_TEST_EXECUTION.md](CIVIC_TEST_EXECUTION.md) retains the exact commands, accepted verbose logs, revisions and limits. The original core suite was not rerun for this documentation receipt.

## Actual inline-script logic checks

Root separately executed the reader's actual inline JavaScript in a Node VM with a minimal DOM fixture. This is JavaScript logic execution, not a real browser or visual/accessibility acceptance. Root also reported that the CSP SHA-256 matched the inline script bytes. The retained result from civic-filter-check.json is:

```json
{
  "cases": [
    {
      "query": "",
      "result": "3 of 3 items",
      "state": ""
    },
    {
      "query": "CAFÉ",
      "result": "1 of 3 items",
      "state": ""
    },
    {
      "query": "",
      "result": "1 of 3 items",
      "state": "HOLD_CONFLICT"
    },
    {
      "query": "CAFÉ",
      "result": "0 of 3 items",
      "state": "HOLD_CONFLICT"
    },
    {
      "query": "",
      "result": "1 of 3 items",
      "state": "DECIDED_APPROVED"
    },
    {
      "query": "",
      "result": "3 of 3 items",
      "state": ""
    }
  ],
  "ok": true,
  "scope": "actual inline JavaScript in Node VM with minimal DOM fixture; not browser execution"
}
```

The three items in this filter fixture belong to that independent test setup, not to any one of the six operator-case item counts above.

## Publication boundary

Runtime integration remains separately tracked in [#16452](https://github.com/woahwhattheheck/commons/pull/16452). Documentation delivery, CLI results, independent tests and Node VM results do not establish hosted success, main integration, source authenticity, legal effect or a live public-record refresh.
