'use strict';
function loadIndex(manifest,read){if(manifest.format!=='triangle-edge-partition-shards-v1')throw new Error('format');const out={...manifest.data};out.first_bad_triangle=[];out.branches=[];out.rows=[];out.partition_totals=[];for(const s of manifest.state_shards){if(s.start!==out.rows.length)throw new Error('start');const a=read(s.path);if(!Array.isArray(a)||a.length!==s.count)throw new Error('count');for(const r of a){out.first_bad_triangle.push(r[0]);out.branches.push(r[1]);out.rows.push(r[2]);out.partition_totals.push(r[3]);}}return out;}
module.exports={loadIndex};
