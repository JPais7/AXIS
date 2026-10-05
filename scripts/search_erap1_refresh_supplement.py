"""Supplemental source attempts, missing PMID metadata and material full-text access."""
import hashlib
import gzip
import json
import urllib.parse
import urllib.request
from datetime import datetime, UTC
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'axis/resources/evidence-refresh/erap1-axspa/2020-2026/v1'
log=json.loads((OUT/'search-log.json').read_text())
with gzip.open(OUT/'records.json.gz', 'rt', encoding='utf-8') as handle:
    records=json.load(handle)
def retrieve(source,query,url,method='GET',payload=None):
    item={'source':source,'query':query,'url':url,'method':method,'executed_at':datetime.now(UTC).isoformat(),'errors':[],'pagination':'not_established'}
    try:
        req=urllib.request.Request(url,data=json.dumps(payload).encode() if payload else None,method=method,headers={'User-Agent':'AXIS-EvidenceRefresh/1.0','Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=40) as r:raw=r.read()
        item['response_sha256']=hashlib.sha256(raw).hexdigest()
        try:data=json.loads(raw)
        except (ValueError,UnicodeDecodeError):data={'response_kind':'html_or_xml','bytes':len(raw)}
        item['status']='retrieved'
        print(source,'retrieved',flush=True)
    except Exception as e:item['status']='unavailable';item['errors']=[str(e)];data=None;print(source,str(e),flush=True)
    log.append(item)
    return data
existing={str(r['metadata'].get('pmid',r['metadata'].get('id'))) for r in records if r['database']=='Europe PMC'}
pmids=sorted({i for q in log if q['source']=='PubMed' for i in q['retrieved_identifiers']}-existing)
for start in range(0,len(pmids),50):
    query='SRC:MED AND ('+' OR '.join('EXT_ID:'+i for i in pmids[start:start+50])+')'
    url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urllib.parse.urlencode({'query':query,'format':'json','resultType':'core','pageSize':1000})
    data=retrieve('Europe PMC PMID hydration',query,url)
    if data:
        for m in data['resultList']['result']:records.append({'database':'PubMed via Europe PMC metadata','family':'PMID hydration','metadata':m})
        log[-1]['result_count']=data['hitCount'];log[-1]['pagination']='complete'
sources={}
sources['ClinicalTrials.gov']=retrieve('ClinicalTrials.gov','ERAP1 all indications; then disease screening','https://clinicaltrials.gov/api/v2/studies?query.term=ERAP1&pageSize=100&countTotal=true')
sources['WHO ICTRP']=retrieve('WHO ICTRP','ERAP1','https://trialsearch.who.int/?query=ERAP1')
sources['OpenAlex']=retrieve('OpenAlex','ERAP1 2020-01-01 to 2026-10-05','https://api.openalex.org/works?search=ERAP1&filter=from_publication_date:2020-01-01,to_publication_date:2026-10-05&per-page=200')
sources['Semantic Scholar']=retrieve('Semantic Scholar','ERAP1 2020-2026','https://api.semanticscholar.org/graph/v1/paper/search?query=ERAP1&year=2020:2026&limit=100&fields=title,year,externalIds,abstract')
query={'query':{'type':'terminal','service':'full_text','parameters':{'value':'ERAP1'}},'return_type':'entry','request_options':{'paginate':{'start':0,'rows':1000}}}
sources['RCSB PDB']=retrieve('RCSB PDB','ERAP1 all structures; post-3QNF dates require screen','https://search.rcsb.org/rcsbsearch/v2/query','POST',query)
sources['UniProt']=retrieve('UniProt','Q9NZ08','https://rest.uniprot.org/uniprotkb/Q9NZ08.json')
sources['ChEMBL']=retrieve('ChEMBL','target search ERAP1','https://www.ebi.ac.uk/chembl/api/data/target/search.json?q=ERAP1&limit=100')
sources['PubChem']=retrieve('PubChem','corilagin identity only','https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/corilagin/property/InChIKey,IsomericSMILES,MolecularFormula/JSON')
sources['Preprint search']=retrieve('bioRxiv/medRxiv via Europe PMC','ERAP1 AND SRC:PPR AND FIRST_PDATE:[2020-01-01 TO 2026-10-05]','https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urllib.parse.urlencode({'query':'ERAP1 AND SRC:PPR AND FIRST_PDATE:[2020-01-01 TO 2026-10-05]','format':'json','resultType':'core','pageSize':1000}))
tmp=Path('/tmp/axis-erap1-refresh-fulltext');tmp.mkdir(exist_ok=True)
access=[]
for identifier in ['PMC11647717','PMC9892207','PMC8024916']:
    url=f'https://www.ebi.ac.uk/europepmc/webservices/rest/{identifier}/fullTextXML'
    try:
        with urllib.request.urlopen(url,timeout=40) as response:raw=response.read()
        (tmp/(identifier+'.xml')).write_bytes(raw)
        access.append({'id':identifier,'url':url,'status':'retrieved_for_review','sha256':hashlib.sha256(raw).hexdigest(),'local_path':str(tmp/(identifier+'.xml'))})
    except Exception as e:access.append({'id':identifier,'url':url,'status':'unavailable','error':str(e)})
for url in ['https://www.sciencedirect.com/science/article/pii/S1567576925011701','https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5093704','https://api.elsevier.com/content/article/pii/S1567576925011701?httpAccept=text/xml']:
    data=retrieve('Corilagin full-text attempt','PMID:40680611 full-text methods access',url)
    access.append(log[-1])
(OUT/'fulltext-access.json').write_text(json.dumps(access,indent=2)+'\n')
(OUT/'supplemental-source-responses.json').write_text(json.dumps(sources,indent=2)+'\n')
(OUT/'search-log.json').write_text(json.dumps(log,indent=2)+'\n')
with gzip.open(OUT/'records.json.gz', 'wt', encoding='utf-8') as handle:
    json.dump(records, handle, indent=2)
