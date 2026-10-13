'use strict';
function run(api,bank){
 const outputs=[],inverses=[],families=[];let id=0;
 function ask(name,method,args){const request={id:++id,name,method,args};bank({phase:'before',request});
   const result=api[method](...args),record={...request,result};outputs.push(record);
   bank({phase:'after',record,caches:api.exportCaches(),work:api.work()});return result;}
 const ranks=n=>n===0?[]:[...new Set([0,Math.floor(n/2),n-1])];
 function check(name,expected,actual){inverses.push({name,expected,actual,equal:expected===actual});}
 ask('summary','summary',[]);
 for(const mask of [1,7,63,127,255,511])ask('uniform state '+mask,'state',[mask,'1']);
 for(const t of ['0','1/4','1/3','1/2'])ask('single outcome visibility '+t,'classify',[1,t]);
 const huge=10n**100n+1n;
 ask('small rational visibility','state',[7,'1/'+huge]);
 ask('near-one rational visibility','state',[7,(huge-1n)+'/'+huge]);
 const filters=[{}, {rank:1},{psd:false},{include:1,exclude:2},{visibility:'1/4'},
   {visibility:'1/2'},{visibility:'3/4',size:6},{visibility:'2/3',available:255,size:4},{size:1}];
 const allPhysical=[];
 for(let i=0;i<filters.length;i++){
   const c=ask('support condition '+i,'condition',[filters[i]]);families.push(c);
   const chosen=i===0?Array.from({length:c.count},(_,j)=>j):ranks(c.count);
   for(const rank of chosen){
     const selected=ask('support '+i+' rank '+rank,'select',[c.key,rank]);
     if(i===0)allPhysical.push(selected);
     const inverse=ask('support inverse '+i+' rank '+rank,'rank',[c.key,selected.mask]);check('family '+i,rank,inverse);
   }
 }
 return {schema:'ppl145-hesse-reader-evidence-v1',outputs,inverses,families,all_physical_uniform_states:allPhysical,
   caches:api.exportCaches(),work:api.work(),scope:'New exact rational evaluations and navigation of saved data; no projector, subset-sum or determinant-polynomial construction.'};
}
module.exports={run};
