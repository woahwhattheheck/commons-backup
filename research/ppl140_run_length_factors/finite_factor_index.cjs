"use strict";
// Finite factor comparison of two supplied binary words. No sequence generation.
const SCHEMA="commons.finite_factor_comparison/v1";
const LIMITS=Object.freeze({text:8192,page:64,json_chars:16000000});
const KINDS=["all","present","absent"];
function fail(x){throw new Error(x);}
function nat(x,max,name){if(!Number.isSafeInteger(x)||x<0||x>max)fail(name+" out of range");return x;}
function binary(x){if(typeof x!=="string"||x.length<1||x.length>LIMITS.text||!/^[12]+$/.test(x))fail("nonempty bounded word over {1,2} required");return x;}
function kind(x){if(!KINDS.includes(x))fail("factor kind");return x;}
function copy(x){return JSON.parse(JSON.stringify(x));}
function interval(row,which,maxLength,targetLength){
 const lo=row[1]+1,hi=Math.min(maxLength,targetLength-row[0]);
 if(which==="present")return [lo,Math.min(hi,row[2])];
 if(which==="absent")return [Math.max(lo,row[2]+1),hi];
 return [lo,hi];
}
function minTree(a){
 let base=1;while(base<a.length)base*=2;
 const tree=Array(2*base).fill(-1);for(let i=0;i<a.length;i++)tree[base+i]=a[i];
 for(let i=base-1;i>0;i--){const x=tree[2*i],y=tree[2*i+1];tree[i]=x<0?y:y<0?x:Math.min(x,y);}
 return {base,tree};
}
function compile(sourceText,targetText,maxLength=targetText.length){
 const s=binary(sourceText),t=binary(targetText);nat(maxLength,t.length,"maximum length");if(maxLength===0)fail("positive maximum length");
 const combined=s+"0"+t,n=combined.length,sourceLength=s.length;
 let sa=Array.from({length:n},(_,i)=>i),ranks=Array.from(combined,c=>c.charCodeAt(0));
 const stats={suffix_sort_rounds:0,suffix_sort_comparisons:0,lcp_character_comparisons:0,nearest_source_passes:2,source_sequence_steps:0};
 for(let width=1;width<n;width*=2){
  stats.suffix_sort_rounds++;
  const second=i=>i+width<n?ranks[i+width]:-1;
  sa.sort((a,b)=>{stats.suffix_sort_comparisons++;return ranks[a]-ranks[b]||second(a)-second(b);});
  const next=Array(n);next[sa[0]]=0;
  for(let i=1;i<n;i++){const a=sa[i-1],b=sa[i];next[b]=next[a]+(ranks[a]!==ranks[b]||second(a)!==second(b)?1:0);}
  ranks=next;if(ranks[sa[n-1]]===n-1)break;
 }
 const inverse=Array(n);sa.forEach((p,i)=>inverse[p]=i);
 const lcp=Array(n).fill(0);let h=0;
 for(let i=0;i<n;i++){
  const r=inverse[i];if(r===0){h=0;continue;}const j=sa[r-1];
  while(i+h<n&&j+h<n){stats.lcp_character_comparisons++;if(combined[i+h]!==combined[j+h])break;h++;}
  lcp[r]=h;if(h>0)h--;
 }
 const best=Array(t.length).fill(0),witness=Array(t.length).fill(-1);
 function offer(p,len,src){const j=p-sourceLength-1;if(p<=sourceLength)return;
  if(len>best[j]||(len===best[j]&&(witness[j]<0||src<witness[j]))){best[j]=len;witness[j]=src;}}
 let src=-1,minimum=Infinity;
 for(let r=0;r<n;r++){const p=sa[r];if(p<sourceLength){src=p;minimum=Infinity;}
  else if(src>=0){minimum=Math.min(minimum,lcp[r]);offer(p,minimum,src);}}
 src=-1;minimum=Infinity;
 for(let r=n-1;r>=0;r--){const p=sa[r];if(p<sourceLength){src=p;minimum=Infinity;}
  else if(src>=0){minimum=Math.min(minimum,lcp[r+1]);offer(p,minimum,src);}}
 const rows=[],sourceSA=[];let seen=false,between=Infinity;
 for(let r=0;r<n;r++){
  const p=sa[r];if(seen)between=Math.min(between,lcp[r]);
  if(p<sourceLength)sourceSA.push(p);
  if(p>sourceLength){const j=p-sourceLength-1;rows.push([j,seen?between:0,best[j],witness[j]]);seen=true;between=Infinity;}
 }
 const prefix={},byLength={},totals={};
 for(const which of KINDS){
  const ps=[0],diff=Array(maxLength+2).fill(0);
  for(const row of rows){const [lo,hi]=interval(row,which,maxLength,t.length),c=Math.max(0,hi-lo+1);ps.push(ps[ps.length-1]+c);
   if(c){diff[lo]++;diff[hi+1]--;}}
  const counts=Array(maxLength+1).fill(0);let running=0;for(let l=1;l<=maxLength;l++){running+=diff[l];counts[l]=running;}
  prefix[which]=ps;byLength[which]=counts;totals[which]=ps[ps.length-1];
 }
 let shortest=null;for(let l=1;l<=maxLength;l++)if(byLength.absent[l]){shortest=l;break;}
 return {schema:SCHEMA,source_text:s,target_text:t,max_length:maxLength,separator:"0",
  generalized_sa:sa,generalized_lcp:lcp,source_sa:sourceSA,
  row_columns:["target_start","previous_target_lcp","maximum_source_match","source_match_start"],
  rows,prefix,by_length:byLength,totals,shortest_absent_length:shortest,
  occurrence_minima:{source:minTree(sourceSA),target:minTree(rows.map(r=>r[0]))},stats};
}
function open(saved){
 const text=typeof saved==="string"?saved:JSON.stringify(saved);if(text.length>LIMITS.json_chars)fail("snapshot size");
 const z=JSON.parse(text);if(!z||z.schema!==SCHEMA)fail("schema");
 const s=binary(z.source_text),t=binary(z.target_text),L=nat(z.max_length,t.length,"maximum length");
 if(!L||z.separator!=="0")fail("snapshot contract");
 const n=s.length+t.length+1;
 function permutation(a,size,offset=0){if(!Array.isArray(a)||a.length!==size)fail("permutation size");const seen=new Set();for(const x of a){nat(x-offset,size-1,"permutation entry");if(seen.has(x))fail("duplicate permutation entry");seen.add(x);}}
 permutation(z.generalized_sa,n);permutation(z.source_sa,s.length);
 if(!Array.isArray(z.generalized_lcp)||z.generalized_lcp.length!==n||z.generalized_lcp[0]!==0)fail("LCP dimensions");
 for(const x of z.generalized_lcp)nat(x,n,"LCP");
 if(!Array.isArray(z.rows)||z.rows.length!==t.length)fail("row dimensions");
 permutation(z.rows.map(r=>r[0]),t.length);
 for(const r of z.rows){if(!Array.isArray(r)||r.length!==4)fail("row");nat(r[1],t.length-r[0],"target LCP");nat(r[2],t.length-r[0],"match length");nat(r[3],s.length-1,"source witness");if(r[2]>s.length-r[3])fail("match boundary");}
 for(const which of KINDS){
  const p=z.prefix[which],b=z.by_length[which];if(!Array.isArray(p)||p.length!==t.length+1||p[0]!==0||!Array.isArray(b)||b.length!==L+1||b[0]!==0)fail("count dimensions");
  for(let i=0;i<p.length;i++){nat(p[i],t.length*(t.length+1)/2,"count");if(i&&p[i]<p[i-1])fail("prefix order");}
  for(const c of b)nat(c,t.length,"length count");
  if(p[p.length-1]!==z.totals[which]||b.reduce((a,x)=>a+x,0)!==z.totals[which])fail("count partition");
 }
 if(z.totals.all!==z.totals.present+z.totals.absent)fail("family partition");
 if(z.shortest_absent_length!==null)nat(z.shortest_absent_length,L,"shortest");
 for(const [name,len] of [["source",s.length],["target",t.length]]){
  const m=z.occurrence_minima[name];if(!m||!Number.isSafeInteger(m.base)||m.base<len||m.base>=2*len||(m.base&(m.base-1))||!Array.isArray(m.tree)||m.tree.length!==2*m.base)fail("minimum tree dimensions");
  for(const x of m.tree)if(x!==-1)nat(x,len-1,"minimum-tree value");
 }
 const stats={queries:0,suffix_comparisons:0,character_comparisons:0,minimum_tree_nodes:0,rank_select_steps:0,rows_scanned:0,extracted_symbols:0,suffix_sort_rounds:0,lcp_construction_steps:0,source_sequence_steps:0};
 const targetSA=z.rows.map(r=>r[0]);
 function cmp(str,pos,word){stats.suffix_comparisons++;let i=0;while(i<word.length&&pos+i<str.length){stats.character_comparisons++;if(str[pos+i]!==word[i])return str[pos+i]<word[i]?-1:1;i++;}return i===word.length?0:-1;}
 function range(which,word){const str=which==="source"?s:t,sa=which==="source"?z.source_sa:targetSA;
  let lo=0,hi=sa.length;while(lo<hi){const m=(lo+hi)>>1;if(cmp(str,sa[m],word)<0)lo=m+1;else hi=m;}const first=lo;hi=sa.length;
  while(lo<hi){const m=(lo+hi)>>1;if(cmp(str,sa[m],word)<=0)lo=m+1;else hi=m;}return [first,lo];}
 function minRange(which,left,right){if(left===right)return null;const m=z.occurrence_minima[which];let a=left+m.base,b=right+m.base,res=Infinity;
  while(a<b){if(a&1){stats.minimum_tree_nodes++;res=Math.min(res,m.tree[a++]);}if(b&1){stats.minimum_tree_nodes++;res=Math.min(res,m.tree[--b]);}a>>=1;b>>=1;}return res;}
 function wordRecord(rowId,len){
  const r=z.rows[rowId],word=t.slice(r[0],r[0]+len);stats.extracted_symbols+=len;
  return {row_id:rowId,length:len,word,target_start:r[0],target_index:r[0]+1,present_in_source:len<=r[2],
   maximum_source_match:r[2],source_witness_start:len<=r[2]?r[3]:null,source_witness_index:len<=r[2]?r[3]+1:null};
 }
 function selectRaw(which,rank){
  kind(which);nat(rank,z.totals[which]-1,"rank");const p=z.prefix[which];let lo=0,hi=z.rows.length;
  while(lo<hi){stats.rank_select_steps++;const m=(lo+hi)>>1;if(p[m+1]<=rank)lo=m+1;else hi=m;}
  const [a]=interval(z.rows[lo],which,L,t.length);return {kind:which,rank,...wordRecord(lo,a+rank-p[lo])};
 }
 function rankRaw(which,word){
  kind(which);binary(word);if(word.length>L)return null;const [a,b]=range("target",word);if(a===b)return null;
  const [lo,hi]=interval(z.rows[a],which,L,t.length);if(word.length<lo||word.length>hi)return null;
  return z.prefix[which][a]+word.length-lo;
 }
 function lengthSlice(which,len){
  kind(which);nat(len,L,"length");if(len===0)fail("empty word excluded");
  const ids=[];for(let i=0;i<z.rows.length;i++){stats.rows_scanned++;const [a,b]=interval(z.rows[i],which,L,t.length);if(a<=len&&len<=b)ids.push(i);}
  return {schema:"commons.factor_length_slice/v1",source_text:s,target_text:t,max_length:L,kind:which,length:len,row_ids:ids};
 }
 function openSlice(raw){
  const a=copy(raw);if(a.schema!=="commons.factor_length_slice/v1"||a.source_text!==s||a.target_text!==t||a.max_length!==L)fail("slice binding");
  kind(a.kind);nat(a.length,L,"slice length");if(!a.length||!Array.isArray(a.row_ids)||a.row_ids.length>t.length)fail("slice");
  let prev=-1;for(const id of a.row_ids){nat(id,t.length-1,"slice row");const [lo,hi]=interval(z.rows[id],a.kind,L,t.length);if(id<=prev||a.length<lo||a.length>hi)fail("slice row condition");prev=id;}
  return {
   summary(){stats.queries++;return {kind:a.kind,length:a.length,count:a.row_ids.length};},
   select(rank){stats.queries++;nat(rank,a.row_ids.length-1,"slice rank");return {slice_rank:rank,...wordRecord(a.row_ids[rank],a.length)};},
   page(start=0,limit=64){stats.queries++;nat(start,a.row_ids.length,"start");nat(limit,LIMITS.page,"page size");return {total:a.row_ids.length,start,items:a.row_ids.slice(start,start+limit).map((id,i)=>({slice_rank:start+i,...wordRecord(id,a.length)})),next:start+limit<a.row_ids.length?start+limit:null};},
   rank(word){stats.queries++;binary(word);if(word.length!==a.length)return null;const [left,right]=range("target",word);if(left===right)return null;
    let lo=0,hi=a.row_ids.length;while(lo<hi){stats.rank_select_steps++;const m=(lo+hi)>>1;if(a.row_ids[m]<left)lo=m+1;else hi=m;}return lo<a.row_ids.length&&a.row_ids[lo]===left?lo:null;},
   snapshot(){return copy(a);}
  };
 }
 return {
  summary(){stats.queries++;return {source_length:s.length,target_length:t.length,max_length:L,distinct:copy(z.totals),shortest_absent_length:z.shortest_absent_length,constructor_stats:copy(z.stats)};},
  count(which,len=null){stats.queries++;kind(which);if(len===null)return z.totals[which];nat(len,L,"length");return z.by_length[which][len];},
  select(which,rank){stats.queries++;return selectRaw(which,rank);},
  rank(which,word){stats.queries++;return rankRaw(which,word);},
  page(which,start=0,limit=64){stats.queries++;kind(which);nat(start,z.totals[which],"start");nat(limit,LIMITS.page,"page size");
   return {kind:which,total:z.totals[which],start,items:Array.from({length:Math.min(limit,z.totals[which]-start)},(_,i)=>selectRaw(which,start+i)),next:start+limit<z.totals[which]?start+limit:null};},
  lengthSlice(which,len){stats.queries++;return lengthSlice(which,len);},openSlice,
  shortestAbsent(){stats.queries++;return z.shortest_absent_length===null?null:lengthSlice("absent",z.shortest_absent_length);},
  occurrences(which,word,start=0,limit=64){
   stats.queries++;if(which!=="source"&&which!=="target")fail("text choice");binary(word);nat(limit,LIMITS.page,"page size");
   const [a,b]=range(which,word),sa=which==="source"?z.source_sa:targetSA;nat(start,b-a,"occurrence page start");const first=minRange(which,a,b);
   return {text:which,word,count:b-a,first_start:first,first_index:first===null?null:first+1,ordering:"lexicographic suffix order; offsets zero-based",
    start,positions:sa.slice(a+start,Math.min(a+start+limit,b)),next:start+limit<b-a?start+limit:null};
  },
  rowsPage(start=0,limit=64){stats.queries++;nat(start,z.rows.length,"start");nat(limit,LIMITS.page,"page size");return {total:z.rows.length,start,rows:copy(z.rows.slice(start,start+limit)),next:start+limit<z.rows.length?start+limit:null};},
  lengthsPage(start=1,limit=64){stats.queries++;nat(start,L+1,"start");nat(limit,LIMITS.page,"page size");return {total:L+1,start,rows:Array.from({length:Math.min(limit,L+1-start)},(_,i)=>{const l=start+i;return [l,...KINDS.map(k=>z.by_length[k][l])];}),next:start+limit<L+1?start+limit:null};},
  stats(){return copy(stats);},snapshot(){return copy(z);}
 };
}
module.exports={compile,open,LIMITS,SCHEMA};
