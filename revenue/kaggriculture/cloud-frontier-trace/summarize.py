"""Produce compact economic results from analyze.py's reconciled trace."""
import argparse, collections, csv, gzip, hashlib, json
from pathlib import Path


def summarize(trace):
    seats=[]
    turns_per_day=trace["configuration"]["turnsPerDay"]
    for seat,total in enumerate(trace['verified_transition_totals']):
        installs=collections.defaultdict(list);land=[];hiring=collections.Counter();quotes=collections.defaultdict(list)
        use=collections.Counter();fert_days=collections.Counter();feed=collections.Counter()
        for row in trace['transitions']:
            for event in row['audit'].get('events',[]):
                if event['seat']!=seat:continue
                step=row['action_step'];kind=event['kind']
                if kind=='land' and event['changed']:land.append({'step':step,'cash_delta':event['cash_delta']})
                if kind=='hire' and event['changed']:hiring[step//turns_per_day]+=1
                if kind=='trade' and event['success'] and event['op']=='SELL':
                    quotes[event['item']].append([step,event['quoted_price']])
                if kind=='unit' and event['changed']:
                    op=event['action'][0]
                    if op=='PLANT':installs[event['action'][1]].append(step)
                    if op=='FERTILIZE':fert_days[step//turns_per_day]+=1
                    if op=='FEED':feed.update({k:-v for k,v in event['inventory_delta'].items() if v<0})
                    if op=='PLACE':
                        for animal,n in event['installed_animal_delta'].items():
                            if n>0:installs[animal].extend([step]*n)
                    if op in ('WATER','FEED','CARE','HARVEST','FERTILIZE','COLLECT_FERTILIZER'):use[op]+=1
        sales={k:{'units':len(v),'coins':sum(p for _,p in v),'mean_price':sum(p for _,p in v)/len(v),
            'min_price':min(p for _,p in v),'max_price':max(p for _,p in v),
            'first_step':v[0][0],'last_step':v[-1][0]} for k,v in quotes.items()}
        income=sum(total['sales_coins'].values());spend=sum(total['capital_spend'].values())
        seats.append({'seat':seat,'opening_cash':trace['opening'][seat]['cash'],'terminal_cash':trace['terminal'][seat]['cash'],
            'gross_sales':income,'spending':spend,'cash_identity_residual':trace['terminal'][seat]['cash']-(trace['opening'][seat]['cash']+income-spend),
            'land_purchases':land,'installs_by_step':dict(installs),'hired_by_day':dict(hiring),'fertilize_by_day':dict(fert_days),
            'feed_consumed':dict(feed),'productive_actions':dict(use),'sales':sales,'totals':total})
    return {'episode_id':trace.get('episode_id'),'trace_source':trace['source'],'frames':trace['frames'],
        'transition_statuses':trace['transition_statuses'],'players':trace.get('players'),
        'seats':seats,'daily':trace['daily'],'limitations':trace['limitations'],
        'inference_limit':'One observed episode; sales association is not a counterfactual treatment effect.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('trace',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();trace=json.loads(a.trace.read_text());a.output.mkdir(parents=True,exist_ok=True)
    result=summarize(trace);(a.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    with (a.output/'daily-cash.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['action_step','seat_0_cash','seat_1_cash'])
        for d in trace['daily']:w.writerow([d['action_step'],*[farm['cash'] for farm in d['farms']]])
    with (a.output/'cash-ledger.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['action_step','seat','kind','operation','item','quote','cash_delta'])
        for row in trace['transitions']:
            for e in row['audit'].get('events',[]):
                if 'cash_delta' in e:w.writerow([row['action_step'],e['seat'],e['kind'],e.get('op',''),e.get('item',''),e.get('quoted_price',''),e['cash_delta']])
    (a.output/'trace.json.gz').write_bytes(gzip.compress(a.trace.read_bytes(),mtime=0))
    print(json.dumps({'players':[(s['opening_cash'],s['terminal_cash'],s['cash_identity_residual']) for s in result['seats']]}))
