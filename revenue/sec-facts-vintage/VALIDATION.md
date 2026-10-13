# Validation receipt

Operation: `FINANCE-SEC-FACTS-VINTAGE-ZCAIRN-20260917`  
Builder: Z-Cairn / GPT-6 Astra Pro  
Environment: cloud Linux runtime, CPython 3.13.5, standard library only. No owner-machine execution, credentials or external provider mutation.

## Executed

From `revenue/sec-facts-vintage`:

- `python -m unittest -v`: **82 tests passed**, 5.235 seconds, exit 0.
- `python -O -m unittest -v`: **82 tests passed**, 3.810 seconds, exit 0.
- `python -m py_compile sec_facts_vintage.py test_sec_facts_vintage.py`: exit 0.
- `python sec_facts_vintage.py compile --source examples/companyfacts.synthetic.json --plan examples/plan.synthetic.json --bundle <new-cloud-directory>`: exit 0; six queries; three CHANGED, one AMBIGUOUS_LATEST, two NO_ELIGIBLE_FACT.
- Corresponding `verify`: exit 0, exact source/plan and all four output members matched recomputation.
- `inventory` on the synthetic fixture: exit 0.
- The suite additionally executes separate normal and actual `python -O` CLI processes and checks all four generated members for byte equality.

The observation-history index test confirms one concept/unit history is parsed only once for multiple requested periods.

## Tested byte identities — SHA-256

| File | SHA-256 |
| --- | --- |
| `sec_facts_vintage.py` | `8f29c893bc0be64101bfbe82cf805dec1e035cb96f4ff63d3483b64d48e2cea1` |
| `test_sec_facts_vintage.py` | `5fc55d79f2e28d4c8cafbee4c65eaf2c9c2d8753eed7bf5e6a6bf982f3d0488f` |
| `examples/companyfacts.synthetic.json` | `b03cb91b23750ea7088782327334871276b5fa859e1f139ebbcd141afb5846b9` |
| `examples/plan.synthetic.json` | `63919e20964c6b65b3a8120fb052c0a09f44221e70aae5dbad1b687fdefc7e4d` |

## Coverage limits

All executed financial observations are synthetic. SEC's official API documentation was read, but a live complete Company Facts payload could not be downloaded through the available web/download runtime. No live-corpus compatibility, vendor authenticity, complete historical coverage, intraday availability, financial correctness, customer acceptance or revenue is inferred from these tests.

Hosted Actions, independent review, current branch head and merge status are reported in the PR conversation, not predeclared here. This file is a local-execution receipt, not a claim that hosted checks passed. Python 3.10–3.12 and non-Linux platforms were not executed in this local run.
