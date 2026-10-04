import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const compilerOptions={target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022};
const c=ts.transpileModule(await readFile(new URL('../src/components.ts',import.meta.url),'utf8'),{compilerOptions}).outputText;
const componentUrl=`data:text/javascript;base64,${Buffer.from(c).toString('base64')}`;
const v=ts.transpileModule(await readFile(new URL('../src/campaign.ts',import.meta.url),'utf8'),{compilerOptions}).outputText.replace("'./components'",JSON.stringify(componentUrl));
const view=await import(`data:text/javascript;base64,${Buffer.from(v).toString('base64')}`);

const cand=(over={})=>({compound_ref:'c1',name:'Cand <b>',role:'exploration',cluster:1,why_this_molecule:'because',dimensions:{known_experimental_evidence:{has_experimental_evidence:false,summary:'none'},similarity_to_reference:{value:0.12,reference:'k',meaning:'chemical similarity only'},docking:{status:'not_executed'},chemical_novelty:{value:0.88,meaning:'x'},cellular_evidence:'none indexed',selectivity_evidence:'none indexed',descriptors:{molecular_weight:300},descriptor_flags:[],scaffold:''},supporting_evidence:['h'],contradicting_evidence:[],missing_evidence:['m'],strongest_reason_against:'against',hypotheses_tested:['h1'],distinguishes_from:[],what_would_change_our_mind:['no activity'],review_state:'pending_review',epistemic_status:'ai_suggestion',experimental_package:{title:'t',suggested_assays:['a'],positive_control_candidates:['k'],negative_control:'none',outcomes:{positive:'p',negative:'n',non_interpretable:'x'},decision_consequence:'d',decision_link:{critical_uncertainty_id:'uncertainty:x'},requires:'external experimental validation'},...over});
const camp=(over={},prio={})=>({campaign:{campaign_id:'cm@r1',status:'completed',label:'',question:'q?',synthetic:false,intervention_strategy:'s',software:{rdkit:'1'}},hypotheses:[{id:'h1',statement:'stmt',epistemic_status:'researcher_hypothesis',falsification:['f'],uncertainties:['u']}],chemical_space:{checksum:'a'.repeat(64),source:'src',members:[{ref:'c1',name:'Cand',origin:'researcher_supplied',inclusion_rationale:'why'}]},prepared_structure:null,prepared_compounds:[{compound_ref:'c1',depiction_svg:'<svg></svg>',input_smiles:'CC',status:'prepared'}],observations:[{id:'o',compound_ref:'c1',method:'similarity',epistemic_class:'axis_observation',tool:'RDKit',tool_version:'1',parameters:{}}],prioritization:{outcome:'panel',failure_states:[],failed_preparation:[],statements:['stmt'],panel:[cand(),cand({compound_ref:'c2',name:'Two'})],not_selected:[],reference_chemistry:[{compound_ref:'k',name:'Known',evidence:{summary:'2 measurements'}}],docking:{status:'not_executed',reasons:['no engine'],boundaries:['a docking score is not a binding affinity']},rules_fingerprint:'r',untested_hypotheses:['h2'],method_disagreements:[],diversity:{clusters_represented:[1],panel_size:2},...prio},reviews:[],...over});

test('predicted and experimental evidence are visibly distinct, no total score',()=>{
  const html=view.campaignView(camp());
  assert.match(html,/PREDICTED — chemical similarity/);assert.match(html,/EXPERIMENTAL \(indexed\)/);
  assert.match(html,/there is no total/);assert.doesNotMatch(html,/overall score|AXIS score|rank #/i);
  assert.match(html,/there is no predicted pose to inspect/);
});
test('why, reason against, falsification and package are present per candidate',()=>{
  const html=view.campaignView(camp());
  for (const t of ['Why this molecule?','Strongest reason not to prioritize it','What would change our mind','Experimental validation package','external experimental validation']) assert.ok(html.includes(t),t);
  assert.match(html,/Cand &lt;b&gt;/);assert.doesNotMatch(html,/Cand <b>/);
});
test('failed campaign shows failure and no candidates',()=>{
  const html=view.campaignView(camp({},{outcome:'failed',failure_states:['chemical space empty'],panel:[]}));
  assert.match(html,/Campaign failed — no candidate was produced/);assert.match(html,/chemical space empty/);assert.doesNotMatch(html,/Why this molecule/);
});
test('empty panel is a valid stated outcome',()=>{
  const html=view.campaignView(camp({},{outcome:'no_candidate',panel:[]}));
  assert.match(html,/No candidate is prioritized/);
});
test('synthetic campaigns carry the persistent label; untested hypotheses are listed',()=>{
  const html=view.campaignView(camp({campaign:{...camp().campaign,synthetic:true,label:'x'}}));
  assert.match(html,/SYNTHETIC \/ TEST ONLY \/ NOT SCIENTIFIC EVIDENCE/);assert.match(html,/Hypothesis h2 is untested/);
});
