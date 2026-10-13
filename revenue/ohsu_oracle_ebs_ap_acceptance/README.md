# OHSU Oracle EBS R12 AP acceptance evidence gate

This package turns the bounded acceptance/evidence workstream proposed for OHSU
`RFI-2027-0824` into a deterministic, network-free readiness contract. It is not
an Oracle implementation and it does not represent Token Junkie Labs as the
Oracle EBS prime.

The gate is designed so a potential prime/integration partner can evaluate the
acceptance seam without production access. A complete synthetic matrix must
cover exactly one case for each of these nine scenario families:

- PO two-way match;
- PO three-way match;
- non-PO coding and approval;
- duplicate invoice suppression;
- retry-safe Oracle posting;
- supplier inquiry resolution;
- statement reconciliation;
- exception routing;
- reporting/audit evidence.

Posting cases must prove one stable logical `posting_intent_id` and exactly one
Oracle transaction identity even across retries. A retry may fail and then
succeed, but a logical intent that produces two Oracle transaction identities
fails closed. Non-posting cases cannot contain posting attempts or posting
states.

Every case carries a scenario-bound evidence receipt with source ID, SHA-256,
timezone-aware capture timestamp, and evidence kind. Receipt reuse across cases
is rejected. Case IDs and attempt IDs are unique, state transitions are
validated, and the required scenario coverage must be exact (missing or
duplicate scenario families HOLD the matrix).

## Decision boundary

`ACCEPTANCE_MATRIX_READY` means only that the supplied synthetic acceptance
evidence is internally coherent and covers the declared workstream. Any
coverage gap or case-level failure produces `HOLD_ACCEPTANCE_EVIDENCE`.

The report always fixes these authorities to false:

- partner inclusion approval;
- proposal authorization/submission;
- Oracle production validation;
- buyer acceptance;
- contract award;
- payment;
- recognized revenue.

Nothing here contacts OHSU, a teaming partner, Oracle, or any provider.

## Usage

```sh
python -m revenue.ohsu_oracle_ebs_ap_acceptance.cli \
  revenue/ohsu_oracle_ebs_ap_acceptance/example_matrix.json \
  --output /tmp/ohsu-ap-acceptance.json
```

Exit codes: `0` matrix ready, `2` valid input but evidence on HOLD, `3`
malformed/unsafe input.

File input rejects duplicate JSON keys, symlink/non-regular files, and
input/output aliases. File output uses same-directory temporary publication,
`fsync`, and atomic replacement.
