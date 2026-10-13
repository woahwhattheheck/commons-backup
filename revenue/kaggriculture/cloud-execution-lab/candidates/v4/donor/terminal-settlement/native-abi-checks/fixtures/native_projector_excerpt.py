# SPDX-License-Identifier: Apache-2.0
# Exact post_units function from scheduler.py a483b24dd72b580d7d8811636b54d2d44f391575.
# Tests inject deterministic mechanics and detached_json_value dependencies.
def post_units(obs, action, config, *, shed_capacity=None):
    """Exact deterministic engine unit stage on the player's observed farm."""
    farm = detached_json_value(obs['farms'][obs['player']])
    private = detached_json_value(obs['private'])
    acts = [action.get('farmer',['PASS']), *action.get('hands',[])]
    demand = {}
    for a in acts:
        if a and a[0]=='PLANT' and len(a)>1:
            demand[a[1]]=demand.get(a[1],0)+1
    blocked={p for p,n in demand.items() if n>private['seeds'].get(p,0)}
    capacity=int(config.get('shedCapacity',100)) if shed_capacity is None else int(shed_capacity)
    for i,a in enumerate(acts):
        if a and a[0]=='PLANT' and a[1] in blocked:a=['PASS']
        m._apply_unit_action(farm,private,i,a,len(farm['tiles']),int(obs['step'])//int(config.get('turnsPerDay',24)),int(config.get('turnsPerDay',24)),capacity)
    return farm, private
