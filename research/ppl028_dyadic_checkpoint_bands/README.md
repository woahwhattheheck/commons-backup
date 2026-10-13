# PPL028 dyadic checkpoint bands

Exact joint height-band navigation for seeds x=1+2^475*t, 1<=t<=10^500, consuming the saved nine-map affine blocks from [Commons #31444](https://github.com/woahwhattheheck/commons/pull/31444).

Read [DYADIC_CHECKPOINT_BANDS_API.md](DYADIC_CHECKPOINT_BANDS_API.md) for source attribution, the inherited-input boundary, exact band conventions and the API. Load certificate.json with createReader from checkpoint_bands.cjs; rerunning the constructor is unnecessary for queries.

The new result contains 30 cells and 30 threshold records for checkpoint times 1,2,4,8,16,32,64,128,256 plus the initial coordinate. Thresholds are 10^200,10^400,10^600. The first actual consumer retained 129 responses, 23 selections with both parameter/seed inverses matching, twelve condition caches, six state queries and three marginal tables.

Counts and ranks are over numeric parameters, equivalently seeds. The first qualifying checkpoint is restricted to the saved dyadic times; the initial coordinate requires an explicit option. The checkpoint peak covers only ten selected coordinates. No orbit extension, old-anchor recomputation, valuation or block-composition work was performed. This does not establish divergence or a prize solution.

Public native checkpoint locators are in public_checkpoints.json. Full construction and reader data are present in this directory.
