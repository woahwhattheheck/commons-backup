"use strict";
function consume(index,emit=()=>{}){
 const queries=[];let id=0;
 function call(method,args=[]){const request={id:++id,method,args:JSON.parse(JSON.stringify(args))};emit({phase:"request",request});const response=index[method](...args);const record={...request,response:JSON.parse(JSON.stringify(response))};queries.push(record);emit({phase:"response",record,caches:index.caches(),work:index.work()});return response;}
 try{
  const summary=call("summary"),root=call("distribution",[0]);call("distribution",[3]);call("distribution",[(1<<summary.n)-1]);
  const requests=[{},...summary.frontier.map(p=>({maxX:p.maxX,maxY:p.maxY})),{maxX:20,maxY:20},{maxX:12,maxY:12},{maxX:0,maxY:0},{maxX:1,maxY:37},{maxX:5,maxY:13},{maxX:9,maxY:6},{maxX:13,maxY:4},{maxX:32,maxY:3},{maxX:37,maxY:2},...Array.from({length:summary.n},(_,j)=>({maxX:10,maxY:13,prefix:[j]}))];
  const inverse=[],conditions=[];
  for(const q of requests){
   const condition=call("condition",[q]);conditions.push(condition);call("obstruction",[q]);
   const c=BigInt(condition.count);if(!c)continue;
   const ranks=[...new Set([0n,c/2n,c-1n].map(String))];
   for(const r of ranks){const s=call("select",[q,r]);const got=call("rank",[q,s.permutation]);inverse.push({condition:q,rank:r,returned:got.rank,equal:r===got.rank});if(r==="0")call("condition",[{maxX:condition.maxX,maxY:condition.maxY,prefix:s.permutation}]);}
  }
  const frontierExports=[];
  for(const p of summary.frontier){const q={maxX:p.maxX,maxY:p.maxY};const c=conditions.find(x=>x.maxX===p.maxX&&x.maxY===p.maxY&&x.prefix.length===0);const records=[];for(let r=0n;r<BigInt(c.count);r++)records.push(call("select",[q,r.toString()]).permutation);frontierExports.push({bounds:q,permutations:records});}
  return {schema:"rectangular-matching-reader/v1",queries,conditions,inverse,frontier_exports:frontierExports,caches:index.caches(),work:index.work(),summary:{queries:queries.length,inverse_matches:inverse.filter(x=>x.equal).length,inverse_total:inverse.length,condition_count:conditions.length,root_signatures:root.histogram.length}};
 }catch(error){error.reader_state={queries,caches:index.caches(),work:index.work()};throw error;}
}
module.exports={consume};
