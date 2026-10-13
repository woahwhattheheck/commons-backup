# TITAN V5 candidate identity

Use `v5_candidate_identity.py` before a matched experiment whenever a candidate is assembled from canonical V5 source plus one or more optional components. The manifest answers a narrow but important question: **what exact candidate did this cell run?** It does not claim the candidate engaged in-game; action engagement belongs to the separate policy-fingerprint evidence.

The identity binds:

- the declared canonical base commit/package identity;
- the pinned engine identity;
- an optional opponent-pack identity;
- the full type-preserving config digest;
- each claimed component's exact source bytes; and
- the exact activation evidence for every claimed component.

A component is admitted only when its relative source path resolves inside the chosen root and exists. The manifest records the resolved source as one canonical root-relative path, so lexical aliases such as `dir/../module.py` and in-root symlink aliases cannot mint a second `v5c:` identity for the same component bytes. Config activation is type-exact (`true` is not `1`). Components without a config predicate must explicitly declare `"unconditional": true`; source presence alone is never silently treated as activation. Any source drift, config drift, activation mismatch, manifest edit, path escape, missing file, duplicate component name, unsupported config type, or non-finite float fails closed.

## Spec example

From `revenue/kaggriculture/cloud-execution-lab`, create a JSON spec such as:

```json
{
  "base_id": "main@<exact commit sha>",
  "engine_id": "kaggriculture.py@3c202c7e...",
  "opponent_pack_id": "frontier-top30@<manifest sha>",
  "config": {
    "consumer": "frozen",
    "operating_stock": true,
    "crop_release": true
  },
  "components": [
    {
      "name": "operating-stock",
      "source": "operating_stock.py",
      "activation": {"operating_stock": true}
    },
    {
      "name": "crop-release",
      "source": "crop_release.py",
      "activation": {"crop_release": true}
    }
  ]
}
```

Build the immutable receipt:

```bash
python -B v5_candidate_identity.py --root . build candidate-spec.json --output candidate-manifest.json
```

Validate the same receipt immediately before or after the run:

```bash
python -B v5_candidate_identity.py --root . validate candidate-spec.json candidate-manifest.json
```

`validate` recomputes every field from current evidence and prints the `v5c:<sha256>` ID only on an exact match. Put that ID beside the run ID / seed / seat / opponent identity in `#sim-data`. A source merge with a default-OFF feature therefore cannot masquerade as a changed candidate: its activation predicate will fail until the actual run config enables it.

For a component genuinely active without a config gate, use an explicit declaration:

```json
{"name": "base-router", "source": "main.py", "unconditional": true}
```

Do not use `unconditional` merely because a module exists in the repository.
