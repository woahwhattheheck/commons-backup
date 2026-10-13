"use strict";
function gcd(a,b){a=a<0n?-a:a;b=b<0n?-b:b;while(b){const t=a%b;a=b;b=t;}return a;}
function R(a,b=1n){if(b===0n)throw new RangeError("zero denominator");if(b<0n){a=-a;b=-b;}const g=gcd(a,b);return[a/g,b/g];}
function parse(s){if(typeof s!=="string"||s.length>4096||! /^(0|-?[1-9][0-9]*)(\/[1-9][0-9]*)?$/.test(s))throw new TypeError("rational string");const a=s.split("/");return R(BigInt(a[0]),a[1]?BigInt(a[1]):1n);}
const fmt=x=>x[1]===1n?String(x[0]):String(x[0])+"/"+String(x[1]);
const add=(a,b)=>R(a[0]*b[1]+b[0]*a[1],a[1]*b[1]);
const sub=(a,b)=>R(a[0]*b[1]-b[0]*a[1],a[1]*b[1]);
const mul=(a,b)=>R(a[0]*b[0],a[1]*b[1]);
const div=(a,b)=>R(a[0]*b[1],a[1]*b[0]);
const cmp=(a,b)=>{const z=a[0]*b[1]-b[0]*a[1];return z<0n?-1:z>0n?1:0;};
const clone=x=>JSON.parse(JSON.stringify(x));
function index(x,n){if(!Number.isSafeInteger(x)||x<0||x>=n)throw new RangeError("index");return x;}
function components(strata,ids){
 const out=[];for(const id of ids){const s=strata[id],lo=s.kind==="point"?s.at:s.left,hi=s.kind==="point"?s.at:s.right,closed=s.kind==="point";
  const last=out[out.length-1];if(last&&last.last_stratum+1===id){last.right=hi;last.right_closed=closed;last.last_stratum=id;}
  else out.push({left:lo,left_closed:closed,right:hi,right_closed:closed,first_stratum:id,last_stratum:id});}
 return out;
}
function buildIndex(input){
 const n=input.points.length;if(n<2||n>32)throw new RangeError("point count");
 const p=input.points.map(x=>({name:x.name,u:parse(x.u),v:parse(x.v)}));
 const forms=[],pairIds=Array.from({length:n},()=>Array(n).fill(null)),stars=Array.from({length:n},()=>[]),comparisons=[],eventMap=new Map();
 const counts={pair_coefficients:0,star_equalities:0,positive_event_occurrences:0,persistent_equalities:0,stratum_form_evaluations:0};
 for(let i=0;i<n;i++)for(let j=i+1;j<n;j++){
  const du=sub(p[i].u,p[j].u),dv=sub(p[i].v,p[j].v),a=mul(du,du),b=mul(dv,dv);if(a[0]===0n&&b[0]===0n)throw new RangeError("duplicate points");
  const id=forms.length;forms.push({id,i,j,a:fmt(a),b:fmt(b)});pairIds[i][j]=pairIds[j][i]=id;stars[i].push({neighbor:j,form:id});stars[j].push({neighbor:i,form:id});counts.pair_coefficients++;
 }
 const parsed=forms.map(f=>({a:parse(f.a),b:parse(f.b)}));
 for(let v=0;v<n;v++)for(let i=0;i<stars[v].length;i++)for(let j=i+1;j<stars[v].length;j++){
  const f=stars[v][i],g=stars[v][j],a=sub(parsed[f.form].a,parsed[g.form].a),b=sub(parsed[f.form].b,parsed[g.form].b),id=comparisons.length;
  const row={id,vertex:v,neighbors:[f.neighbor,g.neighbor],forms:[f.form,g.form],slope:fmt(a),intercept:fmt(b)};counts.star_equalities++;
  if(a[0]===0n){row.kind=b[0]===0n?"persistent":"parallel_unequal";if(b[0]===0n)counts.persistent_equalities++;}
  else {const root=div(R(-b[0],b[1]),a);row.root=fmt(root);row.kind=root[0]>0n?"positive_event":"outside_positive_domain";
   if(root[0]>0n){counts.positive_event_occurrences++;if(!eventMap.has(row.root))eventMap.set(row.root,[]);eventMap.get(row.root).push(id);}
  }
  comparisons.push(row);
 }
 const events=[...eventMap].map(([at,equality_ids])=>({at,equality_ids})).sort((a,b)=>cmp(parse(a.at),parse(b.at)));
 const strata=[];
 function append(s){
  const sample=parse(s.sample),vertex_rows=[];
  for(let v=0;v<n;v++){
   const map=new Map();for(const e of stars[v]){const f=parsed[e.form],value=fmt(add(mul(f.a,sample),f.b));counts.stratum_form_evaluations++;
    if(!map.has(value))map.set(value,{sample_squared_distance:value,neighbors:[],forms:[]});const g=map.get(value);g.neighbors.push(e.neighbor);g.forms.push(e.form);}
   const groups=[...map.values()].sort((a,b)=>cmp(parse(a.sample_squared_distance),parse(b.sample_squared_distance)));
   vertex_rows.push({vertex:v,max_multiplicity:Math.max(...groups.map(g=>g.neighbors.length)),groups});
  }
  strata.push({...s,id:strata.length,minimum_star_max:Math.min(...vertex_rows.map(v=>v.max_multiplicity)),stars:vertex_rows});
 }
 let left="0";
 for(const e of events){append({kind:"open",left,right:e.at,sample:fmt(div(add(parse(left),parse(e.at)),R(2n)))});e.stratum=strata.length;append({kind:"point",at:e.at,sample:e.at});left=e.at;}
 append({kind:"open",left,right:null,sample:fmt(add(parse(left),R(1n)))});
 const superlevels=[];for(let threshold=1;threshold<n;threshold++){const ids=strata.filter(s=>s.minimum_star_max>=threshold).map(s=>s.id);superlevels.push({threshold,stratum_ids:ids,components:components(strata,ids)});}
 return {format:"anisotropic-distance-arrangement-v1",input:clone(input),forms,pair_ids:pairIds,comparisons,events,strata,superlevels,counts:{points:n,forms:forms.length,comparisons:comparisons.length,events:events.length,strata:strata.length,...counts}};
}
function openIndex(s){
 if(!s||s.format!=="anisotropic-distance-arrangement-v1"||s.strata.length!==2*s.events.length+1)throw new TypeError("snapshot shape");
 const n=s.input.points.length,stats={queries:0,event_comparisons:0,form_evaluations:0,saved_strata_scanned:0,group_records_read:0};
 function parameter(text){const x=parse(text);if(x[0]<=0n)throw new RangeError("parameter must be positive");return x;}
 function locate(text){const x=parameter(text);let lo=0,hi=s.events.length;while(lo<hi){const mid=Math.floor((lo+hi)/2),c=cmp(x,parse(s.events[mid].at));stats.event_comparisons++;if(c===0)return{parameter:fmt(x),stratum:2*mid+1};if(c<0)hi=mid;else lo=mid+1;}return{parameter:fmt(x),stratum:2*lo};}
 function evaluate(id,x){const f=s.forms[index(id,s.forms.length)];stats.form_evaluations++;return fmt(add(mul(parse(f.a),x),parse(f.b)));}
 function star(id,v,x){const row=s.strata[id].stars[index(v,n)];return {vertex:v,max_multiplicity:row.max_multiplicity,groups:row.groups.map(g=>{stats.group_records_read++;return{neighbors:g.neighbors.slice(),forms:g.forms.slice(),squared_distance:evaluate(g.forms[0],x)};})};}
 function query(q){stats.queries++;switch(q.op){
  case"summary":return clone({counts:s.counts,superlevels:s.superlevels.map(({threshold,components})=>({threshold,components}))});
  case"locate":return locate(q.parameter);
  case"event":return clone(s.events[index(q.index,s.events.length)]);
  case"eventsPage":{index(q.start,s.events.length+1);index(q.limit,1001);return clone(s.events.slice(q.start,q.start+q.limit));}
  case"stratum":return clone(s.strata[index(q.id,s.strata.length)]);
  case"form":return clone(s.forms[index(q.id,s.forms.length)]);
  case"comparison":return clone(s.comparisons[index(q.id,s.comparisons.length)]);
  case"distance":{const i=index(q.i,n),j=index(q.j,n),x=parameter(q.parameter);if(i===j)return{squared_distance:"0"};return{squared_distance:evaluate(s.pair_ids[i][j],x)};}
  case"star":{const l=locate(q.parameter);return{...l,...star(l.stratum,q.vertex,parse(l.parameter))};}
  case"profile":{const l=locate(q.parameter);return{...l,minimum_star_max:s.strata[l.stratum].minimum_star_max,stars:Array.from({length:n},(_,v)=>star(l.stratum,v,parse(l.parameter)))};}
  case"superlevel":return clone(s.superlevels[index(q.threshold-1,n-1)]);
  case"condition":{if(!Array.isArray(q.vertices)||q.vertices.length===0||new Set(q.vertices).size!==q.vertices.length)throw new TypeError("distinct nonempty vertices");q.vertices.forEach(v=>index(v,n));index(q.threshold-1,n-1);const ids=[];
   for(const st of s.strata){stats.saved_strata_scanned++;if(q.vertices.every(v=>st.stars[v].max_multiplicity>=q.threshold))ids.push(st.id);}
   return{vertices:q.vertices.slice(),threshold:q.threshold,stratum_ids:ids,components:components(s.strata,ids)};}
  case"witness":{const l=locate(q.parameter),v=index(q.vertex,n),r=s.strata[l.stratum].stars[v],g=r.groups.find(g=>g.neighbors.length===r.max_multiplicity);stats.group_records_read++;return{...l,vertex:v,neighbors:g.neighbors.slice(),multiplicity:r.max_multiplicity,squared_radius:evaluate(g.forms[0],parse(l.parameter))};}
  default:throw new TypeError("query op");
 }}
 return{query,stats:()=>clone(stats)};
}
module.exports={buildIndex,openIndex};
