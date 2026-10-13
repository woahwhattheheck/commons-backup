# Outbound connector lease — GitHub Administration cutover

This directory contains the reviewed ruleset candidate and an **operator helper** for closing the remaining ref-rollback gap tracked by Commons #14357.

The helper is intentionally narrower than the outbound stack. It can validate and, when run by an explicitly authorized GitHub **Administration(write)** operator, create/read back the reviewed protected-v2 branch ruleset and run one destructive-hostile probe. It does **not** send mail, select a prospect, grant a fleet lease, approve content, move money, recognize revenue, or make the connector lease a complete production mutex.

## Why this exists

A Git branch is mutable unless the host prevents mutation. Before the protected-v2 cutover, a worker could create a v1 lease ref, delete it, and create the same absent ref again. Both creates could succeed. Therefore ref absence did not prove that the seam had never been acquired.

Source containment already landed and correctly holds all connector-branch authority while rollback protection is unverified. `admin_cutover.py` makes the remaining administrator operation reproducible instead of leaving it in Slack/chat history.

## Candidate pin

The helper accepts only the exact reviewed `ruleset-candidate.json` bytes:

`8f697a8372cc4c2aeaf97e7cd7890d9004394667316573ba638df3a095bfc1e9`

The candidate requires active branch enforcement, zero bypass actors, only `refs/heads/outbound-connector-lease/v2/*`, and host blocks for update, deletion, and non-fast-forward mutation. Any raw-byte drift, policy drift, bypass actor, missing rule, or broadened ref scope is `HOLD`.

## Offline plan

No credential or network access is needed:

```bash
python -m revenue.outbound_connector_lease.ref_immutability.admin_cutover plan
```

The deterministic plan remains:

```text
state=HOLD_ADMIN_APPLY_REQUIRED
ref_rollback_protection_required=true
ref_rollback_protection_verified=false
branch_create_authority=false
production_mutex_complete=false
external_send_authorized=false
```

A plan is not evidence that GitHub installed anything.

## Apply — administrator only

A repository administrator may run the `apply` command only after placing an explicitly authorized Administration(write) credential in the environment variable named by `--token-env` (default: `GITHUB_ADMIN_TOKEN`):

```bash
python -m revenue.outbound_connector_lease.ref_immutability.admin_cutover \
  apply --probe-id '<caller-unique-id>'
```

The credential is retained in memory and never written into the receipt.

The helper pins all REST calls to `woahwhattheheck/commons` and performs this sequence:

1. GET the repository ruleset census.
2. If the exact same-name ruleset is absent, POST the reviewed candidate **once**. There is no PATCH/DELETE ruleset path in this helper.
3. GET the exact ruleset and require active enforcement, exact protected-v2 scope, all three mutation blocks, and no bypass actors.
4. GET current `main` and its first parent.
5. CREATE one caller-unique protected-v2 probe from the retained parent SHA.
6. GET rules effective on that exact probe branch and independently require update/deletion/non-fast-forward blocks.
7. Attempt a real fast-forward update to current main — it **must** fail with a host denial.
8. Attempt real deletion — it **must** fail with a host denial.
9. Attempt recreate of the same ref — it **must** fail because the protected original ref still exists.
10. GET the probe ref and require that its SHA is still the original parent SHA.
11. Emit a self-hashed narrow receipt.

A transport timeout, permission ambiguity, unexpected HTTP result, rules drift, bypass, or hostile success is `HOLD`. The helper does not blindly retry an ambiguous mutation. The probe ref is intentionally retained; a successful deletion would invalidate the proof.

## Receipt ceiling

Only a fully successful administrator run may emit:

```text
state=REF_ROLLBACK_PROTECTION_VERIFIED
ref_rollback_protection_verified=true
```

Even then these remain hard false:

```text
branch_create_authority=false
production_mutex_complete=false
external_send_authorized=false
provider_send_authorized=false
payment_authorized=false
revenue_recognized=false
```

A separate reviewed outbound composition/cutover must consume this evidence together with every other current contact, organization, route, DNR/cooldown, provider-generation, and one-shot-send control. This helper never upgrades itself into send authority.

## Receipt self-check

```bash
python -m revenue.outbound_connector_lease.ref_immutability.admin_cutover \
  verify-receipt --receipt receipt.json
```

`VALID_RECEIPT_STRUCTURE` proves only internal receipt integrity and hard-false authority fields. It does **not** re-query GitHub and is not a substitute for the administrator apply run or current host readback.

## Test surface

```bash
python -m py_compile \
  revenue/outbound_connector_lease/ref_immutability/admin_cutover.py \
  revenue/outbound_connector_lease/ref_immutability/test_admin_cutover.py

python -m unittest -v \
  revenue.outbound_connector_lease.ref_immutability.test_admin_cutover

python -O -m unittest -v \
  revenue.outbound_connector_lease.ref_immutability.test_admin_cutover
```

The tests use an in-memory fake GitHub client. They exercise create-only install, exact existing-ruleset reconciliation, candidate byte/policy drift, bypass actors, missing effective rules, update/delete/recreate hostiles, final-ref readback, permission failure, missing administrator credential, receipt tamper, and optimized-Python behavior without mutating GitHub.
