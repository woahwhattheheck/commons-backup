import base64
import json
import unittest
import zlib

import land_staging_oracle as m


def engine_fixture():
    return """
FARMER_MOVES={'NORTH':(0,-1),'SOUTH':(0,1),'EAST':(1,0),'WEST':(-1,0)}
LAND_ORDER=['NE','SW','SE']
LAND_PRICES=[1000,2000,4000]
def _quadrant_of(x,y,board_size):
    half=board_size//2
    return ('N' if y<half else 'S')+('W' if x<half else 'E')
def _shed_access_tiles(board_size):
    half=board_size//2
    return [(half-1,half-1),(half,half-1),(half-1,half),(half,half)]
def _default_spawn(board_size):
    for tile in _shed_access_tiles(board_size):
        if _quadrant_of(tile[0],tile[1],board_size)=='NW':
            return tile
    return (0,0)
def _farmer_position(farm,idx):
    if idx==0:return farm['farmer']
    return farm['hands'][idx-1] if idx-1<len(farm['hands']) else None
def _set_farmer_position(farm,idx,pos):
    if idx==0:farm['farmer']=list(pos)
    else:farm['hands'][idx-1]=list(pos)
def _farmer_inventory(private,idx):
    while len(private['inventories'])<=idx:private['inventories'].append({})
    return private['inventories'][idx]
def _apply_unit_action(farm,private,idx,action,board_size,day,turns_per_day,shed_capacity=100):
    if not isinstance(action,list) or not action:return
    op=action[0];pos=_farmer_position(farm,idx)
    if pos is None:return
    fx,fy=pos;inv=_farmer_inventory(private,idx)
    if op in FARMER_MOVES:
        dx,dy=FARMER_MOVES[op];nx,ny=fx+dx,fy+dy
        if not (0<=nx<board_size and 0<=ny<board_size):return
        _set_farmer_position(farm,idx,(nx,ny));return
def _spawn_hand(farm,board_size):
    occupants={tile:0 for tile in _shed_access_tiles(board_size)}
    all_pos=[tuple(farm['farmer'])]+[tuple(p) for p in farm['hands']]
    for pos in all_pos:
        if pos in occupants:occupants[pos]+=1
    best=sorted(occupants.items(),key=lambda kv:(kv[1],_shed_access_tiles(board_size).index(kv[0])))
    return list(best[0][0])
def _do_buy_land(farm,board_size):
    n=len(farm['unlocked_quadrants'])-1
    if n>=len(LAND_ORDER):return
    cost=LAND_PRICES[n]
    if farm['money']<cost:return
    farm['money']-=cost;quadrant=LAND_ORDER[n];farm['unlocked_quadrants'].append(quadrant)
    for y in range(board_size):
        for x in range(board_size):
            if _quadrant_of(x,y,board_size)==quadrant and farm['tiles'][y][x]=='LOCKED':
                farm['tiles'][y][x]=None
def _process_market(state,env):
    return None
def interpreter(state,env):
    for i,s in enumerate(state):
        _apply_unit_action({}, {}, 0, ['PASS'], 10, 0, 24, 100)
        for h_idx in []:
            _apply_unit_action({}, {}, h_idx+1, ['PASS'], 10, 0, 24, 100)
    _process_market(state,env)
"""


def arlene_fixture():
    payload={
        'main':'main',
        'full':[{'farmer':['PASS'],'hands':[],'market':[]}],
        'tails':[
            {'h':'tail','parent':'main','at':1,'suffix':[{'market':[['HIRE']]}]}
        ],
    }
    blob=base64.b64encode(zlib.compress(json.dumps(payload).encode())).decode()
    return f"_BLOB={blob!r}\n"


class TestLandStaging(unittest.TestCase):
    def test_engine_theorem(self):
        p=m.prove_engine(engine_fixture())
        self.assertTrue(p['unit_before_market'])
        self.assertEqual(p['locked_transit_probe']['end'],[5,4])
        self.assertEqual(p['first_three_hire_spawns'],[[5,4],[4,5],[5,5]])

    def test_geometry(self):
        g=m.geometry()
        self.assertEqual(g['future_quadrant_distances']['NE']['min_moves_from_default_spawn'],1)
        self.assertEqual(g['future_quadrant_distances']['SW']['min_moves_from_default_spawn'],1)
        self.assertEqual(g['future_quadrant_distances']['SE']['min_moves_from_default_spawn'],2)
        self.assertEqual([x['quadrant'] for x in g['first_three_zero_occupancy_hire_spawns']],
                         ['NE','SW','SE'])

    def test_decode_routes(self):
        r=m.decode_arlene_routes(arlene_fixture())
        self.assertEqual(set(r),{'main','tail'})
        self.assertEqual(len(r['tail']),2)

    def test_prestaged_main_detected(self):
        route=[
            {'farmer':['EAST'],'hands':[],'market':[]},
            {'farmer':['PASS'],'hands':[],'market':[['BUY_LAND']]},
        ]
        out=m.census_route('x',route,{'EAST':(1,0)},['NE','SW','SE'])
        e=out['events'][0]
        self.assertEqual(e['staged_actor_ids'],[0])
        self.assertEqual(e['staged_actor_ids_surviving_to_next_callback'],[0])

    def test_same_callback_hire_then_buy_land(self):
        route=[{'farmer':['PASS'],'hands':[],'market':[['HIRE'],['BUY_LAND']]}]
        out=m.census_route('x',route,{},['NE','SW','SE'])
        e=out['events'][0]
        self.assertEqual(e['staged_actor_ids'],[1])
        self.assertEqual(e['same_callback_prior_hire_actor_ids'],[1])

    def test_buy_land_then_hire_not_prior_stage(self):
        route=[{'farmer':['PASS'],'hands':[],'market':[['BUY_LAND'],['HIRE']]}]
        out=m.census_route('x',route,{},['NE','SW','SE'])
        e=out['events'][0]
        self.assertEqual(e['same_callback_prior_hire_actor_ids'],[])

    def test_eod_resets_stage(self):
        route=[{'market':[]} for _ in range(23)]
        route.append({'farmer':['PASS'],'hands':[],'market':[['HIRE'],['BUY_LAND']]})
        out=m.census_route('x',route,{},['NE','SW','SE'])
        e=out['events'][0]
        self.assertTrue(e['eod_reset_after_market'])
        self.assertEqual(e['staged_actor_ids'],[1])
        self.assertEqual(e['staged_actor_ids_surviving_to_next_callback'],[])

    def test_out_of_bounds_move_not_staged(self):
        route=[
            {'farmer':['WEST'],'hands':[],'market':[]}
            for _ in range(5)
        ]+[{'farmer':['PASS'],'hands':[],'market':[['BUY_LAND']]}]
        out=m.census_route('x',route,{'WEST':(-1,0)},['NE','SW','SE'])
        self.assertEqual(out['events'][0]['staged_actor_ids'],[])

    def test_tail_cycle_fails_closed(self):
        payload={'main':'main','full':[],'tails':[
            {'h':'a','parent':'b','at':0,'suffix':[]},
            {'h':'b','parent':'a','at':0,'suffix':[]},
        ]}
        blob=base64.b64encode(zlib.compress(json.dumps(payload).encode())).decode()
        with self.assertRaises(ValueError):
            m.decode_arlene_routes(f"_BLOB={blob!r}\n")


if __name__=='__main__':
    unittest.main()
