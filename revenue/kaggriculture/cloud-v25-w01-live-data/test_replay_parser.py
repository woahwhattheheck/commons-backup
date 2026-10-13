# SPDX-License-Identifier: Apache-2.0
import gzip,json,tempfile,unittest
from pathlib import Path
import replay_parser

PRODUCTS = replay_parser.PRODUCTS
ANIMALS = replay_parser.ANIMALS
CROPS = replay_parser.CROPS

def obs(step, seat, *, own_money, own_wheat, rival_money):
    farms=[{'money':rival_money,'hires_today':0,'unlocked_quadrants':1,'farmer':[0,0],'hands':[],'tiles':[[None]]},
           {'money':rival_money,'hires_today':0,'unlocked_quadrants':1,'farmer':[0,0],'hands':[],'tiles':[[None]]}]
    farms[seat]={'money':own_money,'hires_today':0,'unlocked_quadrants':1,'farmer':[0,0],'hands':[],'tiles':[[None]]}
    return {'day':0,'hour':step,'player':seat,'remainingOverageTime':60,'farms':farms,
            'market':{'prices':{k:1 for k in PRODUCTS},'inventory':{k:10000 for k in PRODUCTS}},
            'private':{'shed':{**{k:0 for k in PRODUCTS+ANIMALS},'WHEAT':own_wheat},
                       'seeds':{k:0 for k in CROPS},'inventories':[{}]}}

def replay():
    seat=0
    return {'configuration':{'seed':None},'info':{'EpisodeId':123,'seed':456,'TeamNames':['Bryce Muhlnickel','rival']},
            'rewards':[10,9],'statuses':['DONE','DONE'],'module_version':'1.32.7',
            'steps':[
             [{'action':{'farmer':['PASS'],'hands':[],'market':[]},'observation':obs(0,seat,own_money=30,own_wheat=0,rival_money=30),'status':'ACTIVE','reward':0},
              {'action':{'farmer':['PASS'],'hands':[],'market':[]},'observation':obs(0,1,own_money=30,own_wheat=0,rival_money=30),'status':'ACTIVE','reward':0}],
             [{'action':{'farmer':['PASS'],'hands':[],'market':[['BUY_PRODUCT','WHEAT',13]]},'observation':obs(1,seat,own_money=17,own_wheat=13,rival_money=30),'status':'DONE','reward':10},
              {'action':{'farmer':['PASS'],'hands':[],'market':[]},'observation':obs(1,1,own_money=30,own_wheat=0,rival_money=17),'status':'DONE','reward':9}],
            ]}

class ParserTests(unittest.TestCase):
    def test_causal_pre_action_post(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'r.json.gz'; p.write_bytes(gzip.compress(json.dumps(replay()).encode()))
            idx,rows=replay_parser.parse(p)
        self.assertEqual(idx['episode_id'],123); self.assertEqual(idx['info_seed'],456); self.assertEqual(idx['own_seat'],0)
        self.assertEqual(idx['configuration_seed'],None); self.assertEqual(idx['result'],'WIN')
        self.assertEqual(len(rows),1); row=rows[0]
        self.assertEqual(row['own_pre']['money'],30); self.assertEqual(row['own_post']['money'],17)
        self.assertEqual(row['own_private_post']['shed']['WHEAT'],13)
        self.assertEqual(row['action']['market'],[['BUY_PRODUCT','WHEAT',13]])
    def test_no_rival_private_field(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'r.json.gz'; p.write_bytes(gzip.compress(json.dumps(replay()).encode()))
            _,rows=replay_parser.parse(p)
        self.assertNotIn('rival_private',rows[0]); self.assertIn('rival_post_public',rows[0])
    def test_requires_own_team(self):
        d=replay(); d['info']['TeamNames']=['a','b']
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'r.json.gz'; p.write_bytes(gzip.compress(json.dumps(d).encode()))
            with self.assertRaises(ValueError): replay_parser.parse(p)

if __name__=='__main__': unittest.main()
