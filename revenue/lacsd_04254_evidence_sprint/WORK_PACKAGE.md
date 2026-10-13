# $5,000 fixed-scope work package — AI/ML validation & evidence sprint

**Commercial status:** offer template only; not accepted, not ordered, not invoiced, and $0 booked.

## Fixed price

**$5,000 USD** for one bounded evidence sprint against one prime-provided candidate AI/ML decision interface or exported decision log.

## Included deliverables

1. **Interface/evidence mapping** — map the provided candidate output into the sprint's strict event/lineage contract without changing the candidate's substantive decisions.
2. **Candidate-build commitment** — record exact candidate ID, model ID, model version, and SHA-256 of the authorized artifact/export; derive one canonical build digest and bind every evaluated event to it.
3. **Synthetic scenario run** — execute the versioned scenario portfolio covering normal flow, blockage drift, storm-driven I/I, sensor dropout, replay/duplicate delivery, and interrupted-transport recovery.
4. **Alert-quality evidence** — detection, false-urgent, timing, and exact-effect/work-intent counts with per-scenario traceability.
5. **Lineage evidence** — exact build, artifact, and input-stream SHA-256 commitments. These are content commitments, not independent proof of ownership or authorization.
6. **Reliability evidence** — globally reserved effect/work-intent identity, duplicate-effect and recovery checks, and integration regression checks where a bounded prime-provided adapter exists.
7. **Evidence pack** — canonical machine-readable `claim → test → result → evidence` receipt plus concise Markdown findings/exception list suitable for capture, demo preparation, or engineering handoff.
8. **One correction rerun** — one rerun against the same fixed scope after the prime supplies a corrected candidate build/export. A changed build must carry a new artifact/build commitment and newly bound event evidence.

## Binary acceptance

The work package itself is complete when:

- the authorized candidate artifact/export is ingested or a specific incompatibility is documented;
- the artifact bytes are hashed and the exact candidate/model/version/artifact build commitment is recorded;
- all evaluated events bind that exact build commitment;
- all fixed scenarios execute or each blocked scenario has an explicit reproducible blocker;
- metrics and per-scenario evidence are generated deterministically;
- effect/work-intent identity has no cross-build, cross-scenario, or cross-input reuse;
- lineage and receipt verification pass for the delivered pack;
- no unsupported field-performance statement is inserted into the evidence pack;
- source inputs, accepted outputs, and rejected/blocked cases reconcile exactly.

A candidate system **does not need to pass every quality gate for the subcontract to be complete**. Finding a reproducible failure is valid paid evidence. `READY_FOR_BUYER_REVIEW` describes the candidate's synthetic gate result, not whether the evidence sprint was performed.

## Artifact-ingress boundary

Candidate and receipt JSON files are accepted only as bounded stable ordinary files. The CLI rejects final symlinks, FIFOs, devices, directories, files over 2 MiB, growth/truncation, path replacement, descriptor-generation drift, invalid UTF-8, duplicate JSON keys, and non-finite JSON numbers. Unsupported platforms fail closed rather than falling back to an unbounded pathname reader.

## Explicit exclusions

Not included without a separately agreed scope: independent authentication of artifact ownership/provenance; production deployment; live sewer controls; maintenance dispatch; field sensor procurement; LACSD credentials/data access; security penetration testing; model retraining; 24/7 operations; regulatory certification; legal/compliance opinion; proposal submission; buyer representation; travel; or performance guarantees on unseen field data.

## Inputs requested from the prime

- one authorized candidate build, API sandbox, or exported decision log;
- exact artifact/export bytes from which SHA-256 can be computed;
- stable candidate, model, and version identifiers;
- bounded interface/schema documentation;
- any prime-owned adapter fixture needed for integration regression;
- one technical contact for interpreting interface errors (not for changing expected results after the run).

## Delivery posture

The package is intentionally prime-neutral. GHD, Jacobs, Sand Tech, StormHarvester, Trinnex, or another authorized party can use the same evidence contract without any claim that they have accepted this offer or that synthetic results represent LACSD field performance.
