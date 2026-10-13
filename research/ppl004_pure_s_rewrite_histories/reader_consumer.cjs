"use strict";
function run(reader,record){
  let id=0;const outcomes=["normal","horizon","leaf_limit"],inverses=[],selectedGroups=[];
  const work={savedRootCoefficientScans:0},conditionKeys=new Set(),termIDs=new Set();
  function query(method,args){const request={id:++id,method,args};record({phase:"before",request});
    const response=reader[method](...args);record({phase:"after",request,response,caches:reader.caches(),work:reader.work()});return response;}
  const summary=query("summary",[]),roots=query("rootProfiles",[]);
  function condition(root,prefix){const key=root+":"+JSON.stringify(prefix);if(!conditionKeys.has(key)){query("condition",[root,prefix]);conditionKeys.add(key);}}
  function term(id){if(!termIDs.has(id)){query("term",[id]);termIDs.add(id);}}
  for(const outcome of outcomes)for(let steps=0;steps<summary.summary.outcomeBySteps[outcome].length;steps++){
    let winner=null,best=0n;
    for(const root of roots){work.savedRootCoefficientScans++;const n=BigInt(root.counts[outcome][steps]);if(n>best){best=n;winner=root;}}
    if(!winner)continue;
    const root=winner.index;selectedGroups.push({root,outcome,steps,count:best.toString()});
    query("count",[root,outcome,steps]);condition(root,[]);term(winner.term);
    const ranks=Array.from(new Set(["0",(best/2n).toString(),(best-1n).toString()]));
    for(const requested of ranks){
      const a=query("select",[root,outcome,steps,requested]);
      const b=query("rank",[root,outcome,steps,a.addresses]);
      inverses.push({kind:"unconditional",root,outcome,steps,requested,returned:b.rank,equal:requested===b.rank});
      term(a.finalTerm);
      if(a.addresses.length>0){
        const prefix=a.addresses.slice(0,Math.max(1,Math.floor(a.addresses.length/2)));
        condition(root,prefix);
        const c=query("rank",[root,outcome,steps,a.addresses,prefix]);
        const d=query("select",[root,outcome,steps,c.rank,prefix]);
        inverses.push({kind:"prefix-conditioned",root,outcome,steps,prefix,
          equal:JSON.stringify(d.addresses)===JSON.stringify(a.addresses),rank:c.rank});
      }
    }
  }
  return {schema:"ppl004.saved-reader/v1",queries:id,selectedGroups,inverses,
    readerWork:reader.work(),driverWork:work,caches:reader.caches()};
}
module.exports={run};
