// Static source collection only. No model, simulator, optimizer or network execution.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const out=__dirname,task=path.dirname(out),workspace=path.dirname(path.dirname(task));
const day=path.join(workspace,'.sentinelayer/sentilab-planning/gpt-astra-carter/daytime-2026-10-31');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const recordNames=[
 ['b978e20952a205bb3deb6ce96fc7b5ff241359f99c4572d83aa642e7c9087b31.json','ANETA-56873.json'],
 ['6a8fec9a3bcaefdd304a8deec23444c7130240d2ec8163d837e2cd16e73bef03.json','FORGE-50176262.json'],
 ['1e19f7a9a31c1b27f2e4fc3ac34b7e1debad3c2073f7805a00298e3399c176ba.json','FORGE-13da40ed.json'],
 ['2c5c7992da55743d8fd3c5231fdbf5bc4d52794a99d112af4703f0167f3d926b.json','ROOT-56874.json']
];
const records=[];
for(const [name,dest]of recordNames){const from=path.join(day,'state/records',name),b=fs.readFileSync(from),record=JSON.parse(b.toString('utf8'));fs.writeFileSync(path.join(out,dest),b,{flag:'wx'});records.push({path:dest,sourcePath:from,bytes:b.length,sha256:sha(b),sourceId:record.sourceId,sequenceId:record.sequenceId,timestamp:record.timestamp,sourceRecordSha256:record.sourceRecordSha256});if(dest==='ANETA-56873.json')fs.writeFileSync(path.join(out,'ANETA-DRAFT.md'),record.text+'\n',{flag:'wx'});}
const batch=fs.readFileSync(path.join(day,'wake-1605-batch.json'));
const excerpts=[];
for(const [rel,first,last]of [['sundai_hotspot6/temperature_grid.c',1783,1798],['sundai_tap/passive_interposer.py',197,210],['sundai_hotspot/slab049.py',863,868]]){const from=path.join(task,'pr56-native6-1525/source',rel),b=fs.readFileSync(from),lines=b.toString('utf8').split(/\r?\n/);excerpts.push({path:rel,exactHead:'6413a3c0cc2b6280dc2bf063812374e0c8d3d337',sourceSha256:sha(b),first,last,lines:lines.slice(first-1,last).map((text,i)=>({line:first+i,text}))});}
fs.writeFileSync(path.join(out,'PRIOR-SOURCE-EXCERPTS.json'),JSON.stringify(excerpts,null,2)+'\n',{flag:'wx'});
fs.writeFileSync(path.join(out,'SOURCE-BINDINGS.json'),JSON.stringify({schema:'sentilab-challenge-math-source-bindings/1',at:new Date().toISOString(),records,batch:{path:path.join(day,'wake-1605-batch.json'),sha256:sha(batch),scope:'Used as source index; only requested original records retained'},priorExactSourceExcerpts:'PRIOR-SOURCE-EXCERPTS.json',executions:{models:0,solves:0,optimizers:0,network:0,posts:0,sourceMutations:0},delegation:'Reusing prior mesh_algebra reviewer was attempted but unavailable: agent thread limit reached; review completed independently.'},null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({sources:records.map(x=>({path:x.path,sourceId:x.sourceId,sha256:x.sha256})),priorExcerpts:excerpts.length},null,2));
