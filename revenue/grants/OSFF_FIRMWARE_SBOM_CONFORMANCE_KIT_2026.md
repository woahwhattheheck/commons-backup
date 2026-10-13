# OSFF 2026/2 proposal — Firmware Embedded SBOM Conformance Kit

Status: **application packet for new future work; not an award and not booked revenue.**

Sponsor: [Open-Source Firmware Foundation — Small-Scale, High-Impact Firmware Contributions 2026/2](https://www.osfw.foundation/funding/small-scale-high-impact-firmware-contributions-2026-2/)  
Call status: open July 15–September 30, 2026  
Published range: **€1,000–€7,500**; the call explicitly says funding is not pre-allocated  
Requested amount: **€7,500**  
Applicant/project home: [woahwhattheheck/commons](https://github.com/woahwhattheheck/commons) (Apache-2.0)  
Primary upstream target: [open-source-firmware/sbom](https://github.com/open-source-firmware/sbom) (CC-BY-4.0 specification)  
Reference implementation dependency: [hughsie/python-uswid](https://github.com/hughsie/python-uswid)

## Source-bound fit check

This packet is bound to OSFF's current public call and to `open-source-firmware/sbom@abab4b8960787b06d47ae5a748a4bfd1fa94d32d` as reviewed on 2026-09-13 UTC.

The current Firmware Embedded SBOM Specification requires coSWID/CBOR for embedded firmware SBOM data, specifies PE/COFF `.sbom` sections, a discoverable uSWID header for non-PE binaries, compressed payload options, and a defragmented firmware-SBOM model. It recommends validation with `uswid`. The upstream specification repository's current CI builds PDF/HTML documentation, but does not contain a machine-checkable conformance fixture suite for those normative embedding cases.

An open upstream issue (#3) is separately exploring optional executable-measurement reconciliation. **This proposal does not duplicate or depend on that work.** It is limited to conformance of the embedding rules already documented by the specification.

## One-page proposal

### Project description

Build a small **Firmware Embedded SBOM Conformance Kit** that turns the OSFF Firmware Embedded SBOM Specification's existing embedding rules into reproducible, machine-checkable fixtures and CI checks.

The project will add an openly licensed synthetic corpus covering the specification's main embedding shapes: PE/COFF binaries with `.sbom` sections, raw non-PE images with the discoverable uSWID header, compressed and uncompressed payloads, aligned/padded headers, and a defragmented top-level firmware SBOM. Each positive fixture will have a paired negative mutation for a specific normative rule (bad magic/version/length, non-NUL padding, invalid compression flags, missing required component coverage, malformed coSWID payload, or inconsistent container metadata).

A small Python CLI, `fw-sbom-conformance`, will run these checks deterministically. It will **reuse `python-uswid`/`uswid` for coSWID parsing and validation rather than reimplementing that parser**; the new code will focus on specification-level container/coverage assertions, fixture generation, stable diagnostics, and a JSON result format suitable for CI. The corpus will use synthetic components only, so contributors and CI systems do not need proprietary firmware images or hardware.

The integration target is upstream-first: propose the fixture corpus, runner, and a CI job to `open-source-firmware/sbom`, plus focused `python-uswid` PRs only if a missing public API prevents clean conformance testing. Documentation will show firmware projects how to run the same suite against their own generated artifacts without uploading firmware anywhere.

This work will not add vulnerability scanning, binary-module identity reconciliation, signing infrastructure, remote services, or proprietary firmware. It is intended to make the existing specification easier to adopt correctly and easier to review as it evolves.

### Impact

Today the OSFF repository can prove that the specification renders, but not automatically that examples and future normative changes remain mutually consistent at the binary-container level. A compact conformance kit gives firmware maintainers a public interoperability target, catches regressions before release, and lowers the barrier for projects that want embedded SBOMs but do not have a private compliance lab.

### Deliverables / acceptance

1. **Synthetic conformance corpus:** at least 12 positive fixtures spanning the documented PE/uSWID/defragmented forms, plus at least one deterministic negative mutation per asserted rule.
2. **`fw-sbom-conformance` CLI:** offline runner with human diagnostics and stable JSON output; no network required after dependencies are installed.
3. **Source-bound tests:** exact fixture manifests and hashes; malformed/truncated/unknown-compression inputs fail closed rather than being silently accepted.
4. **OSFF integration:** upstream PR to `open-source-firmware/sbom` adding the conformance assets and CI execution, or a maintainer-approved adjacent repository if they prefer separation.
5. **Reference-tool integration:** focused `python-uswid` PR(s) only where required for reusable parsing/validation hooks; otherwise consume its existing public CLI/API unchanged.
6. **Adoption guide:** one command for local validation, CI example, fixture-extension rules, and guidance for testing private firmware locally without publishing binaries.

Completion requires a clean run of the corpus, byte-stable fixture regeneration, documented hashes, and submitted upstream integration PR(s). Maintainer review/merge timing is outside the funded implementation's control and will be reported separately from completed engineering work.

### Timeline

**6 weeks.** Week 1: freeze rule matrix and fixture format with upstream feedback. Weeks 2–3: fixture generator/corpus and conformance runner. Week 4: negative/fail-closed matrix and stable JSON diagnostics. Week 5: OSFF CI/adoption docs and upstream PRs. Week 6: review fixes, reproducibility pass, release/tag of the reference kit.

### Budget

Requested: **€7,500** for the six-week milestone. The budget covers implementation, fixture design, deterministic test/CI work, upstream integration, review fixes, and documentation. No hardware purchase, hosted service, paid model/API dependency, or proprietary data is required.

### Background

The applicant maintains the public Apache-2.0 Commons repository and has recent public work centered on deterministic source binding, fail-closed validation, reproducible fixtures, CI contracts, and connector/interoperability tooling. **No prior firmware-specific client delivery is claimed.** This proposal deliberately keeps the firmware-specific scope narrow, builds on the OSFF specification and `python-uswid` rather than inventing a parallel standard, and makes upstream review part of the delivery plan.

## Submission facts / boundaries

- OSFF says applications are open to individual developers/maintainers, small teams/organizations, students, and researchers contributing to open-source firmware.
- The call asks for project description (max 500 words), impact, timeline, budget, and background and directs one-page proposals to `cfp+2026oc3@osfw.foundation`.
- OSFF says proposals are reviewed on a rolling basis with a target response in 2–3 weeks.
- The call explicitly says funding is **not pre-allocated**; therefore this packet records **€0 awarded / €0 booked** until OSFF accepts it.
- All proposed engineering is new future work. Existing Commons work is cited only as capability evidence and is not being submitted for retroactive reimbursement.
- No customer/private firmware, credentials, proprietary blobs, security exploit reproduction, hardware purchase, or paid provider commitment is part of this proposal.

## Public references

- OSFF call: https://www.osfw.foundation/funding/small-scale-high-impact-firmware-contributions-2026-2/
- OSFF funding page: https://www.osfw.foundation/funding/
- Firmware Embedded SBOM Specification: https://sbomspec.osfw.foundation/
- Specification source: https://github.com/open-source-firmware/sbom
- Current embedding rules reviewed: https://github.com/open-source-firmware/sbom/blob/main/source/embedding.rst
- Current spec CI reviewed: https://github.com/open-source-firmware/sbom/blob/main/.github/workflows/ci.yml
- Existing non-overlapping upstream discussion: https://github.com/open-source-firmware/sbom/issues/3
- `python-uswid`: https://github.com/hughsie/python-uswid
- Commons: https://github.com/woahwhattheheck/commons
