'use strict';
function run(api,emit){
 const responses=[],inverses=[],maxima=[];
 function ask(label,method,args=[]){const request={id:responses.length+1,label,method,args};emit('request',request);const response=api[method](...args);const row={request,response};responses.push(row);emit('response',row);emit('snapshot',api.snapshot());return response;}
 const summary=ask('complete saved family summary','summary');
 for(const view of summary.views){
  const graph=view.graph,max=view.inherited_maximum;
  const cases=[
   ['full',{graph}],
   ['maximum',{graph,min_size:max,max_size:max}],
   ['require-zero',{graph,require:[0]}],
   ['forbid-zero',{graph,forbid:[0]}],
   ['require-zero-and-one',{graph,require:[0,1]}],
   ['require-one-and-last',{graph,require:[1,127]}],
   ['incompatible-pair',{graph,require:[126,127]}],
   ['odd-only',{graph,forbid:Array.from({length:64},(_,i)=>2*i)}],
   ['required-and-forbidden',{graph,require:[0],forbid:[0]}],
   ['reversed-cardinality',{graph,min_size:6,max_size:3}],
   ['negative-maximum-size',{graph,max_size:-1}],
   ['above-host-minimum',{graph,min_size:129}]
  ];
  for(const [name,q] of cases){
   const c=ask(graph+' '+name,'condition',[q]),count=BigInt(c.count);
   if(count){
    const ranks=Array.from(new Set(['0',String(count/2n),String(count-1n)]));
    for(const r of ranks){const s=ask(graph+' '+name+' rank '+r,'select',[q,r]);const back=ask(graph+' '+name+' inverse '+r,'rank',[q,s.vertices]);inverses.push({graph,condition:name,rank:r,returned:back.rank,matched:back.status==='OK'&&back.rank===r});}
   }else ask(graph+' '+name+' empty select','select',[q,'0']);
   if(name==='maximum'){
    let offset='0';do{const p=ask(graph+' all maximum cliques '+offset,'page',[q,offset,256]);maxima.push(...p.items.map(x=>({graph,...x})));offset=p.next_offset;}while(offset!==null);
    ask(graph+' maximum end page','page',[q,String(count),256]);
    ask(graph+' maximum past-end page','page',[q,String(count+1n),1]);
   }
   if(['full','maximum','require-zero'].includes(name))ask(graph+' '+name+' vertex marginals','marginals',[q]);
  }
  ask(graph+' invalid full-family pair','rank',[{graph},[126,127]]);
  for(let k=0;k<=max+1;k++)ask(graph+' fixed size '+k,'condition',[{graph,min_size:k,max_size:k}]);
 }
 return {format:'smooth-sum-clique-family-consumer/v1',responses,inverses,maximum_cliques:maxima,snapshot:api.snapshot()};
}
module.exports={run};
