import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import ts from 'typescript';

const options = { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 };
const componentSource = await readFile(new URL('../src/components.ts', import.meta.url), 'utf8');
const components = ts.transpileModule(componentSource, { compilerOptions: options }).outputText;
const componentUrl = `data:text/javascript;base64,${Buffer.from(components).toString('base64')}`;
const source = await readFile(new URL('../src/structure-ui.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: options }).outputText.replace("'./components'", JSON.stringify(componentUrl));
const views = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);

test('structure list escapes source title and distinguishes per-chain descriptive coverage', () => {
  const html = views.StructureSummary({
    structure: { provider_structure_id:'3QNF',title:'<script>',experimental_method:'X-RAY DIFFRACTION',resolution:null,revision:null },
    constructs:[{start_residue:1,end_residue:941}],
    chains:[{label_asym_id:'A',coverage:{canonical_with_coordinates:696,canonical_length:941}},{label_asym_id:'B',coverage:{canonical_with_coordinates:802,canonical_length:941}}],
  }, '/structures');
  assert.match(html,/&lt;script&gt;/);
  assert.doesNotMatch(html,/<script>/);
  assert.match(html,/696\/941/);
  assert.match(html,/802\/941/);
  assert.match(html,/Not reported/);
  assert.doesNotMatch(html,/druggable|inhibitor efficacy/i);
});

test('coverage buttons distinguish unresolved, outside, insertion and substitution textually', () => {
  const html = views.ResidueButtons([
    {canonical_position:1,canonical_identity:'M',status:'unresolved_coordinate',coordinate_present:false},
    {canonical_position:2,canonical_identity:'V',status:'not_in_construct',coordinate_present:false},
    {construct_position:3,residue_identity:'A',status:'insertion',coordinate_present:true},
    {canonical_position:4,canonical_identity:'K',residue_identity:'R',status:'engineered_substitution',coordinate_present:true,author_residue_number:'104',insertion_code:'A'},
  ]);
  for (const status of ['unresolved_coordinate','not_in_construct','insertion','engineered_substitution']) assert.match(html,new RegExp(status));
  assert.match(html,/Construct insertion 3/);
  assert.match(html,/author 104A/);
  assert.match(html,/aria-label=/);
});

test('viewer is lazy, local and missing-WebGL does not remove scientific facts', () => {
  assert.match(source,/import\('\.\/structure-viewer'\)/);
  assert.match(source,/\/coordinates/);
  assert.match(source,/All mapping facts remain available textually/);
  assert.match(source,/Canonical mapping unavailable/);
  assert.match(source,/drawer\.showModal/);
  assert.match(source,/button\.focus/);
  assert.doesNotMatch(source,/files\.rcsb\.org|fetch\(/);
});

test('missing target identity retains an explicit empty state without loading coordinates',async()=>{
  globalThis.location = {search:''};
  let calls = 0;
  const html = await views.structureContent(async()=>{calls++;return {items:[]};},'P');
  assert.match(html,/No protein identity imported/);
  assert.equal(calls,1);
  delete globalThis.location;
});
