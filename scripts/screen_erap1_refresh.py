"""Conservative first-pass triage; unresolved studies are never auto-included."""
import hashlib
import gzip
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'axis/resources/evidence-refresh/erap1-axspa/2020-2026/v1'
with gzip.open(OUT/'records.json.gz', 'rt', encoding='utf-8') as handle:
    raw=json.load(handle)
log=json.loads((OUT/'search-log.json').read_text())
indexed={s['doi'].lower() for s in json.loads((ROOT/'axis/resources/discovery/erap1-axspa/v1/manifest.json').read_text())['sources']}
indexed.add('10.1021/acs.jmedchem.9b00293')
def text(value):
    return value[0] if isinstance(value,list) and value else str(value or '')
unique={};occurrences=[]
for r in raw:
    m=r['metadata'];doi=text(m.get('doi',m.get('DOI'))).lower().removeprefix('https://doi.org/')
    title=text(m.get('title'));pmid=m.get('pmid',m.get('id') if m.get('source')=='MED' else None)
    key=doi or ('PMID:'+str(pmid) if pmid else 'TITLE:'+re.sub(r'\W+','',title.lower()))
    record={'id':key,'doi':doi,'pmid':pmid,'pmcid':m.get('pmcid'),'title':title,'abstract':m.get('abstractText',m.get('abstract','')),'year':m.get('pubYear'),'first_publication_date':m.get('firstPublicationDate'),'publication_types':m.get('pubTypeList',{}).get('pubType',[]) if isinstance(m.get('pubTypeList',{}),dict) else [],'is_open_access':m.get('isOpenAccess'),'authors':m.get('authorString',m.get('author',[])),'discovery':[]}
    if key not in unique: unique[key]=record
    elif not unique[key]['abstract'] and record['abstract']: unique[key].update({k:v for k,v in record.items() if k!='discovery'})
    unique[key]['discovery'].append({'source':r['database'],'family':r['family']})
    occurrences.append({'id':key,'source':r['database'],'family':r['family'],'metadata_sha256':hashlib.sha256(json.dumps(m,sort_keys=True).encode()).hexdigest()})
screen=[]
for key,r in unique.items():
    combined=r['title']+' '+r['abstract'];types=r['publication_types']
    if r['doi'] in indexed:state='already_indexed';reason='Matches frozen baseline DOI'
    elif not r['abstract']:state='awaiting_metadata_or_full_text';reason='Missing abstract: absence of ERAP1 in title is insufficient for exclusion'
    elif not re.search(r'\bERAP[- ]?1\b|endoplasmic reticulum aminopeptidase[- ]?1',combined,re.I):state='proposed_exclusion';reason='No ERAP1 result identifiable in retrieved title/abstract; requires reviewer confirmation'
    elif 'Review' in types or re.search(r'\breview\b',r['title'],re.I):state='proposed_exclusion';reason='Review: retained for discovery/context, not primary assertion; requires reviewer confirmation'
    else:state='awaiting_full_text';reason='Potential ERAP1 primary evidence requires detailed screening and context extraction'
    screen.append({'record_id':key,'stage':1,'state':state,'reason':reason,'review_status':'pending_review','direction_used_for_selection':False})
(OUT/'unique-records.json').write_text(json.dumps(list(unique.values()),indent=2)+'\n')
(OUT/'record-occurrences.json').write_text(json.dumps(occurrences,indent=2)+'\n')
(OUT/'screening.json').write_text(json.dumps(screen,indent=2)+'\n')
from collections import Counter
print(len(unique),Counter(x['state'] for x in screen))
for s in screen:
    if s['state']=='awaiting_full_text':
        r=unique[s['record_id']];print(r['pmid'],r['doi'],r['year'],r['title'])
