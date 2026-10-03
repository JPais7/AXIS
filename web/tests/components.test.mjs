import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import ts from 'typescript';

// Pure rendering contracts; no browser, network or scientific interpretation.
const source = await readFile(new URL('../src/components.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } });
const components = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);

test('compact cards separate context lines and strategies retain compact visible details', async () => {
  const css = await readFile(new URL('../src/hardening.css', import.meta.url), 'utf8');
  assert.match(css, /\.compact-card > span:not\(\.badge\)\{display:block/);
  assert.match(css, /\.strategy-card \.state\{padding:10px 12px/);
  assert.doesNotMatch(css, /\.strategy-card[^}]*display:none/);
});

test('knowledge kind and empty scientific states remain distinguishable', () => {
  assert.match(components.KnowledgeKindBadge('ai_suggestion'), /proposal/);
  assert.match(components.KnowledgeKindBadge('source_assertion'), /source assertion/);
  const states = ['not_assessed', 'no_direct_evidence', 'inconclusive', 'contradicts'].map(components.EvidenceState);
  assert.equal(new Set(states).size, 4);
  assert.match(states[0], /Not assessed/);
  assert.match(states[1], /No direct evidence identified in curated corpus/);
  assert.match(states[2], /Evidence exists but is inconclusive/);
  assert.match(states[3], /Contradictory evidence/);
});

test('context and provenance escape source values without inventing unknowns', () => {
  const context = components.ContextTable({ hla_status: '<B27>', genotype: null });
  assert.match(context, /&lt;B27&gt;/);
  assert.match(context, /Not reported/);
  const transformation = components.Transformations([{ name: 'curation', version: '1', parameters: [['source', '<script>']] }]);
  assert.match(transformation, /&lt;script&gt;/);
  assert.doesNotMatch(transformation, /<script>/);
});

test('graph classifications expose different symbols and inspection identifiers', () => {
  const item = { claim: { subject: { label: 'ERAP1' }, predicate: 'changes', object: { label: 'peptide endpoint' } }, summary: { claim_id: 'C1', source_id: 'PMID:1' } };
  const direct = components.MechanismEdge({ ...item, assessment: { classification: 'directly_demonstrated' } });
  const hypothesis = components.MechanismEdge({ ...item, assessment: { classification: 'hypothesized' } });
  assert.match(direct, /━━→/);
  assert.match(direct, /directly demonstrated/);
  assert.match(hypothesis, /···→/);
  assert.match(hypothesis, /hypothesized/);
  assert.match(direct, /data-claim="C1"/);
});

test('experiment scenarios are conditional proposals, never observed results', () => {
  const html = components.ExperimentCard({ experiment: { title: 'Comparison', question_id: 'Q1', rationale: 'Review needed', experimental_system: 'Undecided', intervention_description: 'Concept', endpoint_description: 'Measured separately', provenance: { source_identifier: 'AI', transformations: [] } }, outcomes: [{ possible_outcome: 'Possible A', interpretation: 'Conditional A' }, { possible_outcome: 'Possible B', interpretation: 'Conditional B' }] });
  assert.match(html, /AXIS SUGGESTION — NOT EXPERIMENTAL EVIDENCE/);
  assert.match(html, /OUTCOME SCENARIO A/);
  assert.match(html, /OUTCOME SCENARIO B/);
  assert.match(html, /Interpretation A/);
  assert.match(html, /Interpretation B/);
});

test('comparison safely displays original fields and independent assessment subjects', () => {
  const item = { claim_id: 'C1', statement: '<script>statement</script>', knowledge_kind: 'source_assertion', source_id: 'PMID:1', context: { hla_status: 'HLA-B27', allotype: null, experimental_system: 'U937' }, claim: { predicate: 'knockdown_increases' }, source: { locator: 'Figure 2' }, perturbations: [], assessments: [{ role: 'inconclusive', strategy_id: 'S1', question_id: null }], mechanisms: [{ classification: 'directly_demonstrated' }], limitation: 'Context-specific' };
  const html = components.ContextComparison([item, { ...item, claim_id: 'C2', context: { experimental_system: 'HeLa.B27', hla_status: null } }]);
  assert.match(html, /<table/);
  assert.match(html, /scope="col"/);
  assert.match(html, /scope="row"/);
  assert.match(html, /U937/);
  assert.match(html, /HeLa.B27/);
  assert.match(html, /Not reported/);
  assert.match(html, /knockdown increases/);
  assert.match(html, /S1/);
  assert.match(html, /no automatic contradiction verdict/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});

test('package review banner and limited coverage do not imply expert validation', () => {
  const html = components.ProjectHeader({ project: { status: 'active' }, pair: { target: { label: 'ERAP1' }, disease: { label: 'axSpA' } }, project_kind: 'curated', coverage: 'AS evidence; broader axSpA unassessed' }, 'Overview');
  assert.match(html, /AI-assisted curation · pending expert review/);
  assert.match(components.EvidenceState('limited_evidence'), /Limited curated coverage/);
  assert.match(components.AppShell('P1', 'overview', html), /Skip to workspace content/);
});

test('hardened primary text and status palettes meet normal-text contrast', () => {
  const luminance = hex => {
    const channels = hex.match(/\w\w/g).map(value => parseInt(value, 16) / 255).map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  };
  for (const [foreground, background] of [['526971', 'ffffff'], ['526971', 'f5f7f8'], ['456b73', 'ffffff'], ['775b22', 'faf4e6'], ['4d6e63', 'ffffff'], ['b9cbd0', '152c32'], ['47665f', 'f0f6f4']]) {
    const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
    assert.ok((values[0] + 0.05) / (values[1] + 0.05) >= 4.5, `${foreground} on ${background}`);
  }
});

test('overview never presents a proposed fixture perturbation as performed', () => {
  const proposal = { status: 'proposed', perturbation_type: 'inhibitor', intervention: null, scientific_context: { experimental_system: 'Proposal only' }, observed_effect_claim_id: null };
  assert.match(components.PerformedPerturbationPreview([proposal]), /No performed perturbation/);
  assert.doesNotMatch(components.PerformedPerturbationPreview([proposal]), /data-claim=/);
  const measured = { ...proposal, status: 'performed', scientific_context: { experimental_system: 'U937' }, observed_effect_claim_id: 'C13' };
  const html = components.PerformedPerturbationPreview([proposal, measured]);
  assert.match(html, /data-claim="C13"/);
  assert.match(html, /U937/);
  assert.doesNotMatch(html, /Proposal only/);
});
