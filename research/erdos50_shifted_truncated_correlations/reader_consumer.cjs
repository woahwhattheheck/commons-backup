"use strict";
function run(reader,certificate,bank){
 const responses=[],inverses=[],profiles=[];let lagRepresentativeProducts=0;
 function call(method,args){
  const id=responses.length+1;bank("pending",{id,method,args});bank("query_"+id+"_request",{method,args});
  const response=reader[method](args);bank("query_"+id+"_response",response);
  responses.push({id,method,args,response});bank("latest_caches",reader.snapshot());bank("latest_work",reader.work());bank("completed",id);bank("pending",null);return response;
 }
 for(let m=0;m<certificate.profiles.length;m++){
  let h=1n;for(let i=0;i<certificate.primes.length;i++)if(m&(1<<i)){h*=BigInt(certificate.primes[i]);lagRepresentativeProducts++;}
  profiles.push(call("profile",{lag:String(h)}));
 }
 const half=["1","2"],one=["1","1"],quarter=["1","4"],threequarter=["3","4"];
 const huge=String(BigInt(certificate.period)*10n**100n+1n);
 const conditions=[
  {name:"lag1",lag:"1"},{name:"lag2",lag:"2"},{name:"lag6",lag:"6"},{name:"lag30",lag:"30"},
  {name:"lag210",lag:"210"},{name:"diagonal",lag:certificate.period},
  {name:"negativeLag",lag:"-1"},{name:"hugeEquivalentLag",lag:huge},
  {name:"asymmetricRectangle",lag:"1",left:{upper:half},right:{lower:threequarter,lower_closed:false}},
  {name:"bothEvenImpossible",lag:"1",require_left:1,require_right:1},
  {name:"bothEvenLag2",lag:"2",require_left:1,require_right:1},
  {name:"quarterHalf",lag:"6",left:{lower:quarter,upper:half,upper_closed:false},right:{lower:half,upper:one}},
  {name:"exactHalf",lag:"1",left:{lower:half,upper:half}},
  {name:"emptyHalf",lag:"1",left:{lower:half,upper:half,upper_closed:false}},
  {name:"supportOverlap",lag:"1",require_left:2,exclude_left:2},
  {name:"reversedBounds",lag:"1",right:{lower:threequarter,upper:quarter}}
 ];
 const conditionResults=[];
 for(const q of conditions){
  const c=call("condition",q);conditionResults.push({name:q.name,...c});
  if(c.mass){
   for(const weighted of [false,true]){
    const total=weighted?c.mass:c.atom_count;
    for(const rank of Array.from(new Set([0,Math.floor(total/2),total-1]))){
     const selected=call("select",{...q,weighted,rank});
     const inverse=call("rank",{...q,weighted,profile_row:selected.profile_row,mass_offset:selected.mass_offset===null?0:selected.mass_offset});
     inverses.push({select_id:responses.length-1,rank_id:responses.length,expected:rank,actual:inverse.rank,match:inverse.status==="FOUND"&&inverse.rank===rank});
    }
   }
   call("select",{...q,weighted:true,rank:c.mass});
  }else call("select",{...q,weighted:true,rank:0});
 }
 const fullLagOnePage=call("page",{lag:"1",start:0,limit:10000});
 const marginalResults=[call("marginals",{lag:"1"}),call("marginals",{lag:"2"}),call("marginals",conditions[8])];
 const aliasChecks=[
  {left:"lag1",right:"negativeLag",match:conditionResults[0].key===conditionResults[6].key},
  {left:"lag1",right:"hugeEquivalentLag",match:conditionResults[0].key===conditionResults[7].key}
 ];
 const result={schema:"commons.erdos50.shifted_reader/v1",profiles,conditions:conditionResults,all_lag_one_atoms:fullLagOnePage,marginals:marginalResults,responses,inverse_checks:inverses,alias_checks:aliasChecks,work:reader.work(),driver_work:{lagRepresentativeProducts},caches:reader.snapshot()};
 bank("final_result",result);return result;
}
module.exports={run};
