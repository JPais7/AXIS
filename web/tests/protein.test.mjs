import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import ts from 'typescript';

const options = { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 };
const componentSource = await readFile(new URL('../src/components.ts', import.meta.url), 'utf8');
const components = ts.transpileModule(componentSource, { compilerOptions: options }).outputText;
const componentUrl = `data:text/javascript;base64,${Buffer.from(components).toString('base64')}`;
const proteinSource = await readFile(new URL('../src/protein.ts', import.meta.url), 'utf8');
const protein = ts.transpileModule(proteinSource, { compilerOptions: options }).outputText.replace("'./components'", JSON.stringify(componentUrl));
const views = await import(`data:text/javascript;base64,${Buffer.from(protein).toString('base64')}`);

const item = { protein: { id: 'P1', primary_accession: 'Q9NZ08', recommended_name: '<script>', namespace: 'uniprot', entry_name: 'ERAP1_HUMAN', organism_name: 'Homo sapiens', taxon_id: 9606, reviewed_status: 'Reviewed', sequence: 'ACDE', sequence_length: 4, sequence_checksum: 'abc', sequence_version: 3, record_version: 218 }, mappings: [{ gene_entity_id: 'ERAP1', gene_namespace: 'HGNC-symbol', taxon_id: 9606, status: 'verified', notes: 'identity only' }], isoforms: [{ accession: 'Q9NZ08-1', canonical: true, sequence_length: 4, sequence_version: null }], snapshot: { provider: 'UniProt', provider_record_id: 'Q9NZ08', retrieval_timestamp: '2026-10-03', request_url: 'https://rest.uniprot.org/uniprotkb/Q9NZ08.json', provider_release: null, raw_content_checksum: 'raw', importer_version: '1', local_resource_path: 'frozen.json' }, boundary: 'Identity is not therapeutic evidence.' };

test('target card distinguishes identities, escapes provider text and discloses indexed absence', () => {
  const html = views.TargetIdentityCard(item);
  for (const heading of ['Gene', 'Protein', 'Isoform', 'Source']) assert.match(html, new RegExp(`<h3>${heading}</h3>`));
  assert.match(html, /encodes/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /No structure records have been imported/);
  assert.match(html, /Not reported/);
  assert.match(html, /Identity is not therapeutic evidence/);
});

test('sequence numbering and copy are explicit and sequence area is keyboard focusable', () => {
  const html = views.SequenceView('A'.repeat(61), 'Canonical');
  assert.match(html, /1  A{60}  60/);
  assert.match(html, /61  A  61/);
  assert.match(html, /tabindex="0"/);
  assert.match(html, /Copy sequence/);
  assert.match(html, /role="status"/);
});

test('provenance drawer preserves unknown release and exposes both checksums', () => {
  const html = views.ProteinProvenance(item);
  assert.match(html, /Close protein provenance/);
  assert.match(html, /Not reported/);
  assert.match(html, /raw checksum/);
  assert.match(html, /sequence checksum/);
  assert.match(html, /frozen.json/);
  assert.match(html, /verified/);
});
