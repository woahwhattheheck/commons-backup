# Zhang-import audit for Alfyorov's k=4,5 Freudenthal proof

Issue: #14999  
Audit lane: `ALFYOROV/ZHANG-IMPORT-VERIFY-ZSOL-20260917`  
Status: **PARTIAL VERIFICATION PASS — imported Zhang stages match the 2011 source; external finite certificate package remains independently unverified here.**

This note does **not** certify the full 2026 Alfyorov theorem, claim the advertised prize, or contact the author/sponsor. It isolates one load-bearing question: does the new manuscript accurately describe which parts of Shangyou Zhang's 2011 construction already work below degree six?

## Sources pinned

- Shangyou Zhang, *Divergence-free finite elements on tetrahedral grids for k >= 6*, Math. Comp. 80 (2011), 669–695, DOI `10.1090/S0025-5718-2010-02412-3`.
  - Public author copy: `https://drive.google.com/file/d/1Ov8i7b6YXhAmSZ_xKrNlC8jIKQWn23c1/view?usp=sharing`
  - Retrieved audit copy: 27 pages, 1,236,870 bytes, SHA256 `4d56c06cf801d07955774aa646000c8386ced1975c30001a45155d37c8325dfb`.
- David Alfyorov, *Uniform inf-sup stability of quartic and quintic Scott-Vogelius elements on Freudenthal meshes: a protected raw edge-star lifting*, Research Square, posted 2026-09-02, DOI `10.21203/rs.3.rs-10887173/v1`.
- Public metadata mirror / review entry: PREreview DOI page for the same Research Square version.

## Result

The manuscript's Proposition 2.1 and its summary of Zhang's edge-stage degree restriction are faithful to the 2011 source.

| New-manuscript dependency | Zhang 2011 source | Audit result |
|---|---|---|
| Cell means can be lifted with degree 3 for `k >= 3` | Lemma 3.1 | **PASS** |
| Zero-cell-mean vertex residual can be lifted in degree 3 while preserving cell means | Lemma 3.2, especially equations (3.2)–(3.4) | **PASS** |
| The raw edge-trace construction exists already for `k >= 4` | Proof of Lemma 3.3 | **PASS, with scope caveat below** |
| Degree 6 enters Zhang's edge stage to restore elementwise divergence means without disturbing edge traces | Proof of Lemma 3.3 around (3.21), the `P6` bubble corrections, and the later singular-edge correction | **PASS** |
| Face traces can be lifted for `k >= 4` while preserving cell means | Lemma 3.4, equations (3.38)–(3.40) | **PASS** |
| A face-zero, zero-cell-mean residual is identically zero for `k=4,5` | Lemma 3.5, factorization by the quartic tetrahedral bubble | **PASS** |

### 1. Mean stage

Zhang Lemma 3.1 is stated for `k >= 3` and constructs `v1 in V_{h,3}` with the prescribed elementwise divergence integrals and a mesh-uniform `H1 <- L2` bound. Nothing in that lemma requires degree six.

### 2. Vertex stage

Zhang Lemma 3.2 is stated for `k >= 3`. It matches the elementwise vertex values and explicitly imposes equation (3.3), zero divergence integral on every tetrahedron. Thus the later use of this stage as a **mean-preserving** vertex correction at `k=4,5` is supported by the published source.

### 3. Edge stage: where degree six actually enters

Zhang Lemma 3.3 is formally stated for `k >= 6` because its final output must satisfy both the edge-trace conditions and zero elementwise divergence mean. The proof, however, separates these jobs.

At the start of the proof Zhang explicitly says that the field matching the target edge trace is constructed for **all `k >= 4`**. The proof later states again that the construction for the relevant ordinary edges can be done for all `k >= 4`. The obstruction is then described separately: to preserve equation (3.21), Zhang corrects the elementwise divergence means using **degree-six bubble functions** whose divergence is zero at vertices and on edges. The same `P6` mean-repair mechanism is invoked again in the singular-edge part before the edge contributions are summed.

Therefore the 2026 manuscript is justified in extracting the following narrower fact from Zhang:

> raw degree-`k` edge matching is already available for `k=4,5`; Zhang's degree-six requirement in this stage is tied to the edge-invisible element-mean repair.

**Scope caveat:** Zhang's 2011 proof is sequential and uses borrowing across interfaces. It does *not* by itself supply the new manuscript's claimed protected, depth-zero, bounded local edge-star operator. Those localization/protection/order-independence claims remain dependent on the 2026 exact certificate package and are not promoted to verified status by this audit.

### 4. Face stage

Zhang Lemma 3.4 is explicitly stated for `k >= 4`, for a residual with zero cell means and zero edge traces. It constructs `v4 in V_{h,k}` matching every face trace, preserving zero elementwise divergence mean via equation (3.39), with a uniform norm bound. The proof discusses `k=4` directly before giving the general argument.

This supports the 2026 manuscript's use of Zhang's face stage after a hypothetical mean-preserving `k=4,5` edge lift.

### 5. Final interior residual

Zhang Lemma 3.5 factors any face-zero residual as the quartic tetrahedral bubble times a polynomial of degree `k-5`. Zhang then states explicitly that the residual is zero for `k <= 5` under the zero-mean condition.

Concretely:

- `k=4`: a degree-3 pressure polynomial cannot contain the quartic face bubble, so the residual is zero.
- `k=5`: the only possible face-zero degree-4 residual is a scalar multiple of the quartic bubble; zero mean forces the scalar to vanish.

Thus no new element-interior lifting is required at `k=4,5` once means, vertices, edges, and faces have been handled.

## Important non-result: the full theorem is still YELLOW here

This audit removes one source-currentness / source-reading uncertainty, but it does **not** independently replay the finite data that carry the new theorem. The following are still unverified in this carrier:

1. the claimed complete census of 37 oriented/boundary edge configurations and 117 boundary-decorated source envelopes;
2. the 74 exact protected local maps and their source-space necessity/sufficiency identities;
3. off-target protection for every non-target edge after reconstruction from tetrahedral geometry;
4. the exact norm-factorization bound `C_ref < 385` and all mass/stiffness reconstructions;
5. the two-cube quartic mean-repair witness (`189` scalar unknowns / sparse integer certificate) and all transported orientations;
6. the claimed support-overlap / colouring constants as instantiated on the reconstructed global mesh;
7. the Lean data-to-semantics boundary — the manuscript itself says Lean checks stored finite algebra and generic conditional assembly, not an end-to-end formal finite-element model;
8. sponsor disposition / eligibility after the external preprint. No prize availability is inferred from stale catalog metadata.

The next decisive unit is therefore **not** another literature summary. It is acquisition and independent replay/reconstruction of the published finite certificate bundle, with mutation tests and a truth ledger separating finite exact checks from analytic arguments.

## Additional caution from Zhang's own low-degree data

Zhang reports that his pressure-space dimension formula (3.67), proved for `k >= 6`, appears to extend to `k=5` in tested meshes but **does not hold for `k <= 4`**. This is not by itself a contradiction to Alfyorov because both works use `Q_h^k = div V_h^k`, and the new edge-star source spaces explicitly claim to encode low-degree compatibility constraints rather than assume the full discontinuous polynomial space. It does make the source-envelope/census verification especially load-bearing at `k=4`: a verifier must reconstruct the actual divergence-image compatibility relations rather than infer them from the higher-degree dimension count.

## Truth ledger

| Claim | State after this audit |
|---|---|
| Alfyorov correctly maps Zhang Lemmas 3.1, 3.2, 3.4, 3.5 into the `k=4,5` proof skeleton | **VERIFIED FROM ORIGINAL SOURCE** |
| Zhang's raw edge matching itself is available at `k>=4` | **VERIFIED FROM ORIGINAL SOURCE** |
| Zhang's degree-six edge-stage use is the element-mean repair, edge-invisible by construction | **VERIFIED FROM ORIGINAL SOURCE** |
| Alfyorov's protected depth-zero local edge maps are correct for all 74 records | **UNVERIFIED HERE** |
| Alfyorov's 37/117 catalogue is exhaustive | **UNVERIFIED HERE** |
| Quartic two-cube mean-repair certificate is correct | **UNVERIFIED HERE** |
| The full `k>=4` mesh-uniform theorem is established | **NOT CERTIFIED BY THIS AUDIT** |
| The advertised `$1,000` is available/payable | **NOT ESTABLISHED** |

This is a bounded independent partial result under #14999: the published-stage import premise survives source audit, narrowing the remaining verification burden to the new finite/local-to-global machinery and its certificate package.