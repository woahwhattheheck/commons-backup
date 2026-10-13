# Pure-S bounded rewrite-history navigator

[PURE_S_HISTORIES_API.md](PURE_S_HISTORIES_API.md) defines the finite model, counting proof, occurrence-address ordering and source limits. The one constructor covers all 429 closed eight-leaf pure-S roots with horizon six and retained leaf cap twelve. Normal forms, horizon stops and leaf-limit exits remain separate.

The complete certificate has 1,321 counted states and is preserved in five raw certificate_part_*.jsonpart files. certificate_manifest.json identifies their order and exact whole bytes; assemble_certificate.cjs joins supplied part texts. Load the assembled object with createReader in pure_s_histories.cjs.

saved_reader.json contains all 202 actual responses, 63 successful inverse checks and complete caches/work. reader_plan.json and reader_consumer.cjs specify the fresh saved-data consumer, with zero new contractions, redex searches or coefficient generation.

input.json, construction_plan.json and SOURCE_QUALIFICATION.md bind the exact scope. public_checkpoints.json records acknowledged public stages. The official S-universality challenge requires a full proof; finite cutoffs here do not certify divergence or resolve that challenge. No published example or accepted computation was replayed.
