import { Stage, Selection, StructureComponent } from 'ngl';
import type { PickingProxy } from 'ngl';
import type { MappingData, ResidueRow, StructureChain } from './structure-ui';

export async function createViewer(element:HTMLElement,raw:string,mapping:MappingData,onSelect:(chain:StructureChain,row:ResidueRow)=>void):Promise<{highlight:(chain:StructureChain,row:ResidueRow)=>void;reset:()=>void;pan:(direction:number)=>void;dispose:()=>void}> {
  const stage = new Stage(element,{backgroundColor:'white'});
  try {
    const loaded = await stage.loadFile(new Blob([raw],{type:'text/plain'}),{ext:'cif',defaultRepresentation:false});
    if (!(loaded instanceof StructureComponent)) throw new Error('Coordinate file did not produce a molecular structure');
    loaded.addRepresentation('cartoon',{colorScheme:'chainname',sele:'protein'});
    loaded.addRepresentation('ball+stick',{sele:'not protein and not water',colorScheme:'element'});
    const highlightRep = loaded.addRepresentation('ball+stick',{sele:'none',color:'magenta'});
    const matches = (atom:{chainname:string;chainid:string;resno:number;inscode:string},chain:StructureChain,row:ResidueRow):boolean => atom.chainname === chain.auth_asym_id && atom.chainid === chain.label_asym_id && atom.resno === Number(row.author_residue_number) && (atom.inscode || '') === (row.insertion_code || '');
    const highlight = (chain:StructureChain,row:ResidueRow):void => {
      const indices:number[] = [];
      if (row.coordinate_present) loaded.structure.eachAtom(atom=>{if(matches(atom,chain,row))indices.push(atom.index);},new Selection('protein'));
      highlightRep.setSelection(indices.length ? `@${indices.join(',')}` : 'none');
    };
    stage.signals.clicked.add((pick:PickingProxy | undefined)=>{
      const atom = pick?.atom;
      if (!atom) return;
      for (const group of mapping.chains) {
        const row = group.rows.find(r=>r.coordinate_present && matches(atom,group.chain,r));
        if (row) {onSelect(group.chain,row);return;}
      }
      const panel = document.querySelector('#residue-detail');
      if (panel) panel.textContent = `Structural component ${atom.resname} ${atom.chainname}:${atom.resno}${atom.inscode || ''}. Canonical mapping unavailable.`;
    });
    stage.autoView();
    const observer = new ResizeObserver(()=>stage.handleResize());
    observer.observe(element);
    return {highlight,reset:()=>{stage.viewerControls.rotate([0,0,0,1]);stage.autoView();},pan:(direction)=>stage.viewerControls.translate([direction*10,0,0]),dispose:()=>{observer.disconnect();stage.dispose();}};
  } catch(error) {stage.dispose();throw error;}
}
