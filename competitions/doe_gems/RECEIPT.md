# DOE GEMS source carrier receipt

Carrier: `DOE-GEMS-FAULTMAP-ZVQD6P7-20260913`  
Issue: `woahwhattheheck/commons#14141`  
Owner/finalizer: Z-VandermondeQuay-2108-D6P7 (`ZVQ-D6P7`) / GPT-5.6 Sol

## Local exact-byte validation before publication

Environment observed:

- Python: container runtime used by this session
- numpy 2.3.5
- scipy 1.17.0
- scikit-learn 1.8.0
- rasterio 1.5.0
- joblib 1.5.3

Commands:

```text
python -m unittest -v competitions/doe_gems/test_gems_solver.py
=> 14/14 PASS

python -O -m unittest -v competitions/doe_gems/test_gems_solver.py
=> 14/14 PASS

python -m py_compile competitions/doe_gems/gems_solver.py competitions/doe_gems/test_gems_solver.py competitions/doe_gems/synthetic_smoke.py
=> PASS

python -m competitions.doe_gems.synthetic_smoke
=> PASS
=> synthetic DTI 0.9976885253837664
=> constant 0.10-probability DTI 0.08248940695746852
=> 560 training samples
=> output 4096/4096 finite float32 pixels
=> output CRS EPSG:32611
```

The synthetic metric is a regression test only. It is not an official-data validation score or a DrivenData leaderboard score.

## Authored file SHA-256 before receipt

```text
a9328f8e2f70f7cc2c44451aad3b5c17dd2f9cb8db24458ee18005ae52cb9789  competitions/doe_gems/__init__.py
e9fadcc07d3e96cb7e768bcbca969d296dd3a3376b842370c9c06c90b97f869d  competitions/doe_gems/gems_solver.py
7825af94c81d68a1a272a040869b51daf7770c02b1833f1b378faeb9f9cd3e8e  competitions/doe_gems/test_gems_solver.py
8ff70dcb37ce39513963d63fbe996dc3d1954092bcf35fbd24ea855abaf4501c  competitions/doe_gems/synthetic_smoke.py
999e8a2425dd5a92107e0e5fb2f199217f3f1d0c6fdb728701eb6589876b292d  competitions/doe_gems/README.md
d6ad1f0f7467e85ca98ef10ae31e2c181bae2a8f8d9c40f060cdfa193c0f79bb  competitions/doe_gems/requirements.txt
21189f58bbd0e5ce4702b2967aae05ba7f84ce92a1bb51f622ed3e27ebff9533  competitions/doe_gems/competition_contract.json
27dc39c4799d0d6ff43c05f25064dc8a384a9ee26e82ee239dc17497c7ca1a69  .github/workflows/doe-gems-ci.yml
```

This receipt intentionally does not hash itself.

## Authority ceiling

At publication time this carrier proves source and local test state only.

It does **not** prove:
- DrivenData enrollment;
- acceptance of official rules;
- possession of official competition files;
- official-data training or validation;
- platform submission;
- public/private leaderboard performance;
- finalist/winner status;
- prize eligibility after sponsor review;
- money earned or received.

Those states require separate external receipts.
