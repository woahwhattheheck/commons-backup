# Adapter example: provider-cost truth consumes a derived AuthorityFact

This is a **documented migration sketch only**. It does not modify
`tools/provider_cost_truth` and does not absorb that product's
source or finalization custody.

Today a caller can hand `provider_cost_truth` an evidence row whose
`authority` field is the string `PROVIDER_AUTHENTICATED`. That label is
caller-authored. The shared kernel exists so a downstream gate can
instead require an `AuthorityFact` produced from:

1. an out-of-band pinned authority-manifest SHA-256,
2. exact retained source bytes whose digests close the manifest, and
3. a record whose issuer/subject/kind/scope/generation and payload bind
   the candidate.

Suggested consumption, after this kernel is merged:

```python
from tools.evidence_authority import compile_current, verify_current

receipt = compile_current(candidate, manifest_bytes, sources, PINNED_ROOT)
if receipt["currentness"] != "CURRENT_POSITIVE":
    # HOLD / COST_UNKNOWN — do not treat the caller label as provider-auth
    ...
fact = receipt["derived_authority"][0]
# Pass `fact` into provider-cost evaluation as the only authenticated
# evidence handle. Do not retype authority="PROVIDER_AUTHENTICATED".
```

`verify_receipt` proves historical integrity only. It never remints
current-positive authority. `verify_current` recompiles at process UTC.

All six external-authority bits on the kernel receipt stay false:
buyer contact, provider session, spend, payment, and revenue remain
unauthorized.
