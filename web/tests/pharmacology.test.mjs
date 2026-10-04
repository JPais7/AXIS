import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const options={target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022};
const components=ts.transpileModule(await readFile(new URL('../src/components.ts',import.meta.url),'utf8'),{compilerOptions:options}).outputText;
const componentUrl=`data:text/javascript;base64,${Buffer.from(components).toString('base64')}`;
const source=ts.transpileModule(await readFile(new URL('../src/pharmacology.ts',import.meta.url),'utf8'),{compilerOptions:options}).outputText.replace("'./components'",JSON.stringify(componentUrl));
const views=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
globalThis.location={search:''};
const page=(items)=>({items,total:items.length,limit:20,offset:0,has_more:false});
const compound={id:'C1',preferred_name:'<script>',identity_status:'unresolved',isomeric_smiles:null,depiction_svg:null};
const api=async(path)=>path.includes('/targets?')?page([{protein:{id:'P1'}}]):page([compound]);

test('unresolved identity has no invented image and provider text is escaped',async()=>{
  const html=await views.pharmacologyContent(api,'project','chemistry');
  assert.match(html,/Chemical structure not resolved/);
  assert.match(html,/&lt;script&gt;/);
  assert.doesNotMatch(html,/<img|<script>/);
  assert.match(html,/data-pharma-kind="compounds"/);
});
test('resolved RDKit depiction retains textual isomeric identity',async()=>{
  const provider=async(path)=>path.includes('/targets?')?page([{protein:{id:'P1'}}]):page([{...compound,identity_status:'resolved',isomeric_smiles:'C[C@@H](N)C(=O)O',depiction_svg:'<svg></svg>'}]);
  const html=await views.pharmacologyContent(provider,'project','chemistry');
  assert.match(html,/data:image\/svg\+xml/);
  assert.match(html,/C\[C@@H\]/);
  assert.match(html,/alt="2D chemical identity/);
});
test('detail keeps original/operator/units and provider provenance apart',async()=>{
  const html=await views.pharmacologyDrawer(async()=>({record:{endpoint:'IC50',relation_operator:'>',original_value:'200',original_unit:'µM',normalized_value:200000,normalized_unit:'nM'},assay:{substrate:'R-AMC',protein_construct_id:null},snapshot:{provider:'primary-publication'},provider_snapshot:{provider:'ChEMBL'},boundary:'No therapeutic efficacy'}),'project','P1','measurements','M1');
  for(const text of ['original value','200','µM','200000','nM','&gt;','Not reported','Provider-normalized','No therapeutic efficacy']) assert.ok(html.includes(text));
  assert.match(html,/aria-label="Close pharmacology detail"/);
});
