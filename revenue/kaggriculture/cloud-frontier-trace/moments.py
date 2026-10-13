"""Cross-check observed decision moments against raw replay and pinned execution."""
import argparse, collections, copy, json
from pathlib import Path
import analyze


def build(replay, trace, engine, ev):
    cfg=trace['configuration'];tpd=cfg['turnsPerDay'];shops=[];allocation=[];cadence=[];joint=[]
    labor=collections.defaultdict(lambda:collections.Counter())
    previous_shops=[]
    for row in trace['transitions']:
        i=row['frame'];step=row['action_step'];day=step//tpd
        before=analyze.observations(replay['steps'][i-1]);after=analyze.observations(replay['steps'][i])
        actions=[s.get('action') or {} for s in analyze.frame_rows(replay['steps'][i])]
        assert actions==row['actions'] and before[0]['step']==step
        assert row['observed_cash_delta']==[after[0]['farms'][s]['money']-before[0]['farms'][s]['money'] for s in range(2)]
        shop_list=after[0]['town']['unlocked_shops']
        if shop_list!=previous_shops:
            shops.append({'action_step':step,'available_step':step+1,'shops':shop_list,
                'prices_before':before[0]['market']['prices'],'prices_after':after[0]['market']['prices'],
                'farms_after':row['farms_after']})
            previous_shops=shop_list
        for seat in range(2):
            stat=labor[(seat,day)];stat['available_unit_actions']+=1+len(before[seat]['farms'][seat]['hands'])
        for e in row['audit']['events']:
            seat=e['seat'];stat=labor[(seat,day)]
            if e['kind']=='hire':stat['hire_spend']-=e['cash_delta'];stat['hires']+=int(e['changed'])
            if e['kind']=='trade' and e['op']=='SELL':stat['sales_coins']+=e['cash_delta']
            if e['kind']!='unit':continue
            op=e['action'][0];stat['changed_actions' if e['changed'] else 'unchanged_actions']+=1
            if op in ('NORTH','SOUTH','EAST','WEST'):stat['movement']+=int(e['changed'])
            elif e['changed']:stat['nonmovement_effects']+=1
            if op=='PASS':stat['pass']+=1
            elif not e['changed']:stat['unchanged_nonpass']+=1
            if e['changed'] and op in ('PLANT','PLACE'):
                allocation.append({'step':step,'seat':seat,'worker':e['worker'],'action':e['action'],
                    'shops_visible':before[0]['town']['unlocked_shops'],'prices_visible':row['prices_before'],
                    'cash_before':before[0]['farms'][seat]['money'],
                    'installed_crop_delta':e['installed_crop_delta'],'installed_animal_delta':e['installed_animal_delta']})
        # Capture exact within-turn tile context with original interpreter calls.
        # audit_transition still gates all context on the raw next-state match.
        contexts=[];growth=[];orig_unit=engine._apply_unit_action
        orig_growth={name:getattr(engine,name) for name in ('_daily_refresh_plants','_daily_refresh_animals')}
        def unit(farm,private,idx,action,*args,**kw):
            pos=engine._farmer_position(farm,idx)
            old=copy.deepcopy(farm['tiles'][pos[1]][pos[0]]) if pos else None
            result=orig_unit(farm,private,idx,action,*args,**kw)
            new=copy.deepcopy(farm['tiles'][pos[1]][pos[0]]) if pos else None
            contexts.append({'worker':idx,'position':pos,'action':action,'tile_before':old,'tile_after':new})
            return result
        def growth_wrap(original):
            def wrapped(farm,*args,**kw):
                old=copy.deepcopy(farm['tiles']);result=original(farm,*args,**kw)
                changes=[]
                for y,tiles in enumerate(old):
                    for x,tile in enumerate(tiles):
                        new=farm['tiles'][y][x]
                        if tile!=new and isinstance(tile,dict) and (tile.get('crop')=='TOMATO' or tile.get('animal')=='COW'):
                            changes.append({'x':x,'y':y,'before':tile,'after':copy.deepcopy(new)})
                growth.append(changes)
                return result
            return wrapped
        try:
            engine._apply_unit_action=unit
            for name,original in orig_growth.items():setattr(engine,name,growth_wrap(original))
            audit=analyze.audit_transition(engine,ev,before,after,actions,cfg,step,replay.get('info',{}))
        finally:
            engine._apply_unit_action=orig_unit
            for name,original in orig_growth.items():setattr(engine,name,original)
        assert audit['status']=='RECONCILED', (step,audit)
        units=[e for e in audit['events'] if e['kind']=='unit']
        assert len(contexts)==len(units)
        for context,event in zip(contexts,units):
            assert context['action']==event['action'] and context['worker']==event['worker']
            tile=context['tile_before'];seat=event['seat'];op=context['action'][0]
            if isinstance(tile,dict) and (tile.get('crop')=='TOMATO' or tile.get('animal')=='COW') and op not in ('NORTH','SOUTH','EAST','WEST','PASS'):
                cadence.append({'step':step,'seat':seat,'changed':event['changed'],**context})
        # Record actual shared-tile assignments for successful parallel operations.
        by_target=collections.defaultdict(list)
        for context,event in zip(contexts,units):
            if context['position'] and context['action'][0] in ('PLANT','WATER','FEED','CARE','HARVEST','FERTILIZE','COLLECT_FERTILIZER'):
                by_target[(event['seat'],*context['position'])].append({'worker':context['worker'],'op':context['action'][0],'changed':event['changed']})
        for target,ops in by_target.items():
            if len(ops)>1:joint.append({'step':step,'seat':target[0],'x':target[1],'y':target[2],'operations':ops})
        if growth:
            # Interpreter calls plants+animals for seat0, then seat1.
            assert len(growth)==4
            for number,changes in enumerate(growth):
                if changes:cadence.append({'step':step,'seat':number//2,'phase':'plant_refresh' if number%2==0 else 'animal_refresh','changes':changes})
    return {'episode_id':trace['episode_id'],'raw_sha256':trace['source']['transport_sha256'],
        'verified_transitions':len(trace['transitions']),'shop_unlocks':shops,'allocation_moments':allocation,
        'labor_by_day':[dict(seat=k[0],day=k[1],**v) for k,v in sorted(labor.items())],
        'tomato_cow_cadence':cadence,'shared_tile_operations':joint,
        'limitations':['One episode; observed response timing is not proof of internal intent.',
            'Hire spending and throughput are observed, not marginal profitability of an extra worker.',
            'Within-turn context is from pinned replay execution reconciled to the raw next state.']}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('replay',type=Path);p.add_argument('trace',type=Path)
    p.add_argument('--engine-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r,_=analyze.load_replay(a.replay);t=json.loads(a.trace.read_text());ev=analyze.evaluator();engine,_=ev.get_engine(a.engine_dir)
    result=build(r,t,engine,ev);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:len(result[k]) for k in ['shop_unlocks','allocation_moments','labor_by_day','tomato_cow_cadence','shared_tile_operations']}))
