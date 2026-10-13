# EvidenceAAR Phase 1 handoff

## Product thesis

After-action review quality breaks when events from radio, video, sensors, and written logs disagree about time or state and the synthesis layer silently chooses one story. EvidenceAAR makes the evidence graph visible: correct clocks first, conserve source identity, segment the timeline, bind every claim back to evidence, mark contradictions unresolved, and report coverage gaps before generating a human-readable AAR.

## Demonstrable source state

- [x] Deterministic strict-JSON input contract.
- [x] Per-source clock correction and corrected-time ordering.
- [x] Gap-based episode segmentation.
- [x] Observation / decision / action / outcome claims with source SHA-256 lineage.
- [x] Same-kind contradiction ledger with explicit `UNRESOLVED` state.
- [x] Required-modality coverage ledger.
- [x] Deterministic JSON, Markdown, HTML, receipt, and exact verifier.
- [x] Synthetic four-modality fixture with complete and incomplete episodes.
- [x] Normal + `python -O` hostile regression suite.
- [x] Stdlib-only Docker/CLI envelope.
- [ ] Authenticated Vulcan registration and challenge terms acceptance.
- [ ] Sponsor-provided / authorized real exercise corpus.
- [ ] Real audio/video/image extraction adapters under the sponsor's data handling rules.
- [ ] Phase 1 submission receipt.
- [ ] Phase 2 selection / participation receipt.
- [ ] Award or payment receipt.

Unchecked rows are **not** implied by the source carrier.

## Suggested 3-minute demo

1. Show the four synthetic evidence sources and their clock offsets.
2. Compile the packet and inspect corrected ordering in `aar.json`.
3. Show episode 1's complete TEXT/AUDIO/VIDEO/SENSOR coverage.
4. Show the two `route-alpha` observations conserved as an unresolved contradiction instead of auto-resolved.
5. Show episode 2's missing VIDEO/SENSOR coverage warning.
6. Show an assertion containing HTML/Markdown metacharacters safely rendered in both outputs.
7. Tamper with one claim or receipt byte and run `verify`; exact recomputation rejects it.
8. Close on the real integration seam: sponsor-authorized multimodal extraction feeds this deterministic evidence/AAR layer; operational ingestion remains gated until actual data-handling authority exists.

## Proposed sponsor-facing architecture after authorized onboarding

```text
Authorized multimodal sources
        |
        v
[extract/transcribe/detect adapters]
        |
        v
normalized event packet + immutable source digests
        |
        v
EvidenceAAR deterministic core
  - clock correction
  - episode segmentation
  - evidence-linked claims
  - contradiction ledger
  - coverage ledger
        |
        +--> AAR JSON
        +--> reviewer Markdown / HTML
        +--> content-addressed receipt + verifier
```

The extraction layer should remain replaceable and should never be allowed to erase the original source digest or silently resolve conflict. Human review can resolve contradictions later with an explicit new evidence event rather than mutating history.

## External truth boundary

Current public challenge information says Phase 1 is due September 25, 2026, with virtual Phase 2 October 20–22 and advertised $50k/$30k/$20k awards. Re-check the controlling Vulcan / sponsor terms immediately before any account or submission mutation. This source tree does not register, accept terms, contact NIWC, upload data, submit, or claim selection/payment.
