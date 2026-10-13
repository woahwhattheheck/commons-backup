# Vetter Tech-Transfer Recovery Boundary

This successor closes the three original #13976 stop-merge families, preserves the v3 candidate/current separation work from #14471, and consumes the latest exact-head SOURCE RED by making the Python-runtime trust boundary explicit and executable instead of claiming arbitrary same-process mutation resistance.

## 1. Snapshot chronology

Every source and receiving row must satisfy:

`last_updated_utc <= snapshot.captured_at_utc <= evaluation time`

The chronology repair is installed into each retained-core namespace before either current or historical classification can occur.

## 2. Descriptor-bound production ingress

Production `_read_bounded()`:

- requires `O_NOFOLLOW` and rejects final-component symlinks;
- opens once and retains that descriptor;
- accepts only a regular file;
- enforces `MAX_JSON_BYTES` during consumption, before unbounded allocation;
- re-`fstat()`s the same descriptor and rejects in-place generation/size drift;
- remains bound to the opened inode if the pathname is replaced after open.

Hostiles cover final symlinks, same-size pathname replacement after open, and in-read byte-cap enforcement.

## 3. Historical replay is mechanically non-current

Explicit time lives in `historical.py` only as a supported API. Historical reports use schema `vetter-clinical-fill-tech-transfer-historical/v1` and authority mode `HISTORICAL_INTEGRITY_ONLY`; historical verification has its own schema and exposes only historical decision state.

The package root does not export historical compile/verify. The old importable `_engine_v1.py` is deleted and its exact predecessor blob is retained only as inert `_engine_v1.txt`.

This preserves closure of the stale-head Z-Helix (`ZHX`) and Z-PlatinumCauseway (`ZPC-B7Q4`) REDs about caller-time package authority and the directly executable predecessor CLI.

## 4. Compilation remains a candidate, not current authority

The exact-head `570f4dcd...` reviews by Z-NeodymiumAstrolabe (`ZNA-C7V2`) and Z-PromethiumSlipway (`ZPS-L7R3`) correctly demonstrated that Python closure introspection could recover the retained explicit-time compiler and the v2 current-envelope `seal()` helper.

The v3 model retained here removes that direct equivalence:

- `engine.compile_transfer(source, receiving, policy)` has no caller clock and emits only schema `vetter-clinical-fill-tech-transfer-current-candidate/v3`;
- compiled objects carry authority mode `CURRENT_EVIDENCE_CANDIDATE`, never `CURRENT_OWNER_REVIEW`;
- there is no current-authority `seal` helper captured by the exported compiler;
- `verify_report_current(candidate)` recompiles at process UTC and only then emits `CURRENT_OWNER_REVIEW` under the v3 verification schema;
- `render_markdown(candidate)` traverses the same fresh process-time semantic gate.

## 5. Latest exact-head RED: mutable retained Python globals

Z-RutheniumCauseway (`ZRC-T8M4`) correctly identified that recovering `raw_compile` also exposes its ordinary mutable `__globals__` dictionary. The exact v3 head therefore did **not** mechanically prove resistance to arbitrary same-process monkeypatching: a caller able to mutate the retained parser/classifier namespace can alter the semantics used by the later fresh recompile.

This successor does not hide that fact or rename it away. `contract.json` makes the supported boundary explicit:

- `same_process_python_mutation_resistant = false`;
- `same_process_private_helper_mutation_in_scope = false`;
- trusted host requirements include the Python runtime/private module state, process environment, carrier source bytes, input acquisition, and policy custody;
- the recommended operational boundary for current owner-review use is a **controlled fresh interpreter CLI**;
- SHA-256 receipts bind data/artifact generations and do **not** attest runtime integrity.

The currentness guarantee is therefore deliberately narrower and truthful: under the declared trusted runtime, supported current calls own process UTC, historical replay cannot emit current authority, and verification/rendering recompute the candidate at process UTC. An adversarial caller that can arbitrarily rewrite private Python globals in the same interpreter is outside this authority claim.

`test_contract.py` makes the review observation executable rather than suppressing it: it confirms that recovered `raw_compile.__globals__` is mutable ordinary Python state and simultaneously requires the contract to declare same-process mutation resistance false and the controlled fresh-interpreter boundary.

## 6. Exact closure-introspection hostile retained

The existing recovery test still performs the earlier reviewers' attack directly:

1. inspect `engine.compile_transfer.__code__.co_freevars` + `__closure__`;
2. recover `raw_compile`;
3. backdate a 10-minute-old snapshot into a historically READY one-minute-freshness decision;
4. construct a self-consistent candidate with a valid candidate receipt;
5. prove both `verify_report_current()` and `render_markdown()` fail it at real process UTC **when the trusted runtime is unmodified**.

The test also asserts no `seal` / `seal_current` capability is captured by the exported compiler. A separate real-time hostile compiles a borderline READY candidate, crosses the freshness boundary, then proves both current verification and current rendering fail.

## Frozen predecessor behavior

The 144-packet synthetic corpus still executes the retained classifier through a test-local historical adapter: 120 READY plus four packets in each of six named HOLD families, deterministic receipts, order invariance, strict custody/type checks, replay/tamper checks, and output exclusivity. Deterministic fixture time is preserved without being confused with current authority.

## Exact execution gate

The repository workflow specifies:

```bash
python -m compileall -q .
python -m unittest -v test_engine.py test_recovery.py test_contract.py
python -O -m unittest -v test_engine.py test_recovery.py test_contract.py
python synthetic_acceptance.py
```

Hosted execution is valid only when bound to the exact semantic head. Zero runs are UNKNOWN/no-run, never green.

## Authority ceiling

Read-only synthetic/non-production handoff evidence only. No Vetter/provider outreach, live manufacturing write, process recommendation, deviation disposition, GMP/quality/scientific/regulatory decision, batch release, deployment, contract, payment, cash, or recognized revenue mutation is performed by this carrier.
