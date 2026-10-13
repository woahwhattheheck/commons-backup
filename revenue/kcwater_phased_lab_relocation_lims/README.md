# KC Water phased laboratory relocation LIMS

Demand: `kcwater-phased-lab-relocation-lims-01`

This pack points to the root synthetic accession and instrument-routing
engine:

```sh
python kcwater_phased_lab_relocation_lims.py
python test_kcwater_phased_lab_relocation_lims.py
```

The frozen fixture has 300 de-identified synthetic drinking-water,
wastewater, and stormwater submissions. It creates exactly 240 `READY`
accessions, tests, results, and staged reports. It puts exactly 60
predetermined rows on `HOLD`: 20 duplicate containers, 20 site/method-scope
mismatches, and 20 custody/temperature failures.

Every valid test binds one active main, temporary, or contingency site and
instrument route. The result, accession, test, and staged report retain
matching site, source, value, unit, qualifier, method, and result hashes.
Replay adds no records; changed payloads conflict by digest. Release rejects
automation and unregistered claims, and permits only the authoritative
synthetic named-human directory entry.

HOLD / BUILD-AND-VERIFY. Synthetic/read-only. No live LIMS, public-health or
diagnostic decision, customer data, production write, outreach, spend, or
automatic report release. PRE-SALE TRANSPORT: NONE.
