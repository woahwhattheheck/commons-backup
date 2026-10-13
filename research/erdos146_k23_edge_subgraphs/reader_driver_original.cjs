'use strict';
function run(reader, plan, record) {
  const outputs=[], inverses=[];let id=0;
  function call(method,args,label) {
    const request={id:++id,method,args,label};
    record('request',request);
    const response=reader[method](...args);
    outputs.push({request,response});record('response',request,response);
    return response;
  }
  const ranks=count=>Array.from(new Set([0,Math.floor(count/2),count-1])).filter(x=>x>=0);
  call('summary',[],'complete finite family');
  call('patterns',[],'all sixty forbidden copies');
  const hostResults=[];
  for(const host of plan.hosts){
    const min=call('minimum',[host.mask],host.name);
    const witness=call('witness',[host.mask],host.name);
    const minimal=call('minimal',[host.mask],host.name);
    hostResults.push({host,min,witness,minimal});
    for(const rank of ranks(min.optimal_count)){
      const selected=call('deletion',[host.mask,rank],host.name+' optimum');
      const back=call('deletionRank',[host.mask,selected.removed],host.name+' inverse');
      inverses.push({kind:'deletion',host:host.mask,rank,back,match:rank===back});
    }
    for(const rank of ranks(minimal.count)) call('minimalSelect',[host.mask,rank],host.name+' inclusion minimal');
  }
  const conditions=[];
  for(const item of plan.filters){
    const c=call('condition',[item.filter],item.name);conditions.push({name:item.name,...c});
    for(const rank of ranks(c.count)){
      const selected=call('select',[c.key,rank],item.name);
      const back=call('rank',[c.key,selected.mask],item.name+' inverse');
      inverses.push({kind:'condition',key:c.key,rank,back,match:rank===back});
    }
  }
  const allMax=conditions.find(x=>x.name==='all_maximum');
  call('page',[allMax.key,0,1000],'all complete-host maxima');
  for(const [size,maximum] of [[15,10],[14,10],[12,10],[10,10],[6,5],[0,0]]){
    const p=call('profile',[size,maximum],'host profile');
    if(p.count)call('hostSelect',[size,maximum,Math.floor(p.count/2)],'middle host profile');
  }
  return {schema:'erdos146-reader-v1',plan,outputs,inverses,all_inverses_match:inverses.every(x=>x.match),
    host_results:hostResults,conditions,caches:reader.exportCaches(),work:reader.work()};
}
module.exports={run};
