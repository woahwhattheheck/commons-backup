# CASMI 2026 multi-spectrum MRR@25 successor

This additive successor keeps the source-locked foundation in `workbench.py` unchanged and narrows one concrete competition-value gap: the public competition pages describe **MRR@25 scored per molecule**, while a test molecule may carry **1–16 spectra**. The original workbench ranks one query spectrum at a time, so it is useful as a spectral-library smoke test but not as a faithful molecule-level objective harness.

## Public contract captured 2026-09-17

`public_competition_contract_2026-09-17.json` pins facts rendered on the current public Kaggle competition/data pages. It does not assert that Bryce has joined the competition or accepted its rules.

The retained public contract records the molecule-level MRR@25 objective, top-25 submission shape, 1–16 spectra per hidden-test molecule, notebook/runtime limits, public deadlines, the advertised $50,000 total prize pool, and an all-false provider/account authority ceiling. The prize pool is not expected value, an award, a receivable, or revenue.

Eligibility, collaboration/team-size details, account-specific rule acceptance, submission quota, and the controlling license/use interpretation for any external dataset remain held for owner/rules review.

## Executable data boundary

This generation executes **SYNTHETIC fixtures only**. `PUBLIC_OPEN` is intentionally not an executable admission class.

That restriction is structural: a caller cannot promote arbitrary gated, private, or restrictively licensed spectra merely by setting `dataset_kind="PUBLIC_OPEN"`. Public/open data can be enabled only by a separately reviewed provenance adapter that binds, at minimum, canonical source identity/URL, exact retained bytes or digest, observed generation/currentness, and an explicit compatible license/use class. Until that adapter exists, the module fails closed on every non-synthetic fixture.

Each synthetic molecule carries 1–16 query spectra; candidates can carry multiple reference spectra. The baseline scores every query spectrum against the candidate's best reference spectrum and aggregates evidence over the molecule (`70% mean + 30% max`). This is a deterministic diagnostic baseline, not a leaderboard claim.

The synthetic fixture contains a predecessor-style adversary: one spectrum for `M-001` is a near-perfect match to distractor `C-D`, while two independent spectra support the true `C-A`. Molecule aggregation recovers `C-A` first.

The module reports reciprocal rank at 25 and mean MRR@25 over molecules, and can render a **preview** CSV with the public `molecule_id,smiles` shape. The preview is synthetic-only and is not a Kaggle submission.

```bash
python competitions/enveda_casmi_2026/multispectrum.py baseline \
  competitions/enveda_casmi_2026/public_competition_contract_2026-09-17.json \
  competitions/enveda_casmi_2026/synthetic_multispectrum_fixture.json

python competitions/enveda_casmi_2026/multispectrum.py preview \
  competitions/enveda_casmi_2026/public_competition_contract_2026-09-17.json \
  competitions/enveda_casmi_2026/synthetic_multispectrum_fixture.json
```

## Research sequence without account mutation

1. Keep experiments synthetic until a reviewed provenance/license adapter exists; public accessibility by itself is not executable evidence.
2. Replace heuristic mean/max aggregation with learned or calibrated fusion across spectra/adducts, while scoring validation at the molecule/MRR@25 unit.
3. Separate library-search candidates from structure-generation candidates and preserve provenance throughout.
4. Optimize top-25 ranking diversity/calibration, not only top-1 spectral similarity.
5. If Bryce later joins, pin the accepted rules/data generation before gated-data work or a real submission and re-run authority/data-license gates.

## Authority ceiling

All account/provider authority in the retained contract is false. No code in this successor signs in to Kaggle, joins the competition, accepts rules, changes a team, downloads gated data, submits a notebook/file, contacts organizers, asserts eligibility, claims a prize, or recognizes revenue.
