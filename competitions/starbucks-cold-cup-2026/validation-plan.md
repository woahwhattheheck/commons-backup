# Validation and scale plan

The program is designed to fail cheaply and early. No downstream success can erase a failed hard gate.

## Phase A — optical/process kill screen

Freeze analytical methods before looking at results.

Candidate variables:
- CNF/chitosan dry ratio: e.g. 90/10, 80/20, 75/25.
- CNF solids/fibrillation window.
- densification pressure/temperature.
- shellac add-on: 0, low, medium; target the minimum continuous barrier.
- process order: coat-flat-then-form vs form-then-coat.
- optional citric-acid condition only after baseline failure.

Measurements:
1. ASTM D1003 total transmittance and haze, n>=5 per condition.
2. thickness and surface roughness.
3. dry/wet tensile and swelling.
4. color/yellowness and odor screen.

**Hard exit:** no candidate proceeds if representative final-thickness material exceeds 5% haze.

## Phase B — 24 h wet-service screen

Condition at relevant humidity. Use ice-water fill and closed-loop gravimetric leak detection.

Measure:
- leak/no leak over 24 h;
- mass uptake;
- diameter/height/rim dimensional change;
- top-load/lid-application compression before and after exposure;
- coating defects by microscopy.

Define pass thresholds prospectively with Starbucks/packaging engineer; do not retrofit thresholds after data.

## Phase C — formed cup/lid performance

Use representative commercial forming geometry and final coating order.

Tests:
- repeated lid application;
- espresso-shot heat pulse followed by dimensional/creep measurement;
- filled 1 m drop at controlled orientations, with sample size and crack/leak endpoint frozen in advance;
- rim/corner haze after forming;
- thermal cycling and cold condensation;
- blinded organoleptic screen.

## Phase D — chemical/regulatory gate

On the exact surviving formulation:
- supplier SDS/CoA and traceability;
- targeted analytical evidence for the challenge's prohibited substances;
- regulatory expert assessment of all ingredients/process aids and intended conditions of use;
- migration/testing plan appropriate to the resulting regulatory route;
- no “FDA/NOL compliant” claim until documented.

## Phase E — compostability

Request BPI eligibility/test-scheme review on the final article. Execute the required ASTM route (including D8410 when applicable) plus BPI fluorine/PFAS and formulation documentation requirements. Home compostability is a later preference target, not assumed.

## Phase F — scale + LCA

Pilot mass balance:
- kg dry CNF/chitosan/shellac per 1,000 articles;
- water input/recovery;
- electricity for fibrillation/dewatering/drying/pressing;
- coating solvent input/recovery;
- scrap/yield;
- cycle time/line rate;
- supplier production capacity and geographic concentration.

Then conduct comparative LCA for at least challenge categories GHG, fossil-fuel use and water use using measured pilot data. Natural origin is not a substitute for LCA.

## Decision rule

`readiness_gate.py` requires evidence references for every hard release item. The checked-in `readiness.json` is intentionally BLOCKED. A future operator may populate it only with real evidence; the gate never manufactures or infers test results.
