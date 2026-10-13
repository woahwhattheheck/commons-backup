"use strict";
function run(reader,bank){
 const responses=[],inverseChecks=[];
 function call(method,args){
  const id=responses.length+1;bank("pending",{id,method,args});bank("query_"+id+"_request",{method,args});
  const response=reader[method](...(method==="condition"?[args.required,args.excluded]:method==="summary"?[]:[args]));
  bank("query_"+id+"_response",response);responses.push({id,method,args,response});
  bank("latest_caches",reader.snapshot());bank("latest_work",reader.work());bank("completed",id);bank("pending",null);return response;
 }
 function pair(args){
  const s=call("select",args);
  if(s.status==="FOUND"){
   const r=call("rank",{...args,mask:s.mask});inverseChecks.push({select_id:responses.length-1,rank_id:responses.length,expected:args.rank,actual:r.rank,match:r.status==="FOUND"&&r.rank===args.rank});
  }
 }
 const summary=call("summary",{});
 const specifications=[
  {name:"full",required:0,excluded:0},{name:"require87",required:16,excluded:0},
  {name:"require88",required:32,excluded:0},{name:"knownConflict",required:48,excluded:0},
  {name:"hugeRequired",required:65536,excluded:0},{name:"hugeExcluded",required:0,excluded:65536},
  {name:"require38exclude53",required:1,excluded:2},{name:"emptyOnly",required:0,excluded:131071},
  {name:"overlap",required:1,excluded:1},{name:"require117",required:128,excluded:0}
 ];
 const conditionOutputs=[];
 for(const s of specifications){
  const c=call("condition",s);conditionOutputs.push({name:s.name,...c});
  if(c.total){
   const feasible=c.counts.map((v,k)=>v?k:-1).filter(k=>k>=0);
   const sizes=Array.from(new Set([feasible[0],feasible[Math.floor(feasible.length/2)],c.max_size]));
   for(const size of sizes){
    const total=c.counts[size];
    for(const rank of Array.from(new Set([0,Math.floor(total/2),total-1])))pair({...s,size,rank});
    pair({...s,size,rank:0,optimal:true});
   }
   call("select",{...s,size:c.max_size,rank:c.max_size_count});
  }else call("select",{...s,size:2,rank:0});
 }
 const allLargest=call("page",{required:0,excluded:0,size:summary.full.max_size,start:0,limit:10000});
 const fixedSizeOptima=[];
 for(let size=0;size<=summary.full.max_size;size++)fixedSizeOptima.push(call("page",{required:0,excluded:0,size,optimal:true,start:0,limit:10000}));
 call("marginals",{required:0,excluded:0,size:summary.full.max_size});
 call("marginals",{required:16,excluded:0,size:10});
 call("rank",{required:0,excluded:0,size:2,mask:48});
 call("rank",{required:16,excluded:0,size:1,mask:32});
 const result={schema:"commons.erdos143.saved_reader/v1",summary,conditions:conditionOutputs,all_largest:allLargest,fixed_size_optima:fixedSizeOptima,responses,inverse_checks:inverseChecks,caches:reader.snapshot(),work:reader.work()};
 bank("final_result",result);return result;
}
module.exports={run};
