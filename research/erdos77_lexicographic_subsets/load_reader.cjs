'use strict';
function loadReader(manifest,read){if(manifest.schema!=='commons.cycle_lexicographic_reader_manifest/v1')throw new TypeError('manifest');const outputs=[];for(const s of manifest.shards){if(s.start!==outputs.length)throw new TypeError('start');const a=JSON.parse(read(s.path));if(!Array.isArray(a)||a.length!==s.count)throw new TypeError('count');outputs.push(...a);}return{...manifest.base,outputs};}
module.exports={loadReader};
