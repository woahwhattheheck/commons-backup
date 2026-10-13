'use strict';
function run(api,bank){
 const outputs=[],inverses=[],conditions=[],subhosts=[];let id=0;
 function ask(name,method,args){const request={id:++id,name,method,args};bank({phase:'before',request});
   const result=api[method](...args),record={...request,result};outputs.push(record);
   bank({phase:'after',record,caches:api.exportCaches(),work:api.work()});return result;}
 function ranks(n){const N=BigInt(n);return N===0n?[]:[...new Set([0n,N/2n,N-1n].map(String))];}
 function inverse(name,rank,actual){inverses.push({name,expected:String(rank),actual:actual===null?null:String(actual),equal:String(rank)===String(actual)});}
 ask('summary','summary',[]);
 for(const m of [0,1,1022,1023])ask('subhost '+m,'row',[m]);
 const huge='1000000000000000000000000000007';
 for(const m of [0,1022,1023])for(const q of ['0','1','2','3',huge])ask('palette '+m+' '+q,'count',[m,q]);
 const filters=[
 {},{blocks:3},{together:[[0,1]]},{apart:[[0,1]]},
 {together:[[0,1],[1,2]]},
 {available:0,together:[[0,1],[1,2],[2,3],[3,4],[4,5]]},
 {available:1022,together:[[0,1]],apart:[[2,3]]}
 ];
 for(let i=0;i<filters.length;i++){
   const c=ask('partition condition '+i,'condition',[filters[i]]);conditions.push(c);
   for(const r of ranks(c.count)){
     const selected=ask('partition '+i+' rank '+r,'partitionSelect',[c.key,Number(r)]);
     const rr=ask('partition inverse '+i+' '+r,'partitionRank',[c.key,selected.rgs]);inverse('partition '+i,r,rr);
   }
   for(const q of ['2','3',huge]){
     const total=ask('condition palette '+i+' '+q,'conditionedCount',[c.key,q]);
     if(i===0||i===4||i===5)for(const r of ranks(total.count)){
       const selected=ask('coloring '+i+' '+q+' '+r,'coloringSelect',[c.key,q,r]);
       const rr=ask('coloring inverse '+i+' '+q+' '+r,'coloringRank',[c.key,q,selected.colors]);inverse('coloring '+i+' '+q,r,rr);
     }
   }
 }
 for(let edge=0;edge<10;edge++)ask('single-edge deletion '+edge,'count',[1023^(1<<edge),'2']);
 for(const [i,f] of [{max_chromatic:2},{size:9,max_chromatic:2},{include:1,exclude:2,size:5,max_chromatic:2},{include:1023,max_chromatic:2}].entries()){
   const c=ask('edge subhost condition '+i,'subhostCondition',[f]);subhosts.push(c);
   for(const r of ranks(c.count)){
     const selected=ask('subhost '+i+' rank '+r,'subhostSelect',[c.key,Number(r)]);
     const rr=ask('subhost inverse '+i+' '+r,'subhostRank',[c.key,selected.mask]);inverse('subhost '+i,r,rr);
   }
 }
 return {schema:'erdos593-reader-evidence-v1',outputs,inverses,conditions,subhosts,caches:api.exportCaches(),work:api.work(),
   scope:'These are fresh saved-index queries; no compiler, old edge-coloring or ZDD calculation was called.'};
}
module.exports={run};
