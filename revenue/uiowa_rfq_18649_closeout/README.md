# UIOWA-099 — evidence lifecycle and engagement closeout kit

This directory is a **preparation and validation kit** for the RFQ 18649 evidence closeout lane. It does not delete files, return evidence, modify permissions, contact the University, or certify that disposition occurred.

## What is runnable

- `closeout.py` validates an engagement descriptor, evidence inventory, and disposition log.
- `test_closeout.py` exercises deadline, accountability, retention-exception, public-repository, and credential-safety behavior.
- `sample/` is a fully synthetic worked packet and generated PASS report.
- `evidence_inventory_template.csv`, `disposition_log_template.csv`, and `closeout_confirmation_template.md` are operator templates.
- `requirements_register.csv` and `SOURCE_NOTES.md` preserve the current source hierarchy and the unresolved primary-locator fact.

## Source boundary

The current UIOWA-099 work order explicitly requires a **30-day post-completion** closeout rule. The repository also has an independently useful custody boundary in
`revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_EXHIBIT.md`: real University, prime, customer, credential, or confidential assessment evidence must not be committed to the public Commons repository; restricted evidence belongs in an authorized private custody boundary.

At publication time, the exact **controlling RFQ / Professional Services Agreement locator** for the 30-day return/destruction clause was not present in the public Commons carrier. This kit therefore does **not** invent one. The sample sets:

`primary_requirement_locator_status = work_order_pending_primary_locator`

and the validator emits a warning until an operator replaces that with:

`verified_controlling_source`

after binding the live engagement to the controlling agreement clause.

The University standard terms also state that University records must not be removed from the University. Treat that as a separate records-custody constraint; do not interpret it as a substitute for the assessment-evidence closeout clause.

## Quick start

```bash
cd revenue/uiowa_rfq_18649_closeout
python -m unittest -v test_closeout.py
python closeout.py \
  sample/engagement.json \
  sample/evidence_inventory.csv \
  sample/disposition_log.csv \
  --as-of 2026-12-21 \
  --json-out /tmp/uiowa-closeout.json \
  --md-out /tmp/uiowa-closeout.md
```

Expected synthetic result:

- status: `PASS`
- completion: `2026-11-20`
- 30-calendar-day deadline: `2026-12-20`
- protected evidence accounted: `4/4`
- warning: primary 30-day source locator still requires binding before live use

## Operating sequence

1. **At kickoff:** bind the controlling RFQ/agreement version and exact closeout locator in the engagement record.
2. **During intake:** assign every evidence object a stable ID and minimum-necessary metadata. Do not put real confidential evidence in Commons.
3. **During delivery:** keep derived copies linked to the originating evidence ID.
4. **At completion:** freeze the completion date and compute the closeout deadline from the controlling rule.
5. **Before disposition:** reconcile the inventory against actual authorized custody locations.
6. **Disposition:** record `returned`, `destroyed`, `retained_by_instruction`, or `never_received`. Retention exceptions require a written authority reference.
7. **Verification:** capture independent verification artifacts outside this public repository.
8. **Written confirmation:** populate the closeout confirmation only from completed records; never use the template itself as proof.
9. **Final validation:** run `closeout.py` with an explicit `--as-of` date and resolve every failure.

## Safety behavior

The validator fails or warns when it encounters:

- protected evidence in a public Commons custody location;
- ingested credential material;
- a retained-evidence exception without written authority;
- return/destruction after the calculated deadline;
- duplicate or unknown evidence IDs;
- missing disposition for protected evidence after the closeout deadline;
- a missing primary source locator for the 30-day rule.

This kit is not legal advice, a compliance certification, a deletion utility, or proof that any real evidence has been disposed.
