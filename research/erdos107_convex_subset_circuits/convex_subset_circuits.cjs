"use strict";
function gcd(a,b){a=a<0n?-a:a;b=b<0n?-b:b;while(b){const t=a%b;a=b;b=t;}return a;}
function rational(s){if(typeof s!=="string"||s.length>512||! /^(0|-?[1-9][0-9]*)(\/[1-9][0-9]*)?$/.test(s))throw new TypeError("rational coordinate");const a=s.split("/"),n=BigInt(a[0]),d=a[1]?BigInt(a[1]):1n,g=gcd(n,d);return[n/g,d/g];}
function bits(mask,n){const a=[];for(let i=0;i<n;i++)if(mask&(1<<i))a.push(i);return a;}
function pop(mask){let c=0;while(mask){mask&=mask-1;c++;}return c;}
const copy=x=>JSON.parse(JSON.stringify(x));
function buildIndex(input){
 const n=input.points.length;if(n<3||n>17)throw new RangeError("3..17 points");
 const rats=input.points.map(p=>[rational(p.u),rational(p.v)]);let L=1n;for(const p of rats)for(const q of p)L=L/gcd(L,q[1])*q[1];
 const points=rats.map(p=>p.map(q=>q[0]*(L/q[1]))),triples=[],lookup=new Map();
 for(let i=0;i<n;i++)for(let j=i+1;j<n;j++)for(let k=j+1;k<n;k++){
  const [x,y]=points[i],[X,Y]=points[j],[a,b]=points[k],det=(X-x)*(b-y)-(Y-y)*(a-x);
  if(det===0n)throw new RangeError("not in general position: "+[i,j,k].join(","));
  const row={vertices:[i,j,k],determinant_numerator:String(det),sign:det>0n?1:-1};lookup.set([i,j,k].join(","),row.sign);triples.push(row);
 }
 let orientation_lookups=0;
 function sign(i,j,k){const a=[i,j,k];let parity=1;for(let x=0;x<3;x++)for(let y=x+1;y<3;y++)if(a[x]>a[y]){[a[x],a[y]]=[a[y],a[x]];parity=-parity;}orientation_lookups++;return parity*lookup.get(a.join(","));}
 const circuits=[];let containment_candidates=0;
 for(let i=0;i<n;i++)for(let j=i+1;j<n;j++)for(let k=j+1;k<n;k++)for(let l=k+1;l<n;l++){
  const q=[i,j,k,l];for(const p of q){const t=q.filter(x=>x!==p),s=sign(...t);containment_candidates++;
   if(sign(t[0],t[1],p)===s&&sign(t[1],t[2],p)===s&&sign(t[2],t[0],p)===s){const tm=t.reduce((m,x)=>m|(1<<x),0);circuits.push({id:circuits.length,point:p,triangle:t,triangle_mask:tm,support_mask:tm|(1<<p)});}
  }
 }
 const total=1<<n,full=total-1,interior_masks=Array(total).fill(0);let superset_updates=0;
 for(const c of circuits){const free=full^c.triangle_mask;let sub=free;while(true){interior_masks[sub|c.triangle_mask]|=1<<c.point;superset_updates++;if(sub===0)break;sub=(sub-1)&free;}}
 const convex=[],empty=[],convex_histogram=Array(n+1).fill(0),empty_histogram=Array(n+1).fill(0),sizes=Array(total);
 for(let mask=0;mask<total;mask++){const size=pop(mask);sizes[mask]=size;if((mask&interior_masks[mask])===0){convex.push(mask);convex_histogram[size]++;if(size>=3&&interior_masks[mask]===0){empty.push(mask);empty_histogram[size]++;}}}
 return{format:"convex-subset-circuits-v1",input:copy(input),n,coordinate_denominator:String(L),determinant_denominator:String(L*L),integer_coordinates:points.map(p=>p.map(String)),triples,circuits,interior_masks,sizes,families:{convex,empty},
 summary:{points:n,subsets:total,orientation_triples:triples.length,containment_circuits:circuits.length,convex_subsets:convex.length,empty_polygons:empty.length,convex_histogram,empty_histogram,max_convex_size:convex_histogram.reduce((a,c,i)=>c?i:a,0),max_empty_size:empty.length?empty_histogram.reduce((a,c,i)=>c?i:a,0):null},
 work:{determinants:triples.length,containment_candidates,orientation_lookups,superset_updates,subset_classifications:total}};
}
function openIndex(s){
 if(!s||s.format!=="convex-subset-circuits-v1"||s.interior_masks.length!==2**s.n||s.sizes.length!==2**s.n)throw new TypeError("snapshot shape");
 const n=s.n,full=(1<<n)-1,stats={queries:0,family_rows_scanned:0,circuit_rows_scanned:0,saved_mask_lookups:0};
 function mask(m){if(!Number.isInteger(m)||m<0||m>full)throw new RangeError("mask");return m;}
 function condition(c={}){
  const mode=c.mode===undefined?"convex":c.mode;if(mode!=="convex"&&mode!=="empty")throw new TypeError("mode");
  const include=mask(c.include===undefined?0:c.include),exclude=mask(c.exclude===undefined?0:c.exclude);if(include&exclude)throw new RangeError("conflicting condition");
  const size=c.size===undefined?null:c.size;if(size!==null&&(!Number.isInteger(size)||size<0||size>n))throw new RangeError("size");
  return {mode,include,exclude,size};
 }
 function family(c){const out=[];for(const m of s.families[c.mode]){stats.family_rows_scanned++;if((m&c.include)===c.include&&(m&c.exclude)===0&&(c.size===null||s.sizes[m]===c.size))out.push(m);}return out;}
 function witness(m,p){for(const c of s.circuits){stats.circuit_rows_scanned++;if(c.point===p&&(m&c.triangle_mask)===c.triangle_mask)return copy(c);}throw new Error("saved witness missing");}
 function classify(m){
  mask(m);stats.saved_mask_lookups+=2;const interior=s.interior_masks[m],bad=m&interior,convex=bad===0;
  const result={mask:m,vertices:bits(m,n),size:s.sizes[m],convex,empty_polygon:convex&&s.sizes[m]>=3&&interior===0,interior_mask:interior,interior_points:bits(interior,n)};
  if(bad)result.nonconvex_witness=witness(m,bits(bad,n)[0]);else if(convex&&s.sizes[m]>=3&&interior)result.nonempty_witness=witness(m,bits(interior,n)[0]);
  return result;
 }
 function query(q){stats.queries++;switch(q.op){
  case"summary":return copy(s.summary);
  case"point":{if(!Number.isInteger(q.index)||q.index<0||q.index>=n)throw new RangeError("point");return copy({index:q.index,...s.input.points[q.index],integer_coordinates:s.integer_coordinates[q.index],denominator:s.coordinate_denominator});}
  case"orientation":{if(!Array.isArray(q.vertices)||q.vertices.length!==3||new Set(q.vertices).size!==3)throw new TypeError("triple");const a=q.vertices.slice();a.forEach(i=>{if(!Number.isInteger(i)||i<0||i>=n)throw new RangeError("vertex");});let parity=1;for(let i=0;i<3;i++)for(let j=i+1;j<3;j++)if(a[i]>a[j]){[a[i],a[j]]=[a[j],a[i]];parity=-parity;}const row=s.triples.find(r=>r.vertices.every((v,i)=>v===a[i]));return{vertices:q.vertices.slice(),sign:parity*row.sign,determinant_numerator:String(BigInt(row.determinant_numerator)*BigInt(parity)),determinant_denominator:s.determinant_denominator};}
  case"circuit":{if(!Number.isInteger(q.id)||q.id<0||q.id>=s.circuits.length)throw new RangeError("circuit");return copy(s.circuits[q.id]);}
  case"classify":return classify(q.mask);
  case"count":{const c=condition(q.condition),f=family(c);return{condition:c,count:f.length};}
  case"page":{const c=condition(q.condition),f=family(c);if(!Number.isInteger(q.start)||q.start<0||q.start>f.length||!Number.isInteger(q.limit)||q.limit<0||q.limit>1000)throw new RangeError("page");return{condition:c,count:f.length,masks:f.slice(q.start,q.start+q.limit)};}
  case"select":{const c=condition(q.condition),f=family(c);if(!Number.isInteger(q.rank)||q.rank<0||q.rank>=f.length)throw new RangeError("rank");return{condition:c,rank:q.rank,count:f.length,...classify(f[q.rank])};}
  case"rank":{mask(q.mask);const c=condition(q.condition),f=family(c),rank=f.indexOf(q.mask);return{condition:c,mask:q.mask,rank:rank<0?null:rank,count:f.length};}
  default:throw new TypeError("query op");
 }}
 return{query,stats:()=>copy(stats)};
}
module.exports={buildIndex,openIndex};
