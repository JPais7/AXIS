"""Small ReportLab template; factual tables and decision values come from replay."""
import hashlib
import json
import subprocess
import re
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
D = json.loads((OUT / 'state-snapshot.json').read_text())
S = D['decision']; C = D['campaign']['prioritization']; L = D['learning']
def resource(path):
    return json.loads((ROOT / 'axis/resources' / path).read_text())
G = resource('discovery/erap1-axspa/v1/manifest.json')
M = resource('pharmacology/erap1/v1/measurements.json')
A = {x['id']: x for x in resource('pharmacology/erap1/v1/assays.json')}
DM = resource('decision/erap1-axspa/v1/manifest.json')
EXP = next(x for x in DM['candidate_experiments'] if x['id'] == S['recommended_experiment_id'])
SHA = '8f4e7797075e2beb25ad80de13d90843ad4e9de2'
subprocess.run(['git', 'diff', '--exit-code', SHA, '--', 'axis'], cwd=ROOT, check=True, capture_output=True)
assert S['critical_uncertainty_id'] == 'uncertainty:target_engagement'
assert S['recommended_experiment_id'] == 'decision:exp:chemical-genetic-engagement'
assert len(M) == 15 and len(L['entries']) == 9
assert all(x['conclusion'] == 'not_eligible' for x in D['eligibility'])
assert {x['name'] for x in C['panel']} == {'Bestatin', 'Captopril', 'Vorinostat'}
assert C['docking']['states']['result'] == 'no_result'
assert all(v['conclusion']['conclusion'] == 'future_evidence_did_not_test_the_decision' for v in D['retrospective'].values())
assert len(D['comparability']) == 36 and all(x['state']=='not_directly_comparable' for x in D['comparability'])
assert sum(x['readiness']=='SAR_ONLY' for x in D['eligibility']) == 6
assert sum(x['readiness']=='INSUFFICIENT_DATA' for x in D['eligibility']) == 3
NAVY = colors.HexColor('#152B36'); TEAL = colors.HexColor('#246E73')
PALE = colors.HexColor('#EDF3F2'); GRAY = colors.HexColor('#52616A')
W = A4[0] - 92
styles = {
 'body': ParagraphStyle('body', fontName='Helvetica', fontSize=10.2, leading=14.8, textColor=NAVY, spaceAfter=9),
 'small': ParagraphStyle('small', fontName='Helvetica', fontSize=8.2, leading=11.3, textColor=GRAY, spaceAfter=6, splitLongWords=True),
 'h1': ParagraphStyle('h1', fontName='Helvetica-Bold', fontSize=24, leading=28, textColor=NAVY, spaceAfter=16),
 'h2': ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=13, leading=17, textColor=TEAL, spaceBefore=10, spaceAfter=8),
 'cell': ParagraphStyle('cell', fontName='Helvetica', fontSize=8.1, leading=10.6, textColor=NAVY),
 'label': ParagraphStyle('label', fontName='Helvetica-Bold', fontSize=8, leading=11, textColor=TEAL, spaceAfter=8),
}
pages=[]; trace=[]
def p(text, style='body'):
    content=escape(str(text)).replace('\n','<br/>')
    content=re.sub(r'(10\.\d{4,9}/[A-Za-z0-9.\-/]+)',r'<link href="https://doi.org/\1" color="#246E73">\1</link>',content)
    return Paragraph(content, styles[style])
def table(rows, widths=None):
    t=Table([[p(v,'cell') for v in r] for r in rows], colWidths=widths or [W/len(rows[0])]*len(rows[0]), hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PALE),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,0),0.8,TEAL),('LINEBELOW',(0,1),(-1,-1),0.35,colors.HexColor('#D6DFDF'))]))
    return t
def box(title,text):
    t=Table([[p(title,'label')],[p(text)]],colWidths=[W])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('LEFTPADDING',(0,0),(-1,-1),14),('RIGHTPADDING',(0,0),(-1,-1),14),('TOPPADDING',(0,0),(-1,0),12),('BOTTOMPADDING',(0,-1),(-1,-1),10),('LINEBEFORE',(0,0),(0,-1),3,TEAL)]))
    return t
class Chain(Flowable):
    def __init__(self): super().__init__(); self.width=W; self.height=192
    def draw(self):
        c=self.canv
        labels=[('Genetics','SUPPORTED'),('Mechanism','SUPPORTED'),('Perturbation','MIXED'),('Structure','SUPPORTED*'),('Chemistry','PARTIAL'),('Cellular','PARTIAL'),('Engagement','MISSING / BLOCKING'),('Translation','INSUFFICIENT')]
        for i,(name,state) in enumerate(labels):
            col=i%4; row=i//4; x=col*(W/4); y=138-row*95
            c.setFillColor(PALE if i!=6 else colors.HexColor('#EEE2D0')); c.roundRect(x,y,W/4-10,61,4,fill=1,stroke=0)
            c.setFillColor(NAVY); c.setFont('Helvetica-Bold',10); c.drawString(x+9,y+39,name)
            c.setFont('Helvetica',7.1); c.drawString(x+9,y+20,state)
            if col<3:
                c.setStrokeColor(TEAL); c.line(x+W/4-9,y+30,x+W/4-1,y+30)
                c.line(x+W/4-4,y+33,x+W/4-1,y+30); c.line(x+W/4-4,y+27,x+W/4-1,y+30)
        c.setStrokeColor(TEAL); c.line(W-10,138,W-10,120); c.line(W-10,120,0,120); c.line(0,120,0,112)
        c.line(-3,115,0,112); c.line(3,115,0,112)
        c.setFont('Helvetica',8);c.setFillColor(GRAY);c.drawString(0,0,'*Experimental structure supported; therapeutic relevance and druggability unestablished.')
def page(title,items,refs=(),label='SCIENTIFIC DECISION INTELLIGENCE'):
    pages.append([p(label,'label'),p(title,'h1'),*items])
    trace.append({'page':len(pages),'section':title,'evidence':list(refs),'editorial_state':'AXIS inference unless explicitly source-labelled'})
def h(text): return p(text,'h2')
def bullets(items): return [p('• '+x) for x in items]

position='PARTIALLY SUPPORTED for investigating context-specific ERAP1 modulation. Therapeutic benefit from ERAP1 inhibition is not established in the current AXIS evidence scope.'
decision='RESOLVE CRITICAL UNCERTAINTY FIRST'
page('ERAP1 × axial\nspondyloarthritis',[
 p('AXIS TARGET DECISION BRIEF | Executive decision | v1.0','label'),
 p('Assessment: 5 October 2026. Frozen evidence snapshot through 5 October 2026; selected corpus, not a comprehensive literature cutoff. Primary disease evidence concerns ankylosing spondylitis (AS); broader axSpA applicability is unassessed.','small'),
 box('CURRENT AXIS POSITION', 'Scientific position: '+position+'\n\nStrongest evidence: AS genetic association and HLA-context interaction, plus source-reported peptide-processing and cellular perturbation effects.\n\nStrongest concern: cellular phenotypes lack established direct engagement; phenotype direction differs between cell systems.\n\nCritical uncertainty: '+S['position']['unresolved'][0]['statement']+'\n\nRecommended next experiment: '+S['recommendation']['title']+'.\n\nCurrent decision: '+decision+'.'),
 h('Why a scientific decision-maker should care'),
 p('ERAP1 has a plausible evidence chain to AS biology, but attributing a compound-induced phenotype to cellular ERAP1 is the unresolved step that determines whether to invest in that chemical strategy.'),
 p('AXIS INFERENCE: bounded decision framing from frozen evidence. Recommendation wording is an AI suggestion grounded by deterministic rules; independent scientific acceptance remains pending.','small'),
],['C01','C02','C03','C05','C08','C09','C10','C11','C12',S['id']])
matrix=[['Evidence layer','AXIS position','Key evidence','Main limitation','Decision relevance'],
 ['Genetics','SUPPORTED','AS association; HLA interaction','Association ≠ therapeutic direction','Biological rationale'],
 ['Target-disease','PARTIAL','Genetics + cellular mechanism','Broader axSpA unassessed','Scope program'],
 ['Mechanism','SUPPORTED','Peptide trimming / repertoire','Allotype and substrate context','Avoid global activity rule'],
 ['Perturbation','MIXED','Genetic + chemical effects','Opposite FHC directions','Test attribution'],
 ['Structure','SUPPORTED*','3QNF open state','Missing coordinates; no drug ligand','Bound structure use'],
 ['Chemical matter','PARTIAL','Maben 1-3','Small set; identity caveats','Reference chemistry'],
 ['Biochemical','SUPPORTED','Context-specific activity','IC50, AC50, Ki differ','Fix assay context'],
 ['Cellular','PARTIAL','FHC / presentation / Th17','Systems are not equivalent','Separate phenotype'],
 ['Engagement','INSUFFICIENT','Not assessed directly','Decision-blocking gap','Measure in cells'],
 ['Selectivity','INSUFFICIENT','Counter-screen bounds','Comparability unresolved','No ratio claim'],
 ['Translation','INSUFFICIENT','AS T-cell coculture','No established disease rescue','Further validation'],
 ['Clinical','NOT ASSESSED','No efficacy indexed','Selected corpus only','No efficacy conclusion']]
page('Evidence chain & chemical opportunity',[
 Chain(),table(matrix,[78,75,110,120,W-383]),
 p('AXIS editorial layer states are categorical summaries, not numeric maturity scores. *Structure existence does not establish druggability. FHC = free heavy chain.','small'),
 p('CHEMISTRY: three experimental Maben compounds; three computational exploration candidates (bestatin, captopril, vorinostat). Candidate identity is externally verified, but ERAP1 pharmacology is unestablished. Docking was not executed.','small'),
 p('MODEL NOT BUILT: 15 measurements, seven assays, nine distinct assay/endpoint datasets; all nine refused predictive modelling. Identity, prediction and experiment stay separate.','small'),
],['C01-C13','measurement:maben:1-15','PDB:3QNF',C['rules_fingerprint'],L['content_key']])
page('The next decision',[
 box('THE DECISION BOTTLENECK','Biochemical activity + cellular phenotype\n↓\nOn-target / off-target / indirect / context-dependent explanations\n↓\nDirect cellular engagement remains unestablished\n↓\nMatched-genotype engagement + phenotype experiment\n↓\nStrengthen, weaken, revise mechanism, or repeat after technical validation'),
 h('WHY THIS EXPERIMENT NEXT?'),*bullets([
 'It separates three pairs of viable explanations using engagement and genetic dependency together.',
 'It can weaken the preferred on-target explanation, rather than merely gather supporting observations.',
 'It connects distinct interpretable outcomes to different scientific actions.',
 'It uses a target-proximal endpoint with genetic and viability controls; engagement alone would not establish phenotype dependency.']),
 table([['Outcome','Interpretation and decision consequence'],['A: engagement + dependency + rescue','Strengthens ERAP1-dependent action for this compound and context. Selectivity, indirect mechanism and broader translation remain open.'],['B: phenotype persists without ERAP1','Weakens ERAP1 attribution for this compound; pursue another chemotype or explanation. Not universal target failure.'],['C: invalid assay/model or toxicity','Non-interpretable. Keep uncertainty open; validate controls and repeat.']],[125,W-125]),
 h('WHAT WOULD CHANGE OUR MIND?'),
 p('Strengthen: engagement aligned with active exposure, genetic dependency and rescue. Weaken: valid engagement-negative result or ERAP1-independent phenotype. Invalidate the local dependency interpretation: reproducible phenotype persistence in a validated ERAP1-null model. Leave unresolved: failed controls, toxicity, or positive engagement without dependency.'),
 p('Prerequisites: validated chemical identity, engagement assay and null/rescue model; a reference engaged ligand and inactive analogue are not established in this corpus. Cost, timing and local feasibility are unknown.','small'),
 p('Selected references: Evans 2011 (doi:10.1038/ng.873); Chen 2014 (doi:10.1002/art.38249); Chen 2016 (doi:10.1136/annrheumdis-2014-206996); Tran 2016 (doi:10.1016/j.molimm.2016.04.002); Maben (doi:10.1021/acs.jmedchem.9b00293). Independent scientific review pending.','small'),
], [S['id'],EXP['id'],'DECISION-EXP-001','DECISION-EXP-002','DECISION-EXP-005'])

page('Genetics & mechanistic scope',[
 h('SOURCE EVIDENCE | Genetic association'),
 *[p(x['statement']+' ['+x['source_id']+']') for x in G['claims'][:2]],
 h('SOURCE EVIDENCE | Peptide processing'),
 *[p(x['statement']+' ['+x['source_id']+']') for x in G['claims'][2:7]],
 h('AXIS INFERENCE | Therapeutic hypothesis'),
 p(DM['hypothesis']['description']),
 p('The formulation is an AI suggestion pending researcher approval. Genetic association and peptide-processing effects justify investigation but do not establish the therapeutic direction, a favorable patient phenotype, or benefit from reducing total activity.'),
 box('PROGRAM BOUNDARY','AS is the disease population indexed in the association studies. ERAP1 genotype, HLA context and substrate dependence constrain extrapolation. An allele-dependent presentation result is not evidence for an allele-specific drug.'),
],['C01-C07',DM['hypothesis']['id']])
page('Perturbation & competing observations',[
 table([['Perturbation','Source observation','Boundary'],['Genetic silencing; HeLa.B27 / C1R.B27','Reduced surface FHC; altered HLA-bound peptides','Genetic depletion is not partial pharmacological inhibition'],['DG013A; HeLa.B27 / C1R.B27','Reduced surface FHC','DG013A inhibits other aminopeptidases; substance identity unresolved'],['APC / AS CD4+ coculture','Suppressed Th17 expansion after silencing or inhibition','Ex vivo response; no in vivo efficacy established'],['shRNA; U937.B27','Increased HC10-reactive FHC and disulfide-linked dimers','Different cell background, HLA repertoire and assay'],['Maben 2 / 3; engineered HeLa','Reduced antigen presentation','Model mouse MHC-I context, not HLA-B27 engagement']],[120,185,W-305]),
 h('Where the evidence disagrees'),
 p('Chen reports reduced surface FHC after ERAP1 silencing in HeLa.B27/C1R.B27; Tran reports increased surface FHC in U937.B27. The Decision Engine retains the directional disagreement. It does not declare either study false or pool their effects.'),
 p('U937.B27 carries transfected HLA-B*27:05 alongside endogenous HLA-B*18:01 and HLA-B*51:01; the frozen curation records ERAP1 rs30187/rs27044 heterozygosity. These contextual differences are possible explanations, not proven causes of the discrepancy.'),
 h('Intervention strategies'),
 p('Catalytic reduction is a testable hypothesis, not an established treatment. Indexed Maben activity supports substrate-dependent biochemical modulation. Allosteric/conformational explanations remain mechanistic interpretations requiring binding evidence. Allotype-dependent modulation is a question motivated by context. Expression/degradation as a therapeutic strategy is not established in the current AXIS evidence scope; silencing is a perturbation observation.'),
],['C08-C13','measurement:maben:8','measurement:maben:15'])
chains=[['Chain','Canonical mapped','Coordinates','Unresolved mapped','Inserted positions']]
for x in D['structure']['chains']:
    cv=x['coverage'];chains.append([x['auth_asym_id'],cv['canonical_mapped'],cv['canonical_with_coordinates'],cv['unresolved_mapped'],cv['inserted_positions']])
page('Experimental structural evidence',[
 box('SOURCE EVIDENCE | PDB 3QNF','Human ERAP1 open-state crystal structure. X-ray diffraction, 3.0 Å resolution; deposited 2011-02-08, released 2011-02-23. Frozen provider revision 2.2 (2024-11-20).'),
 h('Construct and canonical mapping'),
 p('Deposited engineered entity 1, expressed in Trichoplusia ni. AXIS maps canonical UniProt Q9NZ08 positions 1-941 by provider-segment projection and sequence verification. The stored construct has 13 inserted expression-tag positions and no recorded substitutions or deletions. Isoform relation is a sequence-checksum inference, not a provider isoform claim.'),
 table(chains,[50,110,100,140,W-400]),
 p('Canonical mapping is not coordinate completeness. Missing coordinates do not establish physical truncation. Chain A is the computational campaign input; B and C are retained as distinct structural instances.'),
 h('Zinc and computational site'),
 p('The frozen coordinate package records zinc ions, glycans and waters. Campaign preparation retains zinc and records removal of NAG and water. The campaign defines an 8 Å shell around zinc in chain A as a computational site hypothesis. No drug-like ligand is bound in this campaign reference.'),
 h('AXIS INFERENCE | Limits'),
 p('The open state is not established as the disease-relevant conformation. This structure does not establish a validated therapeutic pocket, druggability, occupancy, biochemical potency or disease efficacy. Metal proximity is not evidence of chelation; standard docking would not resolve zinc coordination.'),
],['PDB:3QNF',D['structure']['structure']['source_snapshot_id']])
rows=[['Compound','Assay / endpoint','Source value','Interpretation boundary']]
for x in M:
    assay=x['assay_id'].replace('assay:maben:','')
    value=('>' if x['relation_operator']=='>' else '')+str(x['original_value'])+' '+x['original_unit']
    caveat='Context-specific; not engagement'
    if x['id']=='measurement:maben:6': caveat='Partial inhibition; <90% maximum'
    if x['endpoint']=='AC50': caveat='Activation, not inhibition IC50'
    if x['original_unit']=='fold': caveat='Fold activity, not potency'
    if 'HeLa' in assay: caveat='Presentation phenotype, not binding'
    if x['relation_operator']=='>': caveat='Censored bound, not exact 200'
    rows.append([x['compound_id'].replace('compound:maben-','Maben '),assay+' / '+x['endpoint'],value,caveat])
page('Experimental chemistry: measurements',[
 p('SOURCE EVIDENCE | Maben primary publication, doi:10.1021/acs.jmedchem.9b00293. All 15 indexed measurements are reproduced below without pooling endpoints or censoring boundaries.','small'),
 table(rows,[62,148,82,W-292]),
 p('AMC: ERAP1 L-AMC; ERAP2 R-AMC; mouse LNPEP/IRAP L-AMC. WK10, LF9 and pNA are distinct substrates. Ki uncertainty: compound 1 pNA ±4.3 µM; compound 2 pNA ±1.0 µM; compound 3 LF9 ±0.7 µM; uncertainty type unspecified.','small'),
],['measurement:maben:1-15','primary:maben-2020'])
page('Chemical identity & selectivity',[
 h('SOURCE EVIDENCE | Identity conflicts preserved'),
 p('Maben compound 2 is curated as the source urea C21H30N4O3 from Scheme 2 and synthesis/HRMS. ChEMBL CHEMBL4456470 represents a guanidine C21H31N5O2 and was rejected as a compound mapping. Manual structure transcription still requires independent chemical review.'),
 p('Provider ≤200 µM off-target records conflict with primary >200 µM entries. AXIS retains the provider record and uses the primary censored values. The provider IL1 receptor-antagonist mapping was rejected because it is not mouse IRAP Q8C129.'),
 p('Compound 1 stereochemistry is unresolved in the campaign input; tested substance forms and assay constructs are not fully resolved. DG013A remains a reported perturbagen label and has not been linked to one validated CompoundIdentity. Its cellular observations cannot be attached to Maben biochemical measurements.'),
 h('AXIS OBSERVATION | Selectivity'),
 p('Compounds 2 and 3 have ERAP2 and mouse IRAP IC50 bounds >200 µM. ERAP1 assays differ in substrate, endpoint, construct or conditions. Existing SelectivityAssessments preserve non-comparability and do not establish a quantitative selectivity ratio.'),
 table([['State','What is represented'],['Measured','Source counter-screen bounds for compounds 2 and 3'],['Not directly comparable','ERAP1 versus off-target measurements in differing contexts'],['Not assessed here','Compound 1 numeric off-target bounds; omitted due source/provider inconsistency'],['Unresolved','Broad off-target profile and selectivity at phenotype-active exposure']],[125,W-125]),
 p('DG013A inhibition of ERAP2 and LNPEP is an author-reported caveat in the indexed Chen study, not a new AXIS measurement. No selective therapeutic probe is established.','small'),
],['primary:maben-2020','chembl:maben-37','C11','selectivity:measurement:maben:3:measurement:maben:4'])
page('Cellular pharmacology & engagement',[
 h('SOURCE EVIDENCE | Separate the layers'),
 table([['Layer','What the indexed corpus supports'],['Biochemical modulation','Purified-enzyme, substrate-dependent measurements'],['Cellular phenotype','Surface FHC, peptide repertoire, presentation and coculture Th17 observations'],['Direct engagement','Not established for phenotype-producing compounds'],['Target dependency','Genetic observations exist; chemical phenotype attribution remains unresolved'],['Disease-relevant phenotype','AS T-cell coculture is informative; broader tissue/patient disease rescue is unestablished']],[145,W-145]),
 box('DIRECT CELLULAR ERAP1 ENGAGEMENT','NOT ESTABLISHED in the current AXIS evidence scope for the phenotype-producing compounds. Cellular phenotype and biochemical activity do not close this link.'),
 h('Why this gap controls the decision'),
 p('Two of the three indexed Maben compounds have biochemical activity and cellular phenotypes; the evidence remains separated by compound. Direct cellular engagement has not been assessed. Selectivity is unresolved, leaving an off-target explanation viable. DG013A also has unresolved substance identity.'),
 p('The Decision Engine therefore selects target engagement as decision-blocking and directly testable. It retains target dependency, genetic context, reproducibility, mechanistic bridge and translation as additional uncertainties. More literature or more unlinked biochemical potency measurements would not establish cellular attribution.'),
 p('AXIS INFERENCE | The recommendation is exploratory and pending independent acceptance. No engagement experiment has been performed by AXIS; synthetic result-loop demonstrations are excluded from this brief.','small'),
],['cellular:maben-2:gap','cellular:maben-3:gap','cellular:chen-dg013a-HeLa.B27:gap',S['critical_uncertainty_id']])
erows=[['Explanation / current state','Supporting or compatible evidence','Evidence against / missing evidence']]
for x in S['explanations']:
    support={'on_target':'Biochemical activity and chemical phenotype are compatible','off_target':'DG013A counter-target caveat; selectivity unresolved','indirect_pathway':'Proximal functional modulation insufficiently shown','context_dependent':'Directional FHC disagreement and unmatched contexts'}[x['ground']]
    missing={'on_target':'Missing direct engagement and chemical-genetic dependency','off_target':'No causal off-target mechanism established; genetic effects do not exclude it','indirect_pathway':'No direct pathway discrimination; phenotype alone insufficient','context_dependent':'Allotype/subtype cause unproven; matched comparison needed'}[x['ground']]
    erows.append([x['label']+' / '+x['status'].upper(),support,missing])
page('Competing explanations',[
 p('AXIS INFERENCE | Exact current explanation labels and states: on-target is partially supported; the other three are viable. All remain under consideration; none is an accepted experimental result.'),table(erows,[120,180,W-300]),
 h('Source observations versus interpretation'),
 p('Biochemical activity is observed in the source assays; attribution of the cellular phenotype to on-target action is an inference to be tested. An unresolved off-target profile is not proof of off-target causation. Directional disagreement across cell systems motivates a context-dependent explanation without establishing its cause.'),
 h('What the recommended experiment separates'),
 p('Engagement plus an ERAP1-null/rescue comparison can distinguish on-target, off-target and indirect explanations across the stored outcome scenarios. An engagement-positive, dependency-positive result still does not distinguish every ERAP1-dependent downstream route. A single matched background does not establish generality across allotypes or HLA-B27 subtypes.'),
 p('The underlying state preserves supporting, unresolved and context-limiting links by evidence ID and rule ID. The appendix and state snapshot expose those links so that a reviewer can disagree with the inference without losing the source chain.'),
], [x['id'] for x in S['explanations']])
candidate_rows=[['Candidate / role','Computational evidence','Reason to test / reason against','Required validation']]
for x in C['panel']:
    sim=x['dimensions']['similarity_to_reference']['value']
    candidate_rows.append([x['name']+' / '+x['role'],f'Distinct cluster; reference similarity {sim} (Morgan/Tanimoto). No docking evidence.','Test zinc-region chemical hypothesis; no indexed ERAP1 activity, engagement or selectivity.','Identity/form check; fixed biochemical context; concentration response and interference counterscreen; then engagement.'])
page('Computational discovery: bounded panel',[
 p('RESEARCHER HYPOTHESIS | A molecule with a metal-binding group that reaches the catalytic zinc region may inhibit catalytic trimming. This chemical hypothesis does not assume that inhibition treats disease.'),
 table(candidate_rows,[90,138,155,W-383]),
 p('AXIS OBSERVATION | PubChem identity verification: bestatin CID 72172; captopril CID 44093; vorinostat CID 5311. Identity verification is not ERAP1 pharmacology evidence.'),
 h('Panel interpretation'),
 *[p(x) for x in C['statements']],
 h('Docking status'),
 p('METHOD UNAVAILABLE; VALIDATION NOT ESTABLISHED; EXECUTION NOT ATTEMPTED; NO RESULT. The replay found no docking engine or PDBQT preparation toolchain. The frozen campaign has no validated target/site docking method, and standard scoring does not represent metal coordination.'),
 p('The candidates are computationally prioritized exploration molecules, not active compounds, validated binders or leads. Similarity values are chemical metrics, not target scores, probability estimates or potency predictions.'),
], ['campaign:erap1:bounded-chemistry-v1@r1'])
page('Chemical learning: what can be learned?',[
 box('CHEMISTRY → NEXT TEST','Experimental reference chemistry (Maben 1-3)\n+ computational exploration panel (bestatin, captopril, vorinostat)\n+ model-readiness refusal\n↓\nControlled biochemical testing for new candidates; engagement/dependency remains the main program decision.'),
 box('PREDICTIVE MODEL STATUS | NOT BUILT','All nine frozen ERAP1 chemistry datasets are not eligible. The indexed chemistry is too small and fragmented across assay contexts for defensible predictive modelling under the current AXIS policy.'),
 table([['Dimension','Current AXIS observation'],['Compounds / measurements','3 experimental compounds / 15 source measurements'],['Assays / contexts','7 assays across 3 targets; 9 endpoint-context datasets'],['Comparability','36 dataset-pair assessments; none directly comparable'],['Observed SAR','No matched molecular pairs; no shared-core pair in this set'],['Scaffold records','15 algorithmic scaffold-group records, not 15 experimental SAR relationships'],['Inferred SAR','No SAR hypothesis proposed'],['Readiness','6 SAR_ONLY; 3 INSUFFICIENT_DATA; all model-ineligible']],[140,W-140]),
 h('What the chemistry can teach the program'),
 p('The indexed substrate-dependent activation/inhibition and cellular presentation results establish the need to keep endpoints separate. They do not establish a transferable potency ranking or a predictive structure-activity relationship.'),
 p('The most populated ERAP1 L-AMC IC50 context contains two exact compounds on two scaffolds, spanning about 0.125 log10 units. A useful expansion would measure more compounds in one fixed context, diversify scaffolds and activity range, include actual matched pairs and make off-target measurements comparable.'),
 p('AXIS refuses to manufacture a QSAR result when its indexed evidence does not support one. These limits describe this dataset and modelling policy; they are not universal biological laws.'),
], [L['logical_id'],L['content_key']])
page('Recommended experiment & outcome tree',[
 h('AI SUGGESTION | Deterministically selected'),p(S['recommendation']['title']),
 p('Scientific question: '+S['recommendation']['question']),
 p('Context: '+S['recommendation']['biological_context']),
 p('Intervention: '+S['recommendation']['experiment']),
 p('Primary endpoint: '+S['recommendation']['primary_endpoint']),
 p('Controls: vehicle; matched ERAP1-null/depleted cells; inactive analogue if established; validated engaged reference ligand required. Viability measured separately; ERAP1 re-expression tests restoration.'),
 table([['Outcome','Interpretation / decision'],*[[x['key'].upper()+' / '+x['kind'],x['outcome']+' '+x['consequence']['statement']] for x in EXP['scenarios']]],[85,W-85]),
 p('Prerequisites remain unestablished: compound identity where unresolved, engagement readout and validated null/rescue model. Local cost and time are not estimated. One molecular cellular system does not test disease rescue or resolve full selectivity.','small'),
], [EXP['id'],*['decision:exp:chemical-genetic-engagement:'+x['key'] for x in EXP['scenarios']]])
page('Falsification, decision & validation limits',[
 h('WHAT WOULD CHANGE OUR MIND?'),
 *bullets(['Strengthen: cellular engagement at active exposure plus loss of phenotype in null cells and rescue after re-expression.',
 'Weaken: phenotype persists without ERAP1; or no engagement in a validated assay at phenotype-active exposures.',
 'Invalidate the specific ERAP1-dependent attribution: a reproducible ERAP1-independent phenotype in a valid matched model. This does not invalidate every ERAP1 intervention.',
 'Revise mechanism: dependency without detectable engagement favors an indirect route under the stored scenario.',
 'Leave unresolved: failed assay/model controls, toxicity, or engagement without dependency.']),
 box('CURRENT DECISION | '+decision,'WHY: cellular attribution is unestablished while multiple explanations remain viable.\nNEXT: establish the prerequisites and perform the matched-genotype engagement/phenotype experiment.\nDO NOT CONCLUDE YET: inhibition treats axSpA; computational candidates are active; an ERAP1 QSAR is valid; the phenotype predicts clinical efficacy.'),
 h('Retrospective validation'),
 p('The replayed ERAP1 T2011, T2014 and T2016 cases all conclude: future evidence did not test the decision. Later publications informed other uncertainties but did not resolve the engagement question. AXIS did not force hindsight confirmation. These development benchmarks do not establish prospective predictive validity.'),
 h('Scientific limitations'),
 p('Small purposefully selected corpus; not a systematic review. AS evidence cannot automatically extend to all axSpA. HLA, allotype, cell and substrate contexts differ. Engagement, chemical dependency, selectivity and therapeutic direction remain unresolved. Chemistry is small; no ERAP1 QSAR or prospective validation of candidates. Clinical efficacy and evidence that ERAP1 inhibition treats axSpA are not established in the current AXIS scope. Independent scientific and medicinal-chemistry review is pending.'),
], [S['id'],'erap1-axspa-t2011','erap1-axspa-t2014','erap1-axspa-t2016'])
refs=[]
for src in G['sources']:
    refs.append([src['source_id'],src['title'],src['doi']])
refs.append(['PMID:31841350','Maben et al. Discovery of Selective Inhibitors of Endoplasmic Reticulum Aminopeptidase 1. J Med Chem 2020;63:103-121.','10.1021/acs.jmedchem.9b00293'])
page('Primary references & evidence drill-down',[
 table([['Source','Frozen primary reference','DOI'],*refs],[85,260,W-345]),
 h('Auditable conclusion chains'),
 table([['Conclusion','Claim → experiment → source'],['AS genetic relevance','C01/C02 → association / replication → Evans / Cortes'],['Peptide-processing context','C03-C07 → trimming / immunopeptidome / variant presentation → Chang / Chen 2014'],['Phenotype disagreement','C08 vs C12/C13 → HeLa/C1R vs U937 readouts → Chen 2016 / Tran'],['Biochemical chemistry','measurement:maben:1-15 → substrate-specific assays → Maben, locators in snapshot'],['Engagement gap','cellular gap IDs → engagement assessments → DecisionState critical uncertainty'],['Recommended experiment','DecisionState → DECISION-EXP rules → candidate profile and prospective scenarios']],[125,W-125]),
 p('Reference validation checks identifier consistency against the frozen indexed packages; it is not a new full-text literature audit. Discovery access varies: abstracts/metadata for several sources; selected full-text methods/results for Chen and Tran; Maben primary PDF factual extract. Original publication rights remain with their owners.','small'),
], [r[0] for r in refs])
manifest_paths=['discovery/erap1-axspa/v1','targets/erap1/uniprot/v1','structures/erap1/3qnf/v1','pharmacology/erap1/v1','cellular/erap1-axspa/v1','decision/erap1-axspa/v1','benchmarks/retrospective/erap1-axspa/v1','computational-discovery/erap1/v1']
packages=[]
for path in manifest_paths:
    m=resource(path+'/manifest.json');f=ROOT/'axis/resources'/path/'manifest.json'
    packages.append({'path':'axis/resources/'+path,'version':m.get('package_version',m.get('version','v1 path; no declared semantic version')),'manifest_sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
page('Technical provenance & reproducibility',[
 p('Assessment date: 2026-10-05. Evidence cutoff: frozen indexed snapshot through 2026-10-05; original source retrieval/curation dates preserved. This date is not a claim that the literature is comprehensively current. AXIS 0.2.1.dev0. Repository: JPais7/AXIS. Template: axis-commercial-brief-1.0.'),
 p('Source main SHA: '+SHA,'small'),
 p('DecisionState: '+S['id']+'\nDecision rules: '+S['methodology']['rules_version']+'\nRule fingerprint: '+S['methodology']['rules_fingerprint'],'small'),
 p('ComputationalCampaign: campaign:erap1:bounded-chemistry-v1@r1\nPrioritization fingerprint: '+C['rules_fingerprint'],'small'),
 p('ChemicalLearningState: '+L['logical_id']+'@r'+str(L['revision'])+'\nContent fingerprint: '+L['content_key']+'\nEligibility policy fingerprint: '+D['model_policy_fingerprint'],'small'),
 table([['Frozen package','Version'],*[[x['path'].replace('axis/resources/',''),x['version']] for x in packages]],[W-110,110]),
 p('AXIS modelling policy: minimum 20 exact compounds, 5 scaffolds and 1 log10 activity range; maximum censored fraction 0.5. Other criteria are preserved in state-snapshot.json. These are policy thresholds, not scientific laws.','small'),
 p('Reproduce: run extract.py from the source checkout with AXIS dependencies, then build.py with ReportLab and pypdf. The replay creates a temporary fresh Evidence Store with network connections blocked; no synthetic experimental results are imported. Source data, state snapshot, traceability map, package hashes and output hashes are retained in this directory.','small'),
], [SHA,S['id'],L['content_key'],C['rules_fingerprint']])
page('AXIS',[
 p('Drug Discovery Decision Intelligence','h2'),Spacer(1,30),
 p('From evidence\nto uncertainty\nto the next scientific decision.','h1'),Spacer(1,35),
 p('AXIS is designed to help scientific teams interrogate evidence, expose decision-critical uncertainty and determine what should be tested next. It does not replace experimental validation or scientific judgment.'),
 h('Know what to test next - and why.'),
 p('ERAP1 × axial spondyloarthritis | v1.0 | 5 October 2026'),
 p('READY WITH CONDITIONS for design-partner discussion. AI-assisted curation and proposed experiments remain pending independent scientific review. Scientific approval for external investment diligence has not been obtained.','small'),
], [S['id']])

def footer(canvas,doc):
    canvas.saveState();canvas.setFillColor(TEAL);canvas.setFont('Helvetica-Bold',10);canvas.drawString(46, A4[1]-28,'AXIS')
    canvas.setStrokeColor(colors.HexColor('#D6DFDF'));canvas.line(46,36,A4[0]-46,36)
    canvas.setFillColor(GRAY);canvas.setFont('Helvetica',7.5);canvas.drawString(46,24,'ERAP1 × axSpA | v1.0 | Expert review pending');canvas.drawRightString(A4[0]-46,24,str(doc.page));canvas.restoreState()
def render(name,selected):
    dest=OUT/name;dest.parent.mkdir(parents=True,exist_ok=True)
    story=[]
    for i,pg in enumerate(selected):
        if i:story.append(PageBreak())
        story.extend(pg)
    doc=SimpleDocTemplate(str(dest),pagesize=A4,rightMargin=46,leftMargin=46,topMargin=52,bottomMargin=52,title='AXIS Target Decision Brief - ERAP1 × axial spondyloarthritis',author='AXIS',invariant=1)
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return len(PdfReader(dest).pages)
full=render('full/AXIS-ERAP1-axSpA-Target-Decision-Brief.pdf',pages)
executive_pages = [list(pg) for pg in pages[:3]]
executive_pages[0][-1] = p('Independent scientific review pending.', 'small')
executive=render('executive/AXIS-ERAP1-axSpA-Executive-Brief.pdf',executive_pages)
assert full==len(pages) and executive==3, (full,executive,len(pages))
manifest={'repository':'JPais7/AXIS','source_main_sha':SHA,'brief_version':'1.0','template_version':'axis-commercial-brief-1.0','assessment_date':'2026-10-05','evidence_cutoff':'Frozen indexed snapshot through 2026-10-05; not systematic literature currency','axis_version':'0.2.1.dev0','decision_state':S['id'],'decision_rule_fingerprint':S['methodology']['rules_fingerprint'],'campaign':'campaign:erap1:bounded-chemistry-v1@r1','computational_rule_fingerprint':C['rules_fingerprint'],'chemical_learning_state':L['logical_id']+'@r1','chemical_learning_content_key':L['content_key'],'chemical_learning_policy_fingerprint':D['model_policy_fingerprint'],'packages':packages,'page_count':{'full':full,'executive':executive},'independent_scientific_review':'pending','commercial_readiness':'READY WITH CONDITIONS','outputs':{str(f.relative_to(OUT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in OUT.rglob('*.pdf')}}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(OUT/'traceability.json').write_text(json.dumps({'sections':trace,'source_assertions':G['claims'],'evidence_assessments':G['assessments'],'mechanistic_assessments':G['mechanisms'],'experimental_measurements':M,'assay_contexts':list(A.values()),'references':refs,'decision_snapshot':'state-snapshot.json#/decision','chemical_learning_snapshot':'state-snapshot.json#/learning','computational_snapshot':'state-snapshot.json#/campaign'},indent=2)+'\n')
print(json.dumps({'full_pages':full,'executive_pages':executive,'decision':S['id']}))
