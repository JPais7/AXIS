import { EmptyState, escape, label } from './components';

type API = <T>(path: string) => Promise<T>;
type Fields = Record<string, unknown>;
interface Link { relationship: string; evidence_type: string; evidence_id: string; rule_id: string; rationale: string }
interface Explanation { id: string; label: string; statement: string; status: string; knowledge_kind: string; links: Link[]; rule_ids: string[] }
interface Uncertainty { id: string; category: string; question: string; status: string; decision_relevance: string; resolvability: string; rationale: string; fired_rules: string[]; reasons: string[]; affected_explanation_ids: string[]; source_gap_ids: string[] }
interface Effect { explanation_id: string; effect: string; rationale?: string }
interface Scenario { scenario_id: string; kind: string; outcome: string; interpretation: string; explanation_effects: Effect[]; consequence: { category: string; statement: string; new_uncertainty: string | null } }
interface Candidate {
  experiment_id: string; title: string; rank: number | null; reason: string; role_label: string; low_discrimination: boolean; status: string; cost: string;
  profile: Fields & { considered_for: string[]; target_proximity: string; disease_relevance: string; complexity: string; time_estimate: string; role: string; purpose: string; limitations: string[]; prerequisites: [string, string][]; required: Record<string, string[]> };
  discrimination: { separated_pairs: [string, string][] }; interpretability: { level: string; met: string[] };
  feasibility: { level: string; missing: string[]; note: string }; distinct_consequences: number;
}
interface Recommendation {
  question: string; why_now: string; tied_with?: string[]; experiment_id: string; title: string; experiment: string; biological_context: string;
  controls: { negative: string[]; positive: string[] }; primary_endpoint: string; secondary_endpoints: string[]; limitations: string[];
  outcome_scenarios: Scenario[]; why_this_experiment: { uncertainty: string; explanations_separated: string[][]; why_current_evidence_cannot_answer: string; why_outcome_changes_decision: string; remains_unresolved: string[] };
}
interface Row { statement: string; refs: string[][]; epistemic_kind?: string }
export interface DecisionState {
  id: string; version: number; created_at: string; created_by: string; rules_version: string; disclaimer: string;
  hypothesis: { title: string; description: string; knowledge_kind: string };
  position: { supported: Row[]; contradicted: Row[]; unresolved: Row[] };
  explanations: Explanation[]; excluded_explanations: { id: string; reason: string }[];
  uncertainties: Uncertainty[]; critical: { selected: string | null; reasons: string[]; alternatives: { uncertainty_id: string; reason: string }[]; message?: string; tied_with?: string[] };
  candidates: Candidate[]; recommended_experiment_id: string | null; recommendation: Recommendation | null;
  what_would_change_our_mind: { question: string; label: string; would_weaken: Fields[]; would_strengthen: Fields[] };
  constraints: { id: string | null; note: string | null };
  provenance: { ai_generated: string[]; investigator_approved: string[]; deterministic_rules: string[] };
  trace: { rules_fired: { id: string; version: string; description: string }[]; candidates_considered: { experiment_id: string; rank: number | null; reason: string }[]; outcome_logic: string; explanations_not_admitted: { id: string; reason: string }[] };
  graph: { nodes: { id: string; type: string; label: string }[]; edges: { from: string; to: string; kind: string; basis: string }[] };
  diff: { changes: string[]; new_evidence: string[]; cause?: string[]; cause_summary?: string } | null; supersedes_id: string | null;
  review?: { pending_expert_review: number; accepted: number; message: string | null };
  sensitivity?: { method: string; decision_sensitive: Sensitive[]; explanation_sensitive: Sensitive[]; non_decisive: Sensitive[] };
  no_experiment_message?: string | null;
}
interface Sensitive { group: string; removed: string; changes: string[] }
const short = (id: string): string => id.replace(/^(explanation|uncertainty|decision:exp):/, '');
const tag = (text: string, kind = ''): string => `<span class="badge ${kind}">${escape(label(text))}</span>`;
const list = (items: string[], empty = 'None recorded.'): string => items.length ? `<ul>${items.map(item => `<li>${escape(item)}</li>`).join('')}</ul>` : `<p>${escape(empty)}</p>`;
const refText = (refs: string[][]): string => refs.slice(0, 4).map(([kind = '', id = '']) => `${label(kind)}: ${id}`).join(' · ');
const effectMark: Record<string, string> = { strengthens: '▲ strengthens', weakens: '▼ weakens', contradicts: '▼ contradicts', does_not_discriminate: '■ does not discriminate', resolves_for_current_decision: '▲ resolves for current decision' };
const statusCopy = (status: string): string => status.replaceAll('_', ' ');

export const positionSection = (state: DecisionState): string => {
  const group = (title: string, rows: Row[], empty: string): string => `<section class="card" aria-labelledby="pos-${escape(title)}"><h3 id="pos-${escape(title)}">${escape(title)}</h3>${rows.length ? `<ul>${rows.map(row => `<li>${escape(row.statement)}<small class="refs"> ${escape(refText(row.refs))}</small> ${row.epistemic_kind ? tag(row.epistemic_kind) : ''}</li>`).join('')}</ul>` : `<p>${escape(empty)}</p>`}</section>`;
  return `<h2 id="position">Current scientific position</h2><p class="intro">${escape(state.hypothesis.description)} ${tag(state.hypothesis.knowledge_kind, 'proposal')}</p><div class="three-columns">${group('Supported', state.position.supported, 'No edge is supported.')}${group('Contradicted or conflicting', state.position.contradicted, 'None identified in the represented evidence.')}${group('Unresolved', state.position.unresolved, 'No open uncertainty.')}</div>`;
};

export const criticalCard = (state: DecisionState): string => {
  const selected = state.uncertainties.find(item => item.id === state.critical.selected);
  if (!selected) return `<h2 id="critical">Critical uncertainty</h2>${EmptyState(state.critical.message ?? 'No open, testable uncertainty remains in the current evidence state.')}`;
  const affected = state.explanations.filter(item => selected.affected_explanation_ids.includes(item.id)).map(item => item.label);
  return `<section class="critical-uncertainty" aria-labelledby="critical"><h2 id="critical">Critical uncertainty</h2><article><span class="badge">${escape(statusCopy(selected.status))}</span> ${tag(selected.decision_relevance)} ${tag(selected.resolvability)}<h3>${escape(selected.question)}</h3><p>${escape(selected.rationale)}</p><h4>Why this is critical</h4>${list(state.critical.reasons)}<p><strong>Competing explanations affected:</strong> ${escape(affected.join(', ') || 'none')}</p><p><small>Selected by rule DECISION-CRIT-001 over categorical criteria; no numerical score.</small></p></article><h3>Other open uncertainties and why they were not selected</h3><ul class="plain">${state.critical.alternatives.map(item => `<li><strong>${escape(label(short(item.uncertainty_id)))}</strong> — ${escape(item.reason)}</li>`).join('')}</ul></section>`;
};

export const explanationCards = (state: DecisionState): string => {
  const count = (links: Link[], relationship: string): number => links.filter(link => link.relationship === relationship).length;
  return `<h2 id="explanations">Competing explanations</h2><p class="intro">AI-suggested wording, admitted only when current evidence grounds it. Status is a categorical reading of evidence links, not a probability.</p><div class="strategy-grid">${state.explanations.map(item => `<article class="card"><div class="card-heading"><h3>${escape(item.label)}</h3>${tag(item.status)}</div><p>${escape(item.statement)}</p><p>${tag(item.knowledge_kind, item.knowledge_kind === 'ai_suggestion' ? 'proposal' : '')}</p><ul class="plain"><li>Supporting links: ${count(item.links, 'supports')}</li><li>Contradicting links: ${count(item.links, 'contradicts')}</li><li>Unresolved links: ${count(item.links, 'leaves_unresolved')}</li><li>Context limits: ${count(item.links, 'context_limits')}</li></ul><button data-decision-explanation="${escape(item.id)}">Inspect evidence links</button></article>`).join('')}</div>${state.excluded_explanations.map(item => `<p class="caption">Not admitted: ${escape(item.id)} — ${escape(item.reason)}</p>`).join('')}`;
};

const outcome = (scenario: Scenario, names: Map<string, string>): string => `<li><strong>${tag(scenario.kind)} ${escape(scenario.outcome)}</strong><span class="caption"> (prospective — not observed)</span><ul>${scenario.explanation_effects.map(effect => `<li>${escape(names.get(effect.explanation_id) ?? effect.explanation_id)}: ${escape(effectMark[effect.effect] ?? effect.effect)}</li>`).join('')}<li><strong>Next action (${escape(label(scenario.consequence.category))}):</strong> ${escape(scenario.consequence.statement)}${scenario.consequence.new_uncertainty ? ` New uncertainty: ${escape(scenario.consequence.new_uncertainty)}.` : ''}</li></ul></li>`;

export const outcomeTree = (state: DecisionState): string => {
  const rec = state.recommendation;
  if (!rec) return '';
  const names = new Map(state.explanations.map(item => [item.id, item.label]));
  return `<h3 id="outcomes">Outcome tree</h3><p class="caption">Prospective / hypothetical. No probabilities are assigned to branches and no result has been observed.</p><div class="card"><p><strong>Run:</strong> ${escape(rec.title)}</p><ol class="outcome-tree" aria-label="Possible outcomes of the recommended experiment">${rec.outcome_scenarios.map(item => outcome(item, names)).join('')}</ol></div>`;
};

export const recommendation = (state: DecisionState): string => {
  const rec = state.recommendation;
  if (!rec) return `<h2 id="experiment">Recommended next discriminating experiment</h2>${EmptyState(state.no_experiment_message ?? 'No next discriminating experiment is currently justified.')}`;
  const why = rec.why_this_experiment;
  return `<h2 id="experiment">Recommended next discriminating experiment</h2><p class="caption">Conditional on current evidence, current rules and current constraints.${rec.tied_with && rec.tied_with.length ? ` Tied on every scientific criterion with ${escape(rec.tied_with.join(', '))}; identifier order is a display convention only.` : ''}</p><article class="card"><p>${tag('ai_suggestion', 'proposal')} ${tag('proposed')} <span class="caption">AXIS suggestion — not performed, not investigator-approved.</span></p><h3>${escape(rec.title)}</h3><dl class="context"><dt>Question</dt><dd>${escape(rec.question)}</dd><dt>Why now</dt><dd>${escape(rec.why_now)}</dd><dt>Experiment</dt><dd>${escape(rec.experiment)}</dd><dt>Biological context</dt><dd>${escape(rec.biological_context)}</dd><dt>Negative controls</dt><dd>${list(rec.controls.negative)}</dd><dt>Positive controls</dt><dd>${list(rec.controls.positive)}</dd><dt>Primary endpoint</dt><dd>${escape(rec.primary_endpoint)}</dd><dt>Secondary endpoints</dt><dd>${list(rec.secondary_endpoints)}</dd><dt>Limitations</dt><dd>${list(rec.limitations)}</dd></dl><button data-decision-experiment="${escape(rec.experiment_id)}">Inspect experiment, prerequisites and graph links</button></article><section class="card" aria-labelledby="why-experiment"><h3 id="why-experiment">Why this experiment?</h3><ol><li><strong>Uncertainty addressed:</strong> ${escape(why.uncertainty)}</li><li><strong>Explanations it separates:</strong> ${escape(why.explanations_separated.map(pair => pair.map(id => state.explanations.find(item => item.id === id)?.label ?? id).join(' vs ')).join('; ') || 'none')}</li><li><strong>Why current evidence cannot answer it:</strong> ${escape(why.why_current_evidence_cannot_answer)}</li><li><strong>Why the outcome changes the decision:</strong> ${escape(why.why_outcome_changes_decision)}</li><li><strong>What remains unresolved afterwards:</strong> ${escape(why.remains_unresolved.join('; '))}</li></ol></section>${outcomeTree(state)}`;
};

const cell = (value: string): string => `<td>${escape(value)}</td>`;
export const comparisonMatrix = (state: DecisionState): string => {
  const compared = state.candidates.filter(item => item.rank !== null).sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0));
  const names = new Map(state.explanations.map(item => [item.id, item.label]));
  const rows: [string, (item: Candidate) => string][] = [
    ['Rank for the critical uncertainty', item => `${item.rank} — ${item.reason}`],
    ['Role', item => item.role_label],
    ['Question addressed', item => item.profile.considered_for.map(label).join(', ')],
    ['Explanation discrimination', item => item.discrimination.separated_pairs.map(pair => pair.map(id => names.get(id) ?? id).join(' vs ')).join('; ') || 'Low discrimination: separates no pair'],
    ['Target proximity', item => label(item.profile.target_proximity)],
    ['Disease relevance', item => item.profile.disease_relevance],
    ['Interpretability', item => `${item.interpretability.level} (${item.interpretability.met.length} of 4 criteria)`],
    ['Required models', item => (item.profile.required.models ?? []).join('; ') || 'None stated'],
    ['Required reagents', item => (item.profile.required.reagents ?? []).join('; ') || 'None stated'],
    ['Prerequisites not established', item => item.profile.prerequisites.filter(([, status]) => status !== 'available_in_corpus').map(([text]) => text).join('; ') || 'None'],
    ['Complexity', item => item.profile.complexity],
    ['Time estimate', item => item.profile.time_estimate],
    ['Cost', item => item.cost],
    ['Feasibility', item => `${label(item.feasibility.level)}${item.feasibility.note ? ` — ${item.feasibility.note}` : ''}`],
    ['Remaining uncertainty', item => item.profile.limitations.join('; ')],
  ];
  const others = state.candidates.filter(item => item.rank === null);
  return `<h2 id="comparison">Experiment comparison</h2><p class="intro">Transparent dimensions; there is no hidden weighted total. Complexity and cost are never preferred automatically.</p><div class="table-scroll"><table><caption>Candidate experiments considered for the critical uncertainty</caption><thead><tr><th scope="col">Dimension</th>${compared.map(item => `<th scope="col"><button data-decision-experiment="${escape(item.experiment_id)}">${escape(item.title)}</button>${item.low_discrimination ? ' <span class="badge proposal">Low discrimination</span>' : ''}</th>`).join('')}</tr></thead><tbody>${rows.map(([name, read]) => `<tr><th scope="row">${escape(name)}</th>${compared.map(item => cell(read(item))).join('')}</tr>`).join('')}</tbody></table></div>${others.length ? `<h3>Other candidates, not compared for this uncertainty</h3><ul class="plain">${others.map(item => `<li><button data-decision-experiment="${escape(item.experiment_id)}">${escape(item.title)}</button> — ${escape(item.reason)}</li>`).join('')}</ul>` : ''}`;
};

export const changeMind = (state: DecisionState): string => {
  const row = (item: Fields): string => `<li>${escape(String(item.statement))} <small>(${escape(label(String(item.category)))}; ${escape(short(String(item.experiment_id)))})</small></li>`;
  const mind = state.what_would_change_our_mind;
  return `<h2 id="mind">What would change our mind?</h2><p class="intro">${escape(mind.question)} <span class="caption">${escape(mind.label)}</span></p><div class="two-columns"><section class="card"><h3>Results that would weaken the strategy</h3><ul>${mind.would_weaken.map(row).join('') || '<li>None represented.</li>'}</ul></section><section class="card"><h3>Results that would strengthen it</h3><ul>${mind.would_strengthen.map(row).join('') || '<li>None represented.</li>'}</ul></section></div>`;
};

export const reviewBanner = (state: DecisionState): string => state.review && state.review.pending_expert_review ? `<p class="proposal-banner" role="note"><strong>Pending scientific review.</strong> ${escape(state.review.message ?? '')} (${state.review.pending_expert_review} cellular assessments pending expert review, ${state.review.accepted} accepted.)</p>` : '';

export const robustness = (state: DecisionState): string => {
  const sensitivity = state.sensitivity;
  if (!sensitivity) return '';
  const rows = (items: Sensitive[], empty: string): string => items.length ? `<ul>${items.map(item => `<li><strong>${escape(label(item.group))}</strong> — removing ${escape(item.removed)}:<ul>${item.changes.map(change => `<li>${escape(change)}</li>`).join('')}</ul></li>`).join('')}</ul>` : `<p>${escape(empty)}</p>`;
  return `<h2 id="robustness">Decision robustness</h2><p class="intro">Categorical leave-group-out analysis: which evidence, if removed, would change the decision. No probabilities or scores.</p><div class="two-columns"><section class="card"><h3>Evidence the recommendation depends on</h3>${rows(sensitivity.decision_sensitive, 'No single evidence group changes the critical uncertainty or recommendation.')}</section><section class="card"><h3>Evidence that changes only explanations</h3>${rows(sensitivity.explanation_sensitive, 'None.')}</section></div><details><summary>Supportive but non-decisive evidence (${sensitivity.non_decisive.length})</summary>${rows(sensitivity.non_decisive, 'None.')}</details>`;
};

export const constraintsSection = (state: DecisionState): string => `<h2 id="constraints">Investigator constraints</h2><div class="card">${state.constraints.id ? `<p>Investigator constraints ${escape(state.constraints.id)} applied to feasibility.</p>` : `<p><strong>${escape(state.constraints.note ?? '')}</strong></p><p>Cost: not provided. Time: unknown unless the investigator enters estimates.</p>`}</div>`;

export const traceSection = (state: DecisionState): string => `<h2 id="trace">Evidence and rule trace</h2><details><summary>Rules fired (${state.trace.rules_fired.length}, ${escape(state.rules_version)})</summary><ul>${state.trace.rules_fired.map(rule => `<li><code>${escape(rule.id)}</code> v${escape(rule.version)} — ${escape(rule.description)}</li>`).join('')}</ul></details><details><summary>Candidates considered and why each ranked as it did</summary><ul>${state.trace.candidates_considered.map(item => `<li>${escape(short(item.experiment_id))}: ${escape(item.reason)}</li>`).join('')}</ul></details><details><summary>Outcome logic and graph paths (text equivalent)</summary><p>${escape(state.trace.outcome_logic)}</p><ul>${state.graph.edges.map(edge => `<li>${escape(short(edge.from))} —${escape(label(edge.kind))}→ ${escape(short(edge.to))}: ${escape(edge.basis)}</li>`).join('')}</ul></details><p class="caption">AI-generated: ${state.provenance.ai_generated.length} components. Investigator-approved: ${state.provenance.investigator_approved.length}. ${escape(state.disclaimer)}</p>`;

export const historySection = (items: DecisionState[]): string => `<h2 id="history">Decision history</h2>${items.map(item => `<article class="card"><h3>Decision state v${item.version}</h3><p class="identifier">${escape(item.id)} · ${escape(item.created_at)}</p>${item.diff && item.diff.changes.length ? `<h4>Since previous decision</h4>${item.diff.cause_summary ? `<p><strong>${escape(item.diff.cause_summary)}</strong></p>` : ''}${list(item.diff.changes)}${item.diff.new_evidence.length ? `<p>New evidence: ${escape(item.diff.new_evidence.join('; '))}</p>` : ''}` : `<p>${item.supersedes_id ? 'No changes recorded.' : 'First decision state; nothing to compare.'}</p>`}</article>`).join('')}`;

export const decisionView = (state: DecisionState, history: DecisionState[]): string => `<p class="proposal-banner">${escape(state.disclaimer)}</p>${reviewBanner(state)}<nav aria-label="Decision sections"><p>${[['position', 'Position'], ['critical', 'Critical uncertainty'], ['explanations', 'Competing explanations'], ['experiment', 'Recommended experiment'], ['comparison', 'Comparison'], ['mind', 'What would change our mind'], ['robustness', 'Robustness'], ['constraints', 'Constraints'], ['trace', 'Trace'], ['history', 'History']].map(([id, text]) => `<a href="#${id}">${text}</a>`).join(' · ')}</p></nav><p><span class="badge">Decision state v${state.version}</span> <span class="caption">${escape(state.id)} · rules ${escape(state.rules_version)}</span></p>${positionSection(state)}${criticalCard(state)}${explanationCards(state)}${recommendation(state)}${comparisonMatrix(state)}${changeMind(state)}${robustness(state)}${constraintsSection(state)}${traceSection(state)}${historySection(history)}`;

export async function decisionContent(api: API, project: string): Promise<string> {
  const base = `projects/${encodeURIComponent(project)}`;
  const current = await api<{ state: DecisionState | null; message?: string }>(`${base}/decision`);
  if (!current.state) return EmptyState(current.message ?? 'No DecisionState has been built; do not infer a next experiment.');
  const history = await api<{ items: DecisionState[] }>(`${base}/decision/history?limit=20`);
  return decisionView(current.state, history.items);
}

const close = (name: string): string => `<button data-close class="drawer-close" aria-label="Close ${name}">×</button>`;

export async function explanationDrawer(api: API, project: string, id: string): Promise<string> {
  const data = await api<{ items: Explanation[] }>(`projects/${encodeURIComponent(project)}/explanations`);
  const item = data.items.find(value => value.id === id);
  if (!item) return `${close('explanation')}<h2 id="drawer-title">Explanation unavailable</h2>`;
  const groups = ['supports', 'contradicts', 'leaves_unresolved', 'context_limits'];
  return `${close('explanation')}<div class="eyebrow">EXPLANATION EVIDENCE</div><h2 id="drawer-title">${escape(item.label)}</h2><p>${escape(item.statement)}</p><p>${tag(item.status)} ${tag(item.knowledge_kind, 'proposal')}</p>${groups.map(group => {
    const links = item.links.filter(link => link.relationship === group);
    return `<h3>${escape(label(group))} (${links.length})</h3>${links.length ? `<ul>${links.slice(0, 40).map(link => `<li><code>${escape(link.evidence_type)}</code> ${escape(link.evidence_id)} — ${escape(link.rationale)} <small>(${escape(link.rule_id)})</small></li>`).join('')}</ul>` : '<p>None.</p>'}${links.length > 40 ? `<p class="caption">${links.length - 40} further links not shown.</p>` : ''}`;
  }).join('')}<p class="caption">Status derived by DECISION-EXPL-001 from these links; absence of evidence is listed as unresolved, never as contradiction.</p>`;
}

export async function experimentDrawer(api: API, project: string, id: string): Promise<string> {
  const data = await api<{ experiment: Fields; analysis: Candidate; scenarios: Scenario[]; addressed_gap_ids: string[]; discriminates: string[] }>(`projects/${encodeURIComponent(project)}/candidate-experiments/${encodeURIComponent(id)}`);
  const item = data.analysis;
  return `${close('experiment')}<div class="eyebrow">CANDIDATE EXPERIMENT</div><h2 id="drawer-title">${escape(String(data.experiment.title))}</h2><p>${tag('ai_suggestion', 'proposal')} ${tag(item.status)} ${item.low_discrimination ? '<span class="badge proposal">Low discrimination</span>' : ''}</p><p>${escape(String(data.experiment.rationale))}</p><dl class="context"><dt>System</dt><dd>${escape(String(data.experiment.experimental_system))}</dd><dt>Intervention</dt><dd>${escape(String(data.experiment.intervention_description))}</dd><dt>Purpose</dt><dd>${escape(label(String(item.profile.purpose)))}</dd><dt>Prerequisites</dt><dd>${list(item.profile.prerequisites.map(([text, status]) => `${text} — ${label(status)}`))}</dd><dt>Evidence gaps addressed</dt><dd>${list(data.addressed_gap_ids, 'None; this candidate is not linked to a stored gap.')}</dd><dt>Feasibility</dt><dd>${escape(label(item.feasibility.level))} ${escape(item.feasibility.note)}</dd><dt>Cost</dt><dd>${escape(item.cost)}</dd></dl><h3>Outcome scenarios (prospective)</h3><ul>${data.scenarios.map(scenario => `<li><strong>${tag(scenario.kind)} ${escape(scenario.outcome)}</strong><br>${escape(scenario.consequence.statement)}</li>`).join('')}</ul>`;
}
