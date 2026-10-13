# Titan V5 pairwise composition builder

This directory exists to keep V5 convergence honest: one baseline archive, two exact component postimages, and the four comparable variants `control`, `A`, `B`, and `A+B`. It does **not** create another Titan root and it does not decide whether a component is good.

`compose.py` overlays only files already present in the baseline archive. Before it creates the output directory, it captures the baseline archive once, authenticates that buffer, parses only those captured bytes, authenticates every component source postimage, and verifies the expected **preimage** of every archive member a component will replace. It rejects component targets that are not regular archive files, preflights all four variants in memory, then applies only declared `TITAN-CONFIG.json` activation values and fails closed when two components disagree on a baseline preimage, want different replacement bytes at the same archive path, or conflict on a config value. The output `COMPOSITION.json` binds the exact baseline, each component's preimage and postimage identities, changed archive members, activation values, and hashes of all four generated archives.

## Manifest

A v2 manifest has exactly two components. Component names are lowercase slugs (`[a-z0-9][a-z0-9_-]{0,63}`) and `control` is reserved, which keeps variant receipt keys and archive filenames collision-free. Each replaced member carries both the reviewed baseline member digest (`preimage_sha256`) and the exact replacement/source digest (`sha256`):

```json
{
  "schema": "titan-v5-composition-v2",
  "baseline": {
    "sha256": "<exact baseline archive sha256>",
    "member_count": 75
  },
  "components": {
    "joint_liquidity": {
      "files": [
        {
          "archive_path": "frozen_selected.py",
          "source_path": "frozen_selected.py",
          "preimage_sha256": "<exact baseline frozen_selected.py sha256>",
          "sha256": "<exact source postimage sha256>"
        }
      ],
      "config": {
        "consumer": "frozen",
        "funding": true
      }
    },
    "productive_worker": {
      "files": [
        {
          "archive_path": "spatial_tempo.py",
          "source_path": "spatial_tempo.py",
          "preimage_sha256": "<exact baseline spatial_tempo.py sha256>",
          "sha256": "<exact source postimage sha256>"
        },
        {
          "archive_path": "worker_job_value.py",
          "source_path": "worker_job_value.py",
          "preimage_sha256": "<exact baseline worker_job_value.py sha256>",
          "sha256": "<exact source postimage sha256>"
        }
      ],
      "config": {
        "consumer": "frozen"
      }
    }
  }
}
```

`source_path` is resolved under `--source-root`. Both digests are mandatory canonical lowercase SHA-256 values: `preimage_sha256` proves the component was reviewed for the member bytes in this baseline, while `sha256` proves a moving checkout cannot silently change the replacement. Updating only `baseline.sha256` to point at a different archive is therefore insufficient to make an old component compatible; any targeted member drift is rejected before any output is written. The baseline path is never reopened after authentication, so a moving checkout cannot swap non-target archive members between hashing and tar parsing. A component may replace only an existing regular-file member; directories, symlinks, and other tar metadata cannot be presented as writable component targets. Variant conflicts are rejected before the output directory is created.

Config entries are activation requirements: existing keys are set to those exact values in the applicable variant. Unknown keys are rejected rather than smuggled into the package.

## Build

```bash
python3 -B compose.py \
  --baseline /path/to/frozen-baseline.tar.gz \
  --source-root /path/to/commons/revenue/kaggriculture/cloud-execution-lab \
  --manifest pair.json \
  --output /tmp/titan-v5-pair
```

The output directory contains deterministic rebuilt archives plus `COMPOSITION.json`. Competitive evaluation should run the same opponent, seed, seat and engine identity for all four variants. A composition is promotion-worthy only when `A+B` improves the matched margin relative to **both** `A` and `B`; repository inclusion alone is not an activation or performance claim.

The builder intentionally refuses to combine different postimages of the same archive member. If two policies touch the same file, first converge them on canonical V5 `main`, then treat that converged postimage as one component instead of manufacturing an unreviewed textual merge in the experiment harness.
