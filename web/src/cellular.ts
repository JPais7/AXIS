import { ContextTable, EmptyState, escape } from './components';
import type { Page, TargetProjection } from './types';

type Fields = Record<string, unknown>;
type API = <T>(path: string) => Promise<T>;
interface Edge { edge: string; state: string; assessments: Fields[]; measurements: Fields[] }
interface Chain { edges: Edge[]; boundary: string; has_more: boolean }
interface Experiment extends Fields { id: string; label: string; context: Fields }
const text = (v: unknown): string => v == null ? 'Not reported' : typeof v === 'object' ? JSON.stringify(v) : String(v);
export const cellularFields = (v: Fields): string => {
  const flat:Record<string,string>={};
  const visit=(value:Fields,prefix='',depth=0):void=>{for(const [key,item] of Object.entries(value)){const name=prefix+key;if(item&&typeof item==='object'&&!Array.isArray(item)&&depth<4)visit(item as Fields,name+' · ',depth+1);else flat[name]=text(item);}};
  visit(v);return ContextTable(flat);
};
const labels: Record<string,string> = { exposure:'Cellular exposure', biochemical:'Biochemical activity', engagement:'Direct cellular target engagement', functional:'Functional target modulation', hla:'HLA / antigen-presentation molecular phenotype', immune:'Immune phenotype', disease:'Disease phenotype', clinical:'Clinical effect' };
const link = (p:string, view:string, compound:string|null):string => `/projects/${encodeURIComponent(p)}/${view}${compound?'?compound='+encodeURIComponent(compound):''}`;
const comparisonTable=(c:Fields):string=>{
  const values=Array.isArray(c.inputs)?c.inputs as Fields[]:[];
  const left=values[0]||{},right=values[1]||{};
  const value=(e:Fields,r:Fields):Fields=>{const ctx=(e.context||{}) as Fields;const scientific=(ctx.scientific_context||{}) as Fields;return {experiment:e.label,modality:e.modality,system:ctx.cell_line,species:scientific.species,hla_allele:ctx.hla_allele,hla_expression:ctx.hla_expression,mhc_allele:ctx.mhc_allele,genotype:scientific.genotype,allotype:ctx.erap1_allotype,disease:ctx.disease_status,concentration:e.concentration,duration:e.duration,endpoint:r.endpoint,direction:r.direction,source:e.source_id,locator:e.locator};};
  const a=value(left,values[2]||{}),b=value(right,values[3]||{});
  return `<div class="table-scroll"><table><thead><tr><th scope="col">Context</th><th scope="col">${escape(text(left.label))}</th><th scope="col">${escape(text(right.label))}</th></tr></thead><tbody>${Object.keys(a).map(k=>`<tr><th scope="row">${escape(k.replaceAll('_',' '))}</th><td>${escape(text(a[k]))}</td><td>${escape(text(b[k]))}</td></tr>`).join('')}</tbody></table></div>`;
};
export function evidenceLadder(chain: Chain, protein: string): string {
  const assessment=(a:Fields):string=>`<p>${escape(text(a.experiment_label))}</p><p>${escape(text(a.rationale))}</p><p>Directness: ${escape(text(a.directness))} · Dependency: ${escape(text(a.dependency))}</p>${(a.context as Fields|undefined)?.mhc_allele?'<p>Engineered murine H-2Kb antigen presentation; HLA-B27 effect not established.</p>':''}<button data-cellular-experiment="${escape(text(a.experiment_id))}" data-cellular-protein="${escape(protein)}">Inspect assessment → experiment → readout</button>`;
  const measurement=(m:Fields):string=>`<p>${escape(text(m.endpoint))} ${escape(text(m.relation_operator))} ${escape(text(m.original_value))} ${escape(text(m.original_unit))}</p><button data-pharma-kind="measurements" data-pharma-id="${escape(text(m.id))}" data-pharma-protein="${escape(protein)}">Inspect biochemical input</button>`;
  return `<ol class="evidence-ladder">${chain.edges.map(e=>`<li class="card"><h2>${escape(labels[e.edge]||e.edge)}</h2><span class="badge">${escape(e.state.replaceAll('_',' '))}</span>${e.assessments[0]?assessment(e.assessments[0]):e.measurements[0]?measurement(e.measurements[0]):EmptyState('Not assessed in this imported evidence slice')}${e.assessments.length+e.measurements.length>1?`<details><summary>Inspect ${e.assessments.length+e.measurements.length-1} additional source inputs</summary>${e.assessments.slice(1).map(assessment).join('')}${e.measurements.slice(e.assessments.length?0:1).map(measurement).join('')}</details>`:''}</li>`).join('')}</ol><p>${escape(chain.boundary)}</p>${chain.has_more?'<p>Additional assessments exist outside this read window; do not interpret this view as complete.</p>':''}`;
}
export async function cellularContent(api: API, project: string, route: string): Promise<string> {
  const targets = await api<Page<TargetProjection>>(`projects/${encodeURIComponent(project)}/targets?limit=20`);
  const params = new URLSearchParams(location.search);
  const protein = params.get('protein') || targets.items[0]?.protein.id;
  if (!protein) return EmptyState('No protein identity imported.');
  const compound=params.get('compound');
  const prefix=`projects/${encodeURIComponent(project)}/targets/${encodeURIComponent(protein)}/cellular`;
  const q=compound?'?compound='+encodeURIComponent(compound):'';
  const navigation: [string,string][] = [['chemistry','Chemistry'],['pharmacology','Pharmacology'],['cellular','Cellular Evidence'],['cellular-comparison','Genetic vs chemical'],['cellular-phenotypes','HLA phenotype'],['decision','Decision'],['cellular-next','Next discriminating experiment']];
  const nav=`<p>${navigation.map(([r,t])=>`<a data-nav href="${link(project,r,compound)}">${t}</a>`).join(' · ')}</p>`;
  const intro='<p class="intro">AI-assisted curation · pending expert review. Chemical exposure ≠ direct engagement ≠ functional modulation ≠ phenotype ≠ therapeutic efficacy. No overall score.</p>';
  if(route==='cellular-comparison') {
    const comparisons=await api<{items:Fields[];has_more:boolean}>(prefix+'/concordance');
    return intro+nav+'<p>Project-wide genetic-versus-chemical comparisons; not evidence that another compound shares the same effects.</p>'+comparisons.items.map(c=>`<article class="card"><h2>${escape(text(c.state).replaceAll('_',' '))}</h2><p>${escape(text(c.rationale))}</p><details><summary>Compare exact contexts and directions</summary>${comparisonTable(c)}</details></article>`).join('')+(comparisons.has_more?'<p>Comparison window capped at 20; not a comprehensive concordance analysis.</p>':'');
  }
  if(route==='cellular-phenotypes') {
    const page=await api<Page<Fields>>(prefix+'/readouts'+q);
    return intro+nav+page.items.map(r=>`<article class="card"><h2>${escape(text(r.endpoint))}</h2>${cellularFields(r)}<button data-cellular-experiment="${escape(text(r.experiment_id))}" data-cellular-protein="${escape(protein)}">Inspect experiment and HLA context</button>${r.claim_id?`<button data-claim="${escape(text(r.claim_id))}">Inspect historical source assertion</button>`:''}</article>`).join('');
  }
  const chain=await api<Chain>(prefix+'/evidence-chain'+q);
  if(route==='decision'||route==='cellular-next') {
    const gaps=await api<{items:Fields[]}>(prefix+'/gaps'+q);
    return intro+nav+'<h2>What we know / what we do not know</h2>'+evidenceLadder(chain,protein)+'<h2>Critical uncertainty and next discriminating experiment</h2>'+gaps.items.map(g=>`<article class="card"><h3>${escape(text(g.question))}</h3><p>AXIS proposal — not experimental evidence.</p><p>${escape(text(g.proposal_title))}</p><a data-nav href="${link(project,'experiments',null)}">Inspect proposal controls and alternative outcome scenarios</a></article>`).join('')+(gaps.items.length?'':EmptyState('No generated proposal imported; do not infer a next experiment.'));
  }
  const offset=Math.max(0,Number(params.get('offset'))||0);
  const page=await api<Page<Experiment>>(`${prefix}/experiments?limit=20&offset=${offset}${compound?'&compound='+encodeURIComponent(compound):''}`);
  return intro+nav+'<h2>Translational evidence ladder</h2>'+evidenceLadder(chain,protein)+'<h2>Performed cellular experiments</h2>'+page.items.map(e=>`<article class="card"><h3>${escape(e.label)}</h3>${cellularFields({context:e.context,concentration:e.concentration,duration:e.duration,modality:e.modality})}<button data-cellular-experiment="${escape(e.id)}" data-cellular-protein="${escape(protein)}">Inspect cellular experiment</button></article>`).join('')+(page.total?'':EmptyState('Not assessed: no cellular package imported.'))+`<p>${page.total} experiment records; repeated contexts are not independent cohorts.</p><button data-page="${Math.max(0,offset-20)}" ${!offset?'disabled':''}>Previous</button><button data-page="${offset+20}" ${!page.has_more?'disabled':''}>Next</button>`;
}
export async function cellularDrawer(api: API, project: string, protein: string, id: string): Promise<string> {
  const detail=await api<{experiment:Fields;readouts:Fields[];review_status:string}>(`projects/${encodeURIComponent(project)}/targets/${encodeURIComponent(protein)}/cellular/experiments/${encodeURIComponent(id)}`);
  return '<button data-close class="drawer-close" aria-label="Close cellular experiment">×</button><h2 id="drawer-title">Cellular experiment detail</h2>'+`<p>${escape(detail.review_status)}</p>`+cellularFields(detail.experiment)+'<h3>Readouts and provenance</h3>'+detail.readouts.map(r=>cellularFields(r)+(r.claim_id?`<button data-claim="${escape(text(r.claim_id))}">Inspect source claim and provenance</button>`:r.measurement_id?`<button data-pharma-kind="measurements" data-pharma-id="${escape(text(r.measurement_id))}" data-pharma-protein="${escape(protein)}">Inspect measurement and provenance</button>`:'')).join('')+'<p>No target occupancy, permeability, causal mechanism or therapeutic efficacy inferred.</p>';
}
