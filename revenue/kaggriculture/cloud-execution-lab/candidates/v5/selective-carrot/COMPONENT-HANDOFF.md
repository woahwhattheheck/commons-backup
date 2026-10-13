# TITAN V5 component handoff exporter

`export_staging_component.py` is convergence plumbing for the single production-v3/V5 line. It converts an already-authenticated candidate archive into the exact `titan-v5-staging-component/v1` directory consumed by the landed `staging_composer.py`. It does not decide whether a candidate won a screen or is eligible for CURRENT, release, or Kaggle.

The canonical baseline is fixed by the landed composer to production-v3 SHA256 `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`. The candidate archive requires an explicit expected SHA256. Deletions are refused. Exact byte differences become replacements; candidate-only members become additions.

A direct production-v3 delta needs no composition receipt because production-v3 has no prior component writer. A handoff exported against a later staging boundary **must** provide all four current-boundary inputs: `--current`, its exact SHA256, the landed composer receipt for that current archive, and the receipt's exact expected SHA256. The exporter authenticates the receipt schema/baseline/candidate binding, recomputes its complete file map, replays ordered component replacement/addition hashes, dependencies/conflicts, and overlap chains, then reconstructs the exact final `last_writer` map. This matters even when a prior component wrote byte-identical content: writer custody is history, not a byte-difference heuristic.

Before publication, the exporter writes the generated manifest and payloads to private temporary storage and requires the **landed composer itself** to accept them through `staging_composer.load_component()`. There is no parallel component schema or second handoff format. Final `COMPONENT.json` plus source payloads are then published through the shared `publication_custody.publish_exclusive` primitive.

Direct production-v3 delta:

```bash
python -B export_staging_component.py \
  --baseline /path/to/production-v3.tar.gz \
  --candidate /path/to/measured-winner.tar.gz \
  --candidate-sha256 <exact-winner-sha256> \
  --component-id p05-measured-winner \
  --out-dir /fresh/p05-component
```

Reviewed component exported after an already-composed `p01` boundary:

```bash
python -B export_staging_component.py \
  --baseline /path/to/production-v3.tar.gz \
  --current /path/to/staged-through-p01.tar.gz \
  --current-sha256 <exact-current-sha256> \
  --current-receipt /path/to/staged-through-p01.json \
  --current-receipt-sha256 <exact-current-receipt-sha256> \
  --candidate /path/to/staged-plus-p05.tar.gz \
  --candidate-sha256 <exact-candidate-sha256> \
  --component-id p05 \
  --depends-on p01 \
  --overlap-after r04_full_router.py=p01 \
  --out-dir /fresh/p05-component
```

The output contains only `COMPONENT.json` plus deterministic SHA-named source payloads under `files/`. Source payloads are the exact changed member bytes from the authenticated candidate archive. Publication is create-exclusive and uses the canonical cooperative fail-closed custody helper; pre-existing final files are never overwritten by the exporter.

Safety boundaries: archive members are parsed with the landed composer's exact canonical-file contract, so symlinks/devices/traversal/duplicates reject; deletions and unchanged candidates reject; later-boundary handoffs require an authenticated receipt whose history reproduces the current archive exactly; replacements must name the receipt-derived immediate prior writer and extra/stale overlap declarations reject. The exporter never infers economics, winner status, activation, or release eligibility.