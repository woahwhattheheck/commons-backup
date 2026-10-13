# S12 top-ten replay diagnostics

Worker: TITAN V3 build on grok.com. Archive titan-current.tar.gz SHA256 f8f1750266b3cfaea0ebfe663f287aa9c5a2682f6fc47bc932957e1d48e63f1c left for Bryce. No Kaggle submit.

## Commands

```
git clone --filter=blob:none --sparse https://github.com/woahwhattheheck/commons.git
git checkout d56c11b0199d3fcf7820922023a3aa8d98370888
sha256sum revenue/kaggriculture/cloud-execution-lab/exports/titan-current.tar.gz
curl -L https://www.kaggleusercontent.com/episodes/<id>.json
python3 replay_parser.py
python3 run_titan_vs_leaders.py
```

Engine kaggle-environments==1.32.7. configuration.seed is null. Real seed is info.seed.

## Episode table

episode seed teams rewards
106803087 1794679920 Ad Space Available / Matthew Huang 107361 / 106341
106817281 2019828667 Otter Vibe / SpaTaro 142805 / 142496
107140666 1834999074 cununn / Bryce Muhlnickel 73254 / 76855
107141420 1302127459 insuperabilehart / Bryce Muhlnickel 106032 / 99504
107141525 1085071695 Christoffer Thimsen / Bryce Muhlnickel 93818 / 103089
107142511 194298392 darktetradgod / Bryce Muhlnickel 90661 / 88992
107143501 1310872300 Bryce Muhlnickel / JunWenZhu_1314 64845 / 59643
107143991 1210667910 NoMoreThan20Words / Bryce Muhlnickel 137020 / 133443
107144448 440118348 Bryce Muhlnickel / Esperanza 87053 / 82970
107144556 722644645 John Park / Bryce Muhlnickel 117424 / 128750
107145457 1668671837 Bryce Muhlnickel / skyShenzi5822 88367 / 70305
107146665 1716198739 Mark / Bryce Muhlnickel 94189 / 97956
107147632 200612102 Bryce Muhlnickel / Nadeem Ishikawa 101877 / 98531
107148422 533108679 Bryce Muhlnickel / TTANE 79662 / 79078
107149385 345423202 Bryce Muhlnickel / insuperabilehart 110190 / 116024
107150217 136270408 saitamad / Bryce Muhlnickel 96283 / 93095
107151335 945969299 qiwaki / Bryce Muhlnickel 92099 / 102414
107152257 1537203877 phi / Bryce Muhlnickel 87285 / 88352
107153287 61852159 ymok / Bryce Muhlnickel 87259 / 89508
107162106 1885507524 ominteam / Bryce Muhlnickel 113600 / 116284
107172662 65112964 Gappy / Bryce Muhlnickel 124307 / 136971

## TITAN vs leaders (posted-order diagnostic, not CF cash)

exact action match 8/2160
div_hire 1177
div_land 13
div_plant 800
div_water 2652
div_feed 1477
div_harvest 1436
div_market 1845
div_pass 7315

## Invisible

Replay has no fill receipts. Posted SELL/BUY is not a realized fill.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
