const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const out=__dirname,sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const sources=JSON.parse(fs.readFileSync(path.join(out,'SOURCE-BINDINGS.json'),'utf8'));
for(const r of sources.records)if(sha(fs.readFileSync(path.join(out,r.path)))!==r.sha256)throw Error('Source changed: '+r.path);
const draft=JSON.parse(fs.readFileSync(path.join(out,'ANETA-56873.json'),'utf8'));
if(fs.readFileSync(path.join(out,'ANETA-DRAFT.md'),'utf8')!==draft.text+'\n')throw Error('Draft extraction mismatch');
const summary={schema:'sentilab-challenge-math-review/1',at:new Date().toISOString(),disposition:'CHANGES REQUIRED IN CLAIMS; PROVISIONAL CONTRACT PROVIDED',sourceId:draft.sourceId,sequenceId:draft.sequenceId,
 conclusions:{summedObservedSensitivityIsRigorousBound:false,moreConservativePredicateProvesBoundValidity:false,nativeCentrePaperMetricCorrespondenceEstablished:false,universal85CFeasibilityEstablished:false,publishedTargetsMustRemainSeparateFromJointModelBaseline:true,relaxedWireMustBeNamed:true,wireGainWithThermalDegradationIsStrictPareto:false,tradeoffValuesAreWireBudgets:true,numericalAdmission:'UNKNOWN',unknownBoundsDefaultTo:null,freeInstantUnlimitedComputeEstablished:false,descriptiveStudyRequiresNewFiveArmPrerequisite:false},
 proposedAlternative:'Finite predeclared paired sensitivity screen, explicitly scoped to listed cases; conditional interval formulas only when their bounds are justified',
 pendingPolicyParameters:{D_K:null,wireRelaxation:null,thermalImprovement_K:null,wireImprovement_mm:null,temperatureTarget_C:null,positionUncertainty_mm:null,lattice_mm:null},
 limits:{modelCalls:0,thermalSolves:0,optimizerRuns:0,testsRun:0,networkCalls:0,sourceMutations:0,posts:0,executionGrant:false}};
fs.writeFileSync(path.join(out,'SUMMARY.json'),JSON.stringify(summary,null,2)+'\n',{flag:'wx'});
const artifacts=fs.readdirSync(out).filter(x=>x!=='SEAL.json').sort().map(name=>{const b=fs.readFileSync(path.join(out,name));return {path:name,bytes:b.length,sha256:sha(b)};});
fs.writeFileSync(path.join(out,'SEAL.json'),JSON.stringify({schema:'sentilab-challenge-math-seal/1',at:new Date().toISOString(),reviewer:'/root/science_redteam',sourceId:draft.sourceId,executionGrant:false,artifacts},null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({reportSha256:sha(fs.readFileSync(path.join(out,'REVIEW.md'))),contractSha256:sha(fs.readFileSync(path.join(out,'PROVISIONAL-CONTRACT.md'))),summarySha256:sha(fs.readFileSync(path.join(out,'SUMMARY.json'))),sealSha256:sha(fs.readFileSync(path.join(out,'SEAL.json'))),artifacts:artifacts.length},null,2));
