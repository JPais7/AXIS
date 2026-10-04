import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const compilerOptions={target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022};
const c=ts.transpileModule(await readFile(new URL('../src/components.ts',import.meta.url),'utf8'),{compilerOptions}).outputText;
const componentUrl=`data:text/javascript;base64,${Buffer.from(c).toString('base64')}`;
const r=ts.transpileModule(await readFile(new URL('../src/results.ts',import.meta.url),'utf8'),{compilerOptions}).outputText.replace("'./components'",JSON.stringify(componentUrl));
const view=await import(`data:text/javascript;base64,${Buffer.from(r).toString('base64')}`);

const review=(state='pending')=>({state,reviewers:state==='pending'?[]:['Dr Example'],caveats:[],history:state==='pending'?[]:[{reviewer:'Dr Example',decision:state,rationale:'because <b>',reviewed_at:'2026-10-05T12:00:00'}]});
const detail=(over={})=>({result:{row_id:'R1@v1',id:'R1',version:1,recorded_at:'2026-10-05T09:00:00',recorded_by:'Loader'},
 observed:{endpoint:'signal',result_type:'binary_detection',qualitative_result:'Signal <i>reduced</i>',numeric_value:null,operator:'=',unit:null,replicate_summary:{n:3,type:'biological'},statistics:{},facets:{engagement_signal:'detected'}},
 interpretations:[{id:'I1',statement:'Consistent with engagement',edge:'engagement',scope_type:'compound',scope_id:'compound:x',proposed_state:'supported',knowledge_kind:'ai_suggestion',caveats:['one system'],review:review(),eligibility:{state:'pending_review',eligible:true,reasons:['pending'],caveats:[],rule:'RESULT-REV-002'}}],
 scenario_matches:[{outcome_scenario_id:null,relationship:'matches',rationale:'The observation matches an anticipated outcome scenario.',rule_version:'v'},{outcome_scenario_id:'s1',relationship:'matches',rationale:'matched [a]',rule_version:'v'}],
 review:review(),superseded_by:null,events:[],artifacts:[{id:'a',uri:'u',sha256:'a'.repeat(64),media_type:'text/csv',size_bytes:10,link_role:'raw'}],
 qc:{control_status:'passed',technical_validity:'valid',replicate_quality:'adequate',assessment:'interpretable',rationale:'ok'},deviations:[],
 experiment:{id:'E1',context:{cell_line:'line',hla_allele:null},controls:['vehicle'],assay:'assay',exposure:null,proposal_id:'P1'},synthetic:true,...over});

test('observed, interpreted and reviewed are never blended',()=>{
  const html=view.resultDetailView(detail());
  assert.ok(html.indexOf('OBSERVED')<html.indexOf('INTERPRETATION'));
  assert.match(html,/INTERPRETATION <small>\(not an observation\)/);
  assert.match(html,/Interpretation review/);assert.match(html,/Result review/);
  assert.match(html,/Signal &lt;i&gt;reduced&lt;\/i&gt;/);assert.doesNotMatch(html,/<i>reduced<\/i>/);
});
test('synthetic data is labelled in text, persistently',()=>{
  assert.match(view.resultDetailView(detail()),/Synthetic test fixture — not real experimental evidence/);
  assert.match(view.resultsView([{id:'E',scope:'s',proposal_id:null,measures_edges:['engagement'],results:1,qc:null,synthetic:true,scientific_status:'synthetic_test_fixture'}],[],[]),/SYNTHETIC DEMONSTRATION/);
  assert.doesNotMatch(view.resultDetailView(detail({synthetic:false})),/SYNTHETIC DEMONSTRATION/);
});
test('scenario match shows observed facets and never force-fits',()=>{
  const none=detail({scenario_matches:[{outcome_scenario_id:null,relationship:'outside_predefined_scenarios',rationale:'Observed result falls outside the predefined outcome scenarios.',rule_version:'v'}]});
  const html=view.matchView(none);
  assert.match(html,/outside predefined scenarios/);assert.match(html,/nothing was force-fitted/);
});
test('non-interpretable QC and deviations stay visible',()=>{
  const html=view.resultDetailView(detail({qc:{control_status:'failed',technical_validity:'invalid',replicate_quality:'adequate',assessment:'non_interpretable',rationale:'positive control failed'},deviations:[{field:'context.hla_allele',proposed_value:'B27',actual_value:'other',interpretation_relevance:'limits_interpretation',rationale:'model'}]}));
  assert.match(html,/non interpretable/);assert.match(html,/positive control failed/);assert.match(html,/B27 → <strong>other/);
});
test('ledger lists eligibility and review with their rule and an honest empty state',()=>{
  const row={result_row:'R1@v1',result_id:'R1',version:1,interpretation_id:'I1',experiment_id:'E1',edge:'engagement',scope_type:'compound',scope_id:'compound:x',state:'supported',statement:'s',synthetic:true,scenario_match:'matches',result_review:'accepted',interpretation_review:'pending',eligibility:{state:'pending_review',eligible:true,reasons:[],caveats:[],rule:'RESULT-REV-002'}};
  const html=view.ledgerTable([row]);
  assert.match(html,/pending review/);assert.match(html,/RESULT-REV-002/);assert.match(html,/accepted \/ pending/);assert.match(html,/SYNTHETIC/);
  assert.match(view.ledgerTable([]),/Nothing is inferred/);
});
test('decision impact preview is labelled as not the current decision',()=>{
  const html=view.impactView({label:'Preview — not current decision',assumes:'interpretation I1 accepted',critical_after:'uncertainty:a',recommended_after:null,still_unresolved:['uncertainty:b'],diff:{changes:['Engagement for x: not assessed → supported'],decision_changed:{answer:'partially',why:'states changed'},causes:[]}});
  assert.match(html,/Preview — not current decision/);assert.match(html,/not stored, not the current decision/);assert.match(html,/Partially/);
});
test('review queue states that AI cannot accept itself and shows conflicts',()=>{
  const html=view.reviewQueueView({pending_results:['R1@v1'],pending_interpretations:['I1'],conflicts:['I9'],scenario_mapping_review_counts:{pending:84},mappings_total:84,mode:'exploratory'},[{id:'s|e',effect:'weakens',rationale:'r <b>',review:review()}]);
  assert.match(html,/never resolved by majority/);assert.match(html,/I9/);assert.match(html,/84 pending of 84/);assert.match(html,/r &lt;b&gt;/);
});
test('answers are not forced into yes or no',()=>{
  for (const key of ['yes','no','partially','pending_review']) assert.ok(view.decisionAnswer(key).length>3);
  assert.match(view.decisionAnswer('pending_review'),/Pending review/);
});
