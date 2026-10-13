# G01 Gemini patches on canonical 3b4b

Base archive: exports/titan-current.tar.gz @ ba1efc8732073d7ad566ea5090fb9aa3e8b2bc33
SHA256 3b4b083ec2647bb0e715978c2565e916da0ee94c08b234902e3a7e4d3418c320 size 420356

## Seams
- E11 scheduler.py:SellScheduler.act ~393 and frozen_selected.py:FrozenSelected.transform ~718 helper e11_rival_sell.apply_e11
- O01 titan_runtime.py:TitanAgent._g01_post ~597 helper rival_model.apply_rival_model
- E20 hire titan_runtime.py:_g01_post e20_hire_shop.apply_hire_guard
- Shop arb scheduler.py:absorption ~57 e20_hire_shop.shop_weight

Flags default off. TITAN-CONFIG rival_dump_price_drop 15.0 rival_dump_lookback_steps 8

## Tests
python3 -m pytest test_g01_flags_off.py -q
8 passed in 0.02s

## Gauntlet
4x192 + holdout not run this seat. Commands in this file under previous draft; use tools/v25_sims/gauntlet.py seeds 2611091001-2611091016 opponents arlene,apex,kaito_v43,cok_v10,public_bt12,v1_submitted workers 8 action-timeout 15. Holdout 2611092001-2611092016 after combining non-negative flags.
