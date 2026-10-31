// Read exact local Git objects and already verified successor bytes. No source is executed.
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process'),crypto=require('node:crypto');
const base=__dirname,repo='C:/Users/carth/Desktop/projects/PlexAura_Inc/SentinelLayer/sentilab';
const draft='d25046256b4a712b529977f31e10b7e32248a9c0',head='7f70baf56998cdeea9fcaa56954fc78f8f6c8071';
const previous=path.join(base,'../pr56-7f70baf-review-2225'),source=path.join(previous,'source');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const gitHash=b=>crypto.createHash('sha1').update(Buffer.from(`blob ${b.length}\0`)).update(b).digest('hex');
function git(args){return cp.execFileSync('git',['-C',repo,...args],{windowsHide:true,timeout:30000,maxBuffer:4*1024*1024});}
function save(n,b){const p=path.join(base,n);fs.mkdirSync(path.dirname(p),{recursive:true});fs.writeFileSync(p,b,{flag:'wx'});}
const treeRaw=git(['ls-tree','-r',draft]);save('DRAFT-GIT-TREE.txt',treeRaw);
const tree=new Map(treeRaw.toString('utf8').trimEnd().split('\n').map(l=>{const m=l.match(/^(\d+) (\w+) ([0-9a-f]+)\t(.+)$/);if(!m)throw Error('tree');return [m[4],{mode:m[1],type:m[2],blob:m[3]}];}));
const manifestBytes=fs.readFileSync(path.join(previous,'SOURCE-MANIFEST.json')),manifest=JSON.parse(manifestBytes);
if(manifest.head!==head)throw Error('successor head');
const byPath=new Map(manifest.files.map(f=>[f.path,f]));
const common=['sundai_tap/passive_interposer.py','sundai_tap/system.py','sundai_tap/util/fill_space.py','sundai_tap/util/hotspot.config','sundai_hotspot/temperature_grid.c','sundai_hotspot/temperature_grid.h','sundai_hotspot/temperature.c','sundai_hotspot/temperature.h','sundai_hotspot/hotspot.c','sundai_hotspot/Makefile','sundai_hotspot/tap_oracle.py','sundai_hotspot/tap_oracle_worker.py'];
const newer=['sundai_hotspot6/temperature_grid.c','sundai_hotspot6/temperature_grid.h','sundai_hotspot6/temperature.c','sundai_hotspot6/temperature.h','sundai_hotspot6/hotspot.c','sundai_hotspot6/hotspot.config','sundai_hotspot6/Makefile','sundai_hotspot6/UPSTREAM_COMMIT','sundai_hotspot6/UPSTREAM_BLOBS.txt','scripts/build_hotspot6.sh','sundai_hotspot/evaluators.py','sundai_hotspot/slab049.py','sundai_hotspot/gate_zero.py','sundai_hotspot/reference_validation.py',...['ascend910-tap25d-fig6a-raw-45mm','micro150-tap25d-fig5a-raw-45mm'].flatMap(x=>['new_hotspot.config','samplelayers.lcf','sample.ptrace','sampleL4_ChipLayer.flp'].map(n=>`docs/sentilab/diagnostics/SLAB-049/references/${x}/${n}`))];
const files=[];
for(const p of common){const entry=tree.get(p);if(!entry||entry.type!=='blob'||entry.mode==='120000')throw Error('draft path '+p);const b=git(['show',`${draft}:${p}`]);if(gitHash(b)!==entry.blob)throw Error('draft blob');if(p==='sundai_tap/passive_interposer.py'&&hash(b)!=='cecc5b85f7dd8e6a3816c635879eb06193a270595f6bdbc71b76e4ef96f227df')throw Error('draft writer differs from TRACE48');save('draft-d2504625/'+p,b);files.push({set:'draft',commit:draft,path:p,bytes:b.length,gitBlob:entry.blob,sha256:hash(b),packetPath:'draft-d2504625/'+p});}
for(const p of [...common,...newer]){const f=byPath.get(p);if(!f)throw Error('successor path '+p);const b=fs.readFileSync(path.join(source,p));if(hash(b)!==f.sha256||gitHash(b)!==f.gitBlob||b.length!==f.bytes)throw Error('successor bytes '+p);save('successor-7f70baf5/'+p,b);files.push({set:'successor',commit:head,path:p,bytes:b.length,gitBlob:f.gitBlob,sha256:f.sha256,packetPath:'successor-7f70baf5/'+p});}
const comparisons=common.map(p=>{const a=files.find(f=>f.set==='draft'&&f.path===p),b=files.find(f=>f.set==='successor'&&f.path===p);return {path:p,draftSha256:a.sha256,successorSha256:b.sha256,byteIdentical:a.sha256===b.sha256};});
const room=path.join(base,'../../../.sentinelayer/sentilab-planning/gpt-astra-carter/daytime-2026-10-31/cad-room/read-2232-new/RECEIPT.json');
const receiptBytes=fs.readFileSync(room),roomReceipt=JSON.parse(receiptBytes);
const ids=['6ec0f5df-997a-4369-8a71-c412f0583c77','96f0434f-4f34-47cb-bd8a-8df2585c4574','383df803-be5f-4d23-a8ad-d499f67d944c'];
const records=roomReceipt.records.filter(r=>ids.includes(r.sourceId));if(records.length!==3)throw Error('records');
save('CAD-SOURCE-REQUESTS.json',JSON.stringify({capture:room,receiptSha256:hash(receiptBytes),records},null,2)+'\n');
const result={at:new Date().toISOString(),scope:'Exact object/data reads only; none of the captured source code executed.',draftCommit:draft,draftWriterPinMatched:true,successorCommit:head,successorManifest:{path:path.join(previous,'SOURCE-MANIFEST.json'),sha256:hash(manifestBytes)},localGitReadOnly:true,files,comparisons};
save('SOURCE-BINDINGS.json',JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({files:files.length,totalBytes:files.reduce((n,f)=>n+f.bytes,0),comparisons,draftWriterPinMatched:true},null,2));
