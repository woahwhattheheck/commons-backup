"use strict";
// Restricted affine incidence family; inherited difference-set premise is not reverified.
const mod=(x,m)=>((x%m)+m)%m;
function gcd(a,b){while(b){const t=a%b;a=b;b=t;}return a;}
function int(x,lo,hi,name){if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new RangeError(name);return x;}
function dec(x){if(typeof x!=="string"||! /^(0|[1-9][0-9]*)$/.test(x)||x.length>2048)throw new TypeError("nonnegative decimal string required");return BigInt(x);}
function buildIndex(input){
 const m=int(input.modulus,3,1000,"modulus"),D=input.difference_set.slice();
 if(D.length<2||D.length>64||D.some((x,i)=>!Number.isInteger(x)||x<0||x>=m||(i&&D[i-1]>=x)))throw new TypeError("sorted distinct difference set");
 const pos=new Map(D.map((d,i)=>[d,i])),screen=[],accepted=[],counters={gcd_evaluations:0,candidate_translations:0,image_membership_checks:0,multiplier_products:0,fixed_object_checks:0};
 for(let u=1;u<m;u++){
  const g=gcd(u,m);counters.gcd_evaluations++;
  if(g!==1){screen.push({u,gcd:g,excluded_nonunit:true});continue;}
  const candidates=[];
  for(const anchor of D){
   const c=mod(u*D[0]-anchor,m);counters.candidate_translations++;
   const image=[];let reject=null;
   for(let i=0;i<D.length;i++){const y=mod(u*D[i]-c,m);counters.image_membership_checks++;if(!pos.has(y)){reject={index:i,value:D[i],image:y};break;}image.push(pos.get(y));}
   if(reject)candidates.push({c,reject});
   else {candidates.push({c,accepted:true});accepted.push({u,c,image});}
  }
  screen.push({u,gcd:1,candidates});
 }
 accepted.sort((a,b)=>a.u-b.u||a.c-b.c);
 if(accepted.filter(a=>a.u===1).length!==1)throw new RangeError("requires trivial translation stabilizer");
 const byU=new Map();accepted.forEach((a,i)=>{if(byU.has(a.u))throw new Error("multiple slides");byU.set(a.u,i);});
 const k=accepted.length,products=[],inverse=[];
 for(let i=0;i<k;i++){const row=[];for(let j=0;j<k;j++){
  const a=accepted[i],b=accepted[j],v=byU.get(mod(a.u*b.u,m));counters.multiplier_products++;
  if(v===undefined||accepted[v].c!==mod(a.u*b.c+a.c,m))throw new Error("multiplier closure");
  row.push(v);if(accepted[v].u===1)inverse[i]=j;
 }products.push(row);}
 const elements=[],buckets=new Map();
 for(let i=0;i<k;i++)for(let t=0;t<m;t++){
  const a=accepted[i],point_fixed=[],line_fixed=[],difference_fixed=[];
  for(let x=0;x<m;x++){counters.fixed_object_checks+=2;if(mod(a.u*x+t,m)===x)point_fixed.push(x);if(mod(a.u*x+t+a.c,m)===x)line_fixed.push(x);}
  for(let d=0;d<D.length;d++)if(a.image[d]===d)difference_fixed.push(d);
  const row={id:i*m+t,multiplier:i,t,point_fixed,line_fixed,difference_fixed,flag_fixed_count:line_fixed.length*difference_fixed.length};
  elements.push(row);const key=[point_fixed.length,line_fixed.length,row.flag_fixed_count].join(",");
  if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(row.id);
 }
 const difference_orbits=[],visited=new Set();
 for(let d=0;d<D.length;d++)if(!visited.has(d)){
  const orbit=[...new Set(accepted.map(a=>a.image[d]))].sort((a,b)=>a-b);
  orbit.forEach(x=>visited.add(x));difference_orbits.push({id:difference_orbits.length,indices:orbit,differences:orbit.map(x=>D[x]),flag_count:m*orbit.length,flag_stabilizer_size:k/orbit.length});
 }
 return {format:"cyclic-affine-incidence-v1",input:JSON.parse(JSON.stringify(input)),modulus:m,difference_set:D,screen,multipliers:accepted,products,inverse,elements,difference_orbits,
 fixed_buckets:[...buckets].map(([key,ids])=>({signature:key.split(",").map(Number),count:ids.length,element_ids:ids})),
 counts:{residues:m,differences:D.length,units:screen.filter(r=>r.gcd===1).length,multipliers:k,elements:k*m,flags:m*D.length,flag_orbits:difference_orbits.length},counters};
}
function openIndex(s){
 if(!s||s.format!=="cyclic-affine-incidence-v1")throw new TypeError("snapshot format");
 const m=s.modulus,D=s.difference_set,k=s.multipliers.length;
 if(s.elements.length!==m*k||s.products.length!==k||s.inverse.length!==k)throw new TypeError("snapshot shape");
 const stats={queries:0,element_scans:0,multiplier_scans:0,table_lookups:0,affine_evaluations:0,power_products:0};
 const out=x=>JSON.parse(JSON.stringify(x));
 function element(id){int(id,0,s.elements.length-1,"element id");stats.table_lookups++;return s.elements[id];}
 function compose(a,b){const g=element(a),h=element(b),u=s.multipliers[g.multiplier].u;stats.table_lookups++;return s.products[g.multiplier][h.multiplier]*m+mod(u*h.t+g.t,m);}
 function inverse(id){const e=element(id),i=s.inverse[e.multiplier];stats.table_lookups++;return i*m+mod(-s.multipliers[i].u*e.t,m);}
 function action(id,type,label){const e=element(id),a=s.multipliers[e.multiplier];
  if(type==="flag"){if(!Array.isArray(label)||label.length!==2)throw new TypeError("flag [line,difference index]");const l=int(label[0],0,m-1,"line"),d=int(label[1],0,D.length-1,"difference index");stats.affine_evaluations+=2;const line=mod(a.u*l+e.t+a.c,m),di=a.image[d];return{line,difference_index:di,point:mod(line+D[di],m)};}
  int(label,0,m-1,"label");if(type!=="point"&&type!=="line")throw new TypeError("object type");stats.affine_evaluations++;return mod(a.u*label+e.t+(type==="line"?a.c:0),m);
 }
 function query(q){
  stats.queries++;
  switch(q.op){
   case"summary":return out({counts:s.counts,fixed_buckets:s.fixed_buckets.map(({signature,count})=>({signature,count})),difference_orbits:s.difference_orbits});
   case"multiplier":return out(s.multipliers[int(q.index,0,k-1,"multiplier index")]);
   case"screen":return out(s.screen[int(q.u,1,m-1,"unit candidate")-1]);
   case"element":return out(element(q.id));
   case"compose":return {id:compose(q.left,q.right)};
   case"inverse":return {id:inverse(q.id)};
   case"power":{let n=dec(q.exponent),a=q.id,r=0;element(a);while(n){if(n&1n){r=compose(a,r);stats.power_products++;}n>>=1n;if(n){a=compose(a,a);stats.power_products++;}}return{id:r};}
   case"action":return {image:action(q.id,q.type,q.label)};
   case"fixed":{const e=element(q.id);return out({points:e.point_fixed,lines:e.line_fixed,difference_indices:e.difference_fixed,flag_count:e.flag_fixed_count});}
   case"orbit":{const d=int(q.difference_index,0,D.length-1,"difference index");return out(s.difference_orbits.find(o=>o.indices.includes(d)));}
   case"flagSelect":{const o=s.difference_orbits[int(q.orbit,0,s.difference_orbits.length-1,"orbit")],rank=int(q.rank,0,o.flag_count-1,"rank"),line=Math.floor(rank/o.indices.length),di=o.indices[rank%o.indices.length];return {line,difference_index:di,point:mod(line+D[di],m)};}
   case"flagRank":{const line=int(q.line,0,m-1,"line"),di=int(q.difference_index,0,D.length-1,"difference index"),o=s.difference_orbits.find(o=>o.indices.includes(di));return {orbit:o.id,rank:line*o.indices.length+o.indices.indexOf(di)};}
   case"transporter":{
    const rows=[];if(q.type==="flag"){const [l,d]=q.from,[L,e]=q.to;int(l,0,m-1,"line");int(L,0,m-1,"line");int(d,0,D.length-1,"difference");int(e,0,D.length-1,"difference");
     for(let i=0;i<k;i++){stats.multiplier_scans++;const a=s.multipliers[i];if(a.image[d]===e)rows.push(i*m+mod(L-a.u*l-a.c,m));}
    }else{if(q.type!=="point"&&q.type!=="line")throw new TypeError("type");int(q.from,0,m-1,"from");int(q.to,0,m-1,"to");
     for(let i=0;i<k;i++){stats.multiplier_scans++;const a=s.multipliers[i];rows.push(i*m+mod(q.to-a.u*q.from-(q.type==="line"?a.c:0),m));}}
    return{count:rows.length,ids:rows};
   }
   case"condition":{if(!Array.isArray(q.constraints)||q.constraints.length>8)throw new TypeError("constraints");const ids=[];
    for(const e of s.elements){stats.element_scans++;if(q.constraints.every(c=>JSON.stringify(action(e.id,c.type,c.from))===JSON.stringify(c.to)))ids.push(e.id);}
    return{count:ids.length,ids};
   }
   case"bucket":return out(s.fixed_buckets[int(q.index,0,s.fixed_buckets.length-1,"bucket")]);
   default:throw new TypeError("query op");
  }
 }
 return {query,stats:()=>out(stats)};
}
module.exports={buildIndex,openIndex};
