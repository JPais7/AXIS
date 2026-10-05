import { EmptyState, escape, label } from './components';

type API = <T>(path: string) => Promise<T>;
export interface DatasetRow { id: string; endpoint: string; target: string; assay_context: Record<string, string | number | null>; revision: number; compounds: number; measurements: number; checksum: string; synthetic: boolean; label: string; review_state: string }
export interface Comparability { dataset_a: string; dataset_b: string; state: string; rationale: string[] }
export interface Overview { datasets: DatasetRow[]; comparability: Comparability[]; models: { id: string; algorithm: string; fingerprint: string }[]; boundaries: string[] }
export interface Pair { id: string; statement: string; compound_a: string; compound_b: string; transformation: string; measurement_a: { value: number | null; operator: string }; measurement_b: { value: number | null; operator: string }; activity_change: { direction: string } }
export interface Sar { observed: { label: string; matched_pairs: Pair[]; scaffold_groups: { scaffold: string; members: string[] }[] }; inferred: { label: string; hypotheses: { id: string; statement: string; supporting_observations: string[]; contradictory_observations: string[]; falsification: string; review_state: string }[] }; contradictory: unknown[]; missing_experiments: string[] }
export interface Eligibility { dataset_id: string; assessments: { conclusion: string; readiness: string; reasons: string[]; counts: Record<string, number>; checks: { check: string; passed: boolean; detail: string; blocking: boolean }[] }[] }
export interface State { revision: number; entries: { dataset: DatasetRow; eligibility: string; readiness: string; models: string[]; observed_sar: number; sar_hypotheses: number; predictions: string[] }[]; chemical_uncertainties: { id: string; question: string; status: string }[]; next_compounds: { statement: string; selected: { compound_ref: string; rationales: string[]; conflicts: string[] }[]; rules: Record<string, string>; not_asserted: string[] } | null; diff: { causes: string[] }; boundaries: string[] }

const pill = (text: string): string => `<span class="badge">${escape(label(text))}</span>`;
const SYNTHETIC = 'SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE';
const ctx = (c: Record<string, string | number | null>): string => ['target', 'assay_type', 'substrate', 'endpoint'].map(k => `${escape(label(k))}: ${escape(c[k] ?? 'unspecified')}`).join(' · ');

export const datasetSection = (o: Overview): string => o.datasets.length
  ? `<section class="section"><h2>What has been measured?</h2><p class="caption">One dataset per assay context. Measurements from different contexts are never pooled.</p><div class="table-scroll"><table><caption>Frozen learning datasets (a transformation of existing measurements, not a new source)</caption><thead><tr><th scope="col">Context</th><th scope="col">Compounds</th><th scope="col">Measurements</th><th scope="col">Revision</th><th scope="col">Review</th></tr></thead><tbody>${o.datasets.map(d => `<tr><th scope="row">${ctx(d.assay_context)}${d.synthetic ? `<br><span class="source-tag">${SYNTHETIC}</span>` : ''}</th><td>${d.compounds}</td><td>${d.measurements}</td><td>r${d.revision} <code>${escape(d.checksum.slice(0, 10))}</code></td><td>${pill(d.review_state)}</td></tr>`).join('')}</tbody></table></div></section>`
  : `<section class="section"><h2>What has been measured?</h2>${EmptyState('No learning dataset has been built. Run axis chemistry dataset build.')}</section>`;

export const comparabilitySection = (o: Overview): string => o.comparability.length
  ? `<section class="section"><h2>What is directly comparable?</h2><ul class="plain">${o.comparability.map(c => `<li>${pill(c.state)} ${escape(c.dataset_a.split('|').slice(-2).join(' / '))} versus ${escape(c.dataset_b.split('|').slice(-2).join(' / '))} — ${escape(c.rationale.join('; '))}</li>`).join('')}</ul><p class="caption">No conversion between endpoints (IC50, Ki, AC50) or between biochemical and cellular readouts is performed.</p></section>`
  : '';

export const sarSection = (s: Sar | null): string => !s ? '' : `<section class="section"><h2>What SAR is observed?</h2><h3>${escape(s.observed.label)}</h3><ul class="plain">${s.observed.matched_pairs.slice(0, 12).map(p => `<li>${escape(p.statement)}</li>`).join('') || '<li>no matched pair is measured</li>'}</ul></section><section class="section"><h2>What SAR is only hypothesized?</h2><h3>${escape(s.inferred.label)}</h3>${s.inferred.hypotheses.slice(0, 8).map(h => `<article class="card"><span class="badge proposal">◇ INFERRED — not an observation</span> ${pill(h.review_state)}<p>${escape(h.statement)}</p><p class="caption">${h.supporting_observations.length} supporting · ${h.contradictory_observations.length} contradicting observations. Would change our mind: ${escape(h.falsification)}</p></article>`).join('') || '<p class="caption">none</p>'}${s.missing_experiments.length ? `<h3>Missing experiments</h3><ul class="plain">${s.missing_experiments.map(m => `<li>${escape(m)}</li>`).join('')}</ul>` : ''}</section>`;

export const eligibilitySection = (e: Eligibility | null): string => {
  const a = e?.assessments[e.assessments.length - 1];
  if (!a) return '<section class="section"><h2>Is the dataset model-eligible?</h2><p class="caption">Not assessed.</p></section>';
  const refused = a.conclusion === 'not_eligible';
  return `<section class="section"><h2>Is the dataset model-eligible?</h2><p>${pill(a.conclusion)} ${pill(a.readiness)}</p>${refused ? '<div class="critical-uncertainty" role="status"><h3>MODEL NOT BUILT</h3><p>Insufficient data for a defensible predictive model. This is a scientific result, not a failure.</p></div>' : ''}<ul class="plain">${a.checks.map(c => `<li>${c.passed ? '▪ passed' : c.blocking ? '✕ blocking' : '△ condition'} — ${escape(c.check)}: ${escape(c.detail)}</li>`).join('')}</ul></section>`;
};

export const modelSection = (o: Overview): string => o.models.length
  ? `<section class="section"><h2>What can the model predict?</h2><ul class="plain">${o.models.map(m => `<li>${escape(m.algorithm)} <code>${escape(m.fingerprint.slice(0, 12))}</code> — compared with simpler baselines under a leakage-checked split; validation dimensions are shown separately and there is no model score.</li>`).join('')}</ul><p class="caption">Cross-validation is not prospective validation; model confidence is not experimental certainty.</p></section>`
  : '<section class="section"><h2>What can the model predict?</h2><p>No model exists for this project. <strong>MODEL NOT BUILT</strong> where the dataset is not eligible.</p></section>';

export const nextSection = (s: State | null): string => {
  const n = s?.next_compounds;
  if (!n) return '<section class="section"><h2>Which compound should we test next, and why?</h2><p class="caption">No proposal recorded. Proposals follow explicit rules and are never ranked by a score.</p></section>';
  return `<section class="section"><h2>Which compound should we test next, and why?</h2><p>${escape(n.statement)}</p>${n.selected.map(r => `<article class="card"><strong>${escape(r.compound_ref)}</strong> ${r.rationales.map(pill).join(' ')}${r.conflicts.length ? `<p class="caption">${escape(r.conflicts.join('; '))}</p>` : ''}<ul class="plain">${r.rationales.map(x => `<li>${escape(n.rules[x] ?? x)}</li>`).join('')}</ul></article>`).join('')}<ul class="plain">${n.not_asserted.map(x => `<li>${escape(x)}</li>`).join('')}</ul></section>`;
};

export const stateSection = (s: State | null): string => !s ? '' : `<section class="section"><h2>Chemical learning state r${s.revision}</h2><ul class="plain">${s.entries.map(e => `<li>${escape(String(e.dataset.assay_context.substrate ?? ''))} ${escape(e.dataset.endpoint)}: ${pill(e.readiness)} · ${e.observed_sar} observed SAR records · ${e.sar_hypotheses} hypotheses · ${e.models.length} models · ${e.predictions.length} predictions</li>`).join('')}</ul><h3>Chemical uncertainties</h3><ul class="plain">${s.chemical_uncertainties.map(u => `<li>${escape(u.question)} ${pill(u.status)}</li>`).join('') || '<li>none recorded</li>'}</ul><p class="caption">Cause of last change: ${escape(s.diff.causes.map(label).join(', '))}. History is never rewritten.</p></section>`;

export const learningView = (o: Overview, sar: Sar | null, elig: Eligibility | null, state: State | null): string =>
  `<p class="proposal-banner" role="note"><strong>Observed chemistry, inferred SAR and model predictions are different objects.</strong> ${escape(o.boundaries.join(' · '))}. A prediction is never shown as a measurement.</p>${datasetSection(o)}${comparabilitySection(o)}${sarSection(sar)}${eligibilitySection(elig)}${modelSection(o)}${nextSection(state)}${stateSection(state)}`;

export async function learningContent(api: API, projectId: string): Promise<string> {
  const base = `projects/${encodeURIComponent(projectId)}/chemical-learning`;
  const overview = await api<Overview>(base);
  const params = new URLSearchParams(location.search);
  const selected = params.get('dataset') || overview.datasets[0]?.id || '';
  const picker = overview.datasets.length > 1 ? `<nav aria-label="Datasets" class="strategy-grid">${overview.datasets.map(d => `<a data-nav class="compact-card" ${d.id === selected ? 'aria-current="page"' : ''} href="?dataset=${encodeURIComponent(d.id)}"><strong>${ctx(d.assay_context)}</strong><span>${d.compounds} compounds</span></a>`).join('')}</nav>` : '';
  const [sar, elig, state] = await Promise.all([
    selected ? api<Sar>(`${base}/sar/${encodeURIComponent(selected)}`).catch(() => null) : null,
    selected ? api<Eligibility>(`${base}/eligibility/${encodeURIComponent(selected)}`).catch(() => null) : null,
    api<State>(`${base}/learning-state`).catch(() => null)
  ]);
  return `<p class="intro">What have we actually learned from the chemistry, what can we responsibly predict, and which compound would teach us the most if tested next?</p>${picker}${learningView(overview, sar, elig, state)}`;
}
