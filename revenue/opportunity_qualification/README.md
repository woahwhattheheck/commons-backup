# Opportunity Qualification Engine

Reusable offline qualification for public RFPs, paid-work solicitations, and teaming opportunities.

The engine emits one conservative state: `PRIME_READY`, `TEAMING_READY`, `HOLD`, or `NO_BID`. These are internal evidence-package states, never external-action authority.

## Independent trust boundary

Qualification uses three separate inputs:

1. the opportunity packet;
2. an independently retained `tjlabs.opportunity-qualification-completeness/v2` manifest; and
3. the independently retained canonical SHA-256 of that normalized manifest.

The packet cannot prove its own requirement set or buyer-source authority.

The v2 completeness manifest binds the complete gate set **and every buyer-source descriptor that can influence qualification authority**. Each authority source is committed by source ID, `scope`, `source_class`, URL/provenance, capture time, and content SHA-256. The committed set covers the controlling source, proposal/question deadline sources, teaming source, and every requirement's buyer source.

This closes the source-authority predecessor from #13741: a byte-identical mirror cannot be relabeled from `SECONDARY` to `OFFICIAL` under the same retained root, and an official buyer URL/source cannot be replaced with a mirror while preserving readiness. Separate addendum/deadline/team sources are bound by the same rule.

The manifest also retains:

- opportunity ID;
- controlling buyer source ID + SHA-256;
- extraction time + extraction-evidence SHA-256;
- exact `complete` boolean;
- expected gate count and canonical gate-set SHA-256; and
- every expected gate's ID, category, mandatory/scoreable status, route, cure policy, buyer source ID + SHA-256, and description SHA-256.

Without both the manifest and its separately retained expected digest, package completeness is unverified. Any would-be `PRIME_READY`, `TEAMING_READY`, or requirement-derived `NO_BID` becomes `HOLD`. A separately buyer-official expired proposal deadline may still produce `NO_BID`, because that fact does not depend on requirement-set completeness.

## Requirement and evidence semantics

Mandatory gates cannot green from procurement mirrors; they must bind buyer `OFFICIAL` sources. Capability readiness evidence must bind official capability sources.

Each requirement has a stable gate ID, category, mandatory flag, route (`PRIME`, `TEAM`, `BOTH`), cure policy (`NONE`, `PARTNER`), buyer-source binding, and prime/team evidence state plus evidence IDs. `MISSING` cannot carry evidence. `PASS`/`FAIL` require evidence. Duplicate IDs, changed same-ID replays, source/subject/category drift, future or expired evidence, duplicate JSON keys, floats/non-finite numbers, malformed digests/URLs, and credential-shaped text fail closed.

## Negative authority

A non-curable mandatory failure can become a gate-derived `NO_BID` only when the independently committed package boundary verifies. An expired proposal deadline can independently produce `NO_BID` only when the controlling package and deadline source are buyer-official. Secondary mirrors cannot close the team route or force deadline authority.

An official addendum may move a deadline or carry a requirement only when that source descriptor is independently committed.

## Verification

`verify_receipt()` verifies receipt integrity and refuses external-authority mutations. `verify_receipt_against_inputs()` recompiles from the packet, trusted time, completeness manifest, and retained manifest digest, then compares canonical bytes.

The repository retains `completeness_fixture.json` and `completeness_fixture.sha256` as separate artifacts to demonstrate that the trust root is not derived from the packet at verification time.

The historical #13741 core and legacy semantic suites are preserved byte-for-byte. Root `test_opportunity_qualification.py` adapts only test-only commitment construction to v2, runs the preserved suites, adds frozen-root OFFICIAL/SECONDARY/scope/URL/deadline/team/verifier predecessors, and recursively runs the same root suite under `python -O`. This uses the repository's existing root test battery and adds no active workflow.

## CLI

```bash
python engine.py packet.json \
  --completeness completeness.json \
  --completeness-sha256 <independently-retained-manifest-sha256> \
  --as-of 2026-09-13T10:00:00Z \
  --markdown qualification.md
```

## Commercial boundary

This module evaluates supplied evidence only. It does not contact buyers or partners, log into portals, register entities, submit questions or proposals, commit pricing, sign, spend, mutate payment providers, deploy, assert an award, or recognize revenue.
