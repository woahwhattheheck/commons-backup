# CASMI synthetic neutral-loss consensus experiment

This additive experiment is a **SYNTHETIC-only** successor to the existing
`multispectrum.py` molecule-level baseline. It does not modify the public
competition contract, provenance/admission code, or the baseline itself.

## Research question

The frozen baseline compares absolute fragment m/z evidence plus precursor
proximity for each spectrum and aggregates a candidate with the existing
`70% mean + 30% max` rule. That is useful when precursor/adduct conditions line
up, but it can be brittle when absolute fragments move together with the
precursor.

`neutral_loss_consensus.py` adds a separate diagnostic:

1. derive each neutral-loss peak as `precursor_mz - fragment_mz`;
2. score both the frozen absolute-fragment/precursor predecessor and
   neutral-loss cosine evidence;
3. replace the predecessor's max-spectrum bonus in the successor with the
   median per-spectrum score in each evidence space;
4. blend the two median consensus scores using fixture-bound integer basis
   points (`3500` fragment / `6500` neutral loss in the retained fixture);
5. rank at the molecule unit and report deterministic top-25 + reciprocal-rank
   diagnostics.

Scores are quantized to integer parts-per-million before consensus/blending so
the published ordering is deterministic and receipt-bound.

## Retained hostile

`synthetic_neutral_loss_fixture.json` includes `M-ADDUCT-SHIFT`.

Its two query spectra shift precursor and fragment m/z together, preserving
neutral losses. `C-FRAGMENT-DECOY` matches the absolute fragments of one query
very well but carries a different precursor-to-fragment loss pattern.
`C-TRUE-LOSS` has shifted absolute fragments but preserves the query neutral
losses.

The committed synthetic receipt records:

- frozen predecessor expected rank for `M-ADDUCT-SHIFT`: **3**;
- successor expected rank: **1**;
- stable-control `M-STABLE`: **1 -> 1**;
- local predecessor MRR@25 diagnostic: **0.666667**;
- local successor MRR@25 diagnostic: **1.000000**.

Those numbers are **not a Kaggle score, leaderboard claim, expected prize,
payment, or revenue**. They only describe the retained synthetic fixture.

## Evidence and failure boundary

The module accepts only exact-schema `dataset_kind="SYNTHETIC"` fixtures.
Inputs use the same conservative family of boundaries as the existing CASMI
workbench: regular-file bounded JSON, duplicate-key rejection, non-finite and
bool-numeric rejection, strict IDs/text, strictly increasing fragments, and
`fragment_mz < precursor_mz`.

It additionally rejects invalid blend weights, duplicate candidate/molecule
identities, absent expected candidates, unsupported SMILES separators/newlines,
and any authority flag set true. All validations are ordinary runtime checks
and remain active under `python -O`.

The result carries a SHA-256 semantic receipt. Verification checks the receipt
and exact recompilation from the fixture; rehashing a forged semantic result
does not make it valid. CLI output publication is create-exclusive.

## Reproduce

```bash
python competitions/enveda_casmi_2026/neutral_loss_consensus.py compile \
  competitions/enveda_casmi_2026/synthetic_neutral_loss_fixture.json \
  /tmp/casmi-neutral-loss.json

python competitions/enveda_casmi_2026/neutral_loss_consensus.py verify \
  competitions/enveda_casmi_2026/synthetic_neutral_loss_fixture.json \
  /tmp/casmi-neutral-loss.json

python test_casmi_neutral_loss_consensus.py
python -O test_casmi_neutral_loss_consensus.py
```

The committed `synthetic_neutral_loss_experiment_receipt.json` must equal a
fresh compile of the committed fixture.

## Authority ceiling

The fixture and result require all of these to remain false: Kaggle account
authority, competition join, rules acceptance, gated download, submission,
team mutation, prize/payment claim, and revenue recognition. The module has no
network/provider action surface.
