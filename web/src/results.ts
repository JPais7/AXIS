import { EmptyState, escape, label } from './components';

type API = <T>(path: string) => Promise<T>;
type Fields = Record<string, unknown>;
export interface LedgerEntry {
  result_row: string; result_id: string; version: number; interpretation_id: string; experiment_id: string;
  edge: string; scope_type: string; scope_id: string; state: string; statement: string; synthetic: boolean;
  scenario_match: string; result_review: string; interpretation_review: string;
  eligibility: { state: string; eligible: boolean; reasons: string[]; caveats: string[]; rule: string };
}
interface ExperimentRow { id: string; scope: string; proposal_id: string | null; measures_edges: string[]; results: number; qc: string | null; synthetic: boolean; scientific_status: string }
interface TimelineItem { at: string; kind: string; id: string; label: string; detail: string }
interface Review { state: string; reviewers: string[]; caveats: string[]; history: { reviewer: string; decision: string; rationale: string; reviewed_at: string }[] }
interface Detail {
  result: Fields & { row_id: string; id: string; version: number; recorded_at: string; recorded_by: string };
  observed: Fields; interpretations: (Fields & { id: string; statement: string; edge: string; scope_type: string; scope_id: string; proposed_state: string; knowledge_kind: string; caveats: string[]; review: Review; eligibility: LedgerEntry['eligibility'] })[];
  scenario_matches: { outcome_scenario_id: string | null; relationship: string; rationale: string; rule_version: string }[];
  review: Review; superseded_by: string | null; events: Fields[];
  artifacts: { id: string; uri: string; sha256: string; media_type: string; size_bytes: number; link_role: string }[];
  qc: { control_status: string; technical_validity: string; replicate_quality: string; assessment: string; rationale: string } | null;
  deviations: { field: string; proposed_value: string; actual_value: string; interpretation_relevance: string; rationale: string }[];
  experiment: Fields & { id: string; context: Fields; controls: string[]; assay: string | null; exposure: string | null; proposal_id: string | null };
  synthetic: boolean;
}
interface Impact { label: string; assumes: string; critical_after: string | null; recommended_after: string | null; still_unresolved: string[]; diff: { changes: string[]; decision_changed: { answer: string; why: string }; causes: { category: string }[] } }

export const SYNTHETIC_WARNING = 'Synthetic test fixture — not real experimental evidence';
const badge = (text: string, extra = ''): string => `<span class="badge ${extra}">${escape(label(text))}</span>`;
const answerText: Record<string, string> = { yes: 'Yes — the critical uncertainty or recommendation changed', no: 'No — nothing changed', partially: 'Partially — states changed, but not the critical uncertainty or recommendation', pending_review: 'Pending review — changed only on interpretations still pending review' };
export const decisionAnswer = (answer: string): string => answerText[answer] ?? label(answer);

export const syntheticBanner = (show: boolean): string => show ? `<p class="proposal-banner synthetic" role="note"><strong>SYNTHETIC DEMONSTRATION.</strong> ${SYNTHETIC_WARNING}. It must never be mixed with production evidence.</p>` : '';

export const ledgerTable = (items: LedgerEntry[]): string => items.length ? `<div class="table-scroll"><table><caption>Results and their interpretations</caption><thead><tr><th scope="col">Result</th><th scope="col">Scope</th><th scope="col">Proposed edge state</th><th scope="col">Scenario match</th><th scope="col">Eligibility</th><th scope="col">Review (result / interpretation)</th></tr></thead><tbody>${items.map(item => `<tr><th scope="row"><button data-result-row="${escape(item.result_row)}" data-interpretation="${escape(item.interpretation_id)}">${escape(item.result_row)}</button>${item.synthetic ? ' <span class="badge proposal">SYNTHETIC</span>' : ''}</th><td>${escape(item.scope_type)}: ${escape(item.scope_id)}</td><td>${escape(label(item.edge))} → ${escape(label(item.state))}</td><td>${escape(label(item.scenario_match))}</td><td>${escape(label(item.eligibility.state))} <small>(${escape(item.eligibility.rule)})</small></td><td>${escape(label(item.result_review))} / ${escape(label(item.interpretation_review))}</td></tr>`).join('')}</tbody></table></div>` : EmptyState('No experimental result has been imported. Nothing is inferred.');

export const timelineList = (items: TimelineItem[]): string => items.length ? `<ol class="timeline" aria-label="Decision timeline">${items.map(item => `<li><time>${escape(item.at.slice(0, 19).replace('T', ' '))}</time> ${badge(item.kind)} ${escape(item.label)}${item.detail ? ` <small>${escape(item.detail)}</small>` : ''}</li>`).join('')}</ol>` : EmptyState('No events yet.');

export const experimentCards = (items: ExperimentRow[]): string => items.length ? `<div class="strategy-grid">${items.map(item => `<article class="card"><div class="card-heading"><h3>${escape(item.id)}</h3>${item.synthetic ? '<span class="badge proposal">SYNTHETIC</span>' : badge('performed')}</div><dl class="context"><dt>Scope</dt><dd>${escape(item.scope)}</dd><dt>Measures</dt><dd>${escape(item.measures_edges.map(label).join(', '))}</dd><dt>Implements proposal</dt><dd>${escape(item.proposal_id ?? 'none (imported laboratory work)')}</dd><dt>Quality control</dt><dd>${escape(label(item.qc ?? 'not reported'))}</dd><dt>Results</dt><dd>${item.results}</dd></dl><button data-experiment-detail="${escape(item.id)}">Inspect execution, deviations and QC</button></article>`).join('')}</div>` : EmptyState('No performed experiment has been recorded. A proposed experiment is not evidence that anything happened.');

export const resultsView = (experiments: ExperimentRow[], ledger: LedgerEntry[], timeline: TimelineItem[]): string => `${syntheticBanner(experiments.some(item => item.synthetic) || ledger.some(item => item.synthetic))}<p class="intro">Proposal, performance, observation, interpretation, review and decision are separate objects. Importing a result never changes the current decision; a new DecisionState is created only by an explicit rebuild.</p><h2 id="performed">Performed experiments</h2>${experimentCards(experiments)}<h2 id="ledger">Results</h2>${ledgerTable(ledger)}<h2 id="timeline">Decision timeline</h2>${timelineList(timeline)}`;

const reviewBlock = (review: Review, title: string): string => `<section class="card" aria-label="${escape(title)}"><h3>${escape(title)}</h3><p>${badge(review.state)} ${review.reviewers.length ? escape(review.reviewers.join(', ')) : 'no reviewer yet'}</p>${review.caveats.length ? `<ul>${review.caveats.map(item => `<li>${escape(item)}</li>`).join('')}</ul>` : ''}${review.history.length ? `<details><summary>Review history (${review.history.length})</summary><ul>${review.history.map(h => `<li>${escape(h.reviewed_at.slice(0, 19))} — ${escape(h.reviewer)}: ${escape(label(h.decision))} — ${escape(h.rationale)}</li>`).join('')}</ul></details>` : ''}</section>`;

export const matchView = (detail: Detail): string => {
  const facets = Object.entries(detail.observed.facets as Record<string, string>);
  const overall = detail.scenario_matches.find(item => item.outcome_scenario_id === null);
  const per = detail.scenario_matches.filter(item => item.outcome_scenario_id !== null);
  return `<h3>Observed result ↕ expected scenario</h3><p>${badge(overall?.relationship ?? 'ambiguous')} ${escape(overall?.rationale ?? 'No scenario comparison is available.')}</p><div class="two-columns"><section class="card"><h4>Observed facets</h4>${facets.length ? `<ul>${facets.map(([k, v]) => `<li>${escape(label(k))}: <strong>${escape(label(v))}</strong></li>`).join('')}</ul>` : '<p>None recorded.</p>'}</section><section class="card"><h4>Anticipated scenarios compared</h4>${per.length ? `<ul>${per.map(item => `<li>${escape(item.outcome_scenario_id ?? '')}: ${badge(item.relationship)} <small>${escape(item.rationale)}</small></li>`).join('')}</ul>` : '<p>No anticipated scenario matched or conflicted; nothing was force-fitted.</p>'}</section></div>`;
};

export const resultDetailView = (detail: Detail): string => {
  const o = detail.observed as Record<string, unknown>;
  const qc = detail.qc;
  const value = o.numeric_value !== null && o.numeric_value !== undefined ? `${String(o.operator)} ${String(o.numeric_value)} ${String(o.unit ?? '')}${o.uncertainty ? ` (${String(o.uncertainty)})` : ''}` : String(o.qualitative_result ?? 'No value recorded');
  return `<button data-close class="drawer-close" aria-label="Close result">×</button><div class="eyebrow">EXPERIMENTAL RESULT</div><h2 id="drawer-title">${escape(detail.result.row_id)}</h2>${syntheticBanner(detail.synthetic)}<p>${detail.superseded_by ? badge('superseded') + ' by ' + escape(detail.superseded_by) : badge('current version')} <small>recorded ${escape(String(detail.result.recorded_at).slice(0, 19))} by ${escape(detail.result.recorded_by)}</small></p>
<section class="card observed" aria-label="Observed"><h3>OBSERVED</h3><p>${escape(value)}</p><dl class="context"><dt>Endpoint</dt><dd>${escape(String(o.endpoint))}</dd><dt>Result type</dt><dd>${escape(label(String(o.result_type)))}</dd><dt>Replicates</dt><dd>${escape(JSON.stringify(o.replicate_summary ?? {}))}</dd><dt>Statistics</dt><dd>${escape(JSON.stringify(o.statistics ?? {}))}</dd></dl></section>
<section class="card interpreted" aria-label="Interpreted"><h3>INTERPRETATION <small>(not an observation)</small></h3>${detail.interpretations.map(i => `<article><p>${badge(i.knowledge_kind, 'proposal')} ${escape(label(i.edge))} for ${escape(i.scope_type)}: ${escape(i.scope_id)} → <strong>${escape(label(i.proposed_state))}</strong></p><p>${escape(i.statement)}</p>${i.caveats.length ? `<p>Caveats: ${escape(i.caveats.join('; '))}</p>` : ''}<p>Eligibility: ${escape(label(i.eligibility.state))} (${escape(i.eligibility.rule)}) — ${escape(i.eligibility.reasons.join('; '))}</p>${reviewBlock(i.review, 'Interpretation review')}<button data-impact="${escape(i.id)}" data-impact-result="${escape(detail.result.row_id)}">Preview decision impact if accepted</button></article>`).join('') || '<p>No interpretation proposed.</p>'}</section>
${reviewBlock(detail.review, 'Result review')}
<h3>Quality control</h3>${qc ? `<dl class="context"><dt>Controls</dt><dd>${escape(label(qc.control_status))}</dd><dt>Technical validity</dt><dd>${escape(label(qc.technical_validity))}</dd><dt>Replicate quality</dt><dd>${escape(label(qc.replicate_quality))}</dd><dt>Assessment</dt><dd><strong>${escape(label(qc.assessment))}</strong> — ${escape(qc.rationale)}</dd></dl>` : '<p>No quality assessment recorded.</p>'}
${matchView(detail)}
<h3>Design deviations</h3>${detail.deviations.length ? `<ul>${detail.deviations.map(d => `<li>${escape(d.field)}: ${escape(d.proposed_value)} → <strong>${escape(d.actual_value)}</strong> (${escape(label(d.interpretation_relevance))}) — ${escape(d.rationale)}</li>`).join('')}</ul>` : '<p>No deviation from the proposed design recorded.</p>'}
<h3>Execution context</h3><dl class="context">${Object.entries(detail.experiment.context).map(([k, v]) => `<dt>${escape(label(k))}</dt><dd>${escape(String(v ?? 'Not reported'))}</dd>`).join('')}<dt>Assay</dt><dd>${escape(String(detail.experiment.assay ?? 'Not reported'))}</dd><dt>Controls</dt><dd>${escape(detail.experiment.controls.join('; ') || 'Not reported')}</dd><dt>Implements proposal</dt><dd>${escape(detail.experiment.proposal_id ?? 'none')}</dd></dl>
<h3>Raw and processed artifacts</h3>${detail.artifacts.length ? `<ul>${detail.artifacts.map(a => `<li>${badge(a.link_role)} <code>${escape(a.id)}</code> ${escape(a.media_type)}, ${a.size_bytes} bytes<br><small>sha256 ${escape(a.sha256)}</small></li>`).join('')}</ul>` : '<p>No artifact.</p>'}<div id="impact-preview" aria-live="polite"></div>`;
};

export const impactView = (impact: Impact): string => `<section class="card preview" aria-label="Decision impact preview"><h3>${escape(impact.label)}</h3><p class="caption">Assumes ${escape(impact.assumes)}. Derived by the real decision rules; not stored, not the current decision.</p><p><strong>${escape(decisionAnswer(impact.diff.decision_changed.answer))}.</strong> ${escape(impact.diff.decision_changed.why)}</p>${impact.diff.changes.length ? `<ul>${impact.diff.changes.map(c => `<li>${escape(c)}</li>`).join('')}</ul>` : '<p>No state would change.</p>'}<p>Critical uncertainty after: ${escape(impact.critical_after ?? 'none')}. Recommended experiment after: ${escape(impact.recommended_after ?? 'none')}.</p><p>Still unresolved: ${escape(impact.still_unresolved.map(i => i.replace('uncertainty:', '')).join(', ') || 'nothing')}.</p></section>`;

export const reviewQueueView = (queue: { pending_results: string[]; pending_interpretations: string[]; conflicts: string[]; scenario_mapping_review_counts: Record<string, number>; mappings_total: number; mode: string }, mappings: { id: string; effect: string; rationale: string; review: Review }[]): string => `<p class="intro">Scientific review is explicit and append-only. AI-generated mappings and interpretations stay pending until an investigator reviews them; disagreement is shown as a conflict, never resolved by majority.</p><h2 id="pending">Pending</h2><div class="two-columns"><section class="card"><h3>Results (${queue.pending_results.length})</h3>${queue.pending_results.length ? `<ul>${queue.pending_results.map(r => `<li><button data-result-row="${escape(r)}">${escape(r)}</button></li>`).join('')}</ul>` : '<p>None pending.</p>'}</section><section class="card"><h3>Interpretations (${queue.pending_interpretations.length})</h3>${queue.pending_interpretations.length ? `<ul>${queue.pending_interpretations.map(r => `<li>${escape(r)}</li>`).join('')}</ul>` : '<p>None pending.</p>'}</section></div><h2 id="conflicts">Review conflicts</h2>${queue.conflicts.length ? `<ul>${queue.conflicts.map(c => `<li>${escape(c)}</li>`).join('')}</ul>` : '<p>No conflicting reviews.</p>'}<h2 id="mappings">Scenario → explanation mappings</h2><p class="intro">Experiment ranking depends on these authored mappings. ${Object.entries(queue.scenario_mapping_review_counts).map(([k, v]) => `${v} ${escape(label(k))}`).join(', ')} of ${queue.mappings_total}.</p><div class="table-scroll"><table><caption>First mappings awaiting review (AI suggestion)</caption><thead><tr><th scope="col">Scenario | explanation</th><th scope="col">Proposed effect</th><th scope="col">Rationale</th><th scope="col">Review</th></tr></thead><tbody>${mappings.map(m => `<tr><th scope="row">${escape(m.id)}</th><td>${escape(label(m.effect))}</td><td>${escape(m.rationale)}</td><td>${escape(label(m.review.state))}</td></tr>`).join('')}</tbody></table></div>`;

export async function resultsContent(api: API, project: string): Promise<string> {
  const base = `projects/${encodeURIComponent(project)}`;
  const [experiments, ledger, timeline] = await Promise.all([
    api<{ items: ExperimentRow[] }>(`${base}/performed-experiments?limit=50`),
    api<{ items: LedgerEntry[] }>(`${base}/results?limit=50`),
    api<{ items: TimelineItem[] }>(`${base}/decision/timeline`).catch(() => ({ items: [] as TimelineItem[] }))
  ]);
  return resultsView(experiments.items, ledger.items, timeline.items);
}

export async function reviewContent(api: API, project: string): Promise<string> {
  const base = `projects/${encodeURIComponent(project)}`;
  const [queue, mappings] = await Promise.all([
    api<Parameters<typeof reviewQueueView>[0]>(`${base}/review-queue`),
    api<{ items: Parameters<typeof reviewQueueView>[1] }>(`${base}/scenario-mappings?limit=12`)
  ]);
  return reviewQueueView(queue, mappings.items);
}

export async function resultDrawer(api: API, project: string, row: string): Promise<string> {
  return resultDetailView(await api<Detail>(`projects/${encodeURIComponent(project)}/results/${encodeURIComponent(row)}`));
}

export async function impactPreview(api: API, project: string, row: string, interpretation: string): Promise<string> {
  return impactView(await api<Impact>(`projects/${encodeURIComponent(project)}/results/${encodeURIComponent(row)}/decision-impact?interpretation=${encodeURIComponent(interpretation)}`));
}

export async function experimentDetailDrawer(api: API, project: string, id: string): Promise<string> {
  const data = await api<{ experiment: Detail['experiment']; proposal: { title: string; knowledge_kind: string } | null; deviations: Detail['deviations']; qc: Detail['qc']; results: { result: { row_id: string }; observed: Fields }[]; synthetic: boolean }>(`projects/${encodeURIComponent(project)}/performed-experiments/${encodeURIComponent(id)}`);
  return `<button data-close class="drawer-close" aria-label="Close experiment">×</button><div class="eyebrow">PERFORMED EXPERIMENT</div><h2 id="drawer-title">${escape(id)}</h2>${syntheticBanner(data.synthetic)}<h3>Design (proposal)</h3><p>${data.proposal ? `${escape(data.proposal.title)} ${badge(data.proposal.knowledge_kind, 'proposal')}` : 'Not implemented from an AXIS proposal.'}</p><h3>Actual execution</h3><dl class="context">${Object.entries(data.experiment.context).map(([k, v]) => `<dt>${escape(label(k))}</dt><dd>${escape(String(v ?? 'Not reported'))}</dd>`).join('')}<dt>Assay</dt><dd>${escape(String(data.experiment.assay ?? 'Not reported'))}</dd><dt>Controls</dt><dd>${escape(data.experiment.controls.join('; ') || 'Not reported')}</dd><dt>Exposure</dt><dd>${escape(String(data.experiment.exposure ?? 'Not reported'))}</dd></dl><h3>Deviations from the proposal</h3>${data.deviations.length ? `<ul>${data.deviations.map(d => `<li>${escape(d.field)}: ${escape(d.proposed_value)} → ${escape(d.actual_value)} (${escape(label(d.interpretation_relevance))})</li>`).join('')}</ul>` : '<p>None recorded.</p>'}<h3>Quality control</h3><p>${data.qc ? `<strong>${escape(label(data.qc.assessment))}</strong> — ${escape(data.qc.rationale)}` : 'Not reported'}</p><h3>Results</h3><ul>${data.results.map(r => `<li><button data-result-row="${escape(r.result.row_id)}">${escape(r.result.row_id)}</button></li>`).join('')}</ul>`;
}
