'use strict';
function run(api,family,emit){
 const responses=[],inverses=[],minimal_ambiguity=[];
 function ask(label,method,args=[]){const request={id:responses.length+1,label,method,args};emit('request',request);const response=api[method](...args);responses.push({request,response});emit('response',{request,response});emit('snapshot',api.snapshot());return response;}
 const summary=ask('declared family summary','summary'),first=summary.codes[0].seed,last=summary.codes.at(-1).seed;
 const cases=[
 ['all',{}],['unique',{max_loss:0}],['ambiguous',{min_loss:1}],['loss-one',{min_loss:1,max_loss:1}],['loss-four',{min_loss:4,max_loss:4}],
 ['minimal-ambiguity',{min_size:4,max_size:4,min_loss:1}],['eight-erased-unique',{min_size:8,max_size:8,max_loss:0}],
 ['eight-erased-loss-one',{min_size:8,max_size:8,min_loss:1,max_loss:1}],['eight-erased-loss-at-least-two',{min_size:8,max_size:8,min_loss:2}],
 ['twelve-erased',{min_size:12,max_size:12,min_loss:4}],
 ['paired-constraints-unique',{require_erased:[0,8],forbid_erased:[1,9],min_size:4,max_size:8,max_loss:0}],
 ['paired-constraints-ambiguous',{require_erased:[0,8],forbid_erased:[1,9],min_size:4,max_size:8,min_loss:1}],
 ['conflicting',{require_erased:[0],forbid_erased:[0]}],['past-host',{min_size:17}],['negative-size',{max_size:-1}],['reversed-loss',{min_loss:5,max_loss:2}],['no-seeds',{seeds:[]}],
 ['first-code',{seeds:[first]}]
 ];
 for(const [name,q] of cases){
  const c=ask(name,'condition',[q]),count=BigInt(c.count);
  if(count)for(const r of new Set(['0',String(count/2n),String(count-1n)])){
   const s=ask(name+' select '+r,'select',[q,r]),back=ask(name+' inverse '+r,'rank',[q,s.seed,s.erased_mask]);inverses.push({condition:name,rank:r,returned:back.rank,matched:back.status==='OK'&&back.rank===r});
  }else ask(name+' empty select','select',[q,'0']);
  if(['all','unique','minimal-ambiguity','paired-constraints-ambiguous'].includes(name))ask(name+' coordinate marginals','marginals',[q]);
  if(name==='minimal-ambiguity'){
   let offset='0';do{const p=ask(name+' complete page '+offset,'page',[q,offset,128]);minimal_ambiguity.push(...p.rows);offset=p.next_offset;}while(offset!==null);
   ask(name+' end page','page',[q,String(count),128]);ask(name+' past-end page','page',[q,String(count+1n),1]);
  }
 }
 for(const code of family.codes){
  const e=code.generator_rows[0],received=code.codewords_by_message[37];
  ask('seed '+code.seed+' generator-support erasure','pattern',[code.seed,e]);
  ask('seed '+code.seed+' consistent generator-support fiber','compatible',[code.seed,e,received]);
 }
 const firstCode=family.codes[0];
 ask('no erasures consistent','compatible',[first,0,firstCode.codewords_by_message[37]]);
 ask('no erasures inconsistent received unit vector','compatible',[first,0,1]);
 ask('all coordinates erased','compatible',[first,65535,1]);
 ask('left systematic half erased','compatible',[first,255,firstCode.codewords_by_message[37]]);
 ask('right half erased','compatible',[first,65280,firstCode.codewords_by_message[37]]);
 ask('empty pattern at last seed','pattern',[last,0]);ask('full pattern at last seed','pattern',[last,65535]);
 return {format:'circulant-type-ii-erasure-consumer/v1',responses,inverses,minimal_ambiguity,snapshot:api.snapshot()};
}
module.exports={run};
