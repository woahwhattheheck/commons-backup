# Diversey 2026 requirement / evidence matrix

Official challenge: https://www.innocentive.com/challenges/novel-technologies-for-rapid-proof-of-clean-in-professional-environments/

Status vocabulary:
- **PUBLISHED PRECEDENT** — demonstrated by cited third-party work, not by this project.
- **DESIGN TARGET** — proposed requirement for an integrated prototype; not measured.
- **OPEN** — requires experiments, partner input, or human/legal review.

| Challenge requirement | Proposed response | Evidence / rationale | Current status |
|---|---|---|---|
| Credible method of verifying cleanliness | Standardized surface wipe + phage-derived RBP capture + electrochemical readout with control lanes | RBP/phage electrochemical sensors have detected Salmonella and E. coli with species-selective response | PUBLISHED PRECEDENT; integrated workflow OPEN |
| Result in <30 minutes | Target workflow budget: sample 5 min, capture/reaction 10 min, electrochemical read 5 min, QC/report 2 min, contingency 3 min; **target ≤25 min** | Published examples report ~30 min Salmonella RBP-DPV, 15 min E. coli phage sensor, and <30 min E. coli O157:H7 phage sensor | PUBLISHED PRECEDENT for components; DESIGN TARGET for cartridge |
| Professional cleaning environments | Handheld reader + sealed disposable cartridge + wipe/elution consumable; no open culture step | Architecture is compatible in principle with kitchens, food facilities and healthcare/facility workflows | DESIGN TARGET; field ergonomics OPEN |
| Basic training | Guided sample timer, keyed cartridge, control-lane pass/fail, single result screen | Reduces interpretation to explicit QC and target-lane states | DESIGN TARGET; usability OPEN |
| No laboratory / prohibitively expensive equipment | Portable potentiostat/readout and disposable electrodes; no incubator/culture/PCR instrument in proposed workflow | Electrochemical transduction is portable in principle; published sensors use electrode-based DPV/EIS | PUBLISHED PRECEDENT; BOM/cost OPEN |
| Distinguish clean vs contaminated | Negative/control lanes establish valid baseline; target lanes exceeding validated decision threshold flag contamination | Electrochemical signal changes have been correlated with target-bacteria binding in published sensors | PUBLISHED PRECEDENT; threshold OPEN and must be experimentally calibrated |
| Explain scientific principle | Phage RBPs recognize bacterial surface receptors; target binding changes interfacial electron transfer/impedance or pulse-voltammetry response | See `SCIENTIFIC-BASIS.md` and cited primary literature | PUBLISHED PRECEDENT |
| Meaningful differentiation from ATP | Organism-specific biorecognition rather than total biological residue proxy; control-lane QC; proposed digital provenance | ATP does not identify organisms; RBP recognition can be species-selective | PRINCIPLE supported; product comparison testing OPEN |
| Supported by evidence / rationale | Primary literature is cited; no internal wet-lab data is claimed | See source list | PUBLISHED PRECEDENT |
| Species-level identification (nice to have) | Separate RBP lanes selected for target organisms | Published RBP/phage examples demonstrate selective Salmonella, E. coli, Campylobacter, Pseudomonas and others | PUBLISHED PRECEDENT; final panel OPEN |
| Strain-level identification (nice to have) | Only if validated RBP selectivity supports it; otherwise explicitly out of claim set | Host-range specificity can vary by phage/RBP | OPEN; **not promised** |
| Portable / field deployable | Battery-powered reader and sealed disposable cartridge | Feasible architecture, not yet engineered | DESIGN TARGET |
| Non-destructive | Surface wipe is minimally invasive; cartridge contains assay | Proposed workflow does not require altering room infrastructure | DESIGN TARGET |
| Low consumable cost | Screen-printed or similarly manufacturable electrodes; recombinant recognition proteins | Cost model not yet established | OPEN |
| Existing workflow integration | Sample ID, location, operator, cartridge lot, calibration ID, raw signal and human disposition retained in an audit record | Commons can implement software provenance, but this is not evidence of biosensor performance | SOFTWARE CAPABILITY plausible; integration OPEN |
| Digital reporting / audit trail | Reader exports signed/hashed result envelope to an append-only review queue; invalid controls block release | Directly aligned with Commons' evidence/provenance engineering patterns | DESIGN TARGET; device integration OPEN |

## Published scientific precedents

1. Ding Y, et al. **An electrochemical biosensor based on phage-encoded protein RBP 41 for rapid and sensitive detection of Salmonella.** *Talanta* 270 (2024) 125561. DOI: https://doi.org/10.1016/j.talanta.2023.125561 — reports RBP 41 / graphene oxide / gold nanoparticle electrode detection within approximately 30 minutes and species-selective performance in food matrices.
2. **Rapid electrochemical detection of Escherichia coli in milk using an oriented phage-based biosensor.** PubMed: https://pubmed.ncbi.nlm.nih.gov/42107219/ — reports 15-minute detection in PBS and milk, with substantially lower response to non-host *S. aureus*.
3. **Development of a phage-based electrochemical biosensor for detection of Escherichia coli O157:H7 GXEC-N07.** PubMed: https://pubmed.ncbi.nlm.nih.gov/36495704/ — reports a full detection process in under 30 minutes in food matrices.
4. **A Bacteriophage Protein-Based Impedimetric Electrochemical Biosensor for the Detection of Campylobacter jejuni.** PubMed: https://pubmed.ncbi.nlm.nih.gov/39194631/ — reports a genetically engineered phage receptor-binding protein used as an EIS bioreceptor with non-target specificity controls.
5. **Potential of bacteriophage proteins as recognition molecules for pathogen detection.** PubMed: https://pubmed.ncbi.nlm.nih.gov/35848817/ — review of RBP/cell-wall-binding-domain specificity, stability, engineering and use in electrochemical/optical detection.

## Non-transferability rule

None of the detection limits, response times, sensitivities, specificities or matrix results above may be represented as measured performance of the proposed CleanTrace cartridge. They justify scientific feasibility and experiment design only. The final proposal must label integrated-system figures as targets until this exact architecture is experimentally tested.

## Explicit out-of-scope claims

The present concept does not rely on ATP swabbing, conventional culture, PCR, hyperspectral imaging, or standard fluorescence cleanliness testing. It does not claim whole-room assessment. A future two-stage system could add a distinct large-area screening method, but that is not needed for this submission and must not be invented merely to satisfy a nice-to-have.