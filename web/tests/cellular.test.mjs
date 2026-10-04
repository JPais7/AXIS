import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const compilerOptions={target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022};
const c=ts.transpileModule(await readFile(new URL('../src/components.ts',import.meta.url),'utf8'),{compilerOptions}).outputText;
const componentUrl=`data:text/javascript;base64,${Buffer.from(c).toString('base64')}`;
const s=ts.transpileModule(await readFile(new URL('../src/cellular.ts',import.meta.url),'utf8'),{compilerOptions}).outputText.replace("'./components'",JSON.stringify(componentUrl));
const view=await import(`data:text/javascript;base64,${Buffer.from(s).toString('base64')}`);
test('missing engagement stays textually not assessed; no score or invented measurement',()=>{
  const html=view.evidenceLadder({edges:[{edge:'engagement',state:'not_assessed',assessments:[],measurements:[]}],boundary:'No causal inference',has_more:false},'P');
  assert.match(html,/Direct cellular target engagement/);assert.match(html,/not assessed/);
  assert.doesNotMatch(html,/demonstrated|\d\/7/);
});
test('mixed and contradicted states retain clickable source path and escaped text',()=>{
  const html=view.evidenceLadder({edges:[{edge:'hla',state:'mixed',assessments:[{experiment_id:'e',rationale:'<script>'}],measurements:[]}],boundary:'',has_more:false},'P');
  assert.match(html,/mixed/);assert.match(html,/data-cellular-experiment/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});
test('unknown context remains visible rather than omitted',()=>{
  assert.match(view.cellularFields({hla_allele:null,erap1_allotype:null}),/Not reported/);
});
