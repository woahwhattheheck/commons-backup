# LANCET: exact-byte TITAN regression gate

TITAN currently has at least four independent identities that can drift:

1. source and deterministic build inputs;
2. the canonical `titan-current.tar.gz` receipt;
3. tests or games that name some archive;
4. the artifact registry used by executors and submission owners.

A passing unit suite on archive **A** is not evidence for archive **B**. A score
from V1, V2, or a predecessor is not a regression panel unless the engine,
environment seed, opponent artifact, and candidate seat are paired exactly.
`titan_regression_gate.py` makes those rules executable.

## Canonical audit

From `revenue/kaggriculture/cloud-execution-lab`:

```bash
python titan_regression_gate.py audit --root .
```

This verifies:

- canonical archive bytes, size, and receipt SHA;
- source-manifest bytes and receipt SHA;
- exact identity parity between `CURRENT-ARCHIVE.json` and
  `CURRENT-TESTS.json`;
- an exact canonical archive path/SHA binding in `exports/ARTIFACTS.json`;
- any positive full-game count is explicitly bound to the canonical archive.

Promotion mode additionally requires exact current-archive full games:

```bash
python titan_regression_gate.py audit --root . --require-games \
  --report-json artifacts/titan-provenance.json
```

Exit code `0` means the requested gate passed. `2` means the audit is blocked.
Integrity can pass while promotion remains false when no current games exist.

## Exact paired comparison

Each ledger is a JSON object with one archive identity, one engine identity, and
completed rows:

```json
{
  "archive_sha256": "...",
  "engine_sha256": "...",
  "rows": [
    {
      "environment_seed": 9600901,
      "opponent_sha256": "...",
      "seat": 0,
      "candidate_score": 1000,
      "opponent_score": 900,
      "status": "DONE"
    }
  ]
}
```

Run:

```bash
python titan_regression_gate.py compare \
  --left artifacts/v1-ledger.json \
  --right artifacts/v2-ledger.json \
  --report-json artifacts/v1-v2-paired.json
```

The default refuses partial schedules. `--allow-partial-panel` permits an
explicitly labeled intersection report, but never fills missing cells or
extrapolates a leaderboard score. Duplicate cells, unfinished rows, errors,
timeouts, changed engines, changed opponents, or changed seats fail closed.

## Current observed break, 2026-09-09

At repository main `021a91b2bed219a84f882de87efaa8245be167f2`, the canonical receipt names:

- archive SHA-256 `17f536087b3a6baf4ae1222a051285766a3ea8c2ca5af6edc190d4f527e12b86`;
- 427,870 bytes;
- 109 runtime files;
- source-manifest SHA-256
  `1feec5a68ffde28ab7b5c7d2c92a34aa66ff5705b7d88182ef6af98df8bb5083`.

The checked-in test receipt instead names archive
`6ac897241cb54baa205e4132fab1f83e7a21e4ae957e19e16c6c48a7ecbd8bc1`,
408,621 bytes, 104 runtime files, with a different source manifest. The artifact
registry does not bind the canonical archive; it names an older sell-lab source
package. The current source manifest says historical results do not transfer and
reports zero new full games for the changed bytes.

Therefore the current V2.5/V3 working package may contain useful mechanisms, but
its checked-in test receipt and historical scores cannot support a current-byte
playing-strength or regression claim. Repair order:

1. regenerate exact-archive tests and bind their receipt to the canonical SHA;
2. register the canonical archive path/SHA;
3. run fresh unused-seed panels against both exact submitted V1 and frozen V2,
   both seats, with fixed opponent artifacts and engine;
4. compare only the exact cell intersection using this tool;
5. promote policy changes only after the dual-predecessor gate and provenance
   gate both pass.

This change does not alter TITAN runtime bytes, build an archive, launch games,
or submit to Kaggle.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
