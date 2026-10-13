"use strict";
const fs=require("fs"),path=require("path");
function loadSavedIndex(directory=__dirname){
 const read=name=>JSON.parse(fs.readFileSync(path.join(directory,name),"utf8"));
 const manifest=read("certificate_manifest.json");
 if(manifest.schema!=="rectangular-matching-manifest/v1")throw new TypeError("manifest schema");
 const states=[];for(const item of manifest.shards){const shard=read(item.path);if(shard.begin!==states.length||shard.states.length!==item.count)throw new Error("shard range");states.push(...shard.states);}
 return require("./rectangular_matching.cjs").createIndex({...manifest.certificate,states});
}
module.exports={loadSavedIndex};
