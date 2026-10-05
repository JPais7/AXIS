import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const compilerOptions={target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022};
const c=ts.transpileModule(await readFile(new URL('../src/components.ts',import.meta.url),'utf8'),{compilerOptions}).outputText;
const componentUrl=`data:text/javascript;base64,${Buffer.from(c).toString('base64')}`;
const v=ts.transpileModule(await readFile(new URL('../src/learning.ts',import.meta.url),'utf8'),{compilerOptions}).outputText.replace("'./components'",JSON.stringify(componentUrl));
const view=await import(`data:text/javascript;base64,${Buffer.from(v).toString('base64')}`);

const dataset=(over={})=>({id:'d@r1',endpoint:'IC50',target:'T',assay_context:{target:'T',assay_type:'biochemical_activity',substrate:'S <b>',endpoint:'IC50'},revision:1,compounds:2,measurements:2,checksum:'a'.repeat(64),synthetic:false,label:'',review_state:'pending_review',...over});
const overview=(over={})=>({datasets:[dataset()],comparability:[{dataset_a:'x|S1|IC50',dataset_b:'x|S2|IC50',state:'not_directly_comparable',rationale:['different substrates']}],models:[],boundaries:['measured activity is not a model prediction','observed SAR is not inferred SAR'],...over});
const sar={observed:{label:'OBSERVED SAR',matched_pairs:[{id:'p',statement:'Within the compounds measured in IC50, B had a lower reported value than A.'}],scaffold_groups:[]},inferred:{label:'INFERRED SAR HYPOTHESES (not observations)',hypotheses:[{id:'h',statement:'may be associated',supporting_observations:['p'],contradictory_observations:[],falsification:'opposite pair',review_state:'pending_review'}]},contradictory:[],missing_experiments:['need a second assay']};
const elig=(conclusion='not_eligible')=>({dataset_id:'d@r1',assessments:[{conclusion,readiness:conclusion==='not_eligible'?'SAR_ONLY':'MODEL_ELIGIBLE',reasons:[],counts:{},checks:[{check:'sample size',passed:conclusion!=='not_eligible',detail:'2 compounds',blocking:true}]}]});

test('observed SAR, inferred hypotheses and predictions are labelled apart',()=>{
  const html=view.learningView(overview(),sar,elig(),null);
  assert.match(html,/OBSERVED SAR/);assert.match(html,/INFERRED SAR HYPOTHESES/);assert.match(html,/INFERRED — not an observation/);
  assert.match(html,/A prediction is never shown as a measurement/);
});
test('a refused dataset shows MODEL NOT BUILT as a first-class state',()=>{
  const html=view.learningView(overview(),sar,elig(),null);
  assert.match(html,/MODEL NOT BUILT/);assert.match(html,/Insufficient data for a defensible predictive model/);assert.match(html,/not a failure/);
  assert.match(html,/No model exists for this project/);
});
test('eligible datasets do not show the refusal',()=>{
  const html=view.learningView(overview({models:[{id:'m',algorithm:'ridge',fingerprint:'f'.repeat(64)}]}),sar,elig('eligible'),null);
  assert.doesNotMatch(html,/<h3>MODEL NOT BUILT<\/h3>/);assert.match(html,/there is no model score/);assert.match(html,/not prospective validation/);
});
test('contexts are shown per dataset, escaped, never pooled; comparability is explicit',()=>{
  const html=view.learningView(overview(),sar,elig(),null);
  assert.match(html,/substrate: S &lt;b&gt;/);assert.doesNotMatch(html,/S <b>/);
  assert.match(html,/not directly comparable/);assert.match(html,/No conversion between endpoints/);
});
test('synthetic datasets carry the persistent label',()=>{
  const html=view.learningView(overview({datasets:[dataset({synthetic:true,label:'x'})]}),sar,elig(),null);
  assert.match(html,/SYNTHETIC \/ TEST ONLY \/ NOT SCIENTIFIC EVIDENCE/);
});
test('next compounds are explained by rules with no score',()=>{
  const state={revision:2,entries:[],chemical_uncertainties:[{id:'u',question:'Is it learnable?',status:'open'}],next_compounds:{statement:'Compounds are proposed because they reduce a stated chemical uncertainty',selected:[{compound_ref:'c1',rationales:['exploration'],conflicts:[]}],rules:{exploration:'outside the dominant scaffold'},not_asserted:['synthesis or purchase availability was not assessed']},diff:{causes:['model_added']},boundaries:[]};
  const html=view.learningView(overview(),sar,elig(),state);
  assert.match(html,/outside the dominant scaffold/);assert.match(html,/availability was not assessed/);assert.match(html,/History is never rewritten/);
  assert.doesNotMatch(html,/acquisition score|AXIS score|best molecule/i);
});
