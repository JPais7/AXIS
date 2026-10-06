"""Generate the external review PDF from frozen Git objects; no network acquisition.

Run with Python + reportlab + pypdf from this directory or anywhere in the checkout.
Content edits belong to this documentation file, never to scientific resources.
"""
import argparse
import hashlib
import html
import json
import subprocess
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.pagesizes import A4
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCI = 'd11128538a2723737eced46be73d40cef56f43db'
REF = '84ecc56e74747bdee12ecdf15b9a80bc760798f4'
CAND = '0dc0ac13746f2e7107abc128d1471a7a99e3f64e'
CLOSURE = '54ea4ef1fe3e53c34a405b9dc98ba41f5a4d6996'
BASE = 'axis/resources/evidence-integration/erap1-data-rich/2026/'
V3 = BASE + 'bradshaw-main-v3/'
PDF = HERE / 'AXIS_ERAP1_Independent_Scientific_Review_Pack.pdf'
BLUE = colors.HexColor('#18384A')
TEAL = colors.HexColor('#20776E')
GREY = colors.HexColor('#EEF2F4')
ledger = []
inputs = {}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--visual-qa-pass', action='store_true', help='Record completed manual inspection of the latest rendered seven pages; do not use before inspection.')
args = parser.parse_args()

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def raw(path, commit=SCI):
    b = git('show', f'{commit}:{path}')
    inputs[f'{commit}:{path}'] = hashlib.sha256(b).hexdigest()
    return b

def read(path, commit=SCI):
    return json.loads(raw(path, commit))

assert git('rev-parse', f'{SCI}^2').decode().strip() == CAND
assert git('rev-parse', f'{SCI}^{{tree}}') == git('rev-parse', f'{CAND}^{{tree}}')
git('merge-base', '--is-ancestor', REF, SCI)
git('merge-base', '--is-ancestor', CLOSURE, 'HEAD')
assert not git('diff', SCI, '--', 'axis', 'scripts', 'reports/commercial', 'benchmarks')
state = read(V3 + 'decision-state-v2.json')
old = read('reports/commercial/erap1-axspa/v1/state-snapshot.json')['decision']
diff = read(V3 + 'causal-decision-diff.json')
comp = read(V3 + 'assay-comparability.json')
unc = read(V3 + 'localized-uncertainty.json')
learning = read(V3 + 'learning-eligibility.json')
provenance = read(V3 + 'source-provenance.json')
manifest = read(V3 + 'manifest.json')
context = read(V3 + 'allotype-substrate-context.json')
sources = read('axis/resources/discovery/erap1-axspa/v1/manifest.json')['sources']
index = read(BASE + 'v1/study-index.json')
chem = read('axis/resources/pharmacology/erap1/v1/chembl-extract.json')['document']['documents'][0]
methods = read(BASE + 'assay-methods-v2/source-artifacts.json')
for path, commit in [('docs/erap1-current-scientific-state.md', SCI), ('docs/axis-repository-consolidation-2026.md', SCI), ('docs/erap1-bradshaw-final-reassessment-2026.md', SCI), ('docs/releases/independent-review-handoff-2026-10-06.md', CLOSURE)]:
    raw(path, commit)
critical = next(x for x in state['uncertainties'] if x['id'] == state['critical_uncertainty_id'])
rec = state['recommendation']
candidate = next(x for x in state['candidates'] if x['experiment_id'] == rec['experiment_id'])
assert old['id'] == state['supersedes_id'] == 'decision-state:1:cebbae3880aeec90'
assert diff['classification'] == 'DECISION STABLE'
assert state['id'] == 'decision-state:2:212f995ecc55c989'
assert critical['id'] == 'uncertainty:target_engagement'
assert rec['experiment_id'] == 'decision:exp:chemical-genetic-engagement'
assert learning['model_trained'] is False if 'model_trained' in learning else 'No model was trained' in raw('docs/erap1-current-scientific-state.md').decode()

styles = {
 'body': ParagraphStyle('body', fontName='Helvetica', fontSize=10.2, leading=14, textColor=BLUE, spaceAfter=8),
 'small': ParagraphStyle('small', fontName='Helvetica', fontSize=8.7, leading=11.5, textColor=BLUE, spaceAfter=5),
 'title': ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=25, leading=30, textColor=BLUE, spaceAfter=16),
 'h': ParagraphStyle('h', fontName='Helvetica-Bold', fontSize=13, leading=17, textColor=TEAL, spaceBefore=9, spaceAfter=7),
 'callout': ParagraphStyle('callout', fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=BLUE, spaceAfter=10),
}

def p(text, kind='directly supported', source=V3+'decision-state-v2.json', style='body'):
    ledger.append({'text':text, 'classification':kind, 'source':source})
    return Paragraph(text, styles[style])

def h(text): return Paragraph(text, styles['h'])
def table(rows, widths, size=8.8):
    for row in rows[1:]:
        ledger.append({'table_row':row, 'classification':'repository-derived inference', 'source':'Frozen DecisionState v2, assay-comparability registry, or reviewer response instructions; see input bindings'})
    st = ParagraphStyle('cell', parent=styles['small'], fontSize=size, leading=size+3)
    cells = [[Paragraph(html.escape(str(x)), st) for x in row] for row in rows]
    t = Table(cells, colWidths=widths, hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),GREY),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),0.7,TEAL),('LINEBELOW',(0,1),(-1,-1),0.3,colors.HexColor('#D5DFE3')),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    return t

story=[]
def page(title):
    if story: story.append(PageBreak())
    story.append(Paragraph(title, styles['title']))

page('AXIS<br/>ERAP1 × Axial Spondyloarthritis')
story += [h('Independent Scientific Review Pack'),p('Version 1.0 | 6 October 2026 | Independent review pending', style='small'),p('Evidence cutoff: <b>2026-10-05</b><br/>Frozen scientific/runtime state:<br/>'+SCI, style='small'),Spacer(1,22)]
story += [p('AXIS is a scientific decision system designed to make the reasoning between evidence, uncertainty and the next discriminating experiment explicit and auditable. In this case, it links source-scoped ERAP1 evidence to categorical assessments, competing explanations and conditional experimental consequences. It preserves distinctions between source assertions, calculations, inferences and proposed experiments. The present pack summarizes one frozen exploratory decision for expert criticism; it does not present AXIS as an autonomous scientist or treat automated reproducibility as scientific approval.', 'repository-derived inference', 'docs/axis-repository-consolidation-2026.md')]
story += [h('Review purpose'),p('This is a request for independent scientific criticism, not endorsement.', 'reviewer question', style='callout'),p('We are not asking whether you endorse AXIS. We are asking where this scientific decision may be wrong.', 'reviewer question', style='callout'),p('Please seek factual errors, overclaims, material missing evidence within scope, inappropriate evidence transfer, flawed assay comparisons, mechanistic reasoning errors, incorrect uncertainty prioritization and weaknesses in the next experiment.', 'reviewer question'),h('Reading route'),p('Read pages 2-5 for the decision in approximately 10 minutes. Use the questions, primary references and immutable repository links on pages 6-7 for a 30-60 minute audit.', 'reviewer question'),h('Status and boundary'),p('AXIS has not been independently scientifically validated.', 'limitation', 'docs/erap1-current-scientific-state.md', 'callout'),p('This document summarizes a frozen scientific decision analysis for independent review. It is not clinical guidance, evidence of therapeutic efficacy, regulatory advice, or an endorsement of ERAP1 as a validated therapeutic target.', 'limitation')]

page('Decision snapshot')
story += [p('Genetics → Mechanism → Structure → Chemistry → Cellular pharmacology → Target engagement → Disease translation', 'repository-derived inference', style='callout')]
edges = state['evidence']['edges']
rows=[['Layer','Frozen assessment / scope'],['Genetics','ERAP1 × HLA association recorded; association does not establish therapeutic direction.'],['Mechanism','Peptide-processing context; functional edge: '+edges['functional']['state'].upper()+'.'],['Structure','13 mapped structures in v2; 12 added since canonical v1. Binding/design context, not cellular occupancy.'],['Chemistry','Biochemical edge: '+edges['biochemical']['state'].upper()+'. Defined preparations and assay contexts only.'],['Cellular pharmacology','HLA-phenotype edge: '+edges['hla']['state'].upper()+'. Reporter/peptidome changes are not direct engagement.'],['Target engagement','Engagement edge: '+edges['engagement']['state'].upper()+'. Historical compound-specific attribution unresolved.'],['Disease translation','Disease-model edge: '+edges['disease']['state'].upper()+'; clinical edge: '+edges['clinical']['state'].upper()+'. No established human axSpA efficacy.']]
assert len(state['evidence']['structure_ids']) == 13
story += [table(rows,[110,397]),Spacer(1,12),h('CURRENT DECISION'),p(diff['classification'], source=V3+'causal-decision-diff.json',style='callout'),p('Expanded evidence coverage did not change the critical uncertainty, next experiment or strategy identifiers. This is not a claim that all evidence or uncertainty states are unchanged.', 'repository-derived inference', V3+'causal-decision-diff.json'),h('CRITICAL UNCERTAINTY'),p(html.escape(critical['question']), 'repository-derived inference'),h('NEXT DISCRIMINATING EXPERIMENT'),p(html.escape(rec['title']), 'repository-derived inference'),p('Engagement at phenotype-active exposure, coupled to a matched null/rescue comparison, can strengthen or weaken compound-specific attribution. The proposal is not performed or investigator-approved; feasibility remains unknown.', 'limitation')]

page('Supporting evidence and constraints')
left = [p('<b>Supporting continued investigation</b>',style='callout'),p('ERAP1/HLA genetic associations motivate peptide-handling biology, not a prescribed intervention. [1,2]',source='axis/resources/discovery/erap1-axspa/v1/manifest.json'),p('Peptide trimming and HLA-B27 repertoire effects provide mechanistic context; cellular responses are system-specific. [3-6]',source='axis/resources/discovery/erap1-axspa/v1/manifest.json'),p('Allotype/substrate dependence is experimentally characterized and material to interpretation. [8,9]',source=BASE+'v1/study-index.json'),p('Ligand-bound experimental regulatory-site structures and measured chemistry support design/tractability under recorded construct and assay contexts. [7,10-12]',source='docs/erap1-bradshaw-final-reassessment-2026.md'),p('BRADSHAW establishes defined Hap2/YTAFTIPSI biochemical activity and HeLa antigen-presentation pharmacology. Tinworth adds separate programme evidence; neither transfers occupancy to Maben compounds. [10-12]',source='docs/erap1-bradshaw-final-reassessment-2026.md')]
right=[p('<b>Limiting the decision</b>',style='callout'),p('Historical phenotype-producing Maben compounds lack demonstrated compound-specific direct cellular engagement in the curated decision. Off-target and indirect explanations remain viable. [7]', 'limitation'),p('Biochemical inhibition, cellular antigen presentation, engagement and disease modification are different evidence classes.', 'limitation'),p('Unreported context and allotype/substrate dependence restrict pooling and transfer. Chen and Tran report different free-heavy-chain directions in different systems. [5,6]', 'limitation'),p('No established human axSpA therapeutic efficacy follows from these preclinical data. Independent review remains pending; no predictive model was trained.', 'limitation','docs/erap1-current-scientific-state.md')]
t=Table([[left,right]],colWidths=[253.5,253.5]); t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),15)])); story += [t,h('Comparability is inference-scoped')]
story += [table([['Comparison','Frozen category'],*[[x['families'],x['status']] for x in comp['comparisons']]],[330,177]),Spacer(1,10),p('Chemical tractability is better established than therapeutic causality in this frozen corpus.', 'repository-derived inference','docs/erap1-bradshaw-final-reassessment-2026.md','callout'),p('COMPARABLE is confined to source-specific Hap2/YTAFTIPSI SAR with exclusions; PARTIALLY_COMPARABLE establishes a method family, not quantitative interchangeability, selectivity ratios or pooling.', 'limitation', V3+'assay-comparability.json', 'small')]

page('Why this experiment next?')
story += [p('Observed activity + cellular phenotype → competing explanations → unresolved engagement → matched engagement/null/rescue experiment → prospective outcome → decision consequence', 'repository-derived inference',style='callout')]
exp_rows=[['Explanation','Frozen status / scientific alternative']]
for x in state['explanations']:
    exp_rows.append([x['label'],x['status'].upper()+': '+x['statement']])
story += [table(exp_rows,[135,372],8.6),h('Proposed design - not an executed result'),p(rec['biological_context']+'. '+rec['experiment'], 'repository-derived inference'),p('<b>Primary endpoint:</b> '+rec['primary_endpoint']+'. <b>Context:</b> report/match ERAP1 allotype; choose/report HLA-B27 subtype. Measure viability separately and use the same phenotype-active exposures.', 'repository-derived inference'),p('<b>Controls and feasibility:</b> vehicle; matched ERAP1-null/depleted cells; rescue; inactive analogue only if established (none identified). No qualifying positive-control ligand is established in the curated corpus. Compound identity, engagement readout and null/rescue validation remain prerequisites; cost/time and local feasibility are unknown.', 'limitation'),h('Outcome → decision (all prospective AI suggestions)')]
summaries=[('s1','Engagement + attenuation in null + rescue','Strengthen this compound/context strategy; indirect downstream action and broader context are not excluded.'),('s2','Engagement + phenotype unchanged in null','Weaken ERAP1 attribution; alternative chemotypes require their own evidence.'),('s3','No signal in validated assay + attenuation in null','Change mechanistic model toward an indirect route; re-justify strategy.'),('s4','Engagement/dependency vary by background','Investigate matched allotype/HLA context before strategy choice.'),('s5','Invalid null/rescue or toxicity confounding','No mechanistic inference; validate controls/model and repeat.')]
assert [x['scenario_id'].rsplit(':',1)[-1] for x in rec['outcome_scenarios']]==[x[0] for x in summaries]
story += [table([['ID','Observation','Decision consequence'],*summaries],[40,196,271],8.2),p('A single system does not establish patient relevance. Null/rescue is not partial pharmacological inhibition; selectivity against other proteins remains unresolved. No scenario has occurred in this reassessment.', 'limitation',style='small')]

page('2026 reassessment: change without closure')
story += [h('What changed'),p('The causal diff records expanded structural, chemical and cellular evidence coverage. Twelve source-mapped structures were added since canonical v1; these provide regulatory-site design context, not occupancy. [7,10-12]',source=V3+'causal-decision-diff.json'),p('Legitimate access to the BRADSHAW main article resolved the assay-identity blocker. Page 17/reference 22 explicitly links to Liddle 2020: purified Hap2, YTAFTIPSI cleavage and RapidFire MS. This chain supports constrained interpretation, not inferred equivalence based on programme similarity. [10,12]',source='docs/erap1-bradshaw-final-reassessment-2026.md'),p('Conservative BRADSHAW subsets retain 38 biochemical compounds/24 Murcko scaffolds and 31 cellular compounds/19 scaffolds. Scientific eligibility is MODEL_ELIGIBLE_WITH_CONDITIONS; no model was trained. Tinworth remains separate SAR-only evidence. [10,11]',source='docs/erap1-current-scientific-state.md'),h('What did not change'),p('Historical Maben compound-specific engagement remains unresolved. Biochemical potency does not establish cellular engagement; a cellular phenotype does not establish a therapeutic mechanism. Later programme evidence cannot supply occupancy for earlier compounds.', 'limitation'),p('Critical uncertainty and the recommended chemical-genetic engagement experiment remain unchanged. Strategy identifiers are stable. No protective human peptide state, optimal modulation magnitude or human axSpA efficacy is established.', 'limitation','docs/erap1-bradshaw-final-reassessment-2026.md'),h('Material restrictions retained'),p('Unknown temperature, preincubation, dose range and tested form restrict exact replication and cross-programme comparison. HeLa ERAP1 allotype, ERAP2, endogenous HLA and control-inhibitor identity remain unconfirmed.', 'limitation',V3+'localized-uncertainty.json'),p('Compound 28 retains the main/SI discrepancy (cellular pIC50 5.3 versus 5.4). Censored occasions for 21/28/33/44, singleton observations and missing N are preserved and excluded where required for fitting. No bound becomes an exact value.', 'limitation','docs/erap1-bradshaw-final-reassessment-2026.md'),h('Epistemic key'),p('<b>Source assertion</b>: what a publication reports. <b>AXIS observation</b>: recorded extraction/calculation. <b>AXIS inference</b>: scoped interpretation. <b>AI suggestion</b>: competing explanations/experiment/scenarios. <b>Researcher hypothesis</b>: proposed mechanism. <b>Experimental result</b>: an observed performed experiment, not a prospective scenario. These kinds are not interchangeable; pending reviews remain pending.', 'repository-derived inference','docs/axis-repository-consolidation-2026.md'),p('The disease-model edge is SUPPORTED in v2 while clinical translation remains NOT_ASSESSED. Animal/cellular evidence is not human axSpA efficacy; the stable decision concerns the still-missing compound-specific engagement link.', 'limitation')]

page('Independent critique and provenance')
questions=['Is the ERAP1/HLA-B27/spondyloarthritis biology represented accurately?','Is any material evidence overstated?','Is important evidence missing within the stated scope and cutoff?','Are assay contexts and comparability restrictions appropriate?','Is allotype/substrate dependence represented appropriately?','Are biochemical activity, phenotype and direct engagement sufficiently distinct?','Is historical Maben evidence correctly separated from later programme tractability?','Is direct cellular engagement the most important unresolved decision uncertainty?','Does the chemical-genetic experiment discriminate the major explanations?','Is DECISION STABLE a scientifically defensible interpretation?']
for i,q in enumerate(questions,1): story.append(p(f'{i}. {q}', 'reviewer question',style='small'))
story += [p('What is the strongest scientific reason this decision could be wrong?', 'reviewer question',style='callout'),table([['Field','Response (repeat for each issue)'],['Severity','CRITICAL / MAJOR / MINOR / NO_ISSUE'],['Claim/artifact','Provide exact locator'],['Evidence/source','Provide exact locator'],['Rationale','Explain the scientific concern'],['Recommended correction','Describe the remedy'],['Changes decision?','YES / NO / UNCERTAIN; explain']],[170,337],8.8),h('Review snapshot'),p('Cutoff 2026-10-05 | Decision: '+diff['classification']+'<br/>Scientific/runtime: '+SCI+'<br/>Scientific reference: '+REF+'<br/>v1: '+old['id']+' | v2: '+state['id']+'<br/>Critical: '+critical['id']+'<br/>Next: '+rec['experiment_id'],style='small'),p('Every material AXIS conclusion is intended to be traceable from conclusion → claim → evidence → experiment/source. This is an intended audit chain, not certification of completeness or factual accuracy.', 'limitation',style='small')]
links=[('Current scientific state','docs/erap1-current-scientific-state.md',SCI),('BRADSHAW reassessment','docs/erap1-bradshaw-final-reassessment-2026.md',SCI),('DecisionState v2',V3+'decision-state-v2.json',SCI),('Causal diff',V3+'causal-decision-diff.json',SCI),('Assay comparability',V3+'assay-comparability.json',SCI),('Evidence manifest',V3+'manifest.json',SCI),('Independent-review handoff','docs/releases/independent-review-handoff-2026-10-06.md',CLOSURE)]
for label,path,commit in links:
    raw(path,commit)
    url=f'https://github.com/JPais7/AXIS/blob/{commit}/{path}'
    story.append(p(f'<link href="{url}" color="#20776E">{label}</link> - immutable '+commit[:7],style='small',source=path))

page('Key primary sources')
refs=[{'title':s['title'],'doi':s['doi'],'year':s['year'],'note':'Frozen discovery provenance; access is claim-specific.'} for s in sources]
refs.append({'title':chem.get('title','Maben et al., ERAP1 inhibitors; J Med Chem 63:103-121'),'doi':chem['doi'],'year':'2020','note':'Historical biochemical/cellular compounds; not direct cellular occupancy.'})
for doi in ['10.1016/j.jbc.2021.100443','10.1002/eji.202350449']:
    s=next(x for x in index if x['doi']==doi)
    refs.append({'title':s['title'],'doi':doi,'year':s['first_publication_date'][:4],'note':'Frozen allotype/substrate or cellular immunopeptidome context.'})
main=provenance['main_source']
refs.append({'title':main['title'],'doi':main['doi'],'year':str(main['year']),'note':'Law et al.; main p4-5, p17/ref22; SI S60/Table S2. Institutional access; PDF not redistributed.'})
tin=next(x for x in index if x['doi']=='10.1021/acs.jmedchem.6c00029')
refs.append({'title':html.unescape(tin['title']).replace('<i>','').replace('</i>',''),'doi':tin['doi'],'year':'2026','note':'Tinworth programme. Methods rely on accessible preprint 10.1101/2025.11.17.686761 v1/SI; final main inaccessible in frozen scope. One publication chain, not independent replication.'})
liddle=next(x for x in methods if x.get('publication_version')=='10.1021/acs.jmedchem.9b02123')
refs.append({'title':'Liddle et al. - ERAP1 biochemical assay-method source','doi':liddle['publication_version'],'year':'2020','note':'Bibliographic locator retained without inventing an unrecorded title; main p8(H), linked explicitly by BRADSHAW p17/ref22.'})
assert len(refs)==12
for i,r in enumerate(refs,1):
    title=html.escape(html.unescape(r['title']))
    url='https://doi.org/'+r['doi']
    story += [p(f'<b>[{i}] {title}</b> ({r["year"]}).<br/><link href="{url}" color="#20776E">DOI: {r["doi"]}</link><br/>{r["note"]}',source='frozen primary provenance',style='small')]
story += [h('Access and scope'),p('References are selected from the frozen corpus, not a new systematic search. Metadata/abstract access is not full-text adjudication. The later BRADSHAW v3 access record supersedes its older insufficient-access label; Tinworth final-main restrictions remain. Licensed primary PDFs are not included. Missing engagement in this corpus is not a claim that no engagement evidence exists anywhere.', 'limitation',style='small'),p('Please return structured criticism of the decision and its provenance. Independent scientific review remains pending.', 'reviewer question',style='small')]

def footer(c, doc):
    c.setStrokeColor(TEAL); c.line(44,42,551,42)
    c.setFont('Helvetica',7.1); c.setFillColor(BLUE)
    c.drawString(44,29,'AXIS ERAP1 × axSpA | Independent Scientific Review | Cutoff 2026-10-05 | State d111285')
    c.drawRightString(551,16,f'v1.0 | 2026-10-06 | {doc.page}')

doc=SimpleDocTemplate(str(PDF),pagesize=A4,rightMargin=44,leftMargin=44,topMargin=42,bottomMargin=58,title='AXIS ERAP1 Independent Scientific Review Pack',author='AXIS',pageCompression=1,invariant=1)
doc.build(story,onFirstPage=footer,onLaterPages=footer)
reader=PdfReader(PDF)
assert len(reader.pages)==7, f'Unexpected overflow: {len(reader.pages)} pages'
text='\n'.join(x.extract_text() for x in reader.pages)
for value in [SCI,REF,old['id'],state['id'],critical['id'],rec['experiment_id'],'2026-10-05']:
    assert value in text, value
for _,path,commit in links: assert git('cat-file','-e',f'{commit}:{path}')==b''
qa={'schema_version':1,'source_branch':'codex/independent-review-freeze-2026','starting_sha':CLOSURE,'scientific_sha':SCI,'reference_sha':REF,'candidate_sha':CAND,'evidence_cutoff':'2026-10-05','pack_version':'1.0','pack_date':'2026-10-06','pages':len(reader.pages),'primary_references':refs,'primary_reference_count':len(refs),'provenance_links':[{'label':l,'url':f'https://github.com/JPais7/AXIS/blob/{c}/{p}','git_object_exists':True} for l,p,c in links],'link_check_scope':'Git object targets verified locally; no new evidence retrieved or remote DOI availability asserted','decision_state_v1':old['id'],'decision_state_v2':state['id'],'classification':diff['classification'],'critical_uncertainty':critical['id'],'recommended_experiment':rec['experiment_id'],'cross_document_consistency':'PASS','scientific_state_changed':False,'input_sha256':inputs,'statement_audit':ledger,'pdf_sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),'visual_qa':'PENDING_RENDER_INSPECTION','conditions':['Independent scientific review pending','Tinworth final main remains inaccessible; accessible preprint/SI provenance identified','Seven readable pages used rather than compressing primary references into six'],'generation_dependencies':'Python, reportlab, pypdf; PDF content is derived from fixed Git objects, no network'}
qa['visual_qa'] = 'PASS: all seven rendered pages manually inspected; revised pages 4/6 rechecked' if args.visual_qa_pass else 'PENDING_RENDER_INSPECTION'
qa['generator_versions'] = {'reportlab': __import__('reportlab').Version, 'pypdf': __import__('pypdf').__version__}
(HERE/'review-pack-audit.json').write_text(json.dumps(qa,sort_keys=True,indent=2)+'\n')
print(json.dumps({'pdf':str(PDF),'pages':len(reader.pages),'references':len(refs),'sha256':qa['pdf_sha256']}))
