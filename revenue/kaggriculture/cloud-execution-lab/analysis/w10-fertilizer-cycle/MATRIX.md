# W10 counterfactual matrix admission

A single favorable fertilizer replay is not enough for promotion. `matrix_runner.py` consumes an explicit manifest of required control/fertilized trace pairs and returns `ADMIT` only when **every distinct comparison identity** earns a `CERTIFIED` result from `realized_fertilizer.py`.

## Manifest

Paths are resolved relative to the manifest directory.

```json
{
  "schema": "titan.w10.realized-fertilizer-matrix/v1",
  "pairs": [
    {
      "id": "seed-718-vs-opponent-a",
      "control": "traces/seed-718.control.json",
      "fertilized": "traces/seed-718.fertilized.json"
    },
    {
      "id": "seed-719-vs-opponent-a",
      "control": "traces/seed-719.control.json",
      "fertilized": "traces/seed-719.fertilized.json"
    }
  ]
}
```

Run it with:

```bash
python matrix_runner.py matrix.json --output matrix-result.json --pretty
```

Exit code `0` means `ADMIT`. Exit code `1` means at least one required pair rejected or the manifest/trace set failed closed.

## Anti-cherry-pick gates

The runner rejects:

- an empty matrix;
- duplicate pair IDs;
- duplicate comparison identities, even under different filenames;
- reuse of one trace file across pairs;
- use of one file as both control and treatment;
- absolute paths, parent traversal, or symlink escapes from the manifest root;
- missing, non-UTF-8, malformed, or oversized trace files;
- unknown manifest keys; and
- any pair whose W10 certificate is not `CERTIFIED`.

Each pair result includes source-file SHA-256 values, certificate SHA-256, identity SHA-256, decision, and rejection reasons. The full matrix result binds the normalized manifest and ordered pair results under `result_sha256`.

The required matrix itself is a release-policy decision and should be committed or otherwise content-addressed by the producer owner. The runner does not silently choose seeds or opponents, and it never drops a failing required pair.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
