import { ContextTable, EmptyState, escape } from './components';
import type { Page, TargetProjection } from './types';

type Fields = Record<string, unknown>;
interface Compound extends Fields {
  id: string; preferred_name: string; depiction_svg: string | null;
  isomeric_smiles: string | null; identity_status: string;
}
interface Measurement extends Fields {
  id: string; compound_id: string; compound_name: string; assay: Fields;
  endpoint: string; relation_operator: string;
  original_value: string | null; original_unit: string | null;
}
interface Assessment extends Fields {
  compound_id: string; comparison_target_id: string;
  primary_measurement_id: string | null; comparison_measurement_id: string | null;
  comparability_status: string; rationale: string;
}
interface Detail { compound?: Compound; record?: Fields; assay?: Fields;
  chemical_identity?: Fields; snapshot?: Fields; provider_snapshot?: Fields;
  identifiers?: Fields[]; forms?: Fields[]; boundary?: string;
  identity_graph?: {edges: {from:string;to:string;relation:string}[];has_more:boolean};
  potential_disagreements?: Fields; }
type API = <T>(path: string) => Promise<T>;
const text = (value: unknown): string => value == null ? 'Not reported' : typeof value === 'object' ? JSON.stringify(value) : String(value);
const fields = (value: Fields): string => ContextTable(Object.fromEntries(Object.entries(value).filter(([k]) => k !== 'depiction_svg').map(([k,v]) => [k,k==='molecular_weight' && typeof v==='number' ? v.toFixed(3) : text(v)])));
const base = (project: string, protein: string): string => `projects/${encodeURIComponent(project)}/targets/${encodeURIComponent(protein)}`;
const button = (kind: string, id: string, protein: string, title: string): string => `<button data-pharma-kind="${kind}" data-pharma-id="${escape(id)}" data-pharma-protein="${escape(protein)}">${escape(title)}</button>`;
export async function pharmacologyContent(api: API, project: string, route: string): Promise<string> {
  const targets = await api<Page<TargetProjection>>(`projects/${encodeURIComponent(project)}/targets?limit=20`);
  const params = new URLSearchParams(location.search);
  const protein = params.get('protein') || targets.items[0]?.protein.id;
  if (!protein) return EmptyState('No protein identity imported. Explicitly import the frozen protein and pharmacology packages.');
  const prefix = base(project,protein);
  const offset = Math.max(0,Number(params.get('offset')) || 0);
  const compounds = await api<Page<Compound>>(`${prefix}/compounds?limit=20&offset=${route === 'chemistry' ? offset : 0}`);
  const boundary = '<p class="intro">Chemical identity ≠ biochemical activity ≠ cellular target engagement ≠ disease response ≠ therapeutic efficacy. No compound ranking.</p>';
  const nav = `<p><a data-nav href="/projects/${encodeURIComponent(project)}/protein">Target / Protein</a> · <a data-nav href="/projects/${encodeURIComponent(project)}/chemistry">Chemistry</a> · <a data-nav href="/projects/${encodeURIComponent(project)}/pharmacology">Pharmacology</a> · <a data-nav href="/projects/${encodeURIComponent(project)}/selectivity">Selectivity</a> · <a data-nav href="/projects/${encodeURIComponent(project)}/evidence">Disease evidence</a></p>`;
  const paginate = (page: Page<unknown>): string => `<div class="pagination"><span>${page.total} records · offset ${page.offset}</span><button data-page="${Math.max(0,page.offset-20)}" ${!page.offset ? 'disabled':''}>Previous</button><button data-page="${page.offset+20}" ${!page.has_more?'disabled':''}>Next</button></div>`;
  if (route === 'chemistry') return boundary + nav + '<div class="source-grid">' + (compounds.items.map(c => `<article class="card"><h2>${escape(c.preferred_name)}</h2><span class="badge">${escape(c.identity_status)}</span>${c.depiction_svg ? `<img class="chemical-depiction" alt="2D chemical identity of ${escape(c.preferred_name)}; textual SMILES below" src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(c.depiction_svg)}">` : EmptyState('Chemical structure not resolved')}<p class="checksum">SMILES: ${escape(c.isomeric_smiles || 'Chemical structure not resolved')}</p>${fields({formula:c.molecular_formula,molecular_weight:c.molecular_weight,formal_charge:c.formal_charge,stereochemistry:c.stereochemistry_status})}${button('compounds',c.id,protein,'Inspect identity, forms & provenance')}</article>`).join('') || EmptyState('No chemical matter imported. GET never retrieves provider data.')) + '</div>' + paginate(compounds);
  if (route === 'selectivity') {
    const selected = params.get('compound') || compounds.items[0]?.id;
    if (!selected) return boundary + nav + EmptyState('Not assessed: no compound imported.');
    const assessment = await api<Page<Assessment>>(`${prefix}/selectivity?compound=${encodeURIComponent(selected)}&limit=20&offset=${offset}`);
    const measured = await api<Page<Measurement>>(`${prefix}/measurements?compound=${encodeURIComponent(selected)}&limit=20`);
    return boundary + nav + `<label for="pharma-compound">Compound</label><select id="pharma-compound">${compounds.items.map(c=>`<option value="${escape(c.id)}" ${c.id===selected?'selected':''}>${escape(c.preferred_name)}</option>`).join('')}</select><p class="caption">Compound selector and inputs bounded to 20; use API pagination for larger collections. Not assessed here does not imply no counter-screen was reported; inspect the frozen curation audit for omitted/conflicting records.</p><div class="three-columns">${['ERAP1','ERAP2','LNPEP'].map(target=>`<article class="card"><h2>${target}</h2>${measured.items.filter(m=>m.assay.target_gene===target).map(m=>`<p>${escape(m.endpoint)} ${escape(m.relation_operator)} ${escape(m.original_value ?? 'Not reported')} ${escape(m.original_unit || '')}<br>${escape(text(m.assay.substrate))} · taxon ${escape(text(m.assay.taxon_id))}</p>${button('measurements',m.id,protein,'Inspect exact input')}`).join('') || EmptyState('Not assessed in this package')}</article>`).join('')}</div>${assessment.items.map(a=>`<article class="card"><h3>ERAP1 → ${escape(a.comparison_target_id)}</h3><span class="badge">${escape(a.comparability_status)}</span><p>${escape(a.rationale)}</p>${fields({ratio:a.ratio,lower_bound:a.ratio_lower_bound,upper_bound:a.ratio_upper_bound,lower_inclusive:a.lower_inclusive,upper_inclusive:a.upper_inclusive,transformation:a.transformation})}${a.primary_measurement_id?button('measurements',a.primary_measurement_id,protein,'Primary input'):''}${a.comparison_measurement_id?button('measurements',a.comparison_measurement_id,protein,'Comparison input'):''}</article>`).join('') || EmptyState('Not assessed')}${paginate(assessment)}`;
  }
  const query = new URLSearchParams({limit:'20',offset:String(offset)});
  for (const key of ['endpoint','target','assay_type']) if(params.get(key)) query.set(key,params.get(key)!);
  const page = await api<Page<Measurement>>(`${prefix}/measurements?${query}`);
  return boundary + nav + `<form id="pharma-filter" class="filters"><label>Endpoint <input name="endpoint" value="${escape(params.get('endpoint')||'')}" placeholder="IC50, AC50, Ki"></label><label>Target <select name="target"><option value="">All</option>${['ERAP1','ERAP2','LNPEP'].map(t=>`<option ${params.get('target')===t?'selected':''}>${t}</option>`).join('')}</select></label><button type="submit">Filter measurements</button></form><div class="table-scroll"><table><thead><tr>${['Compound','Target / organism','Construct','Assay / system','Endpoint','Operator','Value','Unit','Source'].map(h=>`<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${page.items.map(m=>`<tr><td>${escape(m.compound_name)}</td><td>${escape(text(m.assay.target_gene))}<br>Taxon ${escape(text(m.assay.taxon_id))}</td><td>${escape(text(m.assay.construct_mapping_status))}</td><td>${button('measurements',m.id,protein,text(m.assay.name))}<br>${escape(text(m.assay.assay_type))}</td><td>${escape(m.endpoint)}</td><td>${escape(m.relation_operator)}</td><td>${escape(m.original_value??'Not reported')}</td><td>${escape(m.original_unit||'Not reported')}</td><td>${escape(text(m.locator))}</td></tr>`).join('')}</tbody></table></div>${page.total ? paginate(page) : EmptyState('No matching measurements; not evidence of inactivity.')}<p class="caption">Each row is a separate measurement. No mean, median or “best potency”. Compounds 2 and 3 have cellular antigen-presentation phenotypes, not direct target engagement.</p>`;
}
export async function pharmacologyDrawer(api: API, project: string, protein: string, kind: string, id: string): Promise<string> {
  const detail = await api<Detail>(`${base(project,protein)}/${kind}/${encodeURIComponent(id)}`);
  const value = detail.compound || detail.record || {};
  return `<button class="drawer-close" data-close aria-label="Close pharmacology detail">×</button><h2 id="drawer-title">${kind==='compounds'?'Compound identity':'Measurement detail'}</h2>${fields(value)}${detail.assay?'<h3>Assay, exact target & conditions</h3>'+fields(detail.assay):''}${detail.chemical_identity?'<h3>Chemical identity</h3>'+fields(detail.chemical_identity):''}${detail.identifiers?'<h3>External identifiers</h3>'+detail.identifiers.map(fields).join(''):''}${detail.forms?'<h3>Tested chemical form</h3>'+detail.forms.map(fields).join(''):''}${detail.identity_graph?`<details><summary>Identity graph · bounded read</summary>${detail.identity_graph.edges.map(e=>`<p>${escape(e.from)} — ${escape(e.relation)} → ${escape(e.to)}</p>`).join('')}<p>${detail.identity_graph.has_more?'Additional graph records exist.':'All graph records in this read window.'} No therapeutic or observed-ligand edge.</p></details>`:''}${detail.potential_disagreements?'<h3>Potential disagreements — not averaged</h3>'+fields(detail.potential_disagreements):''}<h3>Provenance</h3>${detail.snapshot?fields(detail.snapshot):EmptyState('No source snapshot available')}${detail.snapshot && /^https:\/\//.test(text(detail.snapshot.request_url))?`<p><a href="${escape(text(detail.snapshot.request_url))}" target="_blank" rel="noopener noreferrer">Open original source ↗</a></p>`:''}${detail.provider_snapshot?'<h3>Provider-normalized representation (not primary experiment)</h3>'+fields(detail.provider_snapshot):''}<p>${escape(detail.boundary || 'Chemical identity and tested substance form are not interchangeable. No inference of therapeutic efficacy.')}</p>`;
}
