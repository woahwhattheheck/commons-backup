# INPRS RFP 26-04 — file-backed acceptance handoff v2

This layer binds a normalized CLM migration bundle to independently pinned source and handoff bytes for a qualified-prime review. It does not make Token Junkie Labs a CLM prime, assert buyer acceptance, or create submission/payment/revenue authority.

## Scope before preparing a handoff

Start with the source scope agreed by the prime and buyer, informed by the [current qualification record](https://github.com/woahwhattheheck/commons/issues/14580) and its official sources. This package validates the assets declared in an independently retained manifest; its schema does not decide which agency assets belong in the migration.

Historical-version checks apply to the revisions included in that agreed manifest. Do not invent historical files to satisfy the fictional example, expand the priced scope merely because the verifier supports a field, or silently omit agreed source assets. An adapter must preserve the retained source bytes and document any normalization separately.

## Trust boundary

The canonical `file_backed_acceptance.py` is v2. The independently pinned canonical manifest binds each source record, source byte digest/size, target path, publication classification, and **every historical version as an exact `(revision, path, sha256)` tuple**. Candidate `version_history` must equal those pinned tuples, and the verifier rereads the actual version files and compares them to the manifest-owned digests. A candidate cannot rewrite an old version file and rewrite its own hash alongside it.

The verifier also composes the retained v1 byte/semantic gate: source/target/vendor bytes, public-file closure, redaction-attestation bytes, semantic row identity, path reuse, traversal/symlink rejection, counts, lineage, publication projection, and internal-byte leakage checks remain enforced. Bundle JSON duplicate keys now fail closed before delegation.

`_file_backed_acceptance_v1.py` and `_build_synthetic_file_handoff_v1.py` are retained private compatibility/source-lineage modules only. They are not the canonical acceptance entry points.

The receipt is location-independent canonical JSON. All buyer-contact, proposal-submission, contract-acceptance, payment, and revenue-recognition authority remains false.

## Synthetic executable handoff

```bash
python revenue/inprs_clm_migration_gate/build_synthetic_file_handoff.py /tmp/inprs-demo
PIN=$(python - <<'PY'
import hashlib
from pathlib import Path
print(hashlib.sha256(Path('/tmp/inprs-demo/source_manifest.json').read_bytes()).hexdigest())
PY
)
python revenue/inprs_clm_migration_gate/file_backed_acceptance.py \
  --manifest /tmp/inprs-demo/source_manifest.json \
  --manifest-sha256 "$PIN" \
  --bundle /tmp/inprs-demo/candidate_bundle.json \
  --root /tmp/inprs-demo
```

For real work, the prime/source-export owner records the manifest SHA-256 **before** candidate acceptance. Recomputing a new pin after modifying a manifest is a new trust generation, not proof for the prior one.

## Retained predecessor and closure

The recovered v1 carrier at PR #15430 was source-reviewed at exact head `37a868eb8e2dd31bd85e68f2136f338c8c3ae110`. Review `5233207478` found that v1 pinned historical paths but compared historical bytes only to caller-controlled candidate hashes. V2 closes that paired-rewrite predecessor and retains the original eight hostile tests plus v2-specific roots, paired-rewrite, pin-remint, and duplicate-key hostiles.

Commercial posture remains `PROPOSED_NOT_ACCEPTED`: paid specialist subcontract only. No INPRS/partner/Muse/email/portal/submission/contract/payment/receivable/revenue mutation is performed by this code.
