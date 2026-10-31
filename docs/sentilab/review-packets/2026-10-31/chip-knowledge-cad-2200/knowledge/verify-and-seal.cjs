const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const checks=[];
const check=(name,condition)=>{checks.push({name,passed:!!condition});if(!condition)throw new Error(name);};
const bindings=JSON.parse(fs.readFileSync(path.join(__dirname,'SOURCE-BINDINGS.json'),'utf8'));
const sourceTexts={};
for(const source of bindings.sources){
 const bytes=fs.readFileSync(source.absolute_path);sourceTexts[source.id]=bytes.toString('utf8');
 check('source-hash:'+source.id,sha(bytes)===source.sha256&&bytes.length===source.bytes);
}
const cards=fs.readFileSync(path.join(__dirname,'knowledge.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
check('four-unique-cards',cards.length===4&&new Set(cards.map(c=>c.card_id)).size===4);
const required=['claim','evidence_kind','conditions','objective_metric','comparator_intervention','reported_effect','uncertainty_missingness','independent_verification_scope','architect_usefulness','confidence','sources'];
let quoteChecks=0;
for(const card of cards){
 check('fields:'+card.card_id,required.every(k=>Object.hasOwn(card,k)));
 check('no-new-run:'+card.card_id,card.new_solver_model_gpu_calls===0&&card.public_hardware_measurement===false);
 for(const [n,ref] of card.sources.entries()){
   const source=bindings.sources.find(s=>s.id===ref.source_id);
   const slice=sourceTexts[ref.source_id].split(/\r?\n/).slice(ref.line_start-1,ref.line_end).join('\n');
   check('quote:'+card.card_id+':'+n,source.sha256===ref.sha256&&source.absolute_path===ref.absolute_path&&slice.includes(ref.quote));
   quoteChecks++;
 }
}
const diagnosis=bindings.sources.find(s=>s.id==='diagnosis');
check('frozen-diagnosis-exact',diagnosis.sha256==='132bf28fc6d962ae159a942084b3a7fe4c17fd52dc65da7a13789939a0460a7d'&&diagnosis.bytes===68772);
const fields=JSON.parse(sourceTexts.fields), fieldCard=cards.find(c=>c.card_id==='carter-retained-ascend-stack-drop-20261031');
check('field-row-transcription',fields.rows.length===8&&fields.rows.every((r,i)=>fieldCard.reported_effect.cases[i].case===r.case&&fieldCard.reported_effect.cases[i].spreader_to_sink_drop_K===Number(r.spreaderToSinkDropK.toFixed(2))));
check('field-independent-scope',fieldCard.uncertainty_missingness.all_eight_independently_reparsed===false);
const spend=JSON.parse(sourceTexts.spend),cpu=cards.find(c=>c.card_id==='carter-ascend-lifecycle-cost-forecast-20261031');
check('measured-cpu-transcription',Number(spend.cpu_seconds.toFixed(6))===cpu.reported_effect.measured_CPU_s&&spend.total_calls===cpu.reported_effect.recorded_calls);
check('forecast-not-minimum',cpu.uncertainty_missingness.minimum_possible_CPU_s===null&&cpu.reported_effect.measured_future_spend===null);
const wire=cards.find(c=>c.card_id==='carter-ascend-thermal-wire-domain-20261031');
check('wire-comparators-distinguished',wire.comparator_intervention.comparator_pairs_are_different===true&&wire.objective_metric.wire_is_routed_length===false&&wire.reported_effect.thermal_reduction_relative_to_initial_layout_C===null);
const verification={verified_at:new Date().toISOString(),checks,source_hash_checks:bindings.sources.length,quote_checks:quoteChecks,card_count:cards.length,scientific_execution:false,frozen_diagnosis_unchanged:true};
fs.writeFileSync(path.join(__dirname,'VERIFICATION.json'),JSON.stringify(verification,null,2)+'\n');
const files=fs.readdirSync(__dirname).filter(n=>n!=='SEAL.json').sort().map(name=>{const bytes=fs.readFileSync(path.join(__dirname,name));return{name,bytes:bytes.length,sha256:sha(bytes)};});
const seal=Buffer.from(JSON.stringify({sealed_at:new Date().toISOString(),files},null,2)+'\n');fs.writeFileSync(path.join(__dirname,'SEAL.json'),seal);
console.log(JSON.stringify({checks:checks.length,passed:checks.filter(c=>c.passed).length,source_hash_checks:bindings.sources.length,quote_checks:quoteChecks,card_count:cards.length,knowledge_sha256:files.find(f=>f.name==='knowledge.jsonl').sha256,seal_sha256:sha(seal),frozen_diagnosis_sha256:diagnosis.sha256},null,2));
