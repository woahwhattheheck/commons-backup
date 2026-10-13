# Tate & Lyle / CP Kelco portfolio integration solution-proof gate

Offline, read-only evidence gate for cross-portfolio solution packs. This v2 repair keeps the landed #13938 product semantics while removing its self-authentication flaw.

## Trust boundary

Candidate solution records carry **observations only**. Approved spec/region/use/claim values, legacy mapping, stability requirement, and named owner/version bindings live in a separate strict reference-set generation. `evaluate()` requires an `expected_reference_sha256` that the integration host retained independently of candidate bytes. A changed or substituted reference set fails before classification.

`reference_commitment()` canonicalizes a reference generation for provisioning, but computing a digest does **not** authenticate provenance. A caller that controls both references and the expected digest has not established independent authority. The receipt makes that limitation explicit.

Strongest state remains `READY_FOR_OWNER_INTEGRATION_REVIEW`. This is not formulation approval, claim approval, a regulatory decision, product release, buyer acceptance, payment, or recognized revenue.

## Acceptance fixture

`fixture.make_acceptance_batch()` plus `fixture.make_acceptance_reference_set()` build 120 frozen synthetic packs:

- 90 PASS
- 30 HOLD
- 75 seeded defects: 20 spec + 15 region/use/claim + 15 legacy + 15 stability + 10 owner/version

The hostile suite proves the old coupled-mutation exploit no longer works, reference generation/digest substitution fails closed, arbitrary legacy remapping holds, unused/missing reference authority is rejected, exact replay is deterministic, and all external authority remains false.

## Run

```bash
python -m unittest revenue.tate_lyle_cp_kelco_solution_proof_gate.test_gate -v
python -O -m unittest revenue.tate_lyle_cp_kelco_solution_proof_gate.test_gate -v
python -m py_compile revenue/tate_lyle_cp_kelco_solution_proof_gate/*.py
```
