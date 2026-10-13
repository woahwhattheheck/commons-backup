# TT ONE LAB+ carrier semantic generation

This note closes the post-merge semantic-generation RED discovered against the first recovered carrier and records the exact integrity boundary after independent review.

## Boundary: cooperative in-process only

The machine-readable boundary is `INTEGRITY_BOUNDARY.json`:

`COOPERATIVE_IN_PROCESS_ONLY_NOT_HOSTILE_RUNTIME`

`carrier.py` reads the retained `source_manifest.json` once, validates the code-owned source contract, and constructs one semantic generation. The public `compile_packet()`, `verify_packet()`, `source_manifest_digest()`, and `example_owner_input()` functions are closures over that generation.

The generation captures, rather than late-resolving:

- the exact source-manifest SHA-256;
- the seven mandatory price-row names;
- the six-deliverable source topology check;
- evaluation weights summing to 100;
- the proposal deadline;
- the Ministry submission mailbox and subject;
- the clarification-route conflict and printed typo evidence;
- minimum experience, reference, and validity requirements;
- the complete all-false external-authority map;
- canonical JSON / SHA-256 functions; and
- strict validators, datetime parsing, regexes, and collection/builtin callables used by compile/verify.

This usefully prevents ordinary module-global/helper rebinding from silently changing compiler/verifier semantics. `verify_packet()` also closes over the same private compiler generation directly rather than late-resolving the public `compile_packet` symbol.

It is **not** a hostile same-process Python integrity boundary. CPython exposes writable closure cells (`function.__closure__[i].cell_contents`) and mutable function/runtime objects to code already executing in the interpreter. A hostile peer with reflective same-process access can mutate a captured source digest, buyer route, deadline, authority projection, function object, or equivalent runtime state. If it mutates the compiler generation shared by compile and verify, the same process can self-remint and self-verify changed semantics.

Accordingly, this carrier makes **no machine-strong same-process integrity claim**. The phrase “captured/frozen generation” means resistant to cooperative symbol rebinding, not cryptographic or interpreter-level immutability. Any hostile-runtime use must execute reviewed source in a separately trusted, source-verified environment outside the potentially hostile Python process. This repository does not provide or claim such an isolated runner.

## Time semantics

`evaluated_at` is caller-supplied historical/replay input. Every compiled packet states:

- `evaluation_time_authority = CALLER_SUPPLIED_REPLAY_ONLY_NOT_CURRENT`
- `current_deadline_readiness_claimed = false`

The deadline comparison answers only: **what would this owner packet's blocker state be at the supplied replay instant under the cooperative semantic generation?** It does not establish the supplied instant as current process time and cannot authorize a present-day submission.

No process-clock/current-submission API is exposed by this carrier. Current decision-making still requires owner/provider review of live time, source amendments, qualification evidence, pricing, collision state, and outbound authority.

## Tests

The retained focused suite runs through `test_tt_one_lab_lims_consultant.py` in normal and `python -O` mode.

The suite now tests both sides of the declared boundary:

1. ordinary module-global/helper/public-compiler rebinding does not change the captured cooperative generation; and
2. direct CPython closure-cell mutation **can** remint source/buyer/deadline semantics and self-verify inside the hostile process, which is expected and mechanically tied to the cooperative-only boundary declaration rather than hidden.

The closure-cell predecessor tests restore every mutated cell before returning so they demonstrate the unsupported hostile-runtime condition without contaminating subsequent tests.

The retained source/qualification/commercial hostiles remain unchanged: seven price rows vs six TOR milestones, qualification evidence, reference count, availability evidence, route typo preservation, exact submission metadata, replay deadline arithmetic, packet transplant/tamper, duplicate JSON keys, non-finite values, privacy, and all-false external authority.

No new active GitHub Actions workflow is introduced.
