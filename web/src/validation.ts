import { EmptyState, escape, label } from './components';

type API = <T>(path: string) => Promise<T>;
export interface CaseRow {
  case_id: string; set_id: string; status: string; benchmark_kind: string; synthetic: boolean;
  label: string; cutoff: string; case_type: string; question: string;
}
interface SourceRow { source: string; title: string; nominal_publication_date?: string; first_publicly_accessible_date: string; availability_kind?: string }
interface Finding { category: string; subject: string; detail: string }
interface Relevance { relevance: string; title: string; first_publicly_accessible_date: string; edge_changes: Record<string, string[]>; status_changes: Record<string, string[]>; records: number }
interface Assessment {
  conclusion: { conclusion: string; basis: string[]; label?: string };
  relevance: Record<string, Relevance>;
  matrix: Record<string, { result: string | string[] }>;
  baseline_comparison: { baseline: string; run: string; result: string; stochastic?: boolean; frozen_at: string; baseline_edge: string }[];
  leave_one_source_out: { removed_source: string; decision_changed: string }[];
  provenance: { decision_rules_fingerprint: string; software_commit: string; protocol_fingerprint: string; benchmark_kind: string; rule_revision: { status: string } | null; human_review: string };
  limits: string[];
}
interface Diff { edges: Record<string, string[]>; explanations: Record<string, string[]>; uncertainties: Record<string, string[]>; critical_uncertainty: string[] | null; recommended_experiment: string[] | null; decision_changed: string }
export interface CaseView {
  case_id: string; status: string; label: string;
  protocol: { cutoff: string; cutoff_rationale: string; question: string; selection_rationale: string; protocol_fingerprint: string; benchmark_kind: string; synthetic: boolean; horizon?: string | null; excluded_undated_records?: number };
  snapshots: { fingerprint: string; sources: SourceRow[]; records: Record<string, number> }[];
  cutoff_run: { run_id: string; rules_fingerprint: string; software_commit: string; state: { critical_uncertainty_id: string | null; recommended_experiment_id: string | null; recommendation_question: string | null; no_experiment_message: string | null; edges: Record<string, string>; explanations: Record<string, string>; uncertainties: Record<string, { category: string; status: string }> }; decision_validity: { result: string }; rule_revision: { status: string } | null } | null;
  audits: { phase: string; valid: boolean; findings: Finding[]; label: string | null }[];
  baselines: { kind: string; run: string; frozen_at: string; sha256: string }[];
  reveal: { future_sources: SourceRow[]; diff: Diff } | null;
  assessment: Assessment | null;
  reviews: { id: string; reviewer: string; preference: string; conclusion_opinion: string; rationale: string }[];
}

const SYNTHETIC = 'SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE';
const INVALID = 'INVALID — TEMPORAL LEAKAGE';
const pill = (text: string): string => `<span class="badge">${escape(label(text))}</span>`;
const dl = (rows: [string, string][]): string => `<dl class="context">${rows.map(([k, v]) => `<dt>${escape(k)}</dt><dd>${v}</dd>`).join('')}</dl>`;

export const kindBanner = (c: { synthetic: boolean; benchmark_kind: string }): string =>
  c.synthetic
    ? `<p class="proposal-banner synthetic" role="note"><strong>${SYNTHETIC}.</strong> Invented sources and results that exercise the machinery. They must never be read as findings.</p>`
    : `<p class="proposal-banner" role="note"><strong>${escape(label(c.benchmark_kind).toUpperCase())} benchmark.</strong> Retrospective: it cannot establish clinical efficacy or prospective validity, and it is not an independent validation when the rules were developed on the same data.</p>`;

export const caseList = (cases: CaseRow[], selected: string): string => cases.length
  ? `<nav aria-label="Benchmark cases" class="strategy-grid">${cases.map(c => `<a data-nav class="compact-card" ${c.case_id === selected ? 'aria-current="page"' : ''} href="?case=${encodeURIComponent(c.case_id)}"><strong>${escape(c.case_id)}</strong>${pill(c.status)} ${pill(c.benchmark_kind)}<span>T = ${escape(c.cutoff)}</span>${c.synthetic ? `<span class="source-tag">${SYNTHETIC}</span>` : ''}</a>`).join('')}</nav>`
  : EmptyState('No benchmark case is available.');

export const leakageState = (view: CaseView): string => {
  const failed = view.status === 'invalid' || view.audits.some(a => !a.valid);
  if (failed) {
    const findings = view.audits.filter(a => !a.valid).flatMap(a => a.findings);
    return `<section class="critical-uncertainty" role="alert"><h2>${INVALID}</h2><p>This case is not scientific evidence. No reveal, conclusion or validation matrix is produced for it.</p><ul>${findings.map(f => `<li><strong>${escape(label(f.category))}</strong> — ${escape(f.subject)} ${escape(f.detail)}</li>`).join('')}</ul></section>`;
  }
  const last = view.audits[view.audits.length - 1];
  return `<section class="section"><h2>Temporal leakage audit</h2>${last ? `<p><span class="evidence-state supported">▪ Valid</span> ${escape(label(last.phase))}: no record after the cutoff, no undated record in the window, no future identifier in the template or outputs, baselines frozen before the reveal.</p>` : '<p class="caption">Not run yet.</p>'}</section>`;
};

export const timeline = (view: CaseView): string => {
  const known = view.snapshots[view.snapshots.length - 1]?.sources ?? [];
  const future = view.reveal?.future_sources ?? [];
  const rows = [
    ...known.map(s => ({ ...s, side: 'available at T' })),
    ...future.map(s => ({ ...s, side: 'revealed after T' }))
  ].sort((a, b) => a.first_publicly_accessible_date.localeCompare(b.first_publicly_accessible_date));
  const cutoff = view.protocol.cutoff;
  const marker = `<li class="cutoff-marker"><strong>Cutoff T = ${escape(cutoff)}</strong> — ${escape(view.protocol.cutoff_rationale)}</li>`;
  const before = rows.filter(r => r.first_publicly_accessible_date <= cutoff).map(r => item(r)).join('');
  const after = rows.filter(r => r.first_publicly_accessible_date > cutoff).map(r => item(r)).join('');
  const sealed = !view.reveal ? '<li class="caption">Later evidence is sealed until the reveal; only its existence is withheld, never inferred.</li>' : '';
  return `<section class="section"><h2>Evidence timeline</h2><ol class="timeline">${before}${marker}${after}${sealed}</ol><p class="caption">Dates are first public accessibility, not the nominal publication year.</p></section>`;
  function item(r: SourceRow & { side: string }): string {
    return `<li><strong>${escape(r.first_publicly_accessible_date)}</strong> ${escape(r.source)} — ${escape(r.title)} ${r.nominal_publication_date ? `<small>(nominal ${escape(r.nominal_publication_date)})</small>` : ''} ${pill(r.side)}</li>`;
  }
};

export const decisionAtT = (view: CaseView): string => {
  const run = view.cutoff_run;
  if (!run) return '<section class="section"><h2>Decision at T</h2><p class="caption">Run the case to record the decision made from the window alone.</p></section>';
  const s = run.state;
  const edges = Object.entries(s.edges).map(([k, v]) => `<li>${escape(label(k))}: ${pill(v)}</li>`).join('');
  return `<section class="section"><h2>Decision at T</h2><p class="caption">Produced by the ordinary decision engine from the sealed window only. Rules <code>${escape(run.rules_fingerprint.slice(0, 12))}</code>, software <code>${escape(run.software_commit.slice(0, 12))}</code>.${run.rule_revision ? ' <strong>Post-benchmark rule revision recorded.</strong>' : ''}</p>${dl([
    ['Critical uncertainty', escape(s.critical_uncertainty_id ?? 'none')],
    ['Recommended experiment', escape(s.recommended_experiment_id ?? s.no_experiment_message ?? 'none justified')],
    ['Structural validity at T', pill(run.decision_validity.result)]
  ])}<h3>Evidence edges at T</h3><ul class="plain">${edges}</ul></section>`;
};

export const revealSection = (view: CaseView): string => {
  const a = view.assessment;
  if (!a) return `<section class="section"><h2>What the later evidence tested</h2><p class="caption">${view.status === 'invalid' ? 'No reveal is produced for an invalid case.' : 'Not revealed. The future evidence is sealed.'}</p></section>`;
  const rows = Object.entries(a.relevance).map(([source, r]) => `<tr><th scope="row">${escape(source)}<br><small>${escape(r.title)}</small></th><td>${escape(r.first_publicly_accessible_date)}</td><td>${pill(r.relevance)}</td><td>${Object.entries(r.status_changes).map(([u, s]) => `${escape(u.replace('uncertainty:', ''))}: ${escape(s.join(' → '))}`).join('<br>') || '—'}</td></tr>`).join('');
  return `<section class="section"><h2>What the later evidence tested</h2><div class="table-scroll"><table><caption>Relevance of each later source to the decision made at T</caption><thead><tr><th scope="col">Source</th><th scope="col">Accessible</th><th scope="col">Relevance</th><th scope="col">Uncertainty status changed</th></tr></thead><tbody>${rows}</tbody></table></div><p><strong>Conclusion (system, categorical):</strong> ${pill(a.conclusion.conclusion)}</p><ul class="plain">${a.conclusion.basis.map(b => `<li>${escape(b)}</li>`).join('')}</ul></section>`;
};

export const diffSection = (view: CaseView): string => {
  const d = view.reveal?.diff;
  if (!d) return '';
  const lines = [
    ...Object.entries(d.edges).map(([k, v]) => `edge ${k}: ${v[0]} → ${v[1]}`),
    ...Object.entries(d.explanations).map(([k, v]) => `explanation ${k}: ${v[0]} → ${v[1]}`),
    ...Object.entries(d.uncertainties).map(([k, v]) => `uncertainty ${k}: ${v[0]} → ${v[1]}`),
    ...(d.critical_uncertainty ? [`critical uncertainty: ${d.critical_uncertainty[0]} → ${d.critical_uncertainty[1]}`] : []),
    ...(d.recommended_experiment ? [`recommended experiment: ${d.recommended_experiment[0]} → ${d.recommended_experiment[1]}`] : [])
  ];
  return `<section class="section"><h2>Decision T → T+1</h2><p>Decision changed: ${pill(d.decision_changed)}</p>${lines.length ? `<ul class="plain">${lines.map(l => `<li>${escape(l)}</li>`).join('')}</ul>` : '<p class="caption">No scientific change.</p>'}</section>`;
};

export const matrixSection = (view: CaseView): string => {
  const a = view.assessment;
  if (!a) return '';
  const rows = Object.entries(a.matrix).map(([k, v]) => `<tr><th scope="row">${escape(label(k))}</th><td>${(Array.isArray(v.result) ? v.result : [v.result]).map(pill).join(' ')}</td></tr>`).join('');
  return `<section class="section"><h2>Validation matrix</h2><div class="table-scroll"><table><caption>Each dimension stands alone; there is no AXIS score</caption><thead><tr><th scope="col">Dimension</th><th scope="col">Result</th></tr></thead><tbody>${rows}</tbody></table></div><h3>Robustness: leave one source out</h3><ul class="plain">${a.leave_one_source_out.map(x => `<li>without ${escape(x.removed_source)}: decision changed ${pill(x.decision_changed)}</li>`).join('') || '<li>—</li>'}</ul></section>`;
};

export const baselineSection = (view: CaseView): string => {
  const frozen = view.baselines.map(b => `<li>${escape(b.kind)} · ${escape(b.run)} — frozen ${escape(b.frozen_at.slice(0, 19))}, sha256 <code>${escape(b.sha256.slice(0, 12))}</code></li>`).join('');
  const compared = view.assessment?.baseline_comparison.map(b => `<li>${escape(b.baseline)} · ${escape(b.run)}${b.stochastic ? ' (stochastic)' : ''}: ${pill(b.result)}</li>`).join('') ?? '';
  return `<section class="section"><h2>Baseline comparison</h2><p class="caption">Baseline outputs are frozen before the reveal and every run is kept. A single case supports no claim of general value; whether AXIS beats a literature-aware language-model baseline is not demonstrated unless such runs were imported.</p><h3>Frozen before reveal</h3><ul class="plain">${frozen || '<li>none</li>'}</ul>${compared ? `<h3>Against what the later evidence changed</h3><ul class="plain">${compared}</ul>` : ''}</section>`;
};

export const reviewSection = (view: CaseView): string => `<section class="section"><h2>Blind human review</h2><p class="caption">Human review is stored separately from the system's output and never edits it. Reviews are blind to which option is the software.</p>${view.reviews.length ? view.reviews.map(r => `<article class="card"><strong>${escape(r.reviewer)}</strong> — preference ${pill(r.preference)}, own conclusion ${pill(r.conclusion_opinion)}<p>${escape(r.rationale)}</p></article>`).join('') : '<p class="caption">No human review recorded.</p>'}</section>`;

export const limitsSection = (view: CaseView): string => `<section class="section"><h2>Limits</h2><ul class="plain"><li>${escape(view.protocol.selection_rationale)}</li>${(view.assessment?.limits ?? ['Retrospective: this cannot establish clinical efficacy or prospective validity.']).map(l => `<li>${escape(l)}</li>`).join('')}</ul><p class="caption">Protocol fingerprint <code>${escape(view.protocol.protocol_fingerprint.slice(0, 16))}</code>.</p></section>`;

export const caseView = (view: CaseView): string => {
  const invalid = view.status === 'invalid' || view.audits.some(a => !a.valid);
  return `${kindBanner(view.protocol)}<h2>${escape(view.case_id)} ${pill(view.status)}</h2><p class="intro">${escape(view.protocol.question)}</p>${leakageState(view)}${invalid ? '' : `${timeline(view)}${decisionAtT(view)}${revealSection(view)}${diffSection(view)}${matrixSection(view)}${baselineSection(view)}${reviewSection(view)}`}${limitsSection(view)}`;
};

export async function validationContent(api: API): Promise<string> {
  const list = await api<{ items: CaseRow[] }>('benchmarks');
  const params = new URLSearchParams(location.search);
  const selected = params.get('case') || list.items[0]?.case_id || '';
  const body = selected ? caseView(await api<CaseView>(`benchmarks/${encodeURIComponent(selected)}`)) : EmptyState('Select a benchmark case.');
  return `<p class="intro">Does AXIS make scientifically defensible decisions when the future is hidden, and do they remain useful once it is revealed? The framework reports each dimension separately and never produces a single score.</p>${caseList(list.items, selected)}${body}`;
}
