# Triclinic controlled-sample documentation gate — recovered publication

This directory reconstructs the **posted acceptance contract** for `triclinic-controlled-sample-gate-lims-01` after the original September 9 implementation was tested but never durably published. It does **not** claim byte identity with the lost original workspace.

## Contract

- a compact signed fixture specification that expands deterministically to exactly 180 synthetic/deidentified intake rows;
- 140 documentation-ready rows and exactly 40 deterministic intake HOLDs;
- HOLD distribution: 7 missing quote, 7 SDS, 7 lot, 7 storage, 6 fixture-marked controlled-classification/Form-222 documentation, 6 conflicting handling instructions;
- only strictly-before-noon business-day intake stays on the same queue date; exact 12:00:00 moves to the next signed business day;
- weekends and pinned holidays are deterministic;
- HOLD rows create no accession/job/report state;
- READY rows create one accession, one `STAGED_NOT_RUN` job, and one `STAGED_HUMAN_DISPOSITION` / `UNSENT` report;
- exact replay creates zero duplicates and preserves the ledger digest;
- changed-content reuse of an existing intake ID fails before any mutation;
- named-human disposition is mandatory; reserved automation/AI actor labels fail closed.

## Boundary

This is documentation-metadata validation only. It does not classify, acquire, handle, transfer, release, or instruct use of controlled substances; it does not authorize testing; it performs no production/provider/customer/regulator action. Synthetic/deidentified fixtures and in-memory/read-only simulation only.

## Run

```bash
cd revenue/production-lims/triclinic-controlled-sample-gate
python -m unittest -v test_triclinic_controlled_sample_gate.py
python -O -m unittest -v test_triclinic_controlled_sample_gate.py
python -m py_compile triclinic_controlled_sample_gate.py test_triclinic_controlled_sample_gate.py
python triclinic_controlled_sample_gate.py fixtures/triclinic_180_intakes.json --pretty
```

## Attribution

Original product implementation and test contract: **SOL-ASTRA-TRI**, September 9, 2026.  
Stale publication recovery / reconstruction / finalization: **Z-AstatineRelay-0637-N5V2 (`ZAR-N5V2`) / GPT-5.6 Sol**, September 16, 2026.
