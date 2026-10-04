import { ContextTable, EmptyState, escape } from './components';
import type { Page, TargetProjection } from './types';

export interface ResidueRow { canonical_position: number | null; structural_sequence_position: number | null; construct_position: number | null; author_residue_number: string | null; insertion_code: string | null; residue_identity: string | null; canonical_identity: string | null; coordinate_present: boolean; status: string; source_difference: string | null }
export interface StructureChain { id: string; label_asym_id: string; auth_asym_id: string; chain_sequence: string; coverage: Record<string, number> }
export interface StructureData { structure: { id: string; provider_structure_id: string; title: string; experimental_method: string; resolution: number | null; revision: string | null; revision_date: string | null; raw_file_checksum: string }; chains: StructureChain[]; constructs: Record<string, unknown>[]; components: Record<string, unknown>[]; snapshot: Record<string, unknown>; boundary: string }
export interface MappingData { chains: { chain: StructureChain; rows: ResidueRow[]; transformation: Record<string, unknown> }[] }
type Read = <T>(url: string) => Promise<T>;
const fields = (value: Record<string, unknown>): string => ContextTable(Object.fromEntries(Object.entries(value).map(([k,v]) => [k, v === null ? null : typeof v === 'object' ? JSON.stringify(v) : String(v)])));
export function StructureSummary(data: StructureData, href: string): string {
  const s = data.structure;
  return `<a data-nav class="card project-card" href="${escape(href)}"><h2>${escape(s.provider_structure_id)} · ${escape(s.title)}</h2><p>${escape(s.experimental_method)} · ${s.resolution ?? 'Not reported'} Å · revision ${escape(s.revision ?? 'Not reported')}</p><p>${data.chains.length} protein chains · deposited construct ${escape(data.constructs.map(c => `${c.start_residue}–${c.end_residue}`).join(', '))}</p>${data.chains.map(c => `<p>Chain ${escape(c.label_asym_id)}: ${c.coverage.canonical_with_coordinates}/${c.coverage.canonical_length} canonical residues with coordinates</p>`).join('')}<p>Imported experimental snapshot · inspect structure →</p></a>`;
}
export function ResidueButtons(rows: ResidueRow[]): string {
  return rows.map((r,i) => `<button class="residue ${escape(r.status)} ${r.coordinate_present ? 'observed' : 'missing'}" data-residue="${i}" title="${escape(r.status)}; author ${escape(r.author_residue_number ?? 'Not reported')}${escape(r.insertion_code ?? '')}" aria-label="${r.canonical_position ? `Canonical residue ${r.canonical_position}` : `Construct insertion ${r.construct_position}`} · ${escape(r.status)}">${escape(r.canonical_identity || r.residue_identity || '?')}${r.canonical_position || `+${r.construct_position}`}</button>`).join('');
}
export async function structureContent(read: Read, project: string): Promise<string> {
  const targets = await read<Page<TargetProjection>>(`projects/${encodeURIComponent(project)}/targets`);
  const protein = new URLSearchParams(location.search).get('protein') || targets.items[0]?.protein.id;
  if (!protein) return EmptyState('No protein identity imported for this project.');
  const base = `projects/${encodeURIComponent(project)}/targets/${encodeURIComponent(protein)}/structures`;
  const page = await read<Page<StructureData>>(base);
  const selected = new URLSearchParams(location.search).get('structure');
  if (!selected) return `<p class="intro">Imported experimental objects, not disease conformations or therapeutic validation.</p><div class="source-grid">${page.items.map(s => StructureSummary(s, `/projects/${encodeURIComponent(project)}/structures?protein=${encodeURIComponent(protein)}&structure=${encodeURIComponent(s.structure.id)}`)).join('') || EmptyState('No structure records imported for this target.')}</div>`;
  const detailBase = `${base}/${encodeURIComponent(selected)}`;
  const [data,mapping] = await Promise.all([read<StructureData>(detailBase), read<MappingData>(`${detailBase}/mapping`)]);
  const first = mapping.chains[0];
  if (!first) return EmptyState('No supported protein-chain mapping imported.');
  // Bounded local state is retained in a module variable for this mounted page only.
  active = {data,mapping,base:detailBase,read};
  return `<div id="structure-detail"><a data-nav href="/projects/${encodeURIComponent(project)}/structures?protein=${encodeURIComponent(protein)}">← Imported structures</a><article class="card"><h2>${escape(data.structure.provider_structure_id)} · Experimental structure</h2><p>${escape(data.structure.title)}</p>${fields(data.structure)}<button data-structure-provenance>Source and mapping provenance</button><p>${escape(data.boundary)}</p><h3>Protein → construct → structure → chain → pinned sequence</h3>${data.constructs.map(c => `<details><summary>${escape(c.name)} · canonical range ${c.start_residue}–${c.end_residue}</summary>${fields(c)}</details>`).join('')}<h3>Chain identity and coverage</h3>${data.chains.map(c => `<details><summary>Label ${escape(c.label_asym_id)} / author ${escape(c.auth_asym_id)}</summary>${fields({sequence:c.chain_sequence,...c.coverage})}</details>`).join('')}<label for="structure-chain">Chain for residue mapping</label> <select id="structure-chain">${mapping.chains.map((c,i) => `<option value="${i}">${escape(c.chain.label_asym_id)} (author ${escape(c.chain.auth_asym_id)})</option>`).join('')}</select><p class="caption">Green: coordinates · dashed amber: deposited but unresolved · grey: not in construct/deletion · purple: inserted/tag positions. Substitutions/mismatches retain their classification.</p><div id="coverage-summary">${fields(first.transformation.coverage as Record<string, unknown>)}</div><label for="canonical-position">Canonical residue number</label> <input id="canonical-position" type="number" min="1" max="${Math.max(...first.rows.map(r => r.canonical_position ?? 0))}"><button data-find-residue>Inspect residue</button><div class="residue-list" id="residue-list">${ResidueButtons(first.rows)}</div><div id="residue-detail" class="state" role="status">Select a residue to inspect all numbering systems, mapping and coordinate status.</div><h3>Interactive 3D structure</h3><p>Rotate: left drag · zoom: wheel · pan: right drag. Scientific facts remain available above without WebGL.</p><button data-load-viewer>Load local 3D viewer</button><button data-reset-view>Reset view</button><button data-pan-view="-1">Pan left</button><button data-pan-view="1">Pan right</button><div id="molecular-viewer" aria-label="Interactive experimental structure viewer"></div><p id="viewer-status" role="status">Viewer not loaded; coordinates will be read locally only on request.</p><h3>Observed structural components (not compounds or drugs)</h3><details><summary>${data.components.length} component instances, including explicitly labelled water/ions</summary>${data.components.map(c => fields(c)).join('')}</details></article><a data-nav href="/projects/${encodeURIComponent(project)}/evidence">Return to project disease evidence →</a></div>`;
}
let active: {data:StructureData;mapping:MappingData;base:string;read:Read} | null = null;
export async function mountStructure(): Promise<() => void> {
  const root = document.querySelector<HTMLElement>('#structure-detail');
  const state = active;
  if (!root || !state) return () => {};
  let index = 0;
  let currentRow: ResidueRow | null = null;
  let viewer: {highlight:(chain:StructureChain,row:ResidueRow)=>void;reset:()=>void;pan:(direction:number)=>void;dispose:()=>void} | null = null;
  let disposed = false;
  const select = (row:ResidueRow, chain:StructureChain): void => {
    const selectedIndex = state.mapping.chains.findIndex(g => g.chain.id === chain.id);
    if (selectedIndex >= 0 && selectedIndex !== index) {
      index = selectedIndex;
      const dropdown = root.querySelector<HTMLSelectElement>('#structure-chain');
      if (dropdown) dropdown.value = String(index);
      const list = root.querySelector('#residue-list');
      const summary = root.querySelector('#coverage-summary');
      const selected = state.mapping.chains[index];
      if (list && selected) list.innerHTML = ResidueButtons(selected.rows);
      if (summary && selected) summary.innerHTML = fields(selected.transformation.coverage as Record<string,unknown>);
    }
    currentRow = row;
    const panel = root.querySelector('#residue-detail');
    if (panel) panel.innerHTML = `<strong>${row.canonical_position ? `Canonical position ${row.canonical_position}` : 'Canonical mapping unavailable'}</strong>${fields({chain_label:chain.label_asym_id,chain_author:chain.auth_asym_id,...row})}${!row.coordinate_present ? '<p>No coordinates for this deposited/missing position; nothing is highlighted in 3D.</p>' : ''}`;
    viewer?.highlight(chain,row);
  };
  const chainSelect = root.querySelector<HTMLSelectElement>('#structure-chain');
  chainSelect?.addEventListener('change',()=>{
    index = Number(chainSelect.value);
    const group = state.mapping.chains[index];
    if (!group) return;
    const list = root.querySelector('#residue-list');
    const summary = root.querySelector('#coverage-summary');
    if (list) list.innerHTML = ResidueButtons(group.rows);
    if (summary) summary.innerHTML = fields(group.transformation.coverage as Record<string,unknown>);
    if (currentRow) viewer?.highlight(group.chain,{...currentRow,coordinate_present:false});
    currentRow = null;
    const panel = root.querySelector('#residue-detail');
    if (panel) panel.textContent = 'Select a residue in this chain to inspect its mapping.';
  });
  root.addEventListener('click',event=>{
    const button = event.target instanceof Element ? event.target.closest<HTMLButtonElement>('button') : null;
    const group = state.mapping.chains[index];
    if (!button || !group) return;
    if (button.dataset.residue !== undefined) {
      const row = group.rows[Number(button.dataset.residue)];
      if (row) select(row,group.chain);
    } else if (button.hasAttribute('data-find-residue')) {
      const number = Number(root.querySelector<HTMLInputElement>('#canonical-position')?.value);
      const row = group.rows.find(r=>r.canonical_position === number);
      if (row) select(row,group.chain);
    } else if (button.hasAttribute('data-reset-view')) viewer?.reset();
    else if (button.hasAttribute('data-pan-view')) viewer?.pan(Number(button.dataset.panView));
    else if (button.hasAttribute('data-structure-provenance')) {
      const drawer = document.querySelector<HTMLDialogElement>('#evidence-drawer');
      if (!drawer) return;
      drawer.innerHTML = `<button class="drawer-close" data-close aria-label="Close structure provenance">×</button><h2 id="drawer-title">Structure source and mapping provenance</h2><h3>Provider metadata snapshot</h3>${fields(state.data.snapshot)}<h3>AXIS-computed mapping, not a provider alignment result</h3>${state.mapping.chains.map(c=>fields(c.transformation)).join('')}`;
      drawer.showModal();
      drawer.querySelector<HTMLButtonElement>('button')?.focus();
      drawer.addEventListener('close',()=>button.focus(),{once:true});
    } else if (button.hasAttribute('data-load-viewer')) {
      button.disabled = true;
      const status = root.querySelector('#viewer-status');
      if (status) status.textContent = 'Loading local coordinates and lazy-loaded NGL…';
      void (async()=>{
        try {
          const [module,coordinates] = await Promise.all([import('./structure-viewer'),state.read<{content:string}>(`${state.base}/coordinates`)]);
          if (disposed || !root.isConnected) return;
          const element = root.querySelector<HTMLElement>('#molecular-viewer');
          if (!element) return;
          viewer = await module.createViewer(element,coordinates.content,state.mapping,(chain,row)=>select(row,chain));
          if (disposed) {viewer.dispose();return;}
          const selected = state.mapping.chains[index];
          if (currentRow && selected) viewer.highlight(selected.chain,currentRow);
          if (status) status.textContent = 'Local experimental structure loaded. Cartoon colours distinguish chains; click a residue to inspect its canonical mapping.';
        } catch(error) {if (status) status.textContent = `3D unavailable: ${error instanceof Error ? error.message : 'WebGL initialization failed'}. All mapping facts remain available textually.`;button.disabled=false;}
      })();
    }
  });
  return ()=>{disposed=true;viewer?.dispose();active=null;};
}
