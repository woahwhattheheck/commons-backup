"""Observable production timing contract; scheduling remains the caller's policy.

Rules derived from Apache-2.0 kaggle-environments at 28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c.
Future events are conditional on survival, space, and actions, never guaranteed revenue.
"""
CROPS = {'WHEAT': (2,4,0,6), 'CARROT': (2,3,0,4),
         'TOMATO': (8,8,1,4), 'STRAWBERRY': (10,10,2,4), 'MELON': (10,12,0,6)}
ANIMALS = {'GOOSE': (4,1,4,'EGG'), 'COW': (8,2,6,'MILK'), 'SHEEP': (6,3,6,'WOOL')}


def production_events(tile, step, turns_per_day=24, episode_steps=720):
    """Return future EOD event dictionaries for one installed productive tile.

    available_step is the first action after refresh; fertilizer acts on the
    preceding day. No next-season event or nonongoing WATER yield is fabricated.
    """
    if turns_per_day <= 0 or episode_steps < 2: raise ValueError('Invalid horizon')
    last_action = episode_steps - 2
    if 'animal' in tile:
        first,interval,cap,product=ANIMALS[tile['animal']]
        start=tile['placed_day']+first
        days=range(start,(last_action//turns_per_day)+1,interval)
        kind='animal'
    elif tile.get('kind')=='PLANT':
        first,full,interval,cap=CROPS[tile['crop']]
        if not interval: return []
        product=tile['crop'];kind='crop'
        start=tile['planted_day']+first
        days=range(start,start+cap*interval,interval)
    else: return []
    events=[]
    for day in days:
        available=day*turns_per_day
        boundary=available-1
        if boundary < step or available > last_action: continue
        row={'kind':kind,'product':product,'refresh_step':boundary,'available_step':available,
             'care_day':day-1,'held_capacity':cap,'base_units':1,
             'requires_survival':True,'future_yield_is_conditional':True}
        if kind=='crop':
            row.update(fertilizer_application_days=[day-3,day-1],
                fertilizer_already_covers=tile.get('fertilized_until_day',-1)>=day-1,
                fertilizer_bonus_requires_water=True)
        else:
            row.update(care_bonus_requires_fed=True,
                current_pending_care_bonus=tile.get('pending_care_bonus',0),
                same_day_care_applies_to_later_event=True)
        events.append(row)
    return events


def harvest_contract(tile, step, turns_per_day=24, episode_steps=720):
    """Held-yield deadline and next production; no price or labor assumption."""
    events=production_events(tile,step,turns_per_day,episode_steps)
    last_action=episode_steps-2
    held=tile.get('yield_units',0)
    release=step
    if tile.get('kind')=='PLANT':
        release=max(step,(tile['planted_day']+CROPS[tile['crop']][0])*turns_per_day)
    decay=tile.get('max_lifespan_step',-1)
    deadline=min(last_action,decay) if decay>=0 else last_action
    # Unit actions precede decay and daily refresh: harvesting on these steps
    # avoids that transition's decay/capacity loss.
    next_event=events[0] if events else None
    cap=next_event['held_capacity'] if next_event else None
    cap_deadline=next_event['refresh_step'] if next_event and held>=cap else None
    return {'held_units':held,'harvest_release_step':release,
        'harvest_before_first_decay_step':deadline,'capacity_relief_step':cap_deadline,
        'last_sale_action_step':last_action,'next_event':next_event,
        'survival_action_due_today': bool((tile.get('kind')=='PLANT' and not tile.get('watered_today') and tile.get('consecutive_unwatered',0)>=1)
            or ('animal' in tile and not tile.get('fed_today') and tile.get('consecutive_unfed',0)>=1)),
        'held_harvest_possible_before_terminal':bool(held and release<=deadline)}


def liquidation_window(step, harvest_travel_steps, return_travel_steps, *,
                       turns_per_day=24, episode_steps=720, depot_has_capacity=True):
    """Earliest possible sale under caller-supplied route action counts.

    Travel counts must include actual legal moves; this function does not plan
    routes or reserve shed capacity. HARVEST then DROP need separate unit actions.
    EOD deposits occur after market, so their first sale is the next action.
    """
    if min(step,harvest_travel_steps,return_travel_steps)<0: raise ValueError('Negative action count')
    harvest=step+harvest_travel_steps
    explicit_drop=harvest+return_travel_steps+1
    next_day=((harvest//turns_per_day)+1)*turns_per_day
    sale=min(explicit_drop,next_day) if depot_has_capacity else None
    return {'harvest_step':harvest,'explicit_drop_sale_step':explicit_drop,
            'automatic_deposit_sale_step':next_day,'earliest_sale_step':sale,
            'cash_before_terminal':sale is not None and sale<=episode_steps-2,
            'capacity_must_be_reserved':True}


def farm_contract(observation, configuration):
    """Return coordinate-tagged contracts from the current player's public farm."""
    step=observation['step'];tpd=configuration.get('turnsPerDay',24);end=configuration.get('episodeSteps',720)
    farm=observation['farms'][observation['player']]
    return [dict(x=x,y=y,**harvest_contract(tile,step,tpd,end))
        for y,row in enumerate(farm['tiles']) for x,tile in enumerate(row)
        if isinstance(tile,dict) and (tile.get('kind')=='PLANT' or 'animal' in tile)]


def fertilizer_contract(tile, step, turns_per_day=24, episode_steps=720):
    """Next uncovered ongoing-crop event for FLORA's fertilizer routing.

    Returns None after final realizable event, for nonongoing crops, or when all
    remaining events are already covered. Coverage is checked on refresh's care
    day, not the following availability day. Caller supplies water and capacity.
    """
    if tile.get('kind')!='PLANT': return None
    day=step//turns_per_day
    for event in production_events(tile,step,turns_per_day,episode_steps):
        if event['fertilizer_already_covers']: continue
        first,last=event['fertilizer_application_days']
        return {'product':event['product'],'event_available_step':event['available_step'],
                'care_day':event['care_day'],'earliest_application_day':max(day,first),
                'latest_application_step':event['refresh_step'],
                'apply_today_covers_event':first<=day<=last,
                'days_until_window':max(0,first-day),
                'requires_water_on_care_day':True,
                'held_capacity':event['held_capacity'],
                'bonus_units_upper_bound':1}
    return None
