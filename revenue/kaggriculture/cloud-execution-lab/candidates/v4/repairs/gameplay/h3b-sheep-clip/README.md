# H3b sheep max-held harvest-priority recovery

Canonical V4 current-ABI continuation of the H3b source theorem recovered from PR #12603. This package remains default-OFF research/gameplay evidence; it does not activate H3b in the live runtime or make an economics/promotion claim.

The legacy `apply_v4.py` carrier and old workflow are intentionally not revived. The current package owns only the existing `repairs/gameplay/h3b-sheep-clip/` helper, focused tests, and this documentation.

## Current theorem

H3b may reprioritize an existing V233 sheep-worker `HARVEST` within that worker's already-assigned block only when next-refresh WOOL clipping is provable. It remains harvest-for-harvest only: FEED, CARE, cargo-return, setup, stale same-call state, malformed/nonstandard evidence, final-day behavior, and non-persistent multi-step reroutes fail closed.

The current-ABI source closes four fail-open custody boundaries:

- **required configuration evidence:** every `STANDARD_CONFIG` field must be present with the exact plain-int type/value. Missing configuration, `configuration=None`, or a missing required field cannot self-certify by substituting the expected constant;
- **animal structure provenance:** a target is a sheep only when `kind == "PASTURE"` and `animal == "SHEEP"`; an animal label on a COOP/PLANT/malformed tile cannot authorize a reroute;
- **activation type:** gameplay logic is entered only for the literal boolean `True`. Literal `False` and every malformed/truthy non-bool token preserve the exact parent action object before configuration or V233 state is touched;
- **V233 authority marker:** the same-call parent snapshot is accepted only when `state["committed"] is True`; truthy malformed markers such as `1`, `"false"`, floats, containers, or `None` cannot authorize a harvest reroute.

The first two semantics consume the detached post-#12603 fail-closed successors (`8ad3fb83...` and `1eb2440a...`). The resulting helper before activation hardening was byte-identical to the reviewed successor blob `100ddda513f433f33cd98704a0abab4d49e6c4da`; the current helper extends it with literal-True activation and literal-True V233 committed authority.

## Current candidate custody

Canonical candidate branch/PR authority is the earliest current-package carrier:

- branch `astra/h3b-current-abi-failclosed-20260912`;
- draft PR #13065;
- helper Git blob `7ef50f2ee84dd045b35cd14ad8e56dcdd8b87504`;
- focused current-ABI test Git blob `cfca879d75c688da48f2656d1850a62c5ea80b9e`.

The focused suite contains predecessor killers for `configuration=None` and every missing required standard field, non-PASTURE `kind` values despite `animal == "SHEEP"`, malformed enable tokens (`"false"`, `1`, `1.0`, containers, `None`), malformed V233 committed markers, exact disabled identity, and the canonical literal-True PASTURE/SHEEP positive path.

## Current disposition — EXECUTION HOLD

The source-hold described by the original custody README is closed in this candidate, but **merge/promotion authority is not**. This authoring seat does not claim a repo-mounted/current-seam green run.

Before #13065 can leave draft/HOLD, a genuine current V4 materialization must authenticate the exact candidate blobs and run the H3b focused suite in normal and optimized (`python -O`) mode, `py_compile`, and the current V233/router/config seam gate. The receipt must report the exact head/blobs/counts and confirm all four fail-closed families plus the canonical positive control.

Only after that execution receipt may the same carrier be fresh-main rejoined and, if the existing central integration ledger requires an H3b evidence row, that exact tested identity may be registered. No legacy materializer, sibling V4 root, runtime/default/config/COMPOSITION/archive/Kaggle activation, or economics claim is authorized by this source package alone.
