import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const bytes=p=>fs.readFileSync(path.join(root,p));
const json=p=>JSON.parse(bytes(p));
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
let checks=0;const check=(value,label)=>{assert.ok(value,label);checks++;};
const manifest=json('SOURCE-MANIFEST.json'),seen=new Set();
for(const row of manifest.files){check(typeof row.path==='string'&&!row.path.includes('\\')&&!row.path.startsWith('/')&&!row.path.split('/').includes('..')&&!seen.has(row.path),'safe unique file');seen.add(row.path);const b=bytes(row.path);check(b.length===row.bytes&&sha(b)===row.sha256,'manifest '+row.path);}
for(const [dir,run,receipt]of [['slab047-admission','runtime','DOWNLOAD-AND-CLOSURE.json'],['slab047b-admission','preflight-runtime','PREFLIGHT-DOWNLOAD.json'],['slab047b-admission','gpu-runtime','GPU-DOWNLOAD-AND-CLOSURE.json']])for(const row of json(dir+'/'+receipt).files){const b=bytes(dir+'/'+run+'/'+row.name);check(b.length===row.bytes&&sha(b)===row.sha256,'original download '+row.name);}
const run='slab047b-admission/gpu-runtime/',state=json(run+'state.json'),reservation=json(run+'reservation.json');
check(state.phase==='completed'&&state.inference_requests_completed===20&&state.inference_requests_reserved===20&&!state.retry_allowed&&state.cleanup_verified&&!state.final_deliverable_accepted,'terminal scope');
check(sha(bytes(run+'serve047.py'))===reservation.controller_sha256&&sha(Buffer.from(reservation.policy_bytes))===reservation.policy_sha256,'controller policy binding');
const fixture=json('source/docs/sentilab/evidence/SLAB-018/fixtures/DATA-MANIFEST.json');
for(const name of ['eval.jsonl','train.jsonl'])check(sha(bytes('source/docs/sentilab/evidence/SLAB-018/fixtures/'+name))===fixture.data_files[name],'fixture manifest '+name);
const rows=bytes('source/docs/sentilab/evidence/SLAB-018/fixtures/eval.jsonl').toString().trim().split('\n').map(JSON.parse),train=bytes('source/docs/sentilab/evidence/SLAB-018/fixtures/train.jsonl').toString().trim().split('\n').map(JSON.parse);
check(rows.length===20&&train.length===200&&new Set(rows.map(r=>r.source_record_id)).size===6&&rows.every(r=>train.some(t=>t.source_record_id===r.source_record_id)),'six repeated training-source fixtures');
for(let i=0;i<20;i++){const n=String(i).padStart(2,'0'),receipt=json(run+'inference-'+n+'.json'),request=json(run+'request-'+n+'.json'),response=json(run+'response-'+n+'.json'),row=rows[i];check(sha(bytes(run+'request-'+n+'.json'))===receipt.request_sha256&&sha(bytes(run+'response-'+n+'.json'))===receipt.response_sha256,'request response hashes '+i);assert.deepEqual(request,{max_tokens:80,messages:[{content:row.system,role:'system'},{content:row.instruction,role:'user'}],model:'fixture',seed:818,temperature:0});checks++;assert.deepEqual(JSON.parse(response.choices[0].message.content),JSON.parse(row.output));checks++;check(receipt.row_id===row.row_id&&receipt.http_status===200&&response.choices[0].finish_reason==='stop','fixture receipt '+i);}
const closure=json('slab047b-admission/GPU-DOWNLOAD-AND-CLOSURE.json');check(closure.docker_inventory.exit===0&&closure.docker_inventory.stdout===''&&closure.localhost18047_connect_code===111&&closure.worker_lock_free,'independent later closure');
console.log(JSON.stringify({status:'PASS',checks,files:manifest.files.length,exactFixtures:20,uniqueTrainingSourceCases:6,deviceActions:0,scope:'offline packet integrity and fixture reproduction only'}));
