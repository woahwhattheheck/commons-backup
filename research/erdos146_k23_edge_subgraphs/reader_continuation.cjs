'use strict';
function run(reader, plan, record) {
  const outputs=[],inverses=[];let id=78;
  function call(method,args,label){
    const request={id:++id,method,args,label};record('request',request);
    const response=reader[method](...args);outputs.push({request,response});
    record('response',request,response,reader.exportCaches(),reader.work());return response;
  }
  const ranks=count=>count===0?[]:Array.from(new Set([0,Math.floor(count/2),count-1]));
  const conditions=[];
  for(const item of plan.filters.slice(3)){
    const c=call('condition',[item.filter],item.name);conditions.push({name:item.name,...c});
    for(const rank of ranks(c.count)){
      const s=call('select',[c.key,rank],item.name);
      const back=call('rank',[c.key,s.mask],item.name+' inverse');
      inverses.push({key:c.key,rank,back,match:rank===back});
    }
  }
  for(const [size,maximum] of [[15,10],[14,10],[12,10],[10,10],[6,5],[0,0]]){
    const p=call('profile',[size,maximum],'previously unasked host profile');
    if(p.count)call('hostSelect',[size,maximum,Math.floor(p.count/2)],'middle host profile');
  }
  return {schema:'erdos146-reader-continuation-v1',outputs,inverses,
    all_inverses_match:inverses.every(x=>x.match),conditions,caches:reader.exportCaches(),work:reader.work(),
    omitted:'all-72-maxima page omitted because its earlier query cache was not exported; no old query or lost cache replay'};
}
module.exports={run};
