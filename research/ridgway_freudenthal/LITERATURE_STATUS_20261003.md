# Literature and sponsor status — 2026-10-03

This note records primary sources retrieved on **2026-10-03 UTC** for [Commons #14999](https://github.com/woahwhattheheck/commons/issues/14999). It supplements the existing [bibliography](BIBLIOGRAPHY.md) and [ledger](LEDGER.md) with a dated literature snapshot.

**Finding:** three accessible 2026 preprints state mesh-uniform stability results covering the formerly missing degrees four and five. Their theorem and proof passages were inspected directly. This establishes the existence and contents of those claims; this note does not independently certify their proofs. **Current sponsor disposition was not established.** [A], [D], [L], [S]

## 1. Meaning of the reported claims

The sources below concern continuous vector Lagrange velocities with homogeneous Dirichlet boundary values on uniformly subdivided, consistently oriented Freudenthal cube meshes. Their pressure space is the **actual divergence image**, not an independently specified collection of arbitrary broken polynomials satisfying selected local conditions. For a fixed degree, the reported right-inverse bound is uniform in mesh refinement. ([D], §2; [L], §1)

These qualifications matter when comparing a construction with the literature. A local map, a finite-mesh computation, a global mesh-uniform theorem, an attribution or priority decision, and a sponsor award are separate statements. Evidence for one does not automatically establish the others.

## 2. Primary full texts and precise reading locations

### A. David Alfyorov — Research Square v1

*Uniform inf–sup stability of quartic and quintic Scott–Vogelius elements on Freudenthal meshes: a protected raw edge-star lifting.* DOI **10.21203/rs.3.rs-10887173/v1**. The manuscript is dated **31 August 2026**; its publisher cover says **posted 2 September 2026**. [A]

Theorem 1.1 states the result for each fixed \(k\ge4\), combining the new \(k=4,5\) construction with Zhang for higher degrees. Inspected §4 source/output maps, §5 norm bound, §7 mean repair, §8 assembly, and §9 certificates. [A]

**Locators:** printed p.2, Theorem 1.1; pp.4–5, §4; p.6, §5; pp.8–9, §7; pp.9–10, §8; pp.10–11, §9. Add one to a printed page number for the physical PDF page because of the publisher cover.

The author expressly limits the formal layer: finite algebra and conditional assembly lemmas are encoded, but global mesh instantiation and Sobolev arguments are not an end-to-end formal development (§9, printed p.11). Supplementary certificates were not executed here. [A]

### D. Siqi Ding, Pingbing Ming, Haijun Yu and Quanfan Zhu — arXiv v1

*The Scott–Vogelius element is inf-sup stable on Freudenthal meshes for \(k\ge4\).* **arXiv:2609.25690v1**. The versioned abstract page records **22 September 2026, 04:47:25 UTC** and displays only v1 in its submission history. [D0]

**Read:** §2, equations (2.1)–(2.3) and Theorem 2.1; §§3–4, compatibility and explicit local edge constructions; Theorem 4.7; §5, Lemma 5.1, Theorem 5.2 and the main proof; Appendix A boundary templates. The paper claims every fixed degree \(k\ge4\), describes an explicit construction without required computer verification, and handles \(N=1\) separately from the \(N\ge2\) patch placements. [D]

The introduction, §1, explicitly acknowledges other recent preprints. Their citation leads are accounted for below; this note does not assign priority from the submission dates. [D]

### L. Hanbing Liang and Fujun Liu — arXiv v1

*Uniform Stability of Scott–Vogelius Elements on Three-Dimensional Freudenthal Meshes in Degrees Four and Five: Resolving the Farrell–Mitchell–Scott Conjecture.* **arXiv:2609.29608v1**. Its versioned abstract page displays **28 August 2026, 05:22:11 UTC**, and only v1 in the submission history. That is the date actually displayed despite the identifier's 2609 prefix. [L0]

**Read:** Theorem 1.1; §2 mean and vertex lifts; §3 edge source and output spaces; Lemma 4.1 quartic mean transfer; §5 bounded-cluster routing; Lemma 6.1 element bubbles; §7 global proof, especially residual membership in the divergence image and (109); §8 reproducibility discussion. The stated \(k\ge4\) conclusion combines the new low-degree argument with Zhang's higher-degree result. Remark 5.3 separates \(N=1,2\) as fixed finite cases. [L]

The text links [its reproducibility repository](https://github.com/ToughClimb/freudenthal-sv). Repository programs and certificates were not run here. [L]

## 3. Earlier question and distinct contemporary citations

### Farrell–Mitchell–Scott

The accessible record is **arXiv:2211.05494v2**, with submission history **10 November 2022** for v1 and **11 January 2024** for v2. Its journal reference is *SIAM Journal on Scientific Computing* **46(2), A629–A644 (2024)**, DOI **10.1137/22M1533943**. [F0]

In the full text, **Conjecture 1 (§2, equation (4))** asks for mesh-uniform stability for \(k\ge4\) with pressure equal to the velocity divergence image. **Conjecture 2 (§3.3)** is different: it concerns a vertex-star-supported basis for the preceding potential space, with different conjectured behavior at \(k=4\) and \(k\ge5\). Sections 2, 3.3 and 4 were inspected. A claimed resolution of Conjecture 1 should not be presented as resolution of both conjectures. [F]

The HTML title area also renders a manuscript date of 24 August 2026. The version history above is taken from the abstract record; this note does not reconcile that display difference or use it to infer priority. [F0], [F]

### Zhang

The historical reference is **Shangyou Zhang**, *Divergence-free finite elements on tetrahedral grids for \(k\ge6\)*, *Mathematics of Computation* **80(274), 669–695 (2011)**, DOI **10.1090/S0025-5718-2010-02412-3**. [Z]

The new papers and the earlier conjecture paper cite this as the established higher-degree result. The original AMS full text was not recovered in this session, so its proof was not reread here. Its role in the claims above is reported as those authors' cited input. [D], [L], [F]

### Henry: two identifiers, not one recovered full text

Two distinct bibliographic leads occur in the inspected primary papers:

| Citing source | Cited item | Identifier |
|---|---|---|
| Ding et al., reference [10] | K. Henry, proof preprint, 2026 | [10.5281/zenodo.22286974][H1] |
| Alfyorov, reference [2] | K. Henry, exact computational certificate archive, version 1, 2026 | [10.5281/zenodo.22034908][H2] |

The DOI and Zenodo record requests were unsuccessful. These are **citation-only leads**: neither full text, version relationship, latest revision nor external verification was established. No equivalence between the two records is assumed.

## 4. Sponsor evidence and opportunity status

The official prize-note URL is [Scott's *Inf-sup condition for quartics on the Freudenthal mesh*][S]. Indexed text from that exact official URL gives the date **14 November 2023** and describes a **$1,000** offer for proving and publishing the mesh-uniform three-dimensional result for \(k\ge4\), or an analytical refutation. It also mentions partial awards and treatment of simultaneous independent submissions. This is a **historical offer**, retrieved through indexed official-source text. [S]

Direct access to the PDF and [official prizes index][S0] returned **502 Bad Gateway** during this check. No accessible current sponsor announcement establishing acceptance, award, payment, withdrawal or continued availability was found. The historical advertisement, a preprint's title, and a Commons issue's open or closed state cannot supply that missing disposition.

**Status for planning:** contemporary claimed solutions exist; sponsor disposition remains **unknown from accessible primary evidence as of this date**. A statement that the prize is currently open, won, payable, or available to a new claimant would go beyond this evidence.

## 5. Retrieval record and limits

| Source route | Result on 2026-10-03 |
|---|---|
| Alfyorov publisher assets PDF [A] | Accessible, 16 physical pages including cover and supplement listing. |
| Research Square [latest-version page][A0], version landing and DOI | Unavailable through the retrieval tool; one response was 403. No current revision history established. An unsuccessful v2 probe is not evidence that v2 exists. |
| New arXiv versioned HTML [D], [L] | Accessible full texts; used for the proof passages identified above. |
| New arXiv versioned abstracts [D0], [L0] | Accessible on follow-up, including displayed submission histories. Earlier unversioned/PDF failures do not negate this recovery. |
| Farrell–Mitchell–Scott [F0], [F] and PDF | Accessible metadata and full text. |
| Zhang DOI and official AMS PDF [Z] | Access failed; bibliographic lead retained. |
| Henry DOI and record routes [H1], [H2] | Access failed; citation-only scope retained. |
| Sponsor PDF [S] and index [S0] | Direct requests failed; indexed official PDF text supports only the dated offer. |

The access outcomes are observations of this retrieval session, not claims that a document is unavailable to every reader. No journal acceptance of the three new preprints was established from the inspected records. The linked external code, certificates and supplemental archives were not downloaded or executed. No sponsor contact or submission occurred.

## 6. How to use this note

Use the cited versions when describing what the literature says, and include the contemporaneous authors when discussing the low-degree problem. For any priority, award or current-opportunity statement, obtain a primary source that actually addresses that question.

For a future refresh, the unresolved source questions are concrete: the Research Square revision history; the two Henry record contents and relationship; and a current sponsor disposition. Recovering any one would update a specific row above. Repeating local constructors or treating internal delivery status as external acceptance would not answer those source questions.

This file supplies attribution and source status. It introduces no implementation review gate and makes no change to the existing mathematical constructions.

[A]: https://assets-eu.researchsquare.com/files/rs-10887173/v1_covered_eba39d1d-bd86-4ad1-ba78-f777df531c65.pdf
[A0]: https://www.researchsquare.com/article/rs-10887173/latest
[D]: https://arxiv.org/html/2609.25690v1
[D0]: https://arxiv.org/abs/2609.25690v1
[L]: https://arxiv.org/html/2609.29608v1
[L0]: https://arxiv.org/abs/2609.29608v1
[F]: https://arxiv.org/html/2211.05494v2
[F0]: https://arxiv.org/abs/2211.05494
[Z]: https://doi.org/10.1090/S0025-5718-2010-02412-3
[H1]: https://doi.org/10.5281/zenodo.22286974
[H2]: https://doi.org/10.5281/zenodo.22034908
[S]: https://people.cs.uchicago.edu/~ridg/prizes/kuhnprize.pdf
[S0]: https://people.cs.uchicago.edu/~ridg/prizes/prizes.html
