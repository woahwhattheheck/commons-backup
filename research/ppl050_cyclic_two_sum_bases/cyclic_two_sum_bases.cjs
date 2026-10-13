"use strict";
const VERSION="1.0.0";
function nat(x,name){if(typeof x==="number"){if(!Number.isSafeInteger(x)||x<0)throw Error(name+" natural");return BigInt(x);}if(typeof x!=="string"||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>1200)throw Error(name+" decimal natural");return BigInt(x);}
function integer(x,min,max,name){if(!Number.isSafeInteger(x)||x<min||x>max)throw Error(name+" out of range");return x;}
function hex(a){return Array.from(a,x=>x.toString(16).padStart(2,"0")).join("");}
function unhex(s,m){if(typeof s!=="string"||s.length!==2*m||!/^[0-9a-f]+$/.test(s))throw Error("profile encoding");return Array.from({length:m},(_,i)=>parseInt(s.slice(2*i,2*i+2),16));}
function floor(a,b){return a>=0n?a/b:-((-a+b-1n)/b);}
function compileCyclicBases(input){
 const m=integer(input.modulus,2,16,"modulus"),U=2**m,full=U-1,rows=[],R=[],C=[],pairs=[],fibers=Array.from({length:m},()=>[]);
 const stats={subsets:U,profile_cells:2*U*m,ordered_base_pairs:m*m,parent_profile_cells:0,diagonal_updates:0,off_diagonal_updates:0,immediate_deletion_checks:0};
 for(let a=0;a<m;a++)for(let b=0;b<m;b++){const row={id:pairs.length,a,b,residue:(a+b)%m,carry:Math.floor((a+b)/m),support_mask:(1<<a)|(1<<b)};pairs.push(row);fibers[row.residue].push(row.id);}
 R.push(new Uint8Array(m));C.push(new Uint8Array(m));rows.push([0,0,0,0,0,0,null,hex(R[0]),hex(C[0])]);
 const bases=[],minimal=[],bySize=Array(m+1).fill(0),minimalBySize=Array(m+1).fill(0);
 let minSize=m+1,minMax=m+1;const signatureMap=new Map([["0,0,0,0,0,0,-1",1]]);
 for(let mask=1;mask<U;mask++){
  const bit=mask&-mask,x=31-Math.clz32(bit),parent=mask^bit,r=R[parent].slice(),c=C[parent].slice();stats.parent_profile_cells+=2*m;
  let s=(2*x)%m;r[s]++;if(2*x>=m)c[s]++;stats.diagonal_updates++;
  for(let b=0;b<m;b++)if(parent&(1<<b)){s=(x+b)%m;r[s]+=2;if(x+b>=m)c[s]+=2;stats.off_diagonal_updates++;}
  R.push(r);C.push(c);let covered=0,minimum=m,maximum=0,energy=0,lastMissing=-1;
  for(let t=0;t<m;t++){if(r[t])covered|=1<<t;minimum=Math.min(minimum,r[t]);maximum=Math.max(maximum,r[t]);energy+=r[t]*r[t];if(r[t]===c[t])lastMissing=t;}
  const size=rows[parent][0]+1;let essential=0,conductor=null;
  if(covered===full){bases.push(mask);bySize[size]++;minSize=Math.min(minSize,size);minMax=Math.min(minMax,maximum);conductor=lastMissing+1;for(let b=0;b<m;b++)if(mask&(1<<b)){stats.immediate_deletion_checks++;if(rows[mask^(1<<b)][1]!==full)essential|=1<<b;}if(essential===mask){minimal.push(mask);minimalBySize[size]++;}}
  rows.push([size,covered,minimum,maximum,energy,essential,conductor,hex(r),hex(c)]);
  const key=[size,covered===full?1:0,minimum,maximum,energy,essential===mask&&covered===full?1:0,conductor===null?-1:conductor].join(",");signatureMap.set(key,(signatureMap.get(key)||0)+1);
 }
 const minimumBases=bases.filter(mask=>rows[mask][0]===minSize),minimaxBases=bases.filter(mask=>rows[mask][3]===minMax);
 const snapshot={schema:"commons.cyclic_two_sum_bases/v1",version:VERSION,modulus:m,universe:U,row_columns:["size","covered_mask","minimum_ordered","maximum_ordered","ordered_energy","essential_mask","periodic_conductor","ordered_hex","carry_hex"],rows,pairs,fibers,basis_ids:bases,minimal_basis_ids:minimal,minimum_basis_ids:minimumBases,minimax_basis_ids:minimaxBases,summary:{modulus:m,subsets:U,bases:bases.length,inclusion_minimal_bases:minimal.length,minimum_size:minSize,minimum_size_count:minimumBases.length,minimum_maximum_ordered_multiplicity:minMax,minimax_count:minimaxBases.length,basis_size_histogram:bySize,minimal_size_histogram:minimalBySize},profile_signatures:Array.from(signatureMap,([key,count])=>({signature:key.split(",").map(Number),count})),statistics:stats};
 return {snapshot,summary:snapshot.summary};
}
function openCyclicBases(s){
 if(!s||s.schema!=="commons.cyclic_two_sum_bases/v1"||s.version!==VERSION)throw Error("snapshot schema/version");const m=integer(s.modulus,2,16,"modulus"),U=2**m,full=U-1;
 if(s.universe!==U||!Array.isArray(s.rows)||s.rows.length!==U||s.pairs.length!==m*m||s.fibers.length!==m)throw Error("snapshot dimensions");
 for(const row of s.rows){if(!Array.isArray(row)||row.length!==9||typeof row[7]!=="string"||row[7].length!==2*m||typeof row[8]!=="string"||row[8].length!==2*m)throw Error("row encoding");}
 for(let i=0;i<s.pairs.length;i++)if(s.pairs[i].id!==i)throw Error("pair IDs");
 const stats={queries:0,rows_scanned:0,profile_cells_decoded:0,pair_rows_examined:0,lift_branches:0,derived_diagonal_terms:0,derived_unordered_cells:0,new_ordered_profile_recurrences:0,new_carry_profile_recurrences:0,new_subset_classification:0};
 const copy=x=>JSON.parse(JSON.stringify(x)),validMask=x=>integer(x,0,full,"mask"),members=mask=>Array.from({length:m},(_,i)=>i).filter(i=>mask&(1<<i));
 function profile(mask){validMask(mask);const a=s.rows[mask];stats.profile_cells_decoded+=2*m;const r=unhex(a[7],m),c=unhex(a[8],m),diagonal=Array(m).fill(0);for(const x of members(mask)){diagonal[(2*x)%m]++;stats.derived_diagonal_terms++;}stats.derived_unordered_cells+=m;return {mask,members:members(mask),size:a[0],covered_mask:a[1],missing_residues:Array.from({length:m},(_,i)=>i).filter(i=>!(a[1]&(1<<i))),basis:a[1]===full,inclusion_minimal:a[1]===full&&a[5]===mask,minimum_ordered:a[2],maximum_ordered:a[3],ordered_energy:a[4],essential_mask:a[5],periodic_conductor:a[6],ordered:r,carry:c,diagonal,unordered:r.map((v,i)=>(v+diagonal[i])/2)};}
 function selected(filter={}){
  if(filter===null||typeof filter!=="object"||Array.isArray(filter))throw Error("filter object");const basis=filter.basis===undefined?true:filter.basis;if(basis!==true&&basis!==false&&basis!==null)throw Error("basis filter");const required=validMask(filter.required_mask??0),forbidden=validMask(filter.forbidden_mask??0);if(required&forbidden)throw Error("contradictory masks");
  const size=filter.size===undefined?null:integer(filter.size,0,m,"size"),max=filter.maximum_ordered_at_most===undefined?m:integer(filter.maximum_ordered_at_most,0,m,"max multiplicity");if(filter.minimal!==undefined&&typeof filter.minimal!=="boolean")throw Error("minimal Boolean");
  const ids=[];for(let mask=0;mask<U;mask++){stats.rows_scanned++;const r=s.rows[mask],isBasis=r[1]===full,isMinimal=isBasis&&r[5]===mask;if((basis!==null&&basis!==isBasis)||(size!==null&&r[0]!==size)||r[3]>max||(mask&required)!==required||(mask&forbidden)||(filter.minimal!==undefined&&filter.minimal!==isMinimal))continue;ids.push(mask);}return ids;
 }
 function basePairs(mask,residue,unordered=false){validMask(mask);integer(residue,0,m-1,"residue");const out=[];for(const id of s.fibers[residue]){stats.pair_rows_examined++;const p=s.pairs[id];if((mask&p.support_mask)===p.support_mask&&(!unordered||p.a<=p.b))out.push(copy(p));}return out;}
 function branches(mask,target,order){
  validMask(mask);if(order!=="ordered"&&order!=="unordered")throw Error("order must be ordered or unordered");const t=nat(target,"target"),M=BigInt(m),residue=Number(t%M),K=t/M,base=basePairs(mask,residue,false),out=[];
  for(const p of base){const S=K-BigInt(p.carry);if(S<0n)continue;let last=S;if(order==="unordered"){const b=floor(M*S+BigInt(p.b-p.a),2n*M);if(b<last)last=b;}if(last<0n)continue;stats.lift_branches++;out.push({...p,split_sum:S.toString(),first:"0",last:last.toString(),count:(last+1n).toString()});}
  return {target:t.toString(),residue,quotient:K.toString(),order,branches:out,total:out.reduce((a,b)=>a+BigInt(b.count),0n).toString()};
 }
 return {
 summary(){stats.queries++;return copy(s.summary);},
 profile(mask){stats.queries++;return profile(mask);},
 profilesPage(offset=0,limit=32){stats.queries++;integer(offset,0,U,"offset");integer(limit,0,128,"limit");const out=[];for(let mask=offset;mask<Math.min(U,offset+limit);mask++)out.push(profile(mask));return {offset,total:U,next:Math.min(U,offset+limit),items:out};},
 familyCount(filter={}){stats.queries++;return {filter:copy(filter),count:selected(filter).length,ordering:"increasing residue mask"};},
 familyPage(filter={},offset=0,limit=32){stats.queries++;const ids=selected(filter);integer(offset,0,ids.length,"offset");integer(limit,0,256,"limit");return {filter:copy(filter),offset,total:ids.length,next:Math.min(ids.length,offset+limit),items:ids.slice(offset,offset+limit).map(mask=>({mask,members:members(mask)}))};},
 familySelect(filter,rank){stats.queries++;const ids=selected(filter);integer(rank,0,ids.length-1,"rank");return {rank,total:ids.length,...profile(ids[rank])};},
 familyRank(filter,mask){stats.queries++;validMask(mask);const ids=selected(filter);return {mask,rank:ids.indexOf(mask),total:ids.length,member:ids.includes(mask)};},
 pairFiber(mask,residue,order="ordered"){stats.queries++;if(order!=="ordered"&&order!=="unordered")throw Error("order");return {mask,residue,order,pairs:basePairs(mask,residue,order==="unordered")};},
 deletionCertificate(mask){stats.queries++;validMask(mask);if(s.rows[mask][1]!==full)throw Error("basis required");const rows=[];for(const a of members(mask)){const child=mask^(1<<a),r=s.rows[child],missing=[];for(let t=0;t<m;t++)if(!(r[1]&(1<<t)))missing.push(t);rows.push({removed:a,child_mask:child,child_is_basis:r[1]===full,missing_residues:missing,first_missing_pairs:missing.length?basePairs(mask,missing[0],false):[]});}return {mask,minimal:s.rows[mask][5]===mask,deletions:rows};},
 liftCount(mask,target){stats.queries++;validMask(mask);const t=nat(target,"target"),M=BigInt(m),residue=Number(t%M),K=t/M,row=s.rows[mask];stats.profile_cells_decoded+=2;const r=parseInt(row[7].slice(2*residue,2*residue+2),16),c=parseInt(row[8].slice(2*residue,2*residue+2),16),ordered=(K+1n)*BigInt(r)-BigInt(c),diagonal=(t%2n===0n&&(mask&(1<<Number((t/2n)%M))))?1n:0n;return {mask,target:t.toString(),residue,quotient:K.toString(),modular_ordered:r,carry:c,ordered:ordered.toString(),diagonal:diagonal.toString(),unordered:((ordered+diagonal)/2n).toString(),periodic_conductor:row[6]};},
 liftBranches(mask,target,order="ordered"){stats.queries++;return branches(mask,target,order);},
 liftSelect(mask,target,rank,order="ordered"){stats.queries++;const plan=branches(mask,target,order);let k=nat(rank,"rank");if(k>=BigInt(plan.total))throw Error("rank out of family");const original=k;for(const b of plan.branches){const count=BigInt(b.count);if(k>=count){k-=count;continue;}const x=BigInt(b.a)+BigInt(m)*k,y=BigInt(b.b)+BigInt(m)*(BigInt(b.split_sum)-k);return {mask,target:plan.target,order,rank:original.toString(),total:plan.total,pair:[x.toString(),y.toString()],residue_pair:[b.a,b.b],quotient_split:[k.toString(),(BigInt(b.split_sum)-k).toString()],ordering:"base residue pair (a,b), then first quotient",branch:b};}throw Error("unreachable selection");},
 liftRank(mask,x,y,order="ordered"){stats.queries++;const X=nat(x,"x"),Y=nat(y,"y");if(order==="unordered"&&X>Y)throw Error("unordered pair must satisfy x<=y");const plan=branches(mask,(X+Y).toString(),order),a=Number(X%BigInt(m)),b=Number(Y%BigInt(m)),k=X/BigInt(m);let before=0n;for(const branch of plan.branches){if(branch.a===a&&branch.b===b&&k<=BigInt(branch.last))return {mask,target:plan.target,order,pair:[X.toString(),Y.toString()],member:true,rank:(before+k).toString(),total:plan.total};before+=BigInt(branch.count);}return {mask,target:plan.target,order,pair:[X.toString(),Y.toString()],member:false,rank:null,total:plan.total};},
 statistics(){return copy(stats);}
 };
}
module.exports={VERSION,compileCyclicBases,openCyclicBases};
