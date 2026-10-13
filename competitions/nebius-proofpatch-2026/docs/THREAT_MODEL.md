# ProofPatch threat model

## Trust boundary

A self-digest is tamper evidence after construction, **not provenance authentication**. ProofPatch therefore never equates caller-authored receipt consistency with independently executed truth.

- `STRUCTURAL_EVIDENCE_VERIFIED`: schemas, roots, exact changed bytes, receipt chain, task/phase semantics and authority ceilings are internally consistent. Receipt provenance remains unauthenticated.
- `EXECUTOR_REPLAY_VERIFIED`: a verifier-selected executor reran every claimed command for the exact claimed repository generation and returned the exact claimed result. This state is relative to that executor trust boundary, not a cryptographic provider claim.

## Adversary

Assume the planning model, task text, repository contents, claimed transcript, filenames, command output, caller-supplied JSON, and even a caller-supplied executor may be malicious or stale. A verifier that needs execution truth must choose/control its executor or validate a separately authenticated provider receipt.

## Fail-closed controls

- Paths are normalized POSIX-relative; traversal and alias spellings are rejected.
- Schemas reject extra/missing keys, bool-as-int ambiguity, duplicate/out-of-order path sets, and unsupported commands.
- Commands are structured argv only. Shell metacharacters, URL-bearing tokens, inline Python, package-install modules, and unallowlisted executables are rejected.
- The claimed reproduction must fail while the baseline digest remains unchanged; verifier-selected executor replay must complete before that reproduction result counts as independently executed truth.
- Exact before/after changed-file text is hashed into both roots; declared changes must equal all root differences and may not hide add/delete.
- Focused test must rerun the exact predecessor killer; regression + replay must be green on the exact patched generation.
- Receipts are sequence-, task-, repository-, and predecessor-digest-bound, while provenance is explicitly separated from those self-digests.
- Missing hermetic sandbox evidence is terminal; it never widens model tool privileges.
- Documentation evidence is explicit URL + retained-text digest + task binding.
- Nebius outer/inner model identity is pinned; transport is explicit and credentials are never serialized into proof data.
- Live receipt presence cannot make submission authorization/readiness true.

## External evidence still required

The local carrier does not prove a Nebius/NVIDIA runtime call happened, a deployment URL works, a public demo video exists, or Devpost accepted a submission. Those require separately retained provider/human receipts.
