# V218 current-native binding gate

Status: **BLOCKED_AT_NATIVE_ASSEMBLY** for the authenticated swarm native archive used by current V4 component gates. This is not a V218 cold/unreached result and not economics evidence.

`compose_current_v218.py` already proves the exact current router can be transformed by only the two landed V218 legality lines. The missing boundary is later: a real current `main.py::agent` postimage must actually consume that generated router/source. The authenticated native package from workflow artifact 10175943272 does not.

`check_current_native_binding.py` is a read-only fail-closed audit. It scans production package Python/JSON text (excluding `checks/` reference evidence) for an explicit `r04_full_router` / V218 / movement-parity binding and inspects config keys. It does not compose, activate, run games, infer economics, or create a replacement assembler.

Executed against both packaged roots from artifact 10175943272. They agree exactly:

- `main.py` Git blob `4a8cf7bcda1f0fea231a144692cb84a779a9e73e`, SHA-256 `c4c22d0f2b1071cadf6a9f74effccc8cb20ea9f4d10ca1cf9f1fe57351709dc1`
- `titan_runtime.py` Git blob `b952c9c228ecbde592bf3d2df01638677abb0d24`, SHA-256 `da391af2dbdec0f6e4a25749ed539cdd39578ace8861c0e225b5fbfef90d75a8`
- `TITAN-CONFIG.json` Git blob `3a3bef83899d3010fad623b628d9e95d9978111b`
- 65 production `.py`/`.json` files scanned; router refs 0; V218 refs 0; V218 config keys 0
- `--require-wired` exits 3
- 6/6 tests normal and 6/6 under `python -O`

Therefore a router-only official-engine game would not satisfy the requested current-runtime gate: it would bypass the actual authenticated native `main.py::agent`. The next valid input is an exact combined native postimage from the existing single assembler that consumes the #12772 generated router while preserving newer runtime/main/config work. Once such a postimage exists, this checker must return `WIRED_REQUIRES_RUNTIME_GATE`; then run seeds 17/101 in both seats, OFF vs ON, and collect V218 telemetry/economics as originally demanded.

No production/default/archive/Kaggle activation is made here.
