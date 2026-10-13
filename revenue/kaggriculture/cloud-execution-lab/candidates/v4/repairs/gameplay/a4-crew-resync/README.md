# A4 crew-resync donor preservation

Status: exact V3.1 donor custody only; not current-production activation.

Recovered from commit `7f244af80fb2b770f270a333759f8d1d188753ef`.

- `a4_second_melons.py` is exact Git blob `0db2ab44d468f42a6a25e12853dd3e8f8d577b12`.
- `test_v3_a4_second_melons.py` is exact Git blob `076ce69a9355616b404d1395a6cf840cfadbb667`.
- The reviewed repair tracks the crew tuple used to build queues and rebuilds when crew membership changes mid-day, preventing a late second hire from remaining queue-less.
- Original receipt: 26 A4 tests; materialized V3 suite 133/133; `build_v3.py --check` OK.

The source also carries old A4 melon economics. Per `candidates/v4/CANONICAL.json`, preserve these bytes and provenance before any semantic port. Do not execute the legacy materializer against the current production ABI. A current-ABI port should extract/revalidate the crew-queue ownership theorem separately and remain default-OFF until its evidence gate passes.
