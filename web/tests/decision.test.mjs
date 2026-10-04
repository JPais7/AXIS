import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const compilerOptions={target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022};
const c=ts.transpileModule(await readFile(new URL('../src/components.ts',import.meta.url),'utf8'),{compilerOptions}).outputText;
const componentUrl=`data:text/javascript;base64,${Buffer.from(c).toString('base64')}`;
const r=ts.transpileModule(await readFile(new URL('../src/results.ts',import.meta.url),'utf8'),{compilerOptions}).outputText.replace("'./components'",JSON.stringify(componentUrl));
const resultsUrl=`data:text/javascript;base64,${Buffer.from(r).toString('base64')}`;
const s=ts.transpileModule(await readFile(new URL('../src/decision.ts',import.meta.url),'utf8'),{compilerOptions}).outputText.replace("'./components'",JSON.stringify(componentUrl)).replace("'./results'",JSON.stringify(resultsUrl));
const view=await import(`data:text/javascript;base64,${Buffer.from(s).toString('base64')}`);

const scenario=(kind,effect,category)=>({scenario_id:'s-'+kind,kind,outcome:'Outcome <b>'+kind,interpretation:'i',explanation_effects:[{explanation_id:'e1',effect}],consequence:{category,statement:'If this occurs, the strategy changes.',new_uncertainty:kind==='non_interpretable'?'assay validity':null}});
const candidate=(id,rank,low)=>({experiment_id:id,title:'Title '+id,rank,reason:rank?'reason '+id:'not compared',role_label:low?'low discrimination — replication':'mechanism discrimination',low_discrimination:low,status:'proposed',cost:'not provided',profile:{considered_for:['target_engagement'],target_proximity:'target_proximal',disease_relevance:'molecular only',complexity:'moderate',time_estimate:'unknown',role:'x',purpose:'establish_target_engagement',limitations:['limit'],prerequisites:[['probe','not_established']],required:{models:['cells'],reagents:[]}},discrimination:{separated_pairs:low?[]:[['e1','e2']]},interpretability:{level:'high',met:['a','b','c','d']},feasibility:{level:'unknown',missing:[],note:'Feasibility not assessed against local resource constraints.'},distinct_consequences:3});
const state=(over={})=>({id:'decision-state:1:x',version:1,created_at:'2026-10-04T18:00:00+00:00',created_by:'e',rules_version:'axis-decision-1',disclaimer:'Decision framing given the evidence; not scientific truth.',
 hypothesis:{title:'H',description:'Hypothesis <i>text</i>',knowledge_kind:'ai_suggestion'},
 position:{supported:[{statement:'Biochemical evidence is supported.',refs:[['edge','biochemical']]}],contradicted:[],unresolved:[{statement:'Does it engage?',refs:[['uncertainty','u1']]}]},
 explanations:[{id:'e1',label:'On-target',statement:'S',status:'partially_supported',knowledge_kind:'ai_suggestion',links:[{relationship:'supports',evidence_type:'measurement',evidence_id:'m1',rule_id:'R',rationale:'why'}],rule_ids:[]},{id:'e2',label:'Off-target',statement:'S2',status:'viable',knowledge_kind:'ai_suggestion',links:[],rule_ids:[]}],
 excluded_explanations:[{id:'explanation:indirect',reason:'no grounded evidence link'}],
 uncertainties:[{id:'u1',category:'target_engagement',question:'Does it engage?',status:'open',decision_relevance:'decision_blocking',resolvability:'directly_testable',rationale:'r',fired_rules:['R'],reasons:['x'],affected_explanation_ids:['e1','e2'],source_gap_ids:[]}],
 critical:{selected:'u1',reasons:['decision relevance: decision blocking'],alternatives:[{uncertainty_id:'uncertainty:selectivity',reason:'not selected: lower on decision relevance'}]},
 candidates:[candidate('decision:exp:a',1,false),candidate('decision:exp:rep',2,true),candidate('decision:exp:other',null,false)],
 recommended_experiment_id:'decision:exp:a',
 recommendation:{question:'Q',why_now:'W',experiment_id:'decision:exp:a',title:'Title a',experiment:'E',biological_context:'C',controls:{negative:['vehicle'],positive:['No validated positive control identified in the curated corpus.']},primary_endpoint:'P',secondary_endpoints:[],limitations:['L'],outcome_scenarios:[scenario('supportive','strengthens','strengthen_current_strategy'),scenario('negative','weakens','weaken_current_strategy'),scenario('non_interpretable','does_not_discriminate','require_replication')],why_this_experiment:{uncertainty:'U',explanations_separated:[['e1','e2']],why_current_evidence_cannot_answer:'A',why_outcome_changes_decision:'B',remains_unresolved:['R']}},
 what_would_change_our_mind:{question:'What result would make us reconsider?',label:'prospective / hypothetical — no result has been observed',would_weaken:[{statement:'If no engagement, weaker.',category:'weaken_current_strategy',experiment_id:'decision:exp:a'}],would_strengthen:[]},
 constraints:{id:null,note:'Feasibility not assessed against local resource constraints.'},
 provenance:{ai_generated:['e1'],investigator_approved:[],deterministic_rules:['R']},
 trace:{rules_fired:[{id:'DECISION-CRIT-001',version:'1',description:'d'}],candidates_considered:[{experiment_id:'decision:exp:a',rank:1,reason:'recommended'}],outcome_logic:'Experiment -> OutcomeScenario',explanations_not_admitted:[]},
 graph:{nodes:[],edges:[{from:'decision:exp:a',to:'e1',kind:'discriminates',basis:'Outcomes differ.'}]},diff:null,supersedes_id:null,...over});

test('decision page states framing, never scores and never a bare directive',()=>{
  const html=view.decisionView(state(),[state()]);
  assert.match(html,/not scientific truth/);
  const claims=html.replaceAll('no numerical score','').replaceAll('not a probability','').replaceAll('No probabilities are assigned','').replaceAll('no hidden weighted total','');
  assert.doesNotMatch(claims,/\d+\s*%|\bscore\b|probabilit|information gain|confidence/i);
  assert.doesNotMatch(html,/Run experiment [A-Z]/);
  assert.match(html,/Why this experiment\?/);
  assert.match(html,/Recommended next discriminating experiment/);assert.doesNotMatch(html,/[Bb]est experiment/);
  assert.match(html,/Conditional on current evidence, current rules and current constraints/);
  assert.match(html,/prospective — not observed/);
});
test('outcome tree has a textual equivalent for every branch and a conditional next action',()=>{
  const html=view.outcomeTree(state());
  assert.match(html,/<ol class="outcome-tree" aria-label=/);
  assert.equal((html.match(/<strong>Next action/g)||[]).length,3);
  assert.match(html,/does not discriminate/);assert.match(html,/If this occurs/);
  assert.match(html,/New uncertainty: assay validity/);
});
test('low discrimination and unknown constraints stay visible',()=>{
  const matrix=view.comparisonMatrix(state());
  assert.match(matrix,/Low discrimination/);assert.match(matrix,/Cost<\/th><td>not provided/);
  assert.match(matrix,/Feasibility not assessed against local resource constraints/);
  assert.match(matrix,/Other candidates, not compared/);
  assert.match(view.constraintsSection(state()),/Cost: not provided/);
});
test('critical card lists rejected alternatives and escapes source text',()=>{
  const html=view.criticalCard(state());
  assert.match(html,/Other open uncertainties and why they were not selected/);assert.match(html,/lower on decision relevance/);
  const escaped=view.positionSection(state());
  assert.match(escaped,/Hypothesis &lt;i&gt;text&lt;\/i&gt;/);assert.doesNotMatch(escaped,/<i>text<\/i>/);
});
test('no open uncertainty yields an explicit empty state, not an invented experiment',()=>{
  const html=view.criticalCard(state({critical:{selected:null,reasons:[],alternatives:[]}}));
  assert.match(html,/No open, testable uncertainty/);
  assert.match(view.recommendation(state({recommendation:null})),/No next discriminating experiment is currently justified/);
});
test('explanations show AI provenance and non-admitted suggestions',()=>{
  const html=view.explanationCards(state());
  assert.match(html,/ai suggestion/);assert.match(html,/Not admitted: explanation:indirect/);assert.match(html,/data-decision-explanation="e1"/);
});
test('history shows the diff since the previous state',()=>{
  const html=view.historySection([state({version:2,supersedes_id:'x',diff:{changes:['Engagement: not assessed → supported'],new_evidence:[]}}),state()]);
  assert.match(html,/Since previous decision/);assert.match(html,/not assessed → supported/);assert.match(html,/First decision state/);
});

test('pending expert review is shown above the decision, not hidden in the trace',()=>{
  const html=view.decisionView(state({review:{pending_expert_review:37,accepted:0,message:'This recommendation depends on evidence that has not yet received independent scientific acceptance.'}}),[state()]);
  assert.match(html,/Pending scientific review/);assert.match(html,/has not yet received independent scientific acceptance/);
  assert.ok(html.indexOf('Pending scientific review')<html.indexOf('id="position"'));
  assert.doesNotMatch(view.decisionView(state(),[state()]),/Pending scientific review/);
});
test('robustness lists decisive and non-decisive evidence without scores',()=>{
  const sensitivity={method:'categorical leave-group-out; no probabilities',decision_sensitive:[{group:'pending_review_cellular',removed:'all cellular assessments pending expert review',changes:['critical uncertainty: a → b']}],explanation_sensitive:[],non_decisive:[{group:'structure',removed:'structural evidence',changes:[]}]};
  const html=view.robustness(state({sensitivity}));
  assert.match(html,/Evidence the recommendation depends on/);assert.match(html,/critical uncertainty: a → b/);assert.match(html,/Supportive but non-decisive evidence \(1\)/);
  assert.doesNotMatch(html.replaceAll('No probabilities or scores',''),/\d+\s*%|probabilit|score/i);
});
test('no actionable uncertainty yields an explicit statement, never an invented experiment',()=>{
  const none=state({critical:{selected:null,reasons:[],alternatives:[],message:'No open, testable uncertainty meets the criticality criteria; no next discriminating experiment is currently justified.'},recommendation:null,recommended_experiment_id:null,no_experiment_message:'No next discriminating experiment is currently justified by the represented evidence and rules.'});
  const html=view.decisionView(none,[none]);
  assert.match(html,/no next discriminating experiment is currently justified/i);assert.doesNotMatch(html,/Why this experiment\?/);
});
test('history states whether evidence or methodology changed',()=>{
  const html=view.historySection([state({version:2,supersedes_id:'x',diff:{changes:['c'],new_evidence:[],cause:['methodology'],cause_summary:'This decision differs because the AXIS decision methodology changed.'}})]);
  assert.match(html,/differs because the AXIS decision methodology changed/);
});

test('causal diff separates evidence, review and methodology and states whether the decision changed',()=>{
  const diff={changes:[],new_evidence:[],cause:['evidence'],cause_summary:'This decision differs because the stored evidence changed.',causes:[{category:'new_experimental_evidence',items:[{result_id:'R1'}]},{category:'review_status_change',items:[{result_id:'R2',after:'accepted'}]}],decision_changed:{answer:'pending_review',why:'only pending'},triggering_results:['R1'],
   scientific_diff:{evidence_status_changes:[{kind:'scope',name:'engagement / compound:x',before:'not_assessed',after:'supported',rule:'DECISION-RESULT-001',because:[]}],explanation_changes:[{id:'e',label:'On-target',before:'partially_supported',after:'supported',rules:['DECISION-EXPL-010'],because:[]}],uncertainty_changes:[{id:'uncertainty:target_engagement',before:['open','decision_blocking'],after:['partially_resolved','decision_material'],rules:['R']}],critical:{before:'a',after:'b',because:{}},recommendation:null}};
  const html=view.causalDiff(diff);
  assert.match(html,/Did the decision change\? Pending review/);assert.match(html,/new experimental evidence/);assert.match(html,/review status change/);
  assert.match(html,/not assessed → <strong>supported/);assert.match(html,/DECISION-RESULT-001/);assert.match(html,/Critical uncertainty: a → <strong>b/);
  assert.equal(view.causalDiff(null),'');
});
test('engagement scope breakdown never lets one scope stand for another',()=>{
  const html=view.scopeBreakdown(state({effective_evidence:{engagement_rollup:{status:'partial',scopes:[{scope_type:'compound',scope_id:'compound:a',state:'supported',required:true,contribution_ids:['i'],caveats:['one system'],replicated:false},{scope_type:'compound',scope_id:'compound:b',state:'not_assessed',required:true,contribution_ids:[],caveats:[],replicated:false}]}}}));
  assert.match(html,/resolves only its own compound/);assert.match(html,/partial/);assert.match(html,/compound:b<\/th><td>not assessed/);
});
test('decision page states when no performed result informs it',()=>{
  assert.match(view.resultsSection(state({results:{contributions:[],unexpected:[],synthetic:false}})),/no performed experiment has been imported into it/);
  const html=view.decisionView(state({synthetic:true,results:{contributions:[{id:'i',result_id:'R1',edge:'engagement',scope_type:'compound',scope_id:'x',state:'supported',statement:'s',review_state:'pending',eligibility_state:'pending_review',caveats:[],review_caveats:['pending scientific review'],synthetic:true}],unexpected:[],synthetic:true}}),[state()]);
  assert.match(html,/SYNTHETIC DEMONSTRATION/);assert.match(html,/review: pending/);
});
