import './style.css';
import { pharmacologyContent, pharmacologyDrawer } from './pharmacology';
import { cellularContent, cellularDrawer } from './cellular';
import { decisionContent, experimentDrawer, explanationDrawer } from './decision';
import { experimentDetailDrawer, impactPreview, resultDrawer, resultsContent, reviewContent } from './results';
import { campaignContent } from './campaign';
import { validationContent } from './validation';
import { mountStructure, structureContent } from './structure-ui';
import { ProteinProvenance, TargetIdentityCard } from './protein';
import type { TargetProjection } from './types';
import { AppShell, ClaimButton, ContextComparison, ContextTable, EmptyState, ErrorState, escape, EvidenceGraph, EvidenceMatrix, EvidenceState, ExperimentCard, KnowledgeKindBadge, label, LoadingState, OpenQuestionCard, PerformedPerturbationPreview, ProjectHeader, ProvenanceBadge, SourceCard, StrategyCard, Transformations } from './components';
import type { Assessment, ClaimSummary, Comparison, Drawer, ExperimentItem, MechanismItem, Page, Perturbation, Project, ProjectItem, QuestionItem, Source, SourceDetail, Strategy } from './types';

const root = document.querySelector<HTMLDivElement>('#app');
if (!root) throw new Error('Workspace root is missing');
const app = root;
let projectId = 'AXIS-DD-ERAP1-CURATED-001';
let route = 'overview';
let structureCleanup: (() => void) | null = null;
let offset = 0;
let domain = '';
let generation = 0;
let drawerGeneration = 0;
const selectedClaims = new Set<string>();
let drawerReturnFocus: HTMLElement | null = null;
const pageSize = 20;
async function api<T>(path: string): Promise<T> {
  const response = await fetch(`/api/${path}`);
  const value: unknown = await response.json();
  if (!response.ok) throw new Error(typeof value === 'object' && value && 'error' in value ? String(value.error) : `Read failed (${response.status})`);
  return value as T;
}
const collection = <T>(name: string, limit = pageSize, start = offset): Promise<Page<T>> => api(`projects/${encodeURIComponent(projectId)}/${name}?limit=${limit}&offset=${start}${name === 'evidence' && domain ? `&domain=${encodeURIComponent(domain)}` : ''}`);
const path = (name: string): string => `/projects/${encodeURIComponent(projectId)}/${name}`;
const section = (title: string, content: string, link?: string): string => `<section class="section"><div class="section-heading"><h2>${title}</h2>${link ? `<a data-nav href="${path(link)}">View all →</a>` : ''}</div>${content}</section>`;
function pagination<T>(page: Page<T>): string {
  return `<div class="pagination"><span>${page.total ? page.offset + 1 : 0}–${Math.min(page.offset + page.items.length, page.total)} of ${page.total}</span><button data-page="${Math.max(0, page.offset - page.limit)}" ${page.offset === 0 ? 'disabled' : ''}>← Previous</button><button data-page="${page.offset + page.limit}" ${!page.has_more ? 'disabled' : ''}>Next →</button></div>`;
}
async function overview(project: Project): Promise<string> {
  const [mechanisms, strategies, questions, experiments, perturbations, assessments] = await Promise.all([
    collection<MechanismItem>('mechanism', 8, 0), collection<Strategy>('strategies', 4, 0),
    collection<QuestionItem>('questions', 1, 0), collection<ExperimentItem>('experiments', 1, 0),
    collection<Perturbation>('perturbations', 3, 0), collection<Assessment>('assessments', 100, 0)
  ]);
  const preview = [...mechanisms.items.filter(item => item.assessment.classification !== 'hypothesized').slice(0, 2), ...mechanisms.items.filter(item => item.assessment.classification === 'hypothesized').slice(0, 1)];
  const measured = PerformedPerturbationPreview(perturbations.items);
  const landscape = strategies.items.map(item => {
    const roles = assessments.items.filter(value => value.strategy_id === item.strategy_id);
    return `<a data-nav class="compact-card" href="${path('strategies')}"><strong>${escape(item.description)}</strong>${KnowledgeKindBadge(item.knowledge_kind)}<span>${roles.length ? roles.length + ' stored assessments · inspect roles and context' : 'No strategy-specific assessment in this read window'}</span></a>`;
  }).join('') + '<p class="caption">Competing concepts; no ranking or preferred strategy. This bounded project view does not establish systematic literature coverage.</p>';
  return `<div class="objective"><div class="eyebrow">PROJECT OBJECTIVE</div><h2>${escape(project.project.objective)}</h2><div class="identity"><span><small>TARGET</small><strong>${escape(project.pair.target.label)}</strong></span><span><small>INDICATION SCOPE</small>${escape(project.pair.indication_scope)}</span><span><small>CURATED PACKAGE</small>${escape(project.package_version ?? 'Development fixture')}</span></div></div>
    ${section('Evidence', EvidenceMatrix(project.matrix), 'evidence')}
    <div class="two-columns">${section('Mechanistic picture', EvidenceGraph(preview) + measured, 'mechanism')}${section('Decision landscape', landscape, 'strategies')}</div>
    <section class="critical-uncertainty"><div class="section-heading"><h2>Critical uncertainty</h2><a data-nav href="${path('questions')}">Inspect informing evidence →</a></div><div class="two-columns">${questions.items.map(item => `<article><span class="badge">? Unresolved scientific question</span><h2>${escape(item.question.question)}</h2><a data-nav href="${path('questions')}">Inspect contexts, perturbations and affected strategies →</a></article>`).join('')}${experiments.items.map(item => `<article><div class="proposal-banner">◇ AXIS SUGGESTION — NOT EXPERIMENTAL EVIDENCE</div><h2>${escape(item.experiment.title)}</h2><p>${escape(item.experiment.rationale)}</p><a data-nav href="${path('experiments')}">Inspect conditional outcomes and feasibility →</a></article>`).join('')}</div></section>`;
}
async function strategyView(): Promise<string> {
  const [strategies, assessments, perturbations, evidence, questions] = await Promise.all([collection<Strategy>('strategies'), collection<Assessment>('assessments', 100, 0), collection<Perturbation>('perturbations', 100, 0), collection<ClaimSummary>('evidence', 100, 0), collection<QuestionItem>('questions', 100, 0)]);
  const claims = new Map(evidence.items.map(item => [item.claim_id, item]));
  const claimLink = (id: string): string => claims.has(id) ? ClaimButton(claims.get(id)!) : `<button data-claim="${escape(id)}">Inspect ${escape(id)}</button>`;
  return `<p class="intro">Compare evidence roles within their measured contexts. These are competing proposals; AXIS has not selected a therapeutic direction.</p><div class="strategy-grid">${strategies.items.map(strategy => {
    const entries = assessments.items.filter(item => item.strategy_id === strategy.strategy_id);
    const roleGroup = (title: string, roles: string[], empty: string): string => `<h3>${title}</h3>${entries.filter(item => roles.includes(item.role)).map(item => `<div class="assessment">${EvidenceState(item.role)}${claimLink(item.claim_id)}<p>${escape(item.reasoning)}</p></div>`).join('') || EmptyState(empty)}`;
    const relevant = perturbations.items.filter(item => entries.some(entry => entry.claim_id === item.observed_effect_claim_id));
    const compatible = entries.filter(item => ['supports', 'weakly_supports'].includes(item.role));
    const body = roleGroup('Evidence compatible with strategy', ['supports', 'weakly_supports'], 'No direct strategy-specific supporting evidence identified in the current curated corpus.') + roleGroup('Explicitly assessed contradictory evidence', ['contradicts'], 'No assessment classified as contradictory in this curated corpus; this does not establish consistency or efficacy.') + roleGroup('Inconclusive / context-limited evidence', ['inconclusive', 'neutral', 'untyped_considered'], 'Not assessed: no strategy-specific contextual assessment in this package.') + '<h3>Missing strategy-specific evidence</h3><p>' + (compatible.length ? 'Clinical benefit and the preferred pharmacological direction remain unassessed by this package.' : 'No strategy-specific support is identified in the current project records. This absence is not evidence against the strategy.') + '</p><h3>Relevant perturbations</h3>' + (relevant.map(item => `<p>${escape(label(item.perturbation_type))} · ${escape(item.scientific_context.experimental_system)} ${item.observed_effect_claim_id ? claimLink(item.observed_effect_claim_id) : ''}</p>`).join('') || EmptyState('No directly linked perturbation in the curated strategy assessments.')) + '<h3>Relevant open questions</h3>' + (questions.items.filter(item => item.links.strategy_ids.includes(strategy.strategy_id)).map(item => `<a data-nav class="compact-card" href="${path('questions')}"><span>Unresolved scientific question</span><strong>${escape(item.question.question)}</strong></a>`).join('') || EmptyState('No linked question in the bounded read window.'));
    return StrategyCard(strategy, body);
  }).join('')}</div>${pagination(strategies)}<p class="caption">Related assessments and perturbations are bounded to 100 each. ${assessments.has_more || perturbations.has_more || evidence.has_more ? 'Additional related records exist; inspect Evidence and Perturbations pages.' : 'All current related records fit within these bounds.'}</p>`;
}
async function content(project: Project): Promise<string> {
  if (['chemistry','pharmacology','selectivity'].includes(route)) return pharmacologyContent(api,projectId,route);
  if (route === 'decision') return decisionContent(api,projectId);
  if (route === 'results') return resultsContent(api,projectId);
  if (route === 'review') return reviewContent(api,projectId);
  if (route === 'validation') return validationContent(api);
  if (route === 'campaigns') return campaignContent(api, projectId);
  if (['cellular','cellular-comparison','cellular-phenotypes','cellular-decision','cellular-next'].includes(route)) return cellularContent(api,projectId,route);
  if (route === 'structures') return structureContent(api,projectId);
  if (route === 'protein') {
    const page = await collection<TargetProjection>('targets');
    return `<p class="intro">Gene → source-backed mapping → protein → isoform → snapshot. Identity infrastructure is separate from disease evidence.</p>${page.items.map(TargetIdentityCard).join('') || EmptyState('No protein identity imported for this project. Use an explicit frozen-package or live source import.')}<p><a data-nav href="${path('evidence')}">Return to disease evidence →</a></p>${pagination(page)}`;
  }
  if (route === 'overview') return overview(project);
  if (route === 'evidence') {
    const page = await collection<ClaimSummary>('evidence');
    return `<div class="filters"><label for="domain">Evidence domain</label><select id="domain"><option value="">All evidence and proposals</option>${project.matrix.map(item => `<option value="${item.domain}" ${domain === item.domain ? 'selected' : ''}>${escape(item.label)}</option>`).join('')}<option value="proposal" ${domain === 'proposal' ? 'selected' : ''}>Proposals (not evidence)</option></select></div><p class="intro">Atomic assertions retain their source and context. Inspect a statement or select 2–4 claims to compare their reported contexts. This small corpus is not systematic literature coverage.</p><div class="comparison-toolbar"><span id="comparison-count" role="status">${selectedClaims.size} of 4 selected</span><button data-compare ${selectedClaims.size < 2 ? 'disabled' : ''}>Compare evidence</button><button data-clear-comparison>Clear selection</button></div><div class="claims">${page.items.map(claim => `<div class="selectable-claim"><label class="comparison-select"><input type="checkbox" data-select-claim="${escape(claim.claim_id)}" ${selectedClaims.has(claim.claim_id) ? 'checked' : ''} ${selectedClaims.size >= 4 && !selectedClaims.has(claim.claim_id) ? 'disabled' : ''}><span class="sr-only">Select ${escape(claim.claim_id)} for comparison</span></label>${ClaimButton(claim)}</div>`).join('') || EmptyState(domain ? 'No direct evidence identified in this domain of the curated corpus. See the overview for whether this domain is assessed.' : 'No evidence or proposals have been linked to this project.')}</div>${pagination(page)}`;
  }
  if (route === 'mechanism') { const page = await collection<MechanismItem>('mechanism'); return EvidenceGraph(page.items) + pagination(page); }
  if (route === 'strategies') return strategyView();
  if (route === 'perturbations') {
    const page = await collection<Perturbation>('perturbations');
    return `<p class="intro">Performed study perturbations retain observed-effect claims. Cellular phenotypes do not establish therapeutic benefit.</p>${page.items.map(item => `<article class="card perturbation"><div class="card-heading"><h2>${escape(label(item.perturbation_type))}${item.intervention ? ` · ${escape(item.intervention.label)}` : ''}</h2><span class="badge">${escape(item.status)}</span></div>${KnowledgeKindBadge(item.knowledge_kind)} ${ProvenanceBadge(item.provenance.source_identifier)}<p>Target: <strong>${escape(item.target.label)}</strong> · Target direction: ${escape(item.direction)}</p>${ContextTable(item.scientific_context)}${item.observed_effect_claim_id ? `<p>Observed-effect claim: ${escape(item.observed_effect_claim_id)}</p><button class="primary" data-claim="${escape(item.observed_effect_claim_id)}">Inspect observed effect + source →</button>` : EmptyState('No observed-effect claim linked; proposed intervention is not a result.')}</article>`).join('') || EmptyState('Perturbation evidence not assessed in this project.')}${pagination(page)}`;
  }
  if (route === 'questions') {
    const [page, evidence, experiments, perturbations, strategies] = await Promise.all([
      collection<QuestionItem>('questions'), collection<ClaimSummary>('evidence', 100, 0),
      collection<ExperimentItem>('experiments', 100, 0), collection<Perturbation>('perturbations', 100, 0), collection<Strategy>('strategies', 100, 0)
    ]);
    return page.items.map(item => OpenQuestionCard(item,
      evidence.items.filter(claim => item.links.claim_ids.includes(claim.claim_id)).map(ClaimButton).join('') || EmptyState('No informing claims linked.'),
      experiments.items.filter(value => value.experiment.question_id === item.question.question_id).map(value => `<a data-nav class="compact-card" href="${path('experiments')}">${KnowledgeKindBadge(value.experiment.knowledge_kind)}<strong>${escape(value.experiment.title)}</strong><span>Inspect conditional outcomes →</span></a>`).join('') || EmptyState('No experiment proposed.'),
      perturbations.items.filter(value => item.links.perturbation_ids.includes(value.perturbation_id)).map(value => `<div class="compact-card"><strong>${escape(label(value.perturbation_type))} · ${escape(value.status)}</strong><span>${escape(value.scientific_context.experimental_system || 'Not reported')}</span><span>Endpoint: ${escape(value.scientific_context.endpoint || 'Not reported')}</span>${value.observed_effect_claim_id ? `<button data-claim="${escape(value.observed_effect_claim_id)}">Inspect observed-effect claim →</button>` : ''}</div>`).join('') + strategies.items.filter(value => item.links.strategy_ids.includes(value.strategy_id)).map(value => `<a data-nav class="compact-card" href="${path('strategies')}">${escape(value.description)} · ${KnowledgeKindBadge(value.knowledge_kind)}</a>`).join('')
    )).join('') + pagination(page) + `<p class="caption">Related claims, perturbations, strategies and experiments are bounded to 100 each. ${evidence.has_more || experiments.has_more || perturbations.has_more || strategies.has_more ? 'Additional related records exist outside this read window.' : 'All current linked records fit in the read window.'}</p>`;
  }
  if (route === 'experiments') { const page = await collection<ExperimentItem>('experiments'); return (page.items.map(ExperimentCard).join('') || EmptyState('No experiment proposed.')) + pagination(page); }
  const page = await collection<Source>('sources');
  return `<p class="intro">Primary publications and proposal provenance remain distinct. Open a source to trace its derived claims and import transformations.</p><div class="source-grid">${page.items.map(SourceCard).join('')}</div>${pagination(page)}`;
}
async function render(): Promise<void> {
  structureCleanup?.();
  structureCleanup = null;
  const current = ++generation;
  const parts = location.pathname.split('/').filter(Boolean);
  if (parts[0] === 'projects' && parts[1]) {
    const nextProject = decodeURIComponent(parts[1]);
    if (nextProject !== projectId) selectedClaims.clear();
    projectId = nextProject;
  }
  route = parts[0] === 'projects' && parts[1] ? (parts[2] || 'overview') : (parts[0] || 'overview');
  const allowed = ['home', 'projects', 'targets', 'overview', 'evidence', 'mechanism', 'perturbations', 'strategies', 'questions', 'experiments', 'sources','cellular','cellular-comparison','cellular-phenotypes','decision','cellular-decision','cellular-next','results','review','validation','campaigns'];
  if (!allowed.includes(route) && !['protein','structures','chemistry','pharmacology','selectivity'].includes(route)) route = 'overview';
  const params = new URLSearchParams(location.search);
  offset = Number(params.get('offset')) || 0;
  domain = params.get('domain') || '';
  app.innerHTML = AppShell(projectId, route, LoadingState());
  try {
    let html: string;
    if (['home', 'projects', 'targets'].includes(route)) {
      const page = await api<Page<ProjectItem>>(`projects?limit=${pageSize}&offset=${offset}`);
      html = `<header class="project-header"><div class="eyebrow">DISCOVERY WORKSPACE</div><h1>${route === 'targets' ? 'Target Explorer' : route === 'home' ? 'Evidence to therapeutic decisions' : 'Discovery projects'}</h1><p>Inspect evidence, competing strategies and the uncertainty between them.</p></header><div class="source-grid">${page.items.map(item => `<a data-nav class="card project-card" href="/projects/${escape(item.project.project_id)}/overview"><span class="eyebrow">${item.project.project_id.includes('CURATED') ? 'SOURCE-GROUNDED VERTICAL' : 'DEVELOPMENT FIXTURE'}</span><h2>${escape(item.pair.target.label)} × ${escape(item.pair.disease.label)}</h2><p>${escape(item.project.objective)}</p><small>${escape(item.pair.indication_scope)}</small><p>Open project →</p></a>`).join('') || EmptyState('No projects imported. Import the frozen ERAP1 package explicitly before starting the server.')}</div>${pagination(page)}`;
    } else {
      const project = await api<Project>(`projects/${encodeURIComponent(projectId)}`);
      const titles: Record<string, string> = { overview: 'ERAP1 × Axial Spondyloarthritis', evidence: 'Evidence', mechanism: 'Mechanism', perturbations: 'Perturbations', strategies: 'Competing intervention strategies', questions: 'Open questions', experiments: 'Next experiment', sources: 'Sources & provenance',cellular:'Cellular Evidence','cellular-comparison':'Genetic vs chemical','cellular-phenotypes':'HLA phenotype',decision:'Decision','cellular-decision':'Cellular decision view',results:'Experiments / Results',review:'Scientific review',validation:'Retrospective Validation',campaigns:'Computational Campaigns','cellular-next':'Next discriminating experiment' };
      html = ProjectHeader(project, route === 'protein' ? 'Target / Protein' : route === 'structures' ? 'Experimental structures' : ({chemistry:'Chemistry',pharmacology:'Pharmacology',selectivity:'Selectivity'} as Record<string,string>)[route] || titles[route] || 'Overview') + await content(project);
    }
    if (current === generation) {
      app.innerHTML = AppShell(projectId, route, html);
      if (route === 'structures') structureCleanup = await mountStructure();
    }
  } catch (error) { if (current === generation) app.innerHTML = AppShell(projectId, route, ErrorState(error instanceof Error ? error.message : 'Unable to read records.')); }
}
function navigate(url: string): void { history.pushState({}, '', new URL(url, location.href)); void render().then(() => document.querySelector<HTMLElement>('#main')?.focus()); window.scrollTo(0, 0); }
function drawerElement(): HTMLDialogElement { const drawer = document.querySelector<HTMLDialogElement>('#evidence-drawer'); if (!drawer) throw new Error('Evidence drawer unavailable'); return drawer; }
function openDrawer(): HTMLDialogElement { const drawer = drawerElement(); if (!drawer.open) drawerReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null; drawer.classList.remove('comparison-dialog'); drawer.innerHTML = '<button class="drawer-close" data-close aria-label="Close evidence drawer">×</button><h2 id="drawer-title">Inspect evidence</h2>' + LoadingState(); if (!drawer.open) drawer.showModal(); return drawer; }
function focusDrawer(): void { drawerElement().querySelector<HTMLButtonElement>('[data-close]')?.focus(); }
document.addEventListener('close', event => { if (event.target instanceof HTMLDialogElement) { ++drawerGeneration; if (drawerReturnFocus?.isConnected) drawerReturnFocus.focus(); else document.querySelector<HTMLElement>('#main')?.focus(); } }, true);
async function EvidenceDrawer(id: string): Promise<void> {
  const current = ++drawerGeneration;
  const drawer = openDrawer();
  try {
    const data = await api<Drawer>(`claims/${encodeURIComponent(id)}?project_id=${encodeURIComponent(projectId)}`);
    if (current !== drawerGeneration || !drawer.open) return;
    drawer.innerHTML = `<button class="drawer-close" data-close aria-label="Close evidence drawer">×</button><div class="eyebrow">EVIDENCE DRAWER</div><h2 id="drawer-title">${escape(data.statement)}</h2><p class="identifier">${escape(id)}</p><h3>Epistemic type</h3>${KnowledgeKindBadge(data.knowledge_kind)}<p>${data.knowledge_kind === 'ai_suggestion' ? 'AXIS suggestion — not experimental evidence.' : 'An assertion attributed to the source in its reported context; inclusion is not an endorsement of therapeutic efficacy.'}</p><h3>Context</h3>${ContextTable(data.context)}<h3>Evidence assessments</h3>${data.assessments.map(item => `<section class="assessment">${EvidenceState(item.role)}<p>${escape(item.reasoning)}</p><small>Subject: ${escape(item.strategy_id || item.question_id)}</small><details><summary>Assessment provenance</summary>${ProvenanceBadge(item.provenance.source_identifier)}${Transformations(item.provenance.transformations)}</details></section>`).join('') || EmptyState('Not assessed: no evidence-role assessment linked.')}<h3>Mechanism classification</h3>${data.mechanisms.map(item => `<section class="assessment"><span class="badge">${escape(label(item.classification))}</span><p>${escape(item.reasoning)}</p>${Transformations(item.provenance.transformations)}</section>`).join('') || EmptyState('Not assessed as a mechanistic edge.')}${data.assessments_may_be_truncated ? '<p class="caption">Assessment lists reached their 100-item bound; additional records may exist.</p>' : ''}<h3>Source</h3><p>${ProvenanceBadge(data.source.source_id)} <span class="badge">${escape(label(data.source.source_kind))}</span></p><strong>${escape(data.source.title)}</strong><p>${escape(data.source.locator || '')}</p><p>Retrieved: ${escape(data.source.retrieved_at)}</p><p>${escape(data.source.access || '')}</p><button data-source="${escape(data.source.source_id)}">Source → derived claims → project</button>${safeSourceLink(data.source.source_uri)}<h3>Limitations</h3><p>${escape(data.limitation || 'No additional limitation recorded; inspect the source and context.')}</p><h3>Why included?</h3><p>${escape(data.inclusion_rationale || 'Linked to this project as an explicit proposal.')}</p><h3>Provenance & transformations</h3><p>Package ${escape(data.package_version || 'Proposal fixture')} · ${escape(data.curation_status || 'Proposal')}</p><p class="checksum">Metadata-response SHA-256: ${escape(data.claim.provenance.checksum || 'Not recorded')}</p>${Transformations(data.claim.provenance.transformations)}<p><a data-nav href="${path('overview')}">Return to project →</a></p>`;
    focusDrawer();
  } catch (error) { if (current !== drawerGeneration || !drawer.open) return; drawer.innerHTML = '<button class="drawer-close" data-close aria-label="Close evidence drawer">×</button><h2 id="drawer-title">Evidence unavailable</h2>' + ErrorState(error instanceof Error ? error.message : 'Unable to read evidence.'); focusDrawer(); }
}
function safeSourceLink(uri: string | null): string { if (!uri || !/^https?:\/\//.test(uri)) return ''; return `<p><a href="${escape(uri)}" target="_blank" rel="noopener noreferrer">Open original reference ↗</a></p>`; }
async function sourceDrawer(id: string, start = 0): Promise<void> {
  const current = ++drawerGeneration;
  const drawer = openDrawer();
  try {
    const data = await api<SourceDetail>(`sources/${encodeURIComponent(id)}?project_id=${encodeURIComponent(projectId)}&limit=${pageSize}&offset=${start}`);
    if (current !== drawerGeneration || !drawer.open) return;
    drawer.innerHTML = `<button class="drawer-close" data-close aria-label="Close evidence drawer">×</button><div class="eyebrow">SOURCE PROVENANCE</div><h2 id="drawer-title">${escape(data.source.title)}</h2><p>${ProvenanceBadge(id)} <span class="badge">${escape(label(data.source.source_kind))}</span></p><p>Retrieved ${escape(data.source.retrieved_at)}</p>${safeSourceLink(data.source.source_uri)}<h3>Claims derived from this source</h3>${data.claims.map(ClaimButton).join('')}<div class="pagination"><span>${data.total} derived claims</span><button data-source="${escape(id)}" data-source-offset="${Math.max(0, start - pageSize)}" ${start === 0 ? 'disabled' : ''}>Previous</button><button data-source="${escape(id)}" data-source-offset="${start + pageSize}" ${!data.has_more ? 'disabled' : ''}>Next</button></div><h3>Projects using these claims</h3>${data.projects.map(id => `<p><a data-nav href="/projects/${escape(id)}/overview">${escape(id)} →</a></p>`).join('')}<p class="caption">Project references bounded to 100.</p><h3>Transformations · package ${escape(data.package_version || 'Proposal')}</h3>${Transformations(data.transformations)}`;
    focusDrawer();
  } catch (error) { if (current !== drawerGeneration || !drawer.open) return; drawer.innerHTML = '<button class="drawer-close" data-close aria-label="Close evidence drawer">×</button><h2 id="drawer-title">Source unavailable</h2>' + ErrorState(error instanceof Error ? error.message : 'Unable to read source.'); focusDrawer(); }
}
async function compareDrawer(): Promise<void> {
  const current = ++drawerGeneration;
  const drawer = openDrawer();
  drawer.classList.add('comparison-dialog');
  try {
    const data = await api<Comparison>(`projects/${encodeURIComponent(projectId)}/compare?claim_ids=${encodeURIComponent([...selectedClaims].join(','))}`);
    if (current !== drawerGeneration || !drawer.open) return;
    drawer.innerHTML = `<button class="drawer-close" data-close aria-label="Close evidence drawer">×</button><div class="eyebrow">CONTEXT COMPARISON</div><h2 id="drawer-title">Compare evidence</h2><p>${escape(data.interpretation)}</p>${ContextComparison(data.items)}`;
    focusDrawer();
  } catch (error) { if (current !== drawerGeneration || !drawer.open) return; drawer.innerHTML = '<button class="drawer-close" data-close aria-label="Close evidence drawer">×</button><h2 id="drawer-title">Comparison unavailable</h2>' + ErrorState(error instanceof Error ? error.message : 'Unable to compare records.'); focusDrawer(); }
}
async function proteinDrawer(id: string): Promise<void> {
  const drawer = openDrawer();
  const current = ++drawerGeneration;
  try {
    const data = await api<TargetProjection>(`projects/${encodeURIComponent(projectId)}/targets/${encodeURIComponent(id)}`);
    if (current !== drawerGeneration || !drawer.open) return;
    drawer.innerHTML = ProteinProvenance(data);
    focusDrawer();
  } catch (error) {
    if (current !== drawerGeneration || !drawer.open) return;
    drawer.innerHTML = '<button class="drawer-close" data-close aria-label="Close protein provenance">×</button><h2 id="drawer-title">Protein unavailable</h2>' + ErrorState(error instanceof Error ? error.message : 'Unable to read protein.');
    focusDrawer();
  }
}
function updateComparisonSelection(): void {
  const count = document.querySelector('#comparison-count');
  if (count) count.textContent = `${selectedClaims.size} of 4 selected`;
  const compare = document.querySelector<HTMLButtonElement>('[data-compare]');
  if (compare) compare.disabled = selectedClaims.size < 2;
  document.querySelectorAll<HTMLInputElement>('[data-select-claim]').forEach(input => { input.checked = selectedClaims.has(input.dataset.selectClaim || ''); input.disabled = selectedClaims.size >= 4 && !input.checked; });
}
document.addEventListener('click', event => {
  const target = event.target instanceof Element ? event.target.closest<HTMLElement>('a[data-nav], button') : null;
  if (!target || target.hasAttribute('disabled')) return;
  if(target.dataset.resultRow || target.dataset.experimentDetail) {
    const drawer=openDrawer(); const current=++drawerGeneration;
    const load=target.dataset.resultRow?resultDrawer(api,projectId,target.dataset.resultRow):experimentDetailDrawer(api,projectId,target.dataset.experimentDetail||'');
    void load.then(html=>{if(current===drawerGeneration&&drawer.open){drawer.innerHTML=html;focusDrawer();}}).catch(error=>{if(current===drawerGeneration&&drawer.open){drawer.innerHTML='<button data-close class="drawer-close" aria-label="Close drawer">×</button>'+ErrorState(error instanceof Error?error.message:'Read failed');focusDrawer();}});
    return;
  }
  if(target.dataset.impact && target.dataset.impactResult) {
    const holder=document.querySelector<HTMLElement>('#impact-preview');
    if(holder){holder.innerHTML='<p role="status">Computing preview…</p>';void impactPreview(api,projectId,target.dataset.impactResult,target.dataset.impact).then(html=>{holder.innerHTML=html;}).catch(error=>{holder.innerHTML=ErrorState(error instanceof Error?error.message:'Preview failed');});}
    return;
  }
  if(target.dataset.decisionExplanation || target.dataset.decisionExperiment) {
    const drawer=openDrawer(); const current=++drawerGeneration;
    const load=target.dataset.decisionExplanation?explanationDrawer(api,projectId,target.dataset.decisionExplanation):experimentDrawer(api,projectId,target.dataset.decisionExperiment||'');
    void load.then(html=>{if(current===drawerGeneration&&drawer.open){drawer.innerHTML=html;focusDrawer();}}).catch(error=>{if(current===drawerGeneration&&drawer.open){drawer.innerHTML='<button data-close class="drawer-close" aria-label="Close drawer">×</button>'+ErrorState(error instanceof Error?error.message:'Read failed');focusDrawer();}});
    return;
  }
  if(target.dataset.cellularExperiment && target.dataset.cellularProtein) {
    const drawer=openDrawer(); const current=++drawerGeneration;
    void cellularDrawer(api,projectId,target.dataset.cellularProtein,target.dataset.cellularExperiment).then(html=>{if(current===drawerGeneration&&drawer.open){drawer.innerHTML=html;focusDrawer();}}).catch(error=>{if(current===drawerGeneration&&drawer.open){drawer.innerHTML='<button data-close>Close</button>'+ErrorState(error instanceof Error?error.message:'Read failed');focusDrawer();}});
    return;
  }
  if (target.dataset.pharmaId && target.dataset.pharmaKind && target.dataset.pharmaProtein) {
    const drawer = openDrawer();
    const current = ++drawerGeneration;
    const cellularLink=target.dataset.pharmaKind==='compounds'?`<h3>Cellular Evidence</h3><a data-nav href="${path('cellular')}?compound=${encodeURIComponent(target.dataset.pharmaId)}">Inspect this compound’s cellular evidence and missing links</a>`:'';
    void pharmacologyDrawer(api,projectId,target.dataset.pharmaProtein,target.dataset.pharmaKind,target.dataset.pharmaId).then(html => { if (current===drawerGeneration && drawer.open) { drawer.innerHTML=html+cellularLink; focusDrawer(); } }).catch(error => { if (current===drawerGeneration && drawer.open) { drawer.innerHTML='<button data-close class="drawer-close">×</button><h2 id="drawer-title">Pharmacology unavailable</h2>'+ErrorState(error instanceof Error?error.message:'Read failed'); focusDrawer(); } });
    return;
  }
  if (target.matches('a[data-nav]')) { event.preventDefault(); if(drawerElement().open) drawerElement().close(); navigate(target.getAttribute('href') || '/'); }
  else if (target.dataset.claim) void EvidenceDrawer(target.dataset.claim);
  else if (target.dataset.structures) navigate(`${path('structures')}?protein=${encodeURIComponent(target.dataset.structures)}`);
  else if (target.dataset.proteinSource) void proteinDrawer(target.dataset.proteinSource);
  else if (target.dataset.copySequence) {
    const status = target.parentElement?.querySelector('.copy-status');
    void navigator.clipboard.writeText(target.dataset.copySequence).then(() => { if (status) status.textContent = 'Sequence copied.'; }).catch(() => { if (status) status.textContent = 'Copy unavailable. Select the sequence manually.'; });
  }
  else if (target.dataset.source) void sourceDrawer(target.dataset.source, Number(target.dataset.sourceOffset || 0));
  else if (target.dataset.domain) navigate(`${path('evidence')}?domain=${encodeURIComponent(target.dataset.domain)}`);
  else if (target.dataset.page) { const params = new URLSearchParams(location.search); params.set('offset', target.dataset.page); navigate(`${location.pathname}?${params}`); }
  else if (target.hasAttribute('data-close')) { ++drawerGeneration; drawerElement().close(); }
  else if (target.hasAttribute('data-compare')) void compareDrawer();
  else if (target.hasAttribute('data-clear-comparison')) { selectedClaims.clear(); updateComparisonSelection(); }
  else if (target.hasAttribute('data-retry')) void render();
});
document.addEventListener('change', event => {
  if (event.target instanceof HTMLSelectElement && event.target.id==='pharma-compound') navigate(`${path('selectivity')}?compound=${encodeURIComponent(event.target.value)}`);
  if (event.target instanceof HTMLSelectElement && event.target.id === 'domain') navigate(`${path('evidence')}?domain=${encodeURIComponent(event.target.value)}`);
  if (event.target instanceof HTMLInputElement && event.target.dataset.selectClaim) {
    const id = event.target.dataset.selectClaim;
    if (event.target.checked && selectedClaims.size < 4) selectedClaims.add(id);
    else if (!event.target.checked) selectedClaims.delete(id);
    updateComparisonSelection();
  }
});
document.addEventListener('submit', event => {
  if (!(event.target instanceof HTMLFormElement) || event.target.id!=='pharma-filter') return;
  event.preventDefault();
  const params = new URLSearchParams();
  new FormData(event.target).forEach((value,key)=>{if(typeof value==='string' && value)params.set(key,value);});
  navigate(`${path('pharmacology')}?${params}`);
});
window.addEventListener('popstate', () => void render());
void render();
