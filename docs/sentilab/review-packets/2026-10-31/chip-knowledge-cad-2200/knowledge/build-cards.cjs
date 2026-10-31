const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const workspace = 'C:/Users/carth/Desktop/projects/PlexAura_Inc/SentinelLayer/AIdenID';
const task = 'tasks/sentilab-review-2026-10-30/';
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const definitions = {
  diagnosis: ['reports/SentiLab inconclusive results diagnosis.md','132bf28fc6d962ae159a942084b3a7fe4c17fd52dc65da7a13789939a0460a7d'],
  fields: [task+'existing-field-diagnostics-1441/RESULTS.json','d3ac1b66696e979f2d4ba9ff82faa90ddbdccdd174ff277e283ba63cf3f1715c'],
  independent: [task+'existing-field-independent-1444/RESULTS.json','fdf13ffeba948a46bfb758c28c3ddb0d1e11293e2bdf882f247b2c05bd20fd42'],
  independent_check: [task+'existing-field-independent-1444/CHECK.md'],
  combined: [task+'pr25-fa7ed8f/source/sundai_hotspot/probe_results/combined_report.json','d09d9619ca6c506da9dc232cad3af64f49cb67951c54615a3a45b6f0bb1576b5'],
  geometry: [task+'peer-diagnosis-1318/literature-delta-1347/FINDINGS.md','ee55599045d8f9dbfa7af85cfe71df2a7d85d0285d8c6d715654704032341626'],
  vectors: [task+'peer-diagnosis-1318/literature-delta-1347/FIG6A-VECTORS.json'],
  geometry_manifest: [task+'peer-diagnosis-1318/literature-delta-1347/SOURCE-MANIFEST.json'],
  forensics: ['research_notes/SentiLab inconclusive results diagnosis/numerical_forensics_data.json'],
  spend: [task+'pr25-a10063d-review/source/docs/sentilab/evidence/SLAB-039/SPEND.json'],
};
const sources = Object.fromEntries(Object.entries(definitions).map(([id,[relative,expected]])=>{
  const absolute=path.resolve(workspace,relative).replaceAll('\\','/');
  const bytes=fs.readFileSync(absolute); const digest=sha(bytes);
  if(expected && digest!==expected) throw new Error(id+' source seal mismatch');
  return [id,{id,absolute_path:absolute,workspace_relative_path:relative,sha256:digest,bytes:bytes.length,expected_sha256:expected||null,text:bytes.toString('utf8')}];
}));
function quote(id,exact) {
  const s=sources[id], index=s.text.indexOf(exact);
  if(index<0) throw new Error('Quote missing in '+id+': '+exact);
  const lineStart=s.text.slice(0,index).split('\n').length;
  const lineEnd=lineStart+exact.split('\n').length-1;
  return {source_id:id,absolute_path:s.absolute_path,workspace_relative_path:s.workspace_relative_path,sha256:s.sha256,line_start:lineStart,line_end:lineEnd,quote:exact};
}
function lines(id,first,last) {
  const s=sources[id];
  return {source_id:id,absolute_path:s.absolute_path,workspace_relative_path:s.workspace_relative_path,sha256:s.sha256,line_start:first,line_end:last,quote:s.text.split(/\r?\n/).slice(first-1,last).join('\n'),quote_line_endings:'LF-normalized only'};
}
const fieldData=JSON.parse(sources.fields.text);
const twoDecimal=x=>Number(x.toFixed(2));
const common={
  schema:'sentilab-chip-knowledge-evidence-card/1-proposed',
  contributed_by:'gpt-astra-carter',
  curated_by:'/root/api_batch_review',
  created_at:new Date().toISOString(),
  contribution_scope:'Four additive local-evidence cards; not the whole knowledge base or a new experiment.',
  traceability:{human_request_sequence:57210,human_request_source_id:'94e536af-53bf-4f5e-98a7-04aad97a36ab',existing_ticket_ref:'2559963e',existing_ticket_ref_is_prefix:true,related_existing_ticket_refs:['6053a93c','f1e3bdf0'],ticket_ownership:'Preserved; host files no duplicate ticket.'},
  public_hardware_measurement:false,
  new_solver_model_gpu_calls:0,
  confidence:{source_binding:'Exact source bytes and quotations checked by this curator.',causal_generalization:null,physical_accuracy:null},
};
const cards=[
  {...common,
    card_id:'carter-retained-ascend-stack-drop-20261031',
    title:'Same-index layer fields expose a large retained spreader-to-sink drop',
    claim:'Eight retained hand-authored 50 mm Ascend-derived probes report a spreader-to-sink temperature drop of 51.10–52.40 K at the chip-layer peak index. A separate parser corroborated only the baseline 16/32 subset.',
    evidence_kind:['retained_simulation_outputs','offline_derived_stack_differences','independent_reparse_of_two_cases'],
    conditions:{package:'Six-chiplet Ascend-derived research fixture',geometry:{substrate_mm:[50,50],variants:['baseline_center','left_shift_2mm','left_shift_4mm','right_shift_2mm'],manufacturer_CAD:false},config:{retained_hotspot_commit:fieldData.retainedHotspotCommit,source_reported_binary_sha256:fieldData.retainedBinarySha256,binary_rehashed_by_independent_parser:false,power_W:350,ambient_K:318.15,r_convec_K_per_W:0.009,spreader_m:0.1,sink_m:0.2,grid_variants:[[16,16],[32,32]],config_grid_default:[64,64],effective_map:'max via retained CLI',input_layers:6,total_output_layers:8},workload:'Fixed per-chiplet power; no transient workload or leakage feedback.',host_hardware:null},
    objective_metric:{name:'Layer-6 spreader minus layer-7 sink temperature at the same row-major index selected by the layer-4 active-chip peak',unit:'K',selection:'Same index across layers; not independent layer maxima or native block centres.'},
    comparator_intervention:{comparison:'Spreader versus sink within each retained solve',controlled_new_intervention:null,causal_effect_estimate:null},
    reported_effect:{drop_range_K:[51.10,52.40],cases:fieldData.rows.map(r=>({case:r.case,grid:r.grid,chip_peak_C:twoDecimal(r.gridPeakC),chip_peak_index:r.peakIndex,spreader_to_sink_drop_K:twoDecimal(r.spreaderToSinkDropK)})),independently_reparsed_baselines:[{case:'baseline_center_16',chip_peak_C:118.36,drop_K:51.10,index:135},{case:'baseline_center_32',chip_peak_C:118.89,drop_K:51.60,index:527}],new_optimization_gain:null},
    uncertainty_missingness:{raw_temperature_resolution_K:0.01,confidence_interval_K:null,physical_calibration_error_K:null,repeated_run_distribution:null,all_eight_independently_reparsed:false,correct_coupling_repair:null,universal_drop_threshold_K:null},
    independent_verification_scope:{original_parent_report:'112 retained source file hashes checked across eight datasets.',separate_parser:'28 retained hashes and full grid structure checked for baseline_center_16 and baseline_center_32 only; eight layers with 256/1024 unique cells each.',curator:'Rehashes these analysis reports and binds quotations; does not rerun their parser or claim a new solve.'},
    architect_usefulness:{decision:'Expose per-layer, same-index fields and effective configs to distinguish an internal coupling concern from a boundary cooling assumption.',recommended_design:'Persist actual config, argv, grid/argmax and layer identities; investigate this coupling under a separately specified validation case.',transfer_limit:'No hardware temperature claim, universal pass threshold, isolated cause, historical-v3 reproduction or demonstrated repair.'},
    sources:[lines('fields',1,8),lines('fields',458,460),...fieldData.rows.map(r=>{const key='"spreaderToSinkDropK": '+r.spreaderToSinkDropK;return quote('fields',key);}),quote('independent_check','Both representative rows are corroborated.'),quote('independent_check','The independent parser verified all **28 retained file hashes** listed for `baseline_center_16` and `baseline_center_32`'),quote('independent_check','| baseline_center_16 | 135; (8,7) | 391.51 → 118.36 | 69.58 K | 18.48 K | 51.10 K |'),quote('independent_check','| baseline_center_32 | 527; (16,15) | 392.04 → 118.89 | 70.11 K | 18.51 K | 51.60 K |'),quote('independent_check','The other six rows and the claimed all-eight range were not independently recalculated here.'),quote('combined','Hand-authored placement perturbation on published research data using upstream thermal generator and separately compiled HotSpot7. Not a Jev or agent optimization result, no surrogate training, no commercial chip signoff.')]
  },
  {...common,
    card_id:'carter-ascend-drawing-snap-legality-20261031',
    title:'Preserve raw reconstructed geometry separately from legal snapped layouts',
    claim:'The retained independent vector extraction corroborates displayed Fig.6(a) chiplet centres within 0.054 mm of Warden’s rounded coordinates, but nearest-mm snapping with nominal dimensions creates a 0.125 mm overlap and a 0.05 mm gap where the cited search requires 0.1 mm.',
    evidence_kind:['retained_vector_geometry_reconstruction','offline_geometric_legality_analysis'],
    conditions:{package:'Published TAP Ascend-derived computational reference drawing, Fig.6(a)',geometry:{frame_mm:[45,45],heatmap_cells:4096,origin:'bottom-left',scale:'Independent x/y scaling from retained vector heatmap bounds',compute_and_HBM_rotation:'Orientation adjusted relative to retained nominal config',Nimbus_orientation_mm:[10.5,16],source_CAD:null,legal_snapped_layout_id:null},config:{paper_search_center_grid_mm:1,paper_search_minimum_gap_mm:0.1,raw_reconstruction_is_integer_grid:false},workload_power_W:null,thermal_solver:null},
    objective_metric:{name:'Drawing-coordinate corroboration and geometric feasibility after snapping',units:['mm']},
    comparator_intervention:{comparison:'Independent vector-derived coordinates vs Warden’s rounded reconstruction; nearest-mm snapping of Warden’s centres with nominal chip dimensions',intervention:'Naïve nearest-mm snapping only; no thermal solve'},
    reported_effect:{max_coordinate_difference_upper_bound_mm:0.054,max_dimension_difference_upper_bound_mm:0.091,naive_snap_compute_upper_HBM_overlap_mm:0.125,naive_snap_compute_Nimbus_gap_mm:0.05,required_gap_mm:0.1,raw_centres_mm:{compute:[17.119,22.591],Nimbus:[38.277,22.529],upper_HBM:[[7.310,33.886],[21.288,33.891]],lower_HBM:[[7.322,11.226],[21.247,11.227]]},legalized_layout_thermal_change_K:null,legalized_layout_wire_change:null},
    uncertainty_missingness:{manufacturer_geometry_error_bound_mm:null,uniform_coordinate_error_bound_mm:null,stroke_origin_scale_orientation_assumptions:'Retained in FIG6A-VECTORS.json and findings; displayed vectors are not source CAD.',exact_original_layout_grid:null,legalized_variant_outcome:null},
    independent_verification_scope:{retained_review:'science_redteam independently extracted six chiplet rectangles using 4,096 heatmap cells; baseline_crosswalk reviewed related metric/cooling source. SOURCE-MANIFEST records 14 sources and exact retained PDF hash.',curator:'Rehashes the findings, vectors and source manifest; does not re-extract the PDF or run a layout/thermal solver.'},
    architect_usefulness:{decision:'Do not silently round an imported research baseline to an optimizer grid.',recommended_design:'Represent raw and legalized/snapped layouts as different immutable identities, with explicit transform, origin, scale, rotation, nominal sizes and legality results.',transfer_limit:'Agreement between two reconstructions is not a metrology uncertainty bound or proof that the paper’s original drawing used integer centres.'},
    sources:[quote('geometry','Every coordinate is within **0.054 mm** of Warden\'s rounded list.'),quote('geometry','Vector dimensions agree with the orientation-adjusted nominal dimensions within 0.091 mm'),quote('geometry','Nearest-mm rounding of Warden\'s centres with nominal sizes creates **0.125 mm compute/upper-HBM overlap** and a **0.05 mm compute-Nimbus gap**.'),quote('geometry','The paper\'s search uses 1 mm centres and a 0.1 mm minimum gap'),quote('geometry','This verifies the displayed drawing, not exact source CAD or a uniform +/-0.2 mm uncertainty bound.'),quote('vectors','"frameAssumption": "45x45mm per paper general evaluation; bottom-left origin; independent x/y scaling; displayed vector edges are not certified original CAD"'),quote('geometry_manifest','"maxCoordinateDifferenceMm": 0.05328967118298067'),quote('geometry_manifest','"nearestMmOverlapMm": 0.125')]
  },
  {...common,
    card_id:'carter-ascend-lifecycle-cost-forecast-20261031',
    title:'Budget the measured evaluation lifecycle, and label extrapolations as forecasts',
    claim:'The retained Ascend v3 headroom run executed 2,650 of 4,768 scheduled calls and charged 1,440.294565 CPU seconds; 43.190720 CPU minutes is a proportional full-schedule forecast, not a proven minimum or additional measured spend.',
    evidence_kind:['recorded_computational_resource_accounting','offline_arithmetic','frozen_diagnosis_synthesis'],
    conditions:{package:'Ascend-derived six-chiplet, 350 W computational fixture',geometry:{substrate_mm:[50,50]},config:{metric_layer:4,grid:[32,32],fixed_power_W:[256,14,20,20,20,20],original_CPU_admission_cap_s:1440},workload:'Random, greedy and short simulated annealing eight seeds each plus declared four long-SA reference runs; worker deliberately reaped after each evaluation for SELF+CHILDREN accounting.',host_hardware:null,compiler_build:null,hardware_power_measurement:false},
    objective_metric:{name:'Completed scheduled evaluations and CPU/wall lifecycle charge',units:['calls','CPU seconds','wall seconds']},
    comparator_intervention:{comparison:'Recorded partial execution vs declared full schedule; observed average multiplied by full call count',intervention:null,implemented_speedup:null},
    reported_effect:{scheduled_calls:4768,recorded_calls:2650,unexecuted_scheduled_calls:2118,measured_CPU_s:1440.294565,measured_wall_s:1525.852038,measured_CPU_s_per_call:0.543507383,required_average_to_fit_original_cap_CPU_s:0.302013423,forecast_full_schedule_CPU_s:2591.443202,forecast_full_schedule_CPU_minutes:43.190720,forecast_kind:'Proportional extrapolation of observed implementation/call mix',admitted_final_call_overshoot_CPU_s:0.294565,scientific_verdict:'INCONCLUSIVE',measured_future_spend:null},
    uncertainty_missingness:{forecast_confidence_interval:null,minimum_possible_CPU_s:null,isolated_worker_teardown_CPU_s:null,isolated_native_solve_CPU_s:null,complete_raw_2650_call_archive:false,current_total_dollars:null,other_historical_CI_CPU_s:null},
    independent_verification_scope:{retained_review:'Frozen numerical-forensics analysis rechecked original runner/prereg hashes and retained arithmetic; source records do not retain every native input/output and proposal trajectory.',curator:'Exact-byte and quotation checks only, with no new workload, timing measurement or forecast fit.'},
    architect_usefulness:{decision:'Measure startup, generation, solve, teardown/reap, archival and failure cleanup before committing a scientific schedule.',recommended_design:'Persist actual resource debits separately from forecasts and reserve, bind resource feasibility to the deployed evaluator lifecycle, and keep incomplete-reference acceptance distinct from a promising numeric gap.',transfer_limit:'This call mix and implementation do not establish a universal CPU floor or a measured speedup available from a different design.'},
    sources:[quote('diagnosis','The run completed 2,650 of 4,768 scheduled calls;'),quote('diagnosis','using **1,525.852038 wall seconds and 1,440.294565 CPU seconds**.'),quote('diagnosis','The implementation deliberately reaped the worker after each evaluation so that CHILDREN CPU, including worker startup, would be visible alongside SELF CPU at the next admission check.'),quote('diagnosis','The observed whole-run average was 0.543507383 CPU seconds per call; completing 4,768 calls in 1,440 seconds requires 0.302013423 seconds per call before adding any unaccounted reserve.'),quote('diagnosis','Multiplying the observed average by the full call count gives **2,591.443202 CPU seconds, or 43.190720 minutes**.'),quote('diagnosis','This is a proportional forecast from this implementation and call mix, not measured extra consumption, a worst-case bound, or a request to increase the allowance.'),quote('forensics','"unexecuted_scheduled_calls": 2118'),lines('spend',1,12),quote('spend','"unknown_historical_cpu_seconds": null')]
  },
  {...common,
    card_id:'carter-ascend-thermal-wire-domain-20261031',
    title:'A lower retained thermal objective can accompany a worse interconnect proxy',
    claim:'The lowest-temperature retained Ascend v3 layout increases the frozen weighted Manhattan centre-distance proxy from 27.69934640522876 to 40.529411764705884 mm (+46.319%). Its promising thermal screen does not demonstrate fixed-wire improvement or an agent advantage.',
    evidence_kind:['retained_simulation_summary','recomputed_design_proxy','frozen_diagnosis_synthesis'],
    conditions:{package:'Ascend-derived six-chiplet, 350 W computational fixture',geometry:{substrate_mm:[50,50],initial_centres_mm:[[25,25],[40,40],[8,9],[8,25],[8,41],[41,15]],winner_design_hash:'32f9304667455368f64cd7b805ea055758d0d9c3fea4a78f444efcc86eb5c60a',boundary_margin_mm:0.5},config:{grid:[32,32],active_layer:4,power_W:[256,14,20,20,20,20],wire_ceiling_in_executed_v3:null},workload:'One fixed-power scenario; long-SA screen vs cheap-method medians, with reference incomplete.',hardware_device:null},
    objective_metric:{thermal:'Maximum active-chip layer-4 cell temperature at grid32',wire:'Normalized weighted Manhattan distance between chiplet centres using frozen connectivity',units:['C','mm'],wire_is_routed_length:false},
    comparator_intervention:{wire_comparator:'Saved best vs original initial layout',thermal_comparator:'Best cheap-method median 117.685 C vs retained long-SA best 116.09 C',comparator_pairs_are_different:true,isolated_separation_intervention:null,equal_budget_agent_control:false},
    reported_effect:{initial_wire_proxy_mm:27.69934640522876,best_wire_proxy_mm:40.529411764705884,wire_proxy_increase_percent:46.319,saved_winners_above_initial_wire:25,saved_nonempty_winners:26,cheap_best_method_median_C:117.685,retained_long_SA_best_C:116.09,reported_thermal_screen_gap_C:1.595,historical_threshold_C:0.8,verdict:'INCONCLUSIVE',fresh_reproduction_of_long_SA_best:false,thermal_reduction_relative_to_initial_layout_C:null,routed_wire_change_mm:null},
    uncertainty_missingness:{all_intermediate_proposals_available:false,thermal_gain_causally_attributed_to_separation_C:null,physical_temperature_error_C:null,timing_congestion_power_delivery_reliability:null,equal_budget_agent_effect:null},
    independent_verification_scope:{retained_review:'Original source review found all 26 nonempty retained winners geometrically legal; numerical forensics recomputed the proxy and checked retained summary identities. Fresh long-SA reproduction and full native trajectories are absent.',curator:'Rehashes frozen diagnosis/forensics and binds exact quotations; no new search, geometry solve or reproduction.'},
    architect_usefulness:{decision:'Keep geometric legality, objective value, interconnect cost and scientific acceptance as separate facts.',recommended_design:'If fixed-initial-wire is the intended task, freeze that constraint prospectively and optimize within it; expose wire/thermal tradeoffs without relabeling a distance proxy as routed wire.',transfer_limit:'Increased separation is a plausible mechanism, not an isolated measured cause; post-filtering saved winners cannot reconstruct a constrained search that was never performed.'},
    sources:[quote('diagnosis','With the frozen connectivity, they give **W = 27.69934640522876 mm**.'),quote('diagnosis','has **W = 40.529411764705884 mm**, a **46.319% increase**; 25 of 26 saved winners exceed the initial value.'),quote('diagnosis','It is a useful proxy, not routed wirelength, signal timing, congestion, power-delivery quality or a package reliability check.'),quote('diagnosis','This is a **mismatch between the diagnostic and the intended fixed-initial-wire task**, rather than violation of an explicit v3 wire clause: v3 did not freeze that ceiling.'),quote('diagnosis','Filtering the 26 saved winners cannot recover a constrained search that was never performed; its intermediate paths and discarded candidates are unavailable.'),quote('diagnosis','There were no fresh long-SA reproduction calls in the four retained reference records.'),quote('forensics','"cheap_median_c": 117.68500000000003'),quote('forensics','"best_c": 116.09000000000003'),quote('forensics','"gap_c": 1.5949999999999989')]
  }
];
fs.writeFileSync(path.join(__dirname,'knowledge.jsonl'),cards.map(c=>JSON.stringify(c)).join('\n')+'\n');
fs.writeFileSync(path.join(__dirname,'SOURCE-BINDINGS.json'),JSON.stringify({created_at:new Date().toISOString(),sources:Object.values(sources).map(({text,...s})=>s),frozen_report_unchanged:true,card_count:cards.length,quote_bindings:cards.reduce((n,c)=>n+c.sources.length,0)},null,2)+'\n');
console.log(JSON.stringify({cards:cards.length,sources:Object.keys(sources).length,quotes:cards.reduce((n,c)=>n+c.sources.length,0),knowledge_sha256:sha(fs.readFileSync(path.join(__dirname,'knowledge.jsonl'))),frozen_report_sha256:sources.diagnosis.sha256}));
