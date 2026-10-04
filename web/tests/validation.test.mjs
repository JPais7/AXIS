import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const compilerOptions={target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022};
const c=ts.transpileModule(await readFile(new URL('../src/components.ts',import.meta.url),'utf8'),{compilerOptions}).outputText;
const componentUrl=`data:text/javascript;base64,${Buffer.from(c).toString('base64')}`;
const v=ts.transpileModule(await readFile(new URL('../src/validation.ts',import.meta.url),'utf8'),{compilerOptions}).outputText.replace("'./components'",JSON.stringify(componentUrl));
const view=await import(`data:text/javascript;base64,${Buffer.from(v).toString('base64')}`);

const base=(over={})=>({case_id:'c1',status:'revealed',label:'',protocol:{cutoff:'2019-01-01',cutoff_rationale:'why',question:'q?',selection_rationale:'sel',protocol_fingerprint:'a'.repeat(64),benchmark_kind:'development',synthetic:false},
 snapshots:[{fingerprint:'f',sources:[{source:'S1',title:'Early <b>',first_publicly_accessible_date:'2018-03-01'}],records:{}}],
 cutoff_run:{run_id:'r',rules_fingerprint:'b'.repeat(64),software_commit:'c'.repeat(40),state:{critical_uncertainty_id:'u',recommended_experiment_id:null,recommendation_question:null,no_experiment_message:'none',edges:{engagement:'not_assessed'},explanations:{},uncertainties:{}},decision_validity:{result:'valid'},rule_revision:null},
 audits:[{phase:'pre_reveal',valid:true,findings:[],label:null}],baselines:[{kind:'internal',run:'run-1',frozen_at:'2026-01-01T00:00:00',sha256:'d'.repeat(64)}],
 reveal:{future_sources:[{source:'S2',title:'Later',first_publicly_accessible_date:'2019-09-01'}],diff:{edges:{engagement:['not_assessed','supported']},explanations:{},uncertainties:{},critical_uncertainty:null,recommended_experiment:null,decision_changed:'partially'}},
 assessment:{conclusion:{conclusion:'ambiguous',basis:['b']},relevance:{S2:{relevance:'changes_critical_uncertainty',title:'Later',first_publicly_accessible_date:'2019-09-01',edge_changes:{},status_changes:{'uncertainty:x':['open','resolved']},records:1}},matrix:{temporal_integrity:{result:'valid'},baseline_comparison:{result:['neither_pointed_at_what_changed']}},baseline_comparison:[],leave_one_source_out:[],provenance:{},limits:['Retrospective only']},
 reviews:[],...over});

test('timeline puts the cutoff between available and revealed evidence',()=>{
  const html=view.timeline(base());
  assert.ok(html.indexOf('S1')<html.indexOf('Cutoff T = 2019-01-01'));
  assert.ok(html.indexOf('Cutoff T')<html.indexOf('S2'));
  assert.match(html,/Early &lt;b&gt;/);
});
test('unrevealed case seals the future',()=>{
  const html=view.caseView(base({status:'executed',reveal:null,assessment:null}));
  assert.match(html,/sealed until the reveal/);assert.doesNotMatch(html,/S2/);assert.match(html,/Not revealed/);
});
test('leakage failure replaces every result with the invalid state',()=>{
  const html=view.caseView(base({status:'invalid',audits:[{phase:'pre_reveal',valid:false,label:'x',findings:[{category:'record_after_cutoff',subject:'experiments:e',detail:'S2'}]}]}));
  assert.match(html,/INVALID — TEMPORAL LEAKAGE/);assert.match(html,/record after cutoff/);
  assert.doesNotMatch(html,/Validation matrix/);assert.doesNotMatch(html,/What the later evidence tested/);
});
test('matrix has no scalar score and synthetic cases are labelled',()=>{
  const html=view.caseView(base({protocol:{...base().protocol,synthetic:true,benchmark_kind:'synthetic_test'}}));
  assert.match(html,/there is no AXIS score/);assert.match(html,/SYNTHETIC \/ TEST ONLY \/ NOT SCIENTIFIC EVIDENCE/);
  assert.doesNotMatch(html,/accuracy|pass rate/i);
});
test('baseline and review stay separate from system output',()=>{
  const html=view.caseView(base());
  assert.match(html,/frozen before the reveal/i);assert.match(html,/never edits it/);
});
