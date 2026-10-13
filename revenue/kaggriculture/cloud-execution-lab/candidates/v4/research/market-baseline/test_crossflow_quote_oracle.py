import math
import unittest

import crossflow_quote_oracle as c


class MiniEngine:
    """Source-faithful two-product subset for isolated oracle tests."""
    PRODUCTS = ["WHEAT", "FERTILIZER"]
    MARKET_PARAMS = {
        "WHEAT": {"base":25,"I0":10000,"T":400,"below_func":"sqrt","below_target":.80,"above_func":"log","above_target":.20},
        "FERTILIZER": {"base":100,"I0":10000,"T":200,"below_func":"linear","below_target":.40,"above_func":"linear","above_target":.40},
    }

    @staticmethod
    def _shape(func, x, T=None):
        x = max(0.0, x)
        if func == "linear": return x
        if func == "sqrt": return math.sqrt(x)
        if func == "log": return math.log(1.0 + x)
        raise ValueError(func)

    @classmethod
    def market_price(cls, item, inventory, params=None):
        p=(params or cls.MARKET_PARAMS)[item]; base=p["base"]; I0=p["I0"]; T=p["T"]
        if inventory < I0:
            f=p["below_func"]; amp=p["below_target"]*base/cls._shape(f,T,T)
            price=base+amp*cls._shape(f,I0-inventory,T)
        else:
            f=p["above_func"]; amp=p["above_target"]*base/cls._shape(f,T,T)
            price=base-amp*cls._shape(f,inventory-I0,T)
        return max(1, int(round(price)))

    @classmethod
    def _new_market(cls):
        return {"inventory": {x:10000 for x in cls.PRODUCTS},
                "prices": {x:cls.MARKET_PARAMS[x]["base"] for x in cls.PRODUCTS}}

    @staticmethod
    def _new_farm(board_size, starting_money):
        return {"money": float(starting_money)}

    @staticmethod
    def _new_private():
        return {"shed": {"WHEAT":0,"FERTILIZER":0}, "seeds":{}, "inventories":[{}]}

    @staticmethod
    def _parse(order):
        if not isinstance(order,list) or len(order)<3: return None
        if order[0] not in ("BUY_PRODUCT","SELL"): return None
        try: n=int(order[2])
        except Exception: return None
        if n<=0: return None
        return {"type":order[0],"item":order[1],"remaining":n}

    @classmethod
    def _process_market(cls, states, env):
        farms=states[0].observation.farms
        privates=[s.observation.private for s in states]
        market=states[0].observation.market
        cap=env.configuration["shedCapacity"]
        rows=[s.action.get("market",[]) for s in states]
        for idx in range(max([len(x) for x in rows]+[0])):
            orders=[cls._parse(rows[p][idx]) if idx<len(rows[p]) else None for p in range(2)]
            while any(x is not None and x["remaining"]>0 for x in orders):
                quoted=[None,None]
                for p in range(2):
                    o=orders[p]
                    if o is None or o["remaining"]<=0: continue
                    item=o["item"]
                    if o["type"]=="SELL":
                        quoted[p]=("SELL",item,cls.market_price(item,market["inventory"][item]),o)
                    elif o["type"]=="BUY_PRODUCT" and item in c.BUYABLE:
                        quoted[p]=("BUY_PRODUCT",item,cls.market_price(item,market["inventory"][item]-1),o)
                    else:
                        orders[p]=None
                if all(q is None for q in quoted): break
                committed=False
                for p,q in enumerate(quoted):
                    if q is None: continue
                    op,item,price,o=q
                    if op=="SELL":
                        if privates[p]["shed"].get(item,0)<=0:
                            orders[p]=None; continue
                        privates[p]["shed"][item]-=1; farms[p]["money"]+=price
                        if price>1: market["inventory"][item]+=1
                    else:
                        if farms[p]["money"]<price or sum(privates[p]["shed"].values())>=cap:
                            orders[p]=None; continue
                        farms[p]["money"]-=price
                        privates[p]["shed"][item]=privates[p]["shed"].get(item,0)+1
                        market["inventory"][item]-=1
                    o["remaining"]-=1; committed=True
                if not committed: break


class CrossflowTests(unittest.TestCase):
    E = MiniEngine

    def test_wheat_default_100_exact(self):
        r=c.compare(self.E,item="WHEAT",quantity=100,inventory=10000)
        self.assertTrue(r["clean_same_terminal_quote_theorem"])
        self.assertEqual(r["buyer"]["aligned_cost"],2600)
        self.assertEqual(r["buyer"]["delayed_cost"],2193)
        self.assertEqual(r["buyer"]["saving_by_waiting_for_supply"],407)
        self.assertEqual(r["seller"]["aligned_revenue"],2500)
        self.assertEqual(r["seller"]["delayed_revenue"],3170)
        self.assertEqual(r["seller"]["gain_by_waiting_for_demand"],670)

    def test_fert_default_100_exact(self):
        r=c.compare(self.E,item="FERTILIZER",quantity=100,inventory=10000)
        self.assertTrue(r["clean_same_terminal_quote_theorem"])
        self.assertEqual(r["buyer"]["aligned_cost"],10000)
        self.assertEqual(r["buyer"]["delayed_cost"],9010)
        self.assertEqual(r["buyer"]["saving_by_waiting_for_supply"],990)
        self.assertEqual(r["seller"]["aligned_revenue"],10000)
        self.assertEqual(r["seller"]["delayed_revenue"],11010)
        self.assertEqual(r["seller"]["gain_by_waiting_for_demand"],1010)

    def test_single_unit_wheat_moves_both_sides_one_dollar(self):
        r=c.compare(self.E,item="WHEAT",quantity=1,inventory=10000)
        self.assertEqual(r["buyer"]["saving_by_waiting_for_supply"],1)
        self.assertEqual(r["seller"]["gain_by_waiting_for_demand"],1)

    def test_fert_single_unit_rounds_to_null(self):
        r=c.compare(self.E,item="FERTILIZER",quantity=1,inventory=10000)
        self.assertEqual(r["buyer"]["saving_by_waiting_for_supply"],0)
        self.assertEqual(r["seller"]["gain_by_waiting_for_demand"],0)

    def test_floor_boundary_refuses_clean_theorem(self):
        r=c.compare(self.E,item="FERTILIZER",quantity=100,inventory=10493)
        self.assertFalse(r["clean_same_terminal_quote_theorem"])
        self.assertFalse(r["buyer"]["same_terminal_inventory"] and r["seller"]["same_terminal_inventory"])

    def test_exact_checkout_engine_if_present(self):
        try:
            path=c.default_engine_path()
        except FileNotFoundError:
            self.skipTest("repository checkout not present")
        if not path.exists():
            self.skipTest("repository checkout not present")
        engine=c.load_engine(path)
        wheat=c.compare(engine,item="WHEAT",quantity=100,inventory=10000)
        fert=c.compare(engine,item="FERTILIZER",quantity=100,inventory=10000)
        self.assertEqual(wheat["buyer"]["saving_by_waiting_for_supply"],407)
        self.assertEqual(wheat["seller"]["gain_by_waiting_for_demand"],670)
        self.assertEqual(fert["buyer"]["saving_by_waiting_for_supply"],990)
        self.assertEqual(fert["seller"]["gain_by_waiting_for_demand"],1010)

    def test_quantity_over_capacity_refused(self):
        with self.assertRaises(ValueError): c.compare(self.E,item="WHEAT",quantity=101)

    def test_bool_quantity_refused(self):
        with self.assertRaises(ValueError): c.compare(self.E,item="WHEAT",quantity=True)

    def test_negative_inventory_refused(self):
        with self.assertRaises(ValueError): c.compare(self.E,item="WHEAT",quantity=1,inventory=-1)

    def test_nonbuyable_item_refused(self):
        with self.assertRaises(ValueError): c.compare(self.E,item="MILK",quantity=1)

    def test_delayed_buyer_preserves_quantity(self):
        r=c.buyer_waits_for_rival_supply(self.E,item="WHEAT",quantity=37,inventory=10000,delayed=True)
        self.assertEqual(r["buyer_shed"],37)
        self.assertEqual(r["rival_shed"],0)

    def test_delayed_seller_preserves_quantity(self):
        r=c.seller_waits_for_rival_demand(self.E,item="FERTILIZER",quantity=37,inventory=10000,delayed=True)
        self.assertEqual(r["seller_shed"],0)
        self.assertEqual(r["rival_shed"],37)


if __name__ == "__main__":
    unittest.main()
