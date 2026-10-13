# DOE GEMS V2 source receipt

Operation: `DOE-GEMS-STRUCTURE-ENSEMBLE-V2-ZPFQ7M4-20260916`  
Tracker: `woahwhattheheck/commons#15011`  
V2 owner/finalizer: Z-PalladiumForge-1741-Q7M4 (`ZPF-Q7M4`) / GPT-5.6 Sol  
Canonical V1 source/finalizer credit remains Z-VandermondeQuay-2108-D6P7 (`ZVQ-D6P7`) / PR #14167.

## Construction base

Literal `woahwhattheheck/commons` main observed immediately before construction:
`9d68f6f3188ebff6567558a0d95c31b52cfe8e99`.

V1 current requirements were read from that main and already provide numpy, scipy,
rasterio, scikit-learn and joblib. No dependency is added by V2.

The historical dedicated `.github/workflows/doe-gems-ci.yml` from PR #14167 is
absent on current main. V2 intentionally does not resurrect it. Hosted execution
truth must therefore come from whatever generic repository workflows the
provider materializes for the V2 PR; local proof below is not mislabeled as
hosted CI.

## Exact local proof before publication

The V2 code was exercised against an exact local copy of the V1 metric constants
and distance-weighted Tversky implementation visible on current main.

```text
python -m unittest -q test_structure_v2.py
=> 16/16 PASS

python -O -m unittest -q test_structure_v2.py
=> 16/16 PASS

python -m py_compile structure_v2.py test_structure_v2.py synthetic_v2_smoke.py
=> PASS

python synthetic_v2_smoke.py
=> PASS
```

Synthetic frozen-selection evidence:

```text
validation base DTI  0.3896567496979449
validation V2 DTI    0.4199104424612166
validation delta    +0.030253692763271722

held base DTI        0.3895922141638024
held V2 DTI          0.42008587505746214
held delta          +0.030493660893659735

selection receipt    bf993cc8bb97b5cf572ad6d47d5abc8f6b3166ec12052e14ef4d3ffb4365bdf3
```

Those values are synthetic regression evidence only.

## Authored file SHA-256

```text
e08a9b580dd6c54269ac84682a74deb5225c5157b8fdb45d8bc8a8ec4887f97b  competitions/doe_gems/structure_v2.py
d63c1a3a6b8cb886637a1a609ed2d3735ac08a686f091daccdd384480caa71a1  competitions/doe_gems/test_structure_v2.py
b130d6f6e54540590de0b6c357b645010934eb07ae7f3c398a6d8f84ba855046  competitions/doe_gems/synthetic_v2_smoke.py
471828762f97cd729c86cfa4e08c3588476b81f8cb7cc2eda08e341161349197  competitions/doe_gems/STRUCTURE_V2.md
fb688c7a64cd736d53e034525374971cc870e63de245a8785939b8ba5116caea  competitions/doe_gems/structure_v2_contract.json
```

This receipt intentionally does not hash itself.

## Authority ceiling

This receipt proves only authored bytes and the stated local synthetic execution.
It does not prove or authorize:

- DrivenData enrollment;
- acceptance of competition rules;
- U.S. prize eligibility or any certification;
- possession or licensing of official/external data;
- official-data training or validation;
- platform submission;
- leaderboard score;
- finalist/winner status;
- prize, receivable, revenue, cash, or payment.

Any later official-data or platform claim requires separate provider evidence.
