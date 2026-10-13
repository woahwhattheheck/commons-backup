"use strict";

/* Exact finite prefix tree. No dependencies and no import-time calculation. */
const SCHEMA = "consecutive-sum-prefix-tree/v1";
function nat(x, name, min, max) {
  if (!Number.isSafeInteger(x) || x < min || x > max) throw new RangeError(name);
  return x;
}
function rankValue(x) {
  if (typeof x !== "string" || !/^(0|[1-9][0-9]*)$/.test(x)) throw new TypeError("rank must be a nonnegative decimal string");
  return BigInt(x);
}
function construct(input) {
  const N = nat(input.N, "N", 1, 24);
  const limits = Object.assign({max_states:50000,max_append_attempts:300000,max_new_suffix_cells:2000000}, input.limits || {});
  for (const key of Object.keys(limits)) nat(limits[key], key, 1, Number.MAX_SAFE_INTEGER);
  const nodes = [];
  const work = {accepted_states:0,append_attempts:0,new_suffix_cells:0,old_mask_lookups:0,
    rejected_appends:0,accepted_appends:0,witness_saved_cell_comparisons:0,coefficient_additions:0};
  function charge(key, cap) {
    if (work[key] >= limits[cap]) throw new RangeError("construction cap: " + key);
    ++work[key];
  }
  function oldWitness(node, sum) {
    let at = node;
    while (at !== null) {
      for (let i=0;i<at.suffix_sums.length;i++) {
        ++work.witness_saved_cell_comparisons;
        if (at.suffix_sums[i] === sum) return {start:i,end:at.length-1};
      }
      at = at.parent === null ? null : nodes[at.parent];
    }
    throw new Error("saved mask has no interval witness");
  }
  function visit(parent, last, suffix, mask) {
    charge("accepted_states", "max_states");
    const id = nodes.length, length = parent === null ? 0 : nodes[parent].length + 1;
    const node = {id,parent,last,length,total:suffix.length ? suffix[0] : 0,
      interval_sum_mask_hex:mask.toString(16),suffix_sums:suffix,children:[],rejected:[],coefficients:null};
    nodes.push(node);
    for (let value=last+1;value<=N;value++) {
      charge("append_attempts", "max_append_attempts");
      const next = [];
      let added = 0n, collision = null;
      for (let start=0;start<=length;start++) {
        charge("new_suffix_cells", "max_new_suffix_cells");
        const sum = start === length ? value : suffix[start] + value;
        next.push(sum);
        const bit = 1n << BigInt(sum);
        ++work.old_mask_lookups;
        if ((mask & bit) !== 0n) {
          const old = oldWitness(node, sum);
          collision = {value,sum,new_start:start,new_end:length,old_start:old.start,old_end:old.end};
          break;
        }
        added |= bit;
      }
      if (collision) {
        ++work.rejected_appends;
        node.rejected.push(collision);
      } else {
        ++work.accepted_appends;
        const child = visit(id, value, next, mask | added);
        node.children.push({value,node:child});
      }
    }
    const coefficients = [1n];
    for (const edge of node.children) {
      const child = nodes[edge.node];
      for (let j=0;j<child.coefficients.length;j++) {
        if (coefficients[j+1] === undefined) coefficients[j+1] = 0n;
        coefficients[j+1] += BigInt(child.coefficients[j]);
        ++work.coefficient_additions;
      }
    }
    node.coefficients = coefficients.map(String);
    return id;
  }
  visit(null,0,[],0n);
  const coefficients = nodes[0].coefficients;
  return {schema:SCHEMA,N,root:0,order:"numeric sequence lexicographic; a sequence precedes every proper extension",
    interval_indices:"zero-based inclusive",empty_sequence:true,empty_interval_sum:0,
    coefficients,total:coefficients.reduce((a,b)=>a+BigInt(b),0n).toString(),
    maximum_length:coefficients.length-1,maximum_count:coefficients[coefficients.length-1],
    nodes,limits,provenance:input.provenance || {},work};
}
function open(snapshot) {
  if (!snapshot || snapshot.schema !== SCHEMA || !Array.isArray(snapshot.nodes) || snapshot.root !== 0) throw new TypeError("snapshot schema");
  const N=nat(snapshot.N,"N",1,24), nodes=snapshot.nodes;
  /* Structural checks only: no interval sums, masks, coefficients or witnesses are reconstructed. */
  for (let id=0;id<nodes.length;id++) {
    const n=nodes[id];
    if (!n || n.id!==id || !Array.isArray(n.children) || !Array.isArray(n.rejected) ||
        !Array.isArray(n.suffix_sums) || !Array.isArray(n.coefficients) ||
        n.suffix_sums.length!==n.length || typeof n.interval_sum_mask_hex!=="string") throw new TypeError("node shape");
    if ((id===0 && n.parent!==null) || (id!==0 && (!Number.isSafeInteger(n.parent) || n.parent<0 || n.parent>=id))) throw new TypeError("parent shape");
    for (const e of n.children) if (!Number.isSafeInteger(e.node) || e.node<=id || e.node>=nodes.length) throw new TypeError("child shape");
    for (const c of n.coefficients) if (typeof c!=="string" || !/^(0|[1-9][0-9]*)$/.test(c)) throw new TypeError("coefficient shape");
  }
  const work={queries:0,edge_scans:0,coefficient_reads:0,path_node_reads:0,rank_additions:0,rank_subtractions:0,
    selections:0,ranks:0,prefix_steps:0,node_reads:0,rejection_reads:0,
    construction_calls:0,new_interval_sums:0,new_suffix_cells:0,coefficient_recurrences:0,witness_reconstruction:0};
  function sequence(x,name) {
    if (!Array.isArray(x)) throw new TypeError(name);
    let old=0;
    for (const v of x) { nat(v,name,1,N); if (v<=old) throw new RangeError(name+" must be strictly increasing"); old=v; }
    return x;
  }
  function path(id) {
    const a=[];
    while (id!==0) { const n=nodes[id]; ++work.path_node_reads; a.push(n.last); id=n.parent; }
    return a.reverse();
  }
  function locate(prefix) {
    sequence(prefix,"prefix");
    let id=0;
    for (let i=0;i<prefix.length;i++) {
      const value=prefix[i], n=nodes[id];
      ++work.prefix_steps;
      let child=null;
      for (const e of n.children) { ++work.edge_scans; if(e.value===value){child=e.node;break;} }
      if(child===null) {
        const rejection=n.rejected.find(x=>x.value===value);
        ++work.rejection_reads;
        return {valid:false,node:id,accepted_prefix:prefix.slice(0,i),rejected_value:value,collision:rejection || null};
      }
      id=child;
    }
    return {valid:true,node:id};
  }
  function weight(id,size) {
    const n=nodes[id];
    if(size===null) { let v=0n; for(const c of n.coefficients){++work.coefficient_reads;v+=BigInt(c);} return v; }
    const k=size-n.length;
    if(k<0 || k>=n.coefficients.length) return 0n;
    ++work.coefficient_reads; return BigInt(n.coefficients[k]);
  }
  function family(options) {
    const opts=options || {}, prefix=opts.prefix===undefined?[]:opts.prefix;
    const size=opts.size===undefined?null:nat(opts.size,"size",0,N);
    const loc=locate(prefix);
    return {prefix:prefix.slice(),size,loc,count:loc.valid?weight(loc.node,size):0n};
  }
  function selectCore(f,rank) {
    if(rank<0n || rank>=f.count) throw new RangeError("rank outside family");
    let id=f.loc.node, a=f.prefix.slice(), r=rank;
    ++work.selections;
    while(true) {
      const n=nodes[id];
      if(f.size===null || n.length===f.size) {
        if(r===0n) return {sequence:a,node:id,rank:rank.toString()};
        --r; ++work.rank_subtractions;
      }
      let selected=false;
      for(const e of n.children) {
        ++work.edge_scans;
        const count=weight(e.node,f.size);
        if(r<count){id=e.node;a.push(e.value);selected=true;break;}
        r-=count; ++work.rank_subtractions;
      }
      if(!selected) throw new Error("saved coefficients do not select");
    }
  }
  function rankCore(f,a) {
    sequence(a,"sequence"); ++work.ranks;
    if(!f.loc.valid || (f.size!==null && a.length!==f.size) || a.length<f.prefix.length ||
       f.prefix.some((v,i)=>a[i]!==v)) return {member:false,rank:null};
    let id=f.loc.node, r=0n;
    for(let i=f.prefix.length;i<a.length;i++) {
      const n=nodes[id];
      if(f.size===null || n.length===f.size){++r;++work.rank_additions;}
      let selected=null;
      for(const e of n.children) {
        ++work.edge_scans;
        if(e.value<a[i]){r+=weight(e.node,f.size);++work.rank_additions;}
        else if(e.value===a[i]){selected=e.node;break;}
        else break;
      }
      if(selected===null) {
        ++work.rejection_reads;
        return {member:false,rank:null,accepted_prefix:a.slice(0,i),rejected_value:a[i],
          collision:n.rejected.find(x=>x.value===a[i]) || null};
      }
      id=selected;
    }
    return {member:true,rank:r.toString(),node:id};
  }
  const api={
    summary() {
      ++work.queries;
      return {N,total:snapshot.total,coefficients:snapshot.coefficients.slice(),
        maximum_length:snapshot.maximum_length,maximum_count:snapshot.maximum_count,nodes:nodes.length,
        order:snapshot.order,interval_indices:snapshot.interval_indices,construction_work:snapshot.work};
    },
    family(options) {
      ++work.queries; const f=family(options);
      return {prefix:f.prefix,size:f.size,count:f.count.toString(),prefix_status:f.loc};
    },
    select(rank,options) {
      ++work.queries; const f=family(options);
      return Object.assign({prefix:f.prefix,size:f.size,count:f.count.toString()},selectCore(f,rankValue(rank)));
    },
    rank(a,options) {
      ++work.queries; const f=family(options);
      return Object.assign({prefix:f.prefix,size:f.size,count:f.count.toString()},rankCore(f,a));
    },
    page(start,limit,options) {
      ++work.queries; const f=family(options), r=rankValue(start);
      nat(limit,"limit",0,1000);
      if(r>f.count) throw new RangeError("page start");
      const rows=[];
      for(let i=0;i<limit && r+BigInt(i)<f.count;i++) rows.push(selectCore(f,r+BigInt(i)));
      return {prefix:f.prefix,size:f.size,count:f.count.toString(),start: r.toString(),rows,
        next_rank:(r+BigInt(rows.length)).toString(),complete:r+BigInt(rows.length)===f.count};
    },
    prefix(prefix) {
      ++work.queries; const loc=locate(prefix);
      if(!loc.valid) return loc;
      const n=nodes[loc.node]; ++work.node_reads;
      return {valid:true,prefix:prefix.slice(),node:loc.node,coefficients:n.coefficients.slice(),
        accepted:n.children.map(e=>({value:e.value,node:e.node,completion_count:weight(e.node,null).toString()})),
        rejected:n.rejected.map(x=>Object.assign({},x))};
    },
    node(id) {
      ++work.queries; nat(id,"node",0,nodes.length-1); ++work.node_reads;
      return {sequence:path(id),record:nodes[id]};
    },
    work(){return Object.assign({},work);}
  };
  return api;
}
module.exports={SCHEMA,construct,open};
